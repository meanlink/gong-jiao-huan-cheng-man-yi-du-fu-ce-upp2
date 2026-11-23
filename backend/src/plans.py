from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation

from .analysis import MIN_PER_CELL, coverage, eligible_samples
from .auth import allowed, identity
from .db import connect, record
from .schemas import NewPlan, PlanFields, Stage

router = APIRouter(prefix='/plans', tags=['线路版本'])


def local_today():
    return datetime.now(ZoneInfo('Asia/Shanghai')).date()


def get_plan(db, plan_id, lock=False):
    query = 'SELECT * FROM route_plan WHERE id=%s'
    if lock:
        query += ' FOR UPDATE'
    plan = db.execute(query, (plan_id,)).fetchone()
    if plan is None:
        raise HTTPException(404, '找不到线路方案')
    return plan


def at_stage(plan, stage, detail):
    if plan['stage'] != stage:
        raise HTTPException(409, detail)


@router.get('')
def list_plans(user=Depends(identity)):
    with connect() as db:
        return db.execute('SELECT * FROM route_plan ORDER BY id').fetchall()


@router.post('', status_code=201)
def create_plan(data: NewPlan, user=Depends(allowed('director'))):
    try:
        with connect() as db:
            plan = db.execute('''INSERT INTO route_plan (code, hub, feeder, connection, baseline_path,
                     trial_path, baseline_from, baseline_to, trial_from, trial_to)
                     VALUES (%(code)s,%(hub)s,%(feeder)s,%(connection)s,%(baseline_path)s,%(trial_path)s,
                             %(baseline_from)s,%(baseline_to)s,%(trial_from)s,%(trial_to)s)
                     RETURNING *''', data.model_dump()).fetchone()
            record(db, plan['id'], user['sub'], 'plan.created', code=plan['code'])
            return plan
    except UniqueViolation:
        raise HTTPException(409, '该版本编号已存在') from None


@router.put('/{plan_id}')
def revise_plan(plan_id: int, data: PlanFields, user=Depends(allowed('director'))):
    with connect() as db:
        plan = get_plan(db, plan_id, lock=True)
        at_stage(plan, Stage.DRAFT, '调查启用后，路径与调查日期已锁定')
        updated = db.execute('''UPDATE route_plan SET hub=%(hub)s, feeder=%(feeder)s, connection=%(connection)s,
                 baseline_path=%(baseline_path)s, trial_path=%(trial_path)s,
                 baseline_from=%(baseline_from)s, baseline_to=%(baseline_to)s,
                 trial_from=%(trial_from)s, trial_to=%(trial_to)s WHERE id=%(id)s RETURNING *''',
                             {**data.model_dump(), 'id': plan_id}).fetchone()
        record(db, plan_id, user['sub'], 'plan.revised')
        return updated


@router.post('/{plan_id}/open')
def open_plan(plan_id: int, user=Depends(allowed('director'))):
    try:
        with connect() as db:
            plan = get_plan(db, plan_id, lock=True)
            at_stage(plan, Stage.DRAFT, '只有草稿可开启调查')
            updated = db.execute("UPDATE route_plan SET stage='surveying' WHERE id=%s RETURNING *",
                                 (plan_id,)).fetchone()
            record(db, plan_id, user['sub'], 'plan.opened')
            return updated
    except UniqueViolation:
        raise HTTPException(409, '该枢纽与换乘线路已有未结案版本') from None


@router.get('/{plan_id}/coverage')
def survey_coverage(plan_id: int, user=Depends(identity)):
    with connect() as db:
        get_plan(db, plan_id, lock=True)
        rows = db.execute('''SELECT disposition, count(*) AS count FROM survey_sample
                             WHERE plan_id=%s GROUP BY disposition''', (plan_id,)).fetchall()
        return {'cells': coverage(eligible_samples(db, plan_id)), 'minimum': MIN_PER_CELL,
                'totals': {row['disposition']: row['count'] for row in rows}}


@router.get('/{plan_id}/audit')
def audit_history(plan_id: int, user=Depends(allowed('analyst', 'director'))):
    with connect() as db:
        get_plan(db, plan_id)
        return db.execute('''SELECT actor,event,details,happened_at FROM transfer_audit
                             WHERE plan_id=%s ORDER BY id DESC LIMIT 80''', (plan_id,)).fetchall()
