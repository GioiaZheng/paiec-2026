"""Explain fixed-baseline errors conditional on saved local pools; never fits a predictor."""
import argparse
import collections
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parent
METHODS = ('constant_0.5', 'empirical_mean', 'beta_1_1')
SUBJECT_KEYS = ('normalized_name', 'provider', 'release_date', 'access_date',
                'harness', 'harness_version', 'reasoning_effort', 'subject_features_extra')


def expected_brier(item_means, evaluation_rate, budget, method):
    """Exact expectation over uniform item sampling and one recorded response per item.

    Item means describe the finite acquisition pool. Evaluation outcomes are fixed.
    This retrospective calculation must not be used to choose test predictions.
    """
    size = len(item_means)
    if not size or not 0 <= budget <= size or not 0 <= evaluation_rate <= 1:
        raise ValueError('Invalid pool, budget or evaluation rate')
    if method not in METHODS or any(not 0 <= p <= 1 for p in item_means):
        raise ValueError('Invalid method or item response mean')
    if budget == 0 or method == 'constant_0.5':
        prediction_mean, prediction_variance = .5, 0.
    else:
        mean = statistics.fmean(item_means)
        between = statistics.fmean((p - mean) ** 2 for p in item_means)
        within = statistics.fmean(p * (1 - p) for p in item_means)
        correction = (size - budget) / (size - 1) if size > 1 else 0.
        sum_variance = budget * (correction * between + within)
        alpha = 1 if method == 'beta_1_1' else 0
        prediction_mean = (budget * mean + alpha) / (budget + 2 * alpha)
        prediction_variance = sum_variance / (budget + 2 * alpha) ** 2
    bias_squared = (prediction_mean - evaluation_rate) ** 2
    outcome_term = evaluation_rate * (1 - evaluation_rate)
    return {'brier': prediction_variance + bias_squared + outcome_term,
            'prediction_mean': prediction_mean, 'variance': prediction_variance,
            'squared_bias': bias_squared, 'outcome_term': outcome_term}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(rows, budgets):
    if not rows:
        return {'pairs': 0, 'expected_alc': None, 'observed_alc': None}
    def average(key):
        return statistics.fmean(r[key] for r in rows)
    per_budget = []
    for i, n in enumerate(budgets):
        per_budget.append({'budget': n,
                           'expected_delta': statistics.fmean(r['curve_delta'][i] for r in rows),
                           'variance_change': statistics.fmean(r['variance_delta'][i] for r in rows),
                           'squared_bias_change': statistics.fmean(r['bias_delta'][i] for r in rows)})
    return {'pairs': len(rows),
            'expected_alc': {m: statistics.fmean(r['expected_alc'][m] for r in rows) for m in METHODS},
            'observed_alc': {m: statistics.fmean(r['observed_alc'][m] for r in rows) for m in METHODS},
            'expected_delta': average('expected_delta'), 'observed_delta': average('observed_delta'),
            'expected_improved': sum(r['expected_delta'] < -1e-12 for r in rows),
            'expected_worsened': sum(r['expected_delta'] > 1e-12 for r in rows),
            'observed_improved': sum(r['observed_delta'] < -1e-12 for r in rows),
            'observed_worsened': sum(r['observed_delta'] > 1e-12 for r in rows),
            'observed_loss_but_expected_gain': sum(r['observed_delta'] > 1e-12 and r['expected_delta'] < -1e-12 for r in rows),
            'observed_gain_but_expected_loss': sum(r['observed_delta'] < -1e-12 and r['expected_delta'] > 1e-12 for r in rows),
            'per_budget': per_budget}


