from zoneinfo import ZoneInfo
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from .auth import allowed, identity, passenger_key
from .backfill_schemas import BackfillClose, BackfillStart, BackfillUpload
from .db import connect, record
from .plans import at_stage, get_plan
from .schemas import Cohort, SampleState, Stage

router = APIRouter(prefix='/plans/{plan_id}/backfill', tags=['离线补传'])
LOCAL = ZoneInfo('Asia/Shanghai')
ITEM_COLUMNS = '''bi.id,bi.offline_ref,bi.cohort,bi.trip_day,bi.filled_at,bi.time_band,bi.rating,
                  bi.outcome,bi.basis,bi.sample_id,s.sample_ref,s.disposition,bi.received_at,bi.merged_at'''


def _clock(value):
    return value.astimezone(LOCAL).strftime('%Y-%m-%d %H:%M')


def get_batch(db, plan_id, batch_id, lock=False):
    query = 'SELECT * FROM backfill_batch WHERE plan_id=%s AND id=%s'
    if lock:
        query += ' FOR UPDATE'
    batch = db.execute(query, (plan_id, batch_id)).fetchone()
    if batch is None:
        raise HTTPException(404, '找不到该补传批次')
    return batch


def batch_detail(db, plan_id, batch_id):
    batch = get_batch(db, plan_id, batch_id)
    items = db.execute(f'''SELECT {ITEM_COLUMNS} FROM backfill_item bi
                           LEFT JOIN survey_sample s ON s.id=bi.sample_id
                           WHERE bi.plan_id=%s AND bi.batch_id=%s
                           ORDER BY bi.filled_at, bi.id''', (plan_id, batch_id)).fetchall()
    batch['items'] = items
    batch['received_refs'] = [item['offline_ref'] for item in items]
    batch['counts'] = {
        'received': len(items),
        'pending': sum(1 for item in items if item['sample_id'] is None),
        'first': sum(1 for item in items if item['outcome'] == 'first'),
        'superseded': sum(1 for item in items if item['outcome'] == 'superseded'),
        'duplicate': sum(1 for item in items if item['outcome'] == 'duplicate'),
    }
    return batch


def staging_batches(db, plan_id):
    return db.execute('''SELECT id,batch_ref,expected_items,received_items FROM backfill_batch
                         WHERE plan_id=%s AND status='staging' ORDER BY id''', (plan_id,)).fetchall()


def _passenger_rows(db, plan_id, key, lock=False):
    query = '''SELECT id,source,disposition,duplicate_of,time_band,filled_at,offline_ref,
                      collected_at,COALESCE(filled_at,collected_at) AS effective
               FROM survey_sample WHERE plan_id=%s AND passenger_hash=%s ORDER BY id'''
    if lock:
        query += ' FOR UPDATE'
    return db.execute(query, (plan_id, key)).fetchall()


def _label(row):
    if row['source'] == 'backfill':
        return f'补传 {row["offline_ref"]}（填写于 {_clock(row["effective"])}）'
    return f'线上问卷（登记于 {_clock(row["effective"])}）'


