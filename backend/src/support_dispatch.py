from fastapi import HTTPException

from .support_directory import list_desks
from .support_notices import current_edition
from .support_schemas import Category, Desk

# Accessibility cases may only go to desks that can arrange step-free assistance.
ROUTES = {
    Category.STEP_FREE: (Desk.ACCESS, Desk.STATION),
    Category.WAYFINDING: (Desk.STATION, Desk.ACCESS),
    Category.MISSED_CONNECTION: (Desk.DISPATCH, Desk.STATION),
}


def destination(db, plan_id, category, excluding_case=None):
    desks = {row['desk']: row for row in list_desks(db, plan_id, excluding_case)}
    for index, desk in enumerate(ROUTES[category]):
        entry = desks.get(desk)
        if entry and entry['available'] and entry['active_count'] < entry['capacity']:
            return desk, 'primary' if index == 0 else 'fallback'
    return None, 'waiting'


def board_cases(db, plan_id):
    return db.execute('''SELECT * FROM support_case WHERE plan_id=%s
                         ORDER BY (resolved_at IS NOT NULL),
                                  (desk IS NOT NULL), opened_at, id''', (plan_id,)).fetchall()


def timeline(db, plan_id, case_id):
    get_case(db, plan_id, case_id)
    return db.execute('''SELECT * FROM support_case_event WHERE plan_id=%s AND case_id=%s ORDER BY id''',
                      (plan_id, case_id)).fetchall()


def get_case(db, plan_id, case_id):
    case = db.execute('SELECT * FROM support_case WHERE plan_id=%s AND id=%s', (plan_id, case_id)).fetchone()
    if not case:
        raise HTTPException(404, '找不到该线路的乘客协助单')
    return case


def require_open(case):
    if case['resolved_at']:
        raise HTTPException(409, '已办结的协助单已锁定')


def log_event(db, case, action, actor):
    db.execute('''INSERT INTO support_case_event (plan_id,case_id,action,desk,route_reason,actor)
                  VALUES (%s,%s,%s,%s,%s,%s)''',
               (case['plan_id'], case['id'], action, case['desk'], case['route_reason'], actor))
    return case


def open_case(db, plan_id, data, actor):
    edition = current_edition(db, plan_id)
    if not edition:
        raise HTTPException(409, '请先发布现场指引')
    if data.notice_edition != edition:
        raise HTTPException(409, '现场指引已更新，请重新打开工作台后登记')
    desk, reason = destination(db, plan_id, data.category)
    case = db.execute('''INSERT INTO support_case (plan_id,notice_edition,category,landmark,description,
                          desk,route_reason,opened_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
                      (plan_id, edition, data.category, data.landmark, data.description, desk, reason, actor)).fetchone()
    return log_event(db, case, 'opened', actor)


def redispatch_case(db, plan_id, case_id, actor):
    case = get_case(db, plan_id, case_id)
    require_open(case)
    desk, reason = destination(db, plan_id, case['category'], excluding_case=case_id)
    if desk == case['desk']:
        return case
    changed = db.execute('''UPDATE support_case SET desk=%s,route_reason=%s WHERE plan_id=%s AND id=%s RETURNING *''',
                         (desk, reason, plan_id, case_id)).fetchone()
    return log_event(db, changed, 'redispatched', actor)


def resolve_case(db, plan_id, case_id, note, actor):
    case = get_case(db, plan_id, case_id)
    require_open(case)
    if not case['desk']:
        raise HTTPException(409, '待派单须先分派到服务点')
    changed = db.execute('''UPDATE support_case SET resolution=%s,resolved_by=%s,resolved_at=now()
                            WHERE plan_id=%s AND id=%s RETURNING *''', (note, actor, plan_id, case_id)).fetchone()
    return log_event(db, changed, 'resolved', actor)
