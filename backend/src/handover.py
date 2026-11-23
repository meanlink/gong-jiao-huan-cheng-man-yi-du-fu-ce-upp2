from datetime import date
from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from .auth import allowed, identity
from .db import connect, record
from .plans import get_plan, local_today
from .schemas import Input, Stage

router = APIRouter(prefix='/plans/{plan_id}/handover', tags=['改线交接与站务任务验收'])


class TaskKind(StrEnum):
    STOP_SIGNAGE = 'stop_signage'
    DISPATCH_BRIEFING = 'dispatch_briefing'
    ACCESSIBILITY_NOTICE = 'accessibility_notice'


TASK_ROLES = {
    TaskKind.STOP_SIGNAGE: 'collector',
    TaskKind.DISPATCH_BRIEFING: 'analyst',
    TaskKind.ACCESSIBILITY_NOTICE: 'collector',
}


class Setup(Input):
    effective_on: date


class TaskProof(Input):
    evidence: str = Field(min_length=4, max_length=250)


class Release(Input):
    note: str = Field(min_length=8, max_length=350)


def packet_details(db, plan_id):
    packet = db.execute('''SELECT h.*, c.snapshot_hash, c.signed_at, c.signed_by, c.decision, p.code, p.trial_path
                         FROM route_handover h JOIN retest_conclusion c USING (plan_id)
                         JOIN route_plan p ON p.id=h.plan_id WHERE h.plan_id=%s''', (plan_id,)).fetchone()
    if packet:
        tasks = db.execute('SELECT * FROM handover_task WHERE plan_id=%s ORDER BY kind', (plan_id,)).fetchall()
        packet['tasks'] = [{**task, 'owner_role': TASK_ROLES[task['kind']]} for task in tasks]
        packet['status'] = 'released' if packet['released_at'] else 'preparing'
    return packet


def mutable_packet(db, plan_id):
    get_plan(db, plan_id, lock=True)
    packet = packet_details(db, plan_id)
    if not packet or packet['released_at']:
        raise HTTPException(409, '只有已建档且尚未发布的交接单可以操作')
    return packet


@router.get('')
def handover_detail(plan_id: int, user=Depends(identity)):
    with connect() as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        get_plan(db, plan_id)
        return packet_details(db, plan_id)


@router.post('', status_code=201)
def create_packet(plan_id: int, data: Setup, user=Depends(allowed('director'))):
    with connect() as db:
        plan = get_plan(db, plan_id, lock=True)
        result = db.execute('SELECT decision, status FROM retest_conclusion WHERE plan_id=%s', (plan_id,)).fetchone()
        if plan['stage'] != Stage.DECIDED or not result or result['status'] != 'signed' or result['decision'] != 'adopt':
            raise HTTPException(409, '须先签署采用改线的运营决策，才能建立改线交接单')
        if data.effective_on < local_today():
            raise HTTPException(422, '计划启用日不得早于当地今天')
        exists = db.execute('SELECT 1 FROM route_handover WHERE plan_id=%s', (plan_id,)).fetchone()
        if exists:
            raise HTTPException(409, '该线路版本已经建立交接单')
        db.execute('INSERT INTO route_handover (plan_id, effective_on, created_by) VALUES (%s,%s,%s)',
                   (plan_id, data.effective_on, user['sub']))
        with db.cursor() as cur:
            cur.executemany('INSERT INTO handover_task (plan_id, kind) VALUES (%s,%s)',
                            [(plan_id, kind) for kind in TASK_ROLES])
        record(db, plan_id, user['sub'], 'handover.opened', effective_on=data.effective_on.isoformat())
        return packet_details(db, plan_id)


@router.put('/tasks/{kind}')
def attach_proof(plan_id: int, kind: TaskKind, data: TaskProof, user=Depends(allowed('collector', 'analyst'))):
    if user['role'] != TASK_ROLES[kind]:
        raise HTTPException(403, '当前岗位无权提交该交接项的凭证')
    with connect() as db:
        mutable_packet(db, plan_id)
        task = db.execute('''UPDATE handover_task SET evidence=%s, completed_by=%s, completed_at=now()
                          WHERE plan_id=%s AND kind=%s RETURNING *''', (data.evidence, user['sub'], plan_id, kind)).fetchone()
        record(db, plan_id, user['sub'], 'handover.proof_added', kind=kind, evidence=data.evidence)
        return task


@router.post('/release')
def release_packet(plan_id: int, data: Release, user=Depends(allowed('director'))):
    with connect() as db:
        packet = mutable_packet(db, plan_id)
        received = {task['kind'] for task in packet['tasks'] if task['completed_at']}
        if received != set(TASK_ROLES):
            raise HTTPException(409, '须收齐站牌、调度和无障碍告知凭证，才能发布交接单')
        db.execute('UPDATE route_handover SET released_by=%s, released_at=now(), release_note=%s WHERE plan_id=%s',
                   (user['sub'], data.note, plan_id))
        record(db, plan_id, user['sub'], 'handover.released', snapshot=packet['snapshot_hash'], note=data.note)
        return packet_details(db, plan_id)
