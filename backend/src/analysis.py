import hashlib
import json
import math
from collections import Counter
from statistics import median

from .schemas import Cohort, TimeBand

MIN_PER_CELL = 8
METHOD = 'transfer-rank-v1'
ADOPT_P_MAX = 0.05
ADOPT_EFFECT_MIN = 0.15
BAND_EFFECT_FLOOR = -0.20


def coverage(samples):
    counts = Counter((row['time_band'], row['cohort']) for row in samples)
    return [{
        'band': band.value,
        'baseline': counts[band, Cohort.BASELINE],
        'trial': counts[band, Cohort.TRIAL],
    } for band in TimeBand]


def snapshot_hash(samples):
    content = [[row[key] for key in ('sample_ref', 'cohort', 'time_band', 'rating')]
               for row in sorted(samples, key=lambda row: row['sample_ref'])]
    return hashlib.sha256(json.dumps([METHOD, content], separators=(',', ':')).encode()).hexdigest()


def eligible_samples(db, plan_id):
    return db.execute('''SELECT sample_ref, cohort, time_band, rating FROM survey_sample
                         WHERE plan_id=%s AND disposition='eligible' ''', (plan_id,)).fetchall()


def probability(z):
    return math.erfc(abs(z) / math.sqrt(2))


def mann_whitney(baseline, trial):
    """Use average ranks for ties. U and effect are oriented toward the trial cohort."""
    n_base, n_trial = len(baseline), len(trial)
    total = n_base + n_trial
    pairs = n_base * n_trial
    base_counts, trial_counts = Counter(baseline), Counter(trial)
    previous = 0
    trial_rank_sum = tie_term = 0
    for rating in sorted(base_counts.keys() | trial_counts.keys()):
        ties = base_counts[rating] + trial_counts[rating]
        rank = previous + (ties + 1) / 2
        trial_rank_sum += rank * trial_counts[rating]
        tie_term += ties**3 - ties
        previous += ties
    u = trial_rank_sum - n_trial * (n_trial + 1) / 2
    variance = pairs / 12 * (total + 1 - tie_term / (total * (total - 1)))
    delta = u - pairs / 2
    return {
        'u': u, 'effect': 2 * u / pairs - 1, 'delta': delta, 'variance': variance,
        'p': probability(delta / math.sqrt(variance)) if variance > 0 else 1.0,
        'baseline_median': median(baseline), 'trial_median': median(trial),
        'baseline_scores': [base_counts[i] for i in range(1, 6)],
        'trial_scores': [trial_counts[i] for i in range(1, 6)],
    }


def compare(samples):
    buckets = {(band, cohort): [] for band in TimeBand for cohort in Cohort}
    for row in samples:
        buckets[row['time_band'], row['cohort']].append(row['rating'])
    rows = []
    numerator = variance = pair_weight = 0.0
    for counts in coverage(samples):
        band = counts['band']
        old = buckets[band, Cohort.BASELINE]
        new = buckets[band, Cohort.TRIAL]
        if min(len(old), len(new)) < MIN_PER_CELL:
            raise ValueError(f'{band}: insufficient samples')
        result = mann_whitney(old, new)
        weight = 1 / (len(old) + len(new) + 1)
        numerator += weight * result.pop('delta')
        variance += weight**2 * result.pop('variance')
        pair_weight += weight * len(old) * len(new)
        rows.append({**counts, **result})
    p = probability(numerator / math.sqrt(variance)) if variance > 0 else 1.0
    effect = 2 * numerator / pair_weight
    adopt = p <= ADOPT_P_MAX and effect >= ADOPT_EFFECT_MIN and all(
        row['effect'] > BAND_EFFECT_FLOOR for row in rows
    )
    return p, effect, rows, adopt