def _refresh_items(db, plan_id, key, canonical):
    """Recompute each received offline questionnaire's fate against this passenger's counted first copy."""
    items = db.execute('''SELECT bi.id,bi.offline_ref,bi.filled_at,bi.sample_id,bi.outcome
                          FROM backfill_item bi WHERE bi.plan_id=%s AND bi.passenger_hash=%s
                          AND bi.sample_id IS NOT NULL ORDER BY bi.filled_at, bi.id''',
                       (plan_id, key)).fetchall()
    label = _label(canonical)
    for item in items:
        if item['sample_id'] == canonical['id']:
            outcome = 'first'
            basis = f'补传 {item["offline_ref"]}（填写于 {_clock(item["filled_at"])}）是本乘客实际填写最早的一份，作为首份保留。'
            db.execute('UPDATE survey_sample SET merge_note=%s WHERE id=%s', (basis, item['sample_id']))
        elif item['outcome'] == 'first':
            outcome = 'superseded'
            basis = (f'补传 {item["offline_ref"]} 原按首份计入，被更早填写的 {label} 替下；'
                     f'两份均留档，本份不再计入。')
        else:
            outcome = 'duplicate'
            basis = f'补传 {item["offline_ref"]}（填写于 {_clock(item["filled_at"])}）不早于首份 {label}，留档剔除。'
        if item['sample_id'] != canonical['id']:
            db.execute('''UPDATE survey_sample SET disposition='excluded',
                          cleanup_note=COALESCE(cleanup_note,%s), merge_note=%s
                          WHERE id=%s AND disposition <> 'excluded' ''',
                       (basis, basis, item['sample_id']))
        db.execute('UPDATE backfill_item SET outcome=%s, basis=%s WHERE id=%s', (outcome, basis, item['id']))


def reconcile_passenger(db, plan_id, key, candidate_id, actor):
    """Keep the earliest actually-filled questionnaire per passenger as the single counted first copy."""
    rows = _passenger_rows(db, plan_id, key, lock=True)
    current = next((row for row in rows if row['duplicate_of'] is None), None)
    candidate = next(row for row in rows if row['id'] == candidate_id)
    if current is None:
        canonical = candidate
    elif candidate['effective'] < current['effective']:
        # Equal timestamps keep the copy already counted, so retries and minute-level ties do not churn.
        canonical = candidate
        note = (f'晚到首份：{_label(candidate)} 早于本份登记时间 {_clock(current["effective"])}，'
                f'改计补传首份并留档替代。')
        db.execute('''UPDATE survey_sample SET duplicate_of=%s, disposition='excluded',
                      cleanup_note=COALESCE(cleanup_note,%s), merge_note=%s WHERE id=%s''',
                   (canonical['id'], note, note, current['id']))
        record(db, plan_id, actor, 'backfill.first_replaced', passenger_sample=current['id'],
               replacement_sample=candidate['id'], demoted_ref=current['offline_ref'])
    else:
        canonical = current
    counted = SampleState.ELIGIBLE if canonical['time_band'] else SampleState.QUEUE
    if canonical['id'] == candidate_id:
        # The backfill copy takes over; it was just received and holds no analyst decision yet.
        db.execute('UPDATE survey_sample SET duplicate_of=NULL, disposition=%s, cleanup_note=NULL WHERE id=%s',
                   (counted, canonical['id']))
    else:
        # An analyst's exclusion of the online copy stays in force; the backfill copy is archived against it.
        db.execute('UPDATE survey_sample SET duplicate_of=NULL WHERE id=%s', (canonical['id'],))
    db.execute('''UPDATE survey_sample SET duplicate_of=%s WHERE plan_id=%s AND passenger_hash=%s
                  AND duplicate_of IS NOT NULL AND duplicate_of<>%s''', (canonical['id'], plan_id, key, canonical['id']))
    canonical = next(row for row in _passenger_rows(db, plan_id, key) if row['id'] == canonical['id'])
    # Archives every backfill copy of this passenger that is not the counted first one.
    _refresh_items(db, plan_id, key, canonical)
    return canonical


@router.get('')
def list_batches(plan_id: int, user=Depends(identity)):
    with connect() as db:
        get_plan(db, plan_id)
        ids = db.execute('SELECT id FROM backfill_batch WHERE plan_id=%s ORDER BY id DESC LIMIT 30',
                         (plan_id,)).fetchall()
        return {'batches': [batch_detail(db, plan_id, row['id']) for row in ids],
                'staging': staging_batches(db, plan_id)}


@router.get('/items')
def list_items(plan_id: int, user=Depends(identity)):
    with connect() as db:
        get_plan(db, plan_id)
        return db.execute(f'''SELECT {ITEM_COLUMNS},b.batch_ref FROM backfill_item bi
                              JOIN backfill_batch b ON b.id=bi.batch_id
                              LEFT JOIN survey_sample s ON s.id=bi.sample_id
                              WHERE bi.plan_id=%s ORDER BY bi.id DESC LIMIT 200''',
                          (plan_id,)).fetchall()


