from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import allowed, identity, passenger_key
from .db import connect, record
from .plans import at_stage, get_plan
from .schemas import CleanupInput, Cohort, SampleState, Stage, SurveyInput

router = APIRouter(prefix='/plans/{plan_id}/samples', tags=['乘客调查'])
SAMPLE_COLUMNS = '''id,sample_ref,plan_id,cohort,trip_day,time_band,rating,disposition,
                    duplicate_of,cleanup_note,collected_at'''


@router.get('')
def list_samples(plan_id: int, state: SampleState | None = None, offset: int = Query(0, ge=0),
                 user=Depends(identity)):
    with connect() as db:
        get_plan(db, plan_id)
        samples = db.execute(f'''SELECT {SAMPLE_COLUMNS} FROM survey_sample WHERE plan_id=%s
                                 AND (%s::text IS NULL OR disposition=%s) ORDER BY id DESC LIMIT 21 OFFSET %s''',
                             (plan_id, state, state, offset)).fetchall()
        return {'items': samples[:20], 'has_more': len(samples) > 20}


@router.post('', status_code=201)
def collect_sample(plan_id: int, data: SurveyInput, user=Depends(allowed('collector'))):
    with connect() as db:
        plan = get_plan(db, plan_id, lock=True)
        at_stage(plan, Stage.SURVEYING, '只有调查执行中的版本可录入问卷')
        wave = 'baseline' if data.cohort == Cohort.BASELINE else 'trial'
        if not plan[f'{wave}_from'] <= data.trip_day <= plan[f'{wave}_to']:
            raise HTTPException(422, '乘车日不在所选调查波次的日期范围内')
        key = passenger_key(data.passenger_code)
        original = db.execute('''SELECT id FROM survey_sample WHERE plan_id=%s AND passenger_hash=%s
                                 AND duplicate_of IS NULL''', (plan_id, key)).fetchone()
        duplicate_id = original['id'] if original else None
        state = SampleState.QUEUE if duplicate_id or data.time_band is None else SampleState.ELIGIBLE
        row = db.execute(f'''INSERT INTO survey_sample
                     (sample_ref,plan_id,passenger_hash,cohort,trip_day,time_band,rating,disposition,duplicate_of,collected_by)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {SAMPLE_COLUMNS}''',
                         (f'BT-{uuid4().hex[:12].upper()}', plan_id, key, data.cohort, data.trip_day,
                          data.time_band, data.rating, state, duplicate_id, user['sub'])).fetchone()
        record(db, plan_id, user['sub'], 'sample.captured', sample_ref=row['sample_ref'],
               disposition=state, missing_band=data.time_band is None, duplicate=duplicate_id is not None)
        return row


@router.post('/{sample_id}/cleanup')
def resolve_sample(plan_id: int, sample_id: int, data: CleanupInput, user=Depends(allowed('analyst'))):
    with connect() as db:
        plan = get_plan(db, plan_id, lock=True)
        at_stage(plan, Stage.SURVEYING, '封存后的问卷不能修改')
        sample = db.execute('SELECT * FROM survey_sample WHERE plan_id=%s AND id=%s', (plan_id, sample_id)).fetchone()
        if sample is None:
            raise HTTPException(404, '找不到这份问卷')
        if sample['disposition'] != SampleState.QUEUE:
            raise HTTPException(409, '只有清洗队列中的问卷可以处理')
        if sample['duplicate_of'] and data.time_band is not None:
            raise HTTPException(409, '重复乘客只能留痕剔除，首份问卷继续保留')
        new_state = SampleState.ELIGIBLE if data.time_band else SampleState.EXCLUDED
        row = db.execute(f'''UPDATE survey_sample SET time_band=COALESCE(%s,time_band), cleanup_note=%s,
                      disposition=%s WHERE id=%s RETURNING {SAMPLE_COLUMNS}''',
                         (data.time_band, data.note, new_state, sample_id)).fetchone()
        record(db, plan_id, user['sub'], 'sample.resolved', sample_ref=row['sample_ref'],
               disposition=new_state, time_band=data.time_band, reason=data.note)
        return row