def diagnose(run, pq):
    config, scores, trajectories = (read(run/f'{name}.json') for name in ('config', 'scores', 'trajectories'))
    if config['budgets'] != [0, 1, 3, 7, 15, 31] or config['weights'] != [.1, .2, .2, .2, .2, .1]:
        raise ValueError('Unexpected scoring contract')
    for name, source in read(run/'manifest.json').items():
        if sha(ROOT/name.replace('\\', '/')) != source['sha256']:
            raise ValueError(f'Data hash mismatch: {name}')
    if read(run/'independent_verification.json')['status'] != 'PASS':
        raise ValueError('Verify the saved experiment before diagnosing it')
    grouped = {}
    for b in sorted({t['benchmark'] for t in trajectories}):
        subjects = {s['subject_id']: {k: str(s[k]).strip() if s[k] is not None else '' for k in SUBJECT_KEYS}
                    for s in pq.read_table(ROOT/'data'/b/'subjects.parquet').to_pylist()}
        groups = collections.defaultdict(lambda: collections.defaultdict(list))
        for row in pq.read_table(ROOT/'data'/b/'responses.parquet').to_pylist():
            if row['response'] is not None:
                if row['response'] not in (0, 1):
                    raise ValueError('Nonbinary response')
                groups[json.dumps(subjects[row['subject_id']], sort_keys=True)][row['item_id']].append(row['response'])
        grouped[b] = groups
    by_pair = collections.defaultdict(list)
    for t in trajectories:
        by_pair[t['pair']].append(t)
    records = []
    for pair, ts in sorted(by_pair.items()):
        t = ts[0]
        acquired, evaluation = set(t['acquisition_item_ids']), set(t['evaluation_item_ids'])
        if acquired & evaluation or any(set(x['acquisition_item_ids']) != acquired or set(x['evaluation_item_ids']) != evaluation for x in ts):
            raise ValueError('Expected fixed disjoint pools across seeds')
        cells = grouped[t['benchmark']][json.dumps(t['subject'], sort_keys=True)]
        if acquired | evaluation != set(cells):
            raise ValueError('Incomplete pool coverage')
        means = [statistics.fmean(cells[i]) for i in sorted(acquired)]
        q = statistics.fmean(y for i in sorted(evaluation) for y in cells[i])
        expected, observed = {}, {}
        curves = {m: [expected_brier(means, q, n, m) for n in config['budgets']] for m in METHODS}
        for method in METHODS:
            expected[method] = sum(w * point['brier'] for w, point in zip(config['weights'], curves[method]))
            matched = [s for s in scores if s['pair'] == pair and s['method'] == method]
            if len(matched) != len(config['seeds']) or {s['seed'] for s in matched} != set(config['seeds']):
                raise ValueError('Incomplete saved seed comparison')
            observed[method] = statistics.fmean(s['alc'] for s in matched)
        candidate, reference = curves['beta_1_1'], curves['empirical_mean']
        delta = [c['brier'] - r['brier'] for c, r in zip(candidate, reference)]
        variance = [c['variance'] - r['variance'] for c, r in zip(candidate, reference)]
        bias = [c['squared_bias'] - r['squared_bias'] for c, r in zip(candidate, reference)]
        if not all(math.isclose(d, v+b, abs_tol=1e-12) for d, v, b in zip(delta, variance, bias)):
            raise AssertionError('Bias/variance decomposition failed')
        records.append({'pair': pair, 'benchmark': t['benchmark'], 'subject': t['subject'],
                        'source_items': len(cells), 'acquisition_items': len(acquired),
                        'evaluation_rate': q, 'acquisition_rate': statistics.fmean(means),
                        'expected_alc': expected, 'observed_alc': observed,
                        'expected_delta': expected['beta_1_1'] - expected['empirical_mean'],
                        'observed_delta': observed['beta_1_1'] - observed['empirical_mean'],
                        'curve_delta': delta, 'variance_delta': variance, 'bias_delta': bias})
    populations = {}
    for name, rows in [('all_local_pairs', records), ('size_80_to_1000', [r for r in records if 80 <= r['source_items'] <= 1000])]:
        populations[name] = summarize(rows, config['budgets'])
        populations[name]['by_benchmark'] = {b: summarize([r for r in rows if r['benchmark'] == b], config['budgets'])
                                             for b in sorted({r['benchmark'] for r in records})}
        populations[name]['by_evaluation_rate'] = {label: summarize([r for r in rows if lo <= r['evaluation_rate'] < hi], config['budgets'])
                                                  for label, lo, hi in [('below_0.1', 0., .1), ('0.1_to_0.9', .1, .9), ('0.9_and_above', .9, 1.01)]}
    return records, {'split_unit': config['split_unit'], 'benchmarks': sorted(grouped),
                     'seeds_in_observed_scores': config['seeds'], 'populations': populations,
                     'input_sha256': {name: sha(run/name) for name in ('config.json', 'scores.json', 'trajectories.json', 'manifest.json', 'independent_verification.json')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs', type=Path, nargs='+')
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT/'.deps'))
    import pyarrow.parquet as pq
    out = ROOT/'runs'/('diagnosis-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    summaries = []
    for i, run in enumerate(args.runs):
        records, summary = diagnose(run.resolve(), pq)
        (out/f'pairs_{i}.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
        summaries.append(summary)
    result = {'status': 'RETROSPECTIVE_DIAGNOSTIC_ONLY', 'fit': False, 'predictor_changed': False,
              'expectation': 'Exact over uniform acquisition-item samples without replacement and one uniformly selected recorded outcome per item, conditional on each saved pair of pools.',
              'limitations': ['All acquisition and evaluation outcomes are used for offline diagnosis only; never supplied to the predictor.',
                              'No expectation over alternative pool splits, new items, benchmark selection or unseen response runs.',
                              'Size filtering shows which groups fit alone; it does not simulate the organizer balancing and packing procedure.',
                              'Success-rate slices are retrospective descriptions, not prediction-time features or tuning rules.'],
              'source_sha256': {Path(__file__).name: sha(Path(__file__)), 'test_diagnostics.py': sha(ROOT/'test_diagnostics.py')},
              'studies': summaries}
    (out/'summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(out), 'studies': [{'benchmarks': s['benchmarks'], 'split_unit': s['split_unit'],
                       'all_pairs': s['populations']['all_local_pairs']['pairs'],
                       'fitting_pairs': s['populations']['size_80_to_1000']['pairs'],
                       'expected_alc': s['populations']['size_80_to_1000']['expected_alc']}
                      for s in summaries]}, indent=2))


if __name__ == '__main__':
    main()
