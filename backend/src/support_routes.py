from fastapi import APIRouter, Depends

from .auth import allowed, identity
from .db import connect
from .plans import get_plan
from .support_directory import launch_window, list_desks, require_ready, save_desk
from .support_dispatch import board_cases, open_case, redispatch_case, resolve_case, timeline
from .support_notices import list_notices, publish_notice
from .support_schemas import Desk, DeskSettings, NoticeText, Resolution, TransferRequest

router = APIRouter(prefix='/plans/{plan_id}/support', tags=['改线乘客协助'])


@router.get('')
def support_board(plan_id: int, user=Depends(identity)):
    with connect() as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        plan = get_plan(db, plan_id)
        return {**launch_window(db, plan_id), 'trial_path': plan['trial_path'],
                'desks': list_desks(db, plan_id), 'notices': list_notices(db, plan_id),
                'cases': board_cases(db, plan_id)}


@router.put('/desks/{desk}')
def set_desk(plan_id: int, desk: Desk, data: DeskSettings, user=Depends(allowed('director'))):
    with connect() as db:
        get_plan(db, plan_id, lock=True)
        require_ready(db, plan_id)
        return save_desk(db, plan_id, desk, data, user['sub'])


@router.post('/notices', status_code=201)
def issue_notice(plan_id: int, data: NoticeText, user=Depends(allowed('director'))):
    with connect() as db:
        get_plan(db, plan_id, lock=True)
        require_ready(db, plan_id)
        return publish_notice(db, plan_id, data, user['sub'])


@router.post('/cases', status_code=201)
def file_case(plan_id: int, data: TransferRequest, user=Depends(allowed('collector'))):
    with connect() as db:
        # All capacity-changing writes take the same plan lock before reading desk load.
        get_plan(db, plan_id, lock=True)
        require_ready(db, plan_id, live=True)
        return open_case(db, plan_id, data, user['sub'])


@router.get('/cases/{case_id}/timeline')
def case_history(plan_id: int, case_id: int, user=Depends(identity)):
    with connect() as db:
        get_plan(db, plan_id)
        return timeline(db, plan_id, case_id)


@router.post('/cases/{case_id}/redispatch')
def recalculate_destination(plan_id: int, case_id: int, user=Depends(allowed('analyst'))):
    with connect() as db:
        get_plan(db, plan_id, lock=True)
        require_ready(db, plan_id, live=True)
        return redispatch_case(db, plan_id, case_id, user['sub'])


@router.post('/cases/{case_id}/resolve')
def complete_case(plan_id: int, case_id: int, data: Resolution, user=Depends(allowed('analyst'))):
    with connect() as db:
        get_plan(db, plan_id, lock=True)
        require_ready(db, plan_id, live=True)
        return resolve_case(db, plan_id, case_id, data.note, user['sub'])
