from fastapi import APIRouter, Depends, HTTPException

from .analysis import (ADOPT_EFFECT_MIN, ADOPT_P_MAX, BAND_EFFECT_FLOOR, METHOD,
                       MIN_PER_CELL, coverage, eligible_samples, snapshot_hash)
from .auth import allowed, identity
from .db import connect, record
from .plans import at_stage, get_plan
from .schemas import Decision, DecisionInput, Stage
from .walk_checks import unresolved_trial_count

router = APIRouter(prefix='/plans/{plan_id}/conclusion', tags=['分层比较与运营决策'])


def load_conclusion(db, plan_id, lock=False):
    query = 'SELECT * FROM retest_conclusion WHERE plan_id=%s'
    if lock:
        query += ' FOR UPDATE'
    result = db.execute(query, (plan_id,)).fetchone()
    if result:
        result['method'] = METHOD
        result['unresolved_trial_walks'] = unresolved_trial_count(db, plan_id)
        result['adoption_policy'] = {'p_max': ADOPT_P_MAX, 'effect_min': ADOPT_EFFECT_MIN,
                                     'band_effect_floor': BAND_EFFECT_FLOOR}
    return result


@router.get('')
def conclusion(plan_id: int, user=Depends(identity)):
    with connect() as db:
        get_plan(db, plan_id)
        return load_conclusion(db, plan_id)


@router.post('/seal', status_code=202)
def seal_for_analysis(plan_id: int, user=Depends(allowed('analyst'))):
    with connect() as db:
        plan = get_plan(db, plan_id, lock=True)
        at_stage(plan, Stage.SURVEYING, '只有调查中的方案可以封存')
        queued = db.execute("SELECT count(*) AS n FROM survey_sample WHERE plan_id=%s AND disposition='queue'",
                            (plan_id,)).fetchone()['n']
        if queued:
            raise HTTPException(409, f'还有 {queued} 份问卷待清洗，处理完才能封存')
        samples = eligible_samples(db, plan_id)
        if any(min(cell['baseline'], cell['trial']) < MIN_PER_CELL for cell in coverage(samples)):
            raise HTTPException(409, f'高峰与平峰的基线、复测各需至少 {MIN_PER_CELL} 份有效问卷')
        digest = snapshot_hash(samples)
        db.execute("UPDATE route_plan SET stage='sealed' WHERE id=%s", (plan_id,))
        db.execute('INSERT INTO retest_conclusion (plan_id,snapshot_hash) VALUES (%s,%s)', (plan_id, digest))
        record(db, plan_id, user['sub'], 'survey.sealed', snapshot=digest, sample_count=len(samples))
        return load_conclusion(db, plan_id)


@router.post('/sign')
def sign_decision(plan_id: int, data: DecisionInput, user=Depends(allowed('director'))):
    with connect() as db:
        plan = get_plan(db, plan_id, lock=True)
        at_stage(plan, Stage.SEALED, '该方案尚未封存或已经签署')
        result = load_conclusion(db, plan_id, lock=True)
        if not result or result['status'] != 'ready':
            raise HTTPException(409, '分层检验尚未完成')
        if data.decision == Decision.ADOPT and not result['adopt_allowed']:
            raise HTTPException(409, '当前总体显著性、效应量或单层保护线不满足采用条件')
        if data.decision == Decision.ADOPT and result['unresolved_trial_walks']:
            raise HTTPException(409, '复测路径仍有未关闭的绕行或受阻巡检，完成通行复查后才能采用改线')
        db.execute('''UPDATE retest_conclusion SET status='signed', decision=%s, decision_note=%s,
                   signed_by=%s,signed_at=now() WHERE plan_id=%s''', (data.decision, data.note, user['sub'], plan_id))
        db.execute("UPDATE route_plan SET stage='decided' WHERE id=%s", (plan_id,))
        record(db, plan_id, user['sub'], 'decision.signed', decision=data.decision, note=data.note)
        return load_conclusion(db, plan_id)
