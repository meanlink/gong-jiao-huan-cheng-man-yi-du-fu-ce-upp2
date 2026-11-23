from fastapi import HTTPException

from .db import record


def list_notices(db, plan_id):
    return db.execute('SELECT * FROM support_notice WHERE plan_id=%s ORDER BY edition DESC', (plan_id,)).fetchall()


def current_edition(db, plan_id):
    row = db.execute('SELECT max(edition) AS edition FROM support_notice WHERE plan_id=%s', (plan_id,)).fetchone()
    return row['edition'] or 0


def publish_notice(db, plan_id, data, actor):
    latest = current_edition(db, plan_id)
    if data.previous_edition != latest:
        raise HTTPException(409, '现场指引已更新，请重新打开工作台后发布')
    edition = latest + 1
    notice = db.execute('''INSERT INTO support_notice (plan_id,edition,meeting_point,directions,published_by)
                           VALUES (%s,%s,%s,%s,%s) RETURNING *''',
                        (plan_id, edition, data.meeting_point, data.directions, actor)).fetchone()
    record(db, plan_id, actor, 'support.notice_published', edition=edition)
    return notice
