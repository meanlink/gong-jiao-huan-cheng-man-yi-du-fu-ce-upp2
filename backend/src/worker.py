import logging
from pathlib import Path
from time import sleep

import psycopg
from psycopg.types.json import Jsonb

from .analysis import compare, eligible_samples, snapshot_hash
from .db import connect, record


def process_next():
    with connect() as db:
        job = db.execute('''SELECT * FROM retest_conclusion WHERE status='queued'
                           ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED''').fetchone()
        if job is None:
            return
        samples = eligible_samples(db, job['plan_id'])
        if job['snapshot_hash'] != snapshot_hash(samples):
            raise RuntimeError('Sealed survey data changed after the snapshot was taken')
        p, effect, rows, adopt = compare(samples)
        db.execute('''UPDATE retest_conclusion SET status='ready', calculated_at=now(), combined_p=%s,
                      stratified_effect=%s, band_results=%s, adopt_allowed=%s WHERE id=%s''',
                   (p, effect, Jsonb(rows), adopt, job['id']))
        record(db, job['plan_id'], 'analysis-worker', 'comparison.completed', p=p, effect=effect)


def run():
    logging.basicConfig(level=logging.INFO)
    heartbeat = Path('/runtime/analysis-worker')
    heartbeat.unlink(missing_ok=True)
    while True:
        try:
            process_next()
            heartbeat.touch()
        except psycopg.errors.UndefinedTable:
            logging.info('Waiting for backend migrations')
        except psycopg.Error:
            logging.exception('Database unavailable; the uncommitted job remains queued')
        sleep(1)


if __name__ == '__main__':
    run()
