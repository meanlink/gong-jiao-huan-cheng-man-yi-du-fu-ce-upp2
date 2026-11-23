from datetime import date

from src.auth import passenger_key, password_hash
from src.db import connect, record

from .seed_support import seed_support

ACCOUNTS = (
    ('collector@chengxi.local', '陈毓', 'collector'),
    ('analyst@chengxi.local', '许默', 'analyst'),
    ('director@chengxi.local', '周宁', 'director'),
)
DEMO_PASSWORD = 'transfer1051'
DEMO_PLANS = (
    ('CX-26B', '城西客运枢纽', 'K12', 'M3', '北广场 3 号站台 → 过街天桥 → 地铁 B 口',
     '东连廊 1 号港湾 → 无障碍通道 → 地铁 C 口', '2026-11-03', '2026-11-07', '2026-11-10', '2026-11-14', 'surveying'),
    ('CX-26C', '城西客运枢纽', 'K12', 'M3', '北广场 3 号站台 → 过街天桥 → 地铁 B 口',
     '东连廊 2 号港湾 → 电梯过渡层 → 地铁 D 口', '2026-11-16', '2026-11-18', '2026-11-20', '2026-11-23', 'draft'),
    ('HT-26A', '河塘公交首末站', 'B17', 'K8', '南侧临时停车区 → 站外人行道 → 6 号候车区',
     '南侧固定站位 → 有顶步道 → 4 号候车区', '2026-11-05', '2026-11-09', '2026-11-12', '2026-11-16', 'draft'),
)
DEMO_SCORES = {
    ('peak', 'baseline'): (1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4),
    ('peak', 'trial'): (3, 3, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5),
    ('offpeak', 'baseline'): (2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4, 5),
    ('offpeak', 'trial'): (3, 3, 3, 4, 4, 4, 4, 4, 5, 5, 5, 5),
}


def seed():
    with connect() as db:
        db.execute('SELECT pg_advisory_xact_lock(1051002)')
        for email, name, role in ACCOUNTS:
            db.execute('''INSERT INTO staff_account (email,display_name,role,password_hash)
                          VALUES (%s,%s,%s,%s) ON CONFLICT (email) DO NOTHING''',
                       (email, name, role, password_hash(DEMO_PASSWORD)))
        for fields in DEMO_PLANS:
            row = db.execute('''INSERT INTO route_plan (code,hub,feeder,connection,baseline_path,trial_path,
                             baseline_from,baseline_to,trial_from,trial_to,stage)
                             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                             ON CONFLICT DO NOTHING RETURNING id, code''', fields).fetchone()
            if row:
                record(db, row['id'], ACCOUNTS[2][0], 'plan.seeded', code=row['code'])
            if row and row['code'] == 'CX-26B':
                seed_samples(db, row['id'])
                db.execute("""INSERT INTO route_walk_check (plan_id, cohort, walk_day, time_band, outcome,
                            walk_minutes, source_ref, note, recorded_by)
                            VALUES (%s,'baseline','2026-11-05','peak','clear',11,%s,%s,%s),
                                   (%s,'trial','2026-11-12','peak','clear',7,%s,%s,%s)""",
                           (row['id'], '北广场实走_1105.csv', '从 K12 下客点正常穿行到 B 口', ACCOUNTS[0][0],
                            row['id'], '东连廊实走_1112.csv', '沿无障碍通道正常步行到 C 口', ACCOUNTS[0][0]))
        seed_support(db, DEMO_SCORES)
        counts = db.execute('''SELECT (SELECT count(*) FROM staff_account) AS accounts,
                              (SELECT count(*) FROM route_plan) AS plans,
                              (SELECT count(*) FROM survey_sample) AS samples,
                              (SELECT count(*) FROM route_walk_check) AS walks,
                              (SELECT count(*) FROM route_handover) AS handovers,
                              (SELECT count(*) FROM support_desk) AS desks,
                              (SELECT count(*) FROM support_notice) AS notices,
                              (SELECT count(*) FROM support_case) AS support_cases,
                              (SELECT count(*) FROM support_case_event) AS support_events''').fetchone()
        return counts


def seed_samples(db, plan_id):
    day = {'baseline': date(2026, 11, 5), 'trial': date(2026, 11, 12)}

    def add(ref, token, band, cohort, rating, state, duplicate_of=None):
        return db.execute('''INSERT INTO survey_sample (sample_ref,plan_id,passenger_hash,cohort,trip_day,
                          time_band,rating,disposition,duplicate_of,collected_by)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                          (ref, plan_id, passenger_key(token), cohort, day[cohort], band, rating,
                           state, duplicate_of, ACCOUNTS[0][0])).fetchone()['id']

    index = 1
    for (band, cohort), scores in DEMO_SCORES.items():
        for rating in scores:
            ref = f'CX-{index:03}'
            add(ref, ref, band, cohort, rating, 'eligible')
            index += 1
    add('CX-049', 'CX-049', None, 'trial', 4, 'queue')
    first = db.execute("SELECT id FROM survey_sample WHERE sample_ref='CX-001'").fetchone()['id']
    add('CX-050', 'CX-001', 'peak', 'trial', 5, 'queue', first)
    record(db, plan_id, ACCOUNTS[0][0], 'survey.seeded', eligible=48, queued=2)


if __name__ == '__main__':
    print(seed())
