from datetime import date
from enum import StrEnum
from statistics import median

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation
from pydantic import Field, model_validator

from .auth import allowed, identity
from .db import connect, record
from .plans import get_plan, local_today
from .schemas import Cohort, Input, Stage, TimeBand

router = APIRouter(prefix='/plans/{plan_id}/walk-checks', tags=['站点换乘巡检'])


class WalkOutcome(StrEnum):
    CLEAR = 'clear'
    DETOUR = 'detour'
    BLOCKED = 'blocked'


class WalkInput(Input):
    cohort: Cohort
    walk_day: date
    time_band: TimeBand
    outcome: WalkOutcome
    walk_minutes: int | None = Field(default=None, ge=1, le=90)
    source_ref: str = Field(min_length=3, max_length=120)
    note: str = Field(min_length=4, max_length=250)

    @model_validator(mode='after')
    def require_minutes(self):
        if (self.outcome == WalkOutcome.BLOCKED) != (self.walk_minutes is None):
            raise ValueError('正常通行和绕行须填写分钟数，无法通行时分钟数应留空')
        return self


class ClearanceInput(Input):
    recheck_id: int = Field(gt=0)
    note: str = Field(min_length=6, max_length=250)


def unresolved_trial_count(db, plan_id):
    return db.execute('''SELECT count(*) AS n FROM route_walk_check WHERE plan_id=%s AND cohort='trial'
                         AND outcome <> 'clear' AND cleared_by_walk_id IS NULL''', (plan_id,)).fetchone()['n']


def controls_open(plan):
    if plan['stage'] not in (Stage.SURVEYING, Stage.SEALED):
        raise HTTPException(409, '巡检只在调查开启后、决策签署前接受登记或复查')


def rollup(rows):
    cells = []
    for wave in Cohort:
        for band in TimeBand:
            checks = [row for row in rows if row['cohort'] == wave and row['time_band'] == band]
            timings = [row['walk_minutes'] for row in checks if row['outcome'] == WalkOutcome.CLEAR]
            cells.append({'cohort': wave, 'time_band': band, 'checks': len(checks),
                          'clear_median_minutes': median(timings) if timings else None})
    return cells


@router.get('')
def walk_log(plan_id: int, user=Depends(identity)):
    with connect() as db:
        get_plan(db, plan_id)
        rows = db.execute('SELECT * FROM route_walk_check WHERE plan_id=%s ORDER BY id DESC', (plan_id,)).fetchall()
        pending = sum(row['cohort'] == Cohort.TRIAL and row['outcome'] != WalkOutcome.CLEAR
                      and row['cleared_by_walk_id'] is None for row in rows)
        return {'items': rows, 'cells': rollup(rows), 'unresolved_trial': pending}


@router.post('', status_code=201)
def add_walk(plan_id: int, data: WalkInput, user=Depends(allowed('collector'))):
    try:
        with connect() as db:
            plan = get_plan(db, plan_id, lock=True)
            controls_open(plan)
            if not plan[f'{data.cohort}_from'] <= data.walk_day <= min(plan[f'{data.cohort}_to'], local_today()):
                raise HTTPException(422, '巡检日期须位于所选波次的窗口内，且不得晚于当天')
            row = db.execute('''INSERT INTO route_walk_check
                (plan_id, cohort, walk_day, time_band, outcome, walk_minutes, source_ref, note, recorded_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
                (plan_id, data.cohort, data.walk_day, data.time_band, data.outcome, data.walk_minutes,
                 data.source_ref, data.note, user['sub'])).fetchone()
            record(db, plan_id, user['sub'], 'walk.recorded', walk_id=row['id'], cohort=data.cohort, outcome=data.outcome)
            return row
    except UniqueViolation as exc:
        raise HTTPException(409, '该波次、日期和时段已登记过相同巡检凭证') from exc


@router.post('/{walk_id}/clearance')
def clear_walk(plan_id: int, walk_id: int, data: ClearanceInput, user=Depends(allowed('director'))):
    with connect() as db:
        plan = get_plan(db, plan_id, lock=True)
        controls_open(plan)
        issue = db.execute('SELECT * FROM route_walk_check WHERE plan_id=%s AND id=%s', (plan_id, walk_id)).fetchone()
        if issue is None:
            raise HTTPException(404, '找不到该线路版本的巡检记录')
        if issue['outcome'] == WalkOutcome.CLEAR or issue['cleared_by_walk_id']:
            raise HTTPException(409, '只有未关闭的绕行或受阻记录可签署清除')
        recheck = db.execute('''SELECT id FROM route_walk_check
            WHERE plan_id=%s AND id=%s AND id > %s AND cohort=%s AND time_band=%s AND walk_day >= %s AND outcome='clear' ''',
            (plan_id, data.recheck_id, issue['id'], issue['cohort'], issue['time_band'], issue['walk_day'])).fetchone()
        if not recheck:
            raise HTTPException(422, '请选择事后登记、同线路版本同波次同时段的正常通行复查')
        row = db.execute('''UPDATE route_walk_check SET cleared_by_walk_id=%s, clearance_note=%s,
                          cleared_by=%s, cleared_at=now() WHERE plan_id=%s AND id=%s RETURNING *''',
                         (data.recheck_id, data.note, user['sub'], plan_id, walk_id)).fetchone()
        record(db, plan_id, user['sub'], 'walk.cleared', walk_id=walk_id, recheck_id=data.recheck_id, evidence=data.note)
        return row
