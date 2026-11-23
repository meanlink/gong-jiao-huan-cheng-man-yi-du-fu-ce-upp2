from fastapi import HTTPException

from .db import record
from .plans import local_today
from .support_schemas import Desk


def launch_window(db, plan_id):
    handover = db.execute('SELECT effective_on, released_at FROM route_handover WHERE plan_id=%s',
                          (plan_id,)).fetchone()
    if not handover or not handover['released_at']:
        return {'status': 'awaiting_handover', 'effective_on': None}
    day = handover['effective_on']
    return {'status': 'scheduled' if day > local_today() else 'live', 'effective_on': day}


def require_ready(db, plan_id, *, live=False):
    window = launch_window(db, plan_id)
    if window['status'] == 'awaiting_handover':
        raise HTTPException(409, '请先发布采用路线的交接单')
    if live and window['status'] != 'live':
        raise HTTPException(409, '尚未到交接单的计划启用日')


def list_desks(db, plan_id, excluding_case=None):
    return db.execute('''SELECT d.*, count(c.id)::int AS active_count
                         FROM support_desk d LEFT JOIN support_case c
                           ON c.plan_id=d.plan_id AND c.desk=d.desk AND c.resolved_at IS NULL
                           AND c.id IS DISTINCT FROM %s
                         WHERE d.plan_id=%s GROUP BY d.plan_id,d.desk ORDER BY d.desk''',
                      (excluding_case, plan_id)).fetchall()


def save_desk(db, plan_id, desk: Desk, data, actor):
    row = db.execute('''INSERT INTO support_desk (plan_id,desk,location,capacity,available,updated_by)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (plan_id,desk) DO UPDATE SET location=excluded.location,
                         capacity=excluded.capacity,available=excluded.available,updated_by=excluded.updated_by,
                         updated_at=now() RETURNING *''',
                     (plan_id, desk, data.location, data.capacity, data.available, actor)).fetchone()
    record(db, plan_id, actor, 'support.desk_saved', desk=desk, **data.model_dump())
    return row