@router.post('', status_code=201)
def start_batch(plan_id: int, data: BackfillStart, user=Depends(allowed('collector', 'analyst'))):
    with connect() as db:
        plan = get_plan(db, plan_id, lock=True)
        at_stage(plan, Stage.SURVEYING, '只有调查执行中的版本可补传离线问卷')
        existing = db.execute('SELECT * FROM backfill_batch WHERE plan_id=%s AND batch_ref=%s',
                              (plan_id, data.batch_ref)).fetchone()
        if existing:
            if existing['status'] == 'staging':
                return batch_detail(db, plan_id, existing['id'])
            raise HTTPException(409, '该批次号已结案，请换一个批次号继续补传')
        batch = db.execute('''INSERT INTO backfill_batch (plan_id,batch_ref,expected_items,created_by)
                              VALUES (%s,%s,%s,%s) RETURNING id''',
                           (plan_id, data.batch_ref, data.expected_items, user['sub'])).fetchone()
        record(db, plan_id, user['sub'], 'backfill.started', batch_ref=data.batch_ref,
               expected_items=data.expected_items)
        return batch_detail(db, plan_id, batch['id'])


@router.get('/{batch_id}')
def read_batch(plan_id: int, batch_id: int, user=Depends(identity)):
    with connect() as db:
        get_plan(db, plan_id)
        return batch_detail(db, plan_id, batch_id)


@router.post('/{batch_id}/items', status_code=201)
def upload_items(plan_id: int, batch_id: int, data: BackfillUpload,
                 user=Depends(allowed('collector', 'analyst'))):
    with connect() as db:
        plan = get_plan(db, plan_id, lock=True)
        at_stage(plan, Stage.SURVEYING, '只有调查执行中的版本可补传离线问卷')
        batch = get_batch(db, plan_id, batch_id, lock=True)
        if batch['status'] != 'staging':
            raise HTTPException(409, '该批次已结案，不能再上传问卷')
        accepted, skipped, seen = [], [], set()
        for item in data.items:
            if item.offline_ref in seen:
                skipped.append({'offline_ref': item.offline_ref, 'reason': '本批重复，已忽略'})
                continue
            seen.add(item.offline_ref)
            if db.execute('SELECT id FROM backfill_item WHERE plan_id=%s AND offline_ref=%s',
                          (plan_id, item.offline_ref)).fetchone():
                skipped.append({'offline_ref': item.offline_ref, 'reason': '已收问卷，重试不重复入账'})
                continue
            wave = 'baseline' if item.cohort == Cohort.BASELINE else 'trial'
            if not plan[f'{wave}_from'] <= item.trip_day <= plan[f'{wave}_to']:
                raise HTTPException(422, f'{item.offline_ref} 的乘车日不在所选调查波次的日期范围内')
            row = db.execute('''INSERT INTO backfill_item (plan_id,batch_id,offline_ref,passenger_hash,cohort,
                                 trip_day,filled_at,time_band,rating,received_by)
                                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                             (plan_id, batch_id, item.offline_ref, passenger_key(item.passenger_code),
                              item.cohort, item.trip_day, item.filled_at, item.time_band, item.rating,
                              user['sub'])).fetchone()
            accepted.append({'offline_ref': item.offline_ref, 'item_id': row['id']})
        if accepted:
            db.execute('UPDATE backfill_batch SET received_items=received_items+%s WHERE id=%s',
                       (len(accepted), batch_id))
            record(db, plan_id, user['sub'], 'backfill.items_received', batch_ref=batch['batch_ref'],
                   accepted=[item['offline_ref'] for item in accepted],
                   skipped=[item['offline_ref'] for item in skipped])
        return {**batch_detail(db, plan_id, batch_id), 'accepted': accepted, 'skipped': skipped}


@router.post('/{batch_id}/merge')
def merge_batch(plan_id: int, batch_id: int, data: BackfillClose,
                user=Depends(allowed('collector', 'analyst'))):
    with connect() as db:
        plan = get_plan(db, plan_id, lock=True)
        at_stage(plan, Stage.SURVEYING, '只有调查执行中的版本可合并补传问卷')
        batch = get_batch(db, plan_id, batch_id, lock=True)
        if batch['status'] == 'merged':
            return batch_detail(db, plan_id, batch_id)
        if batch['status'] == 'cancelled':
            raise HTTPException(409, '该批次已取消')
        pending = db.execute('''SELECT * FROM backfill_item WHERE plan_id=%s AND batch_id=%s
                                AND sample_id IS NULL ORDER BY filled_at, id''',
                             (plan_id, batch_id)).fetchall()
        passengers = set()
        for item in pending:
            current = db.execute('''SELECT id FROM survey_sample WHERE plan_id=%s AND passenger_hash=%s
                                    AND duplicate_of IS NULL''', (plan_id, item['passenger_hash'])).fetchone()
            state = SampleState.QUEUE if current or item['time_band'] is None else SampleState.ELIGIBLE
            sample = db.execute('''INSERT INTO survey_sample (sample_ref,plan_id,passenger_hash,cohort,trip_day,
                                      time_band,rating,disposition,duplicate_of,collected_by,source,filled_at,offline_ref)
                                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'backfill',%s,%s) RETURNING id''',
                                (f'BT-{uuid4().hex[:12].upper()}', plan_id, item['passenger_hash'], item['cohort'],
                                 item['trip_day'], item['time_band'], item['rating'], state,
                                 current['id'] if current else None, user['sub'], item['filled_at'],
                                 item['offline_ref'])).fetchone()
            db.execute('''UPDATE backfill_item SET sample_id=%s, merged_by=%s, merged_at=now() WHERE id=%s''',
                       (sample['id'], user['sub'], item['id']))
            passengers.add(item['passenger_hash'])
        for key in passengers:
            merged_sample = db.execute('''SELECT sample_id FROM backfill_item WHERE plan_id=%s
                                          AND batch_id=%s AND passenger_hash=%s AND sample_id IS NOT NULL
                                          ORDER BY filled_at, id LIMIT 1''', (plan_id, batch_id, key)).fetchone()
            reconcile_passenger(db, plan_id, key, merged_sample['sample_id'], user['sub'])
        merged = db.execute('''UPDATE backfill_batch SET status='merged', completed_by=%s, completed_at=now(),
                               closing_note=%s WHERE id=%s RETURNING id''',
                            (user['sub'], data.note, batch_id)).fetchone()
        detail = batch_detail(db, plan_id, merged['id'])
        record(db, plan_id, user['sub'], 'backfill.merged', batch_ref=batch['batch_ref'],
               merged=detail['counts'])
        return detail


@router.post('/{batch_id}/cancel')
def cancel_batch(plan_id: int, batch_id: int, user=Depends(allowed('collector', 'analyst'))):
    with connect() as db:
        plan = get_plan(db, plan_id, lock=True)
        at_stage(plan, Stage.SURVEYING, '只有调查执行中的版本可取消补传')
        batch = get_batch(db, plan_id, batch_id, lock=True)
        if batch['status'] != 'staging':
            raise HTTPException(409, '该批次已结案')
        if batch['received_items']:
            raise HTTPException(409, '已收到问卷的批次只能合并，不能取消')
        db.execute('''UPDATE backfill_batch SET status='cancelled', completed_by=%s, completed_at=now()
                      WHERE id=%s''', (user['sub'], batch_id))
        record(db, plan_id, user['sub'], 'backfill.cancelled', batch_ref=batch['batch_ref'])
        return batch_detail(db, plan_id, batch_id)
