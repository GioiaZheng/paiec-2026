"""Paired weaker-prior ablation on saved, verified acquisition trajectories."""
import argparse
import collections
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

from diagnose_shrinkage import expected_brier, SUBJECT_KEYS
from weaker_shrinkage.model import predict

ROOT = Path(__file__).resolve().parent
METHODS = ('constant_0.5', 'empirical_mean', 'beta_1_1', 'beta_0_5_0_5')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(a, b):
    if not math.isclose(a, b, rel_tol=0., abs_tol=1e-12):
        raise AssertionError(f'Independent recomputation disagrees: {a}, {b}')


def summarize(rows, budgets, weights):
    if not rows:
        return {'pairs': 0}
    result = {'pairs': len(rows)}
    for kind in ('observed', 'expected'):
        result[f'{kind}_alc'] = {m: statistics.fmean(r[f'{kind}_alc'][m] for r in rows) for m in METHODS}
        result[f'{kind}_briers'] = {m: [statistics.fmean(r[f'{kind}_briers'][m][i] for r in rows)
                                       for i in range(len(budgets))] for m in METHODS}
        for reference in ('beta_1_1', 'empirical_mean'):
            deltas = [r[f'{kind}_alc']['beta_0_5_0_5'] - r[f'{kind}_alc'][reference] for r in rows]
            result[f'{kind}_vs_{reference}'] = {
                'delta': statistics.fmean(deltas),
                'improved': sum(d < -1e-12 for d in deltas),
                'worsened': sum(d > 1e-12 for d in deltas),
                'tied': sum(abs(d) <= 1e-12 for d in deltas)}
    result['per_budget_half_minus_one'] = [
        {'budget': n,
         'observed_delta': statistics.fmean(r['observed_briers']['beta_0_5_0_5'][i] - r['observed_briers']['beta_1_1'][i] for r in rows),
         'expected_delta': statistics.fmean(r['expected_briers']['beta_0_5_0_5'][i] - r['expected_briers']['beta_1_1'][i] for r in rows),
         'variance_change': statistics.fmean(r['variance_change'][i] for r in rows),
         'squared_bias_change': statistics.fmean(r['squared_bias_change'][i] for r in rows)}
        for i, n in enumerate(budgets)]
    result['weighted_squared_bias_change'] = math.fsum(w * r['squared_bias_change'] for w, r in zip(weights, result['per_budget_half_minus_one']))
    # Budgets 1 and 3 have equal official weights; report their mean separately.
    result['observed_small_budget_delta_vs_mean'] = statistics.fmean(
        r['observed_briers']['beta_0_5_0_5'][i] - r['observed_briers']['empirical_mean'][i]
        for r in rows for i, n in enumerate(budgets) if n in (1, 3))
    seeds = sorted(rows[0]['seed_alc'])
    result['per_seed_delta_vs_beta_1_1'] = {
        str(s): statistics.fmean(r['seed_alc'][s]['beta_0_5_0_5'] - r['seed_alc'][s]['beta_1_1'] for r in rows)
        for s in seeds}
    return result


def compare(run, protocol, pq):
    config, trajectories, scores = (read(run/f'{n}.json') for n in ('config', 'trajectories', 'scores'))
    for field in ('revision', 'seeds', 'budgets', 'weights'):
        if config[field] != protocol[field]:
            raise ValueError(f'Run has a different {field}')
    if read(run/'independent_verification.json')['status'] != 'PASS':
        raise ValueError('Verify the original run first')
    for name, source in read(run/'manifest.json').items():
        if sha(ROOT/name.replace('\\', '/')) != source['sha256']:
            raise ValueError(f'Data changed: {name}')
    source_hashes = {k.replace('\\', '/'): v for k, v in config['source_sha256'].items()}
    for name in ('shrinkage/model.py', 'upstream/empirical_mean/model.py'):
        if source_hashes[name] != protocol['method_sha256'][name]:
            raise ValueError('Saved baseline used a different predictor')
    benchmarks = sorted({t['benchmark'] for t in trajectories})
    allowed = set(protocol['benchmarks'] + protocol['development_benchmarks'])
    if not set(benchmarks) <= allowed:
        raise ValueError('Run outside the prespecified study')
    stage = 'NEW_PUBLIC_VALIDATION' if set(benchmarks) <= set(protocol['benchmarks']) else 'DEVELOPMENT_REANALYSIS'
    if stage == 'NEW_PUBLIC_VALIDATION':
        if config['protocol_sha256'] != sha(ROOT/'configs/weaker-shrinkage.json'):
            raise ValueError('New validation was not run with the frozen protocol')
        for name, expected in protocol['metadata_sha256'].items():
            if sha(ROOT/name) != expected:
                raise ValueError('Metadata changed after selection')
    grouped = {}
    for b in benchmarks:
        subjects = {r['subject_id']: {k: str(r[k]).strip() if r[k] is not None else '' for k in SUBJECT_KEYS}
                    for r in pq.read_table(ROOT/'data'/b/'subjects.parquet').to_pylist()}
        groups = collections.defaultdict(lambda: collections.defaultdict(list))
        for r in pq.read_table(ROOT/'data'/b/'responses.parquet').to_pylist():
            if r['response'] is not None:
                if r['response'] not in (0, 1):
                    raise ValueError('Nonbinary response')
                groups[json.dumps(subjects[r['subject_id']], sort_keys=True)][r['item_id']].append(r)
        grouped[b] = groups
    score_index = {(s['pair'], s['seed'], s['method']): s for s in scores}
    if len(score_index) != len(scores) or len(scores) != 3 * len(trajectories):
        raise ValueError('Unexpected baseline score coverage')
    records, verified = [], 0
    for pair in sorted({t['pair'] for t in trajectories}):
        ts = [t for t in trajectories if t['pair'] == pair]
        if sorted(t['seed'] for t in ts) != sorted(config['seeds']):
            raise ValueError('Seed coverage mismatch')
        first = ts[0]
        acquired, evaluation = set(first['acquisition_item_ids']), set(first['evaluation_item_ids'])
        if acquired & evaluation:
            raise ValueError('Overlapping pools')
        cells = grouped[first['benchmark']][json.dumps(first['subject'], sort_keys=True)]
        if acquired | evaluation != set(cells):
            raise ValueError('Incomplete pool coverage')
        by_id = {r['response_id']: r for rows in cells.values() for r in rows}
        outcomes = [r['response'] for i in sorted(evaluation) for r in cells[i]]
        q = statistics.fmean(outcomes)
        item_means = [statistics.fmean(r['response'] for r in cells[i]) for i in sorted(acquired)]
        curves = {m: [expected_brier(item_means, q, n, m) for n in config['budgets']] for m in METHODS}
        expected_alc = {m: math.fsum(w * point['brier'] for w, point in zip(config['weights'], curves[m])) for m in METHODS}
        seed_alc, seed_curves, weak_probabilities = {}, {}, {}
        for t in ts:
            if (set(t['acquisition_item_ids']) != acquired or set(t['evaluation_item_ids']) != evaluation
                    or t['benchmark'] != first['benchmark'] or t['subject'] != first['subject']):
                raise ValueError('Pools or subject changed between seeds')
            labels = [by_id[i] for i in t['revealed_response_ids']]
            if len(labels) != 31 or [r['item_id'] for r in labels] != t['acquisition_item_ids'][:31]:
                raise ValueError('Invalid acquisition trajectory')
            target = [t['subject'], {'benchmark_id': t['benchmark']}]
            revealed = [[[t['subject'], {'benchmark_id': t['benchmark']}], int(r['response'])] for r in labels]
            seed_curves[t['seed']], seed_alc[t['seed']] = {}, {}
            weak_probabilities[t['seed']] = []
            for method in METHODS:
                briers = []
                for i, n in enumerate(config['budgets']):
                    successes = math.fsum(r['response'] for r in labels[:n])
                    if method == 'constant_0.5' or n == 0:
                        p = .5
                    elif method == 'empirical_mean':
                        p = successes / n
                    elif method == 'beta_1_1':
                        p = (successes + 1) / (n + 2)
                    else:
                        p = (successes + .5) / (n + 1)
                    brier = math.fsum((p-y)**2 for y in outcomes) / len(outcomes)
                    if method == 'beta_0_5_0_5':
                        actual = predict(target, revealed[:n])
                        close(p, actual)
                        weak_probabilities[t['seed']].append(actual)
                    else:
                        saved = score_index[(pair, t['seed'], method)]
                        if saved['evaluation_responses'] != len(outcomes):
                            raise ValueError('Response-row count mismatch')
                        close(p, saved['probabilities'][i])
                        close(brier, saved['briers'][i])
                    briers.append(brier)
                    verified += 1
                seed_curves[t['seed']][method] = briers
                seed_alc[t['seed']][method] = math.fsum(w*b for w, b in zip(config['weights'], briers))
                if method != 'beta_0_5_0_5':
                    close(seed_alc[t['seed']][method], saved['alc'])
        variance = [h['variance']-o['variance'] for h, o in zip(curves['beta_0_5_0_5'], curves['beta_1_1'])]
        bias = [h['squared_bias']-o['squared_bias'] for h, o in zip(curves['beta_0_5_0_5'], curves['beta_1_1'])]
        for i in range(len(config['budgets'])):
            close(curves['beta_0_5_0_5'][i]['brier']-curves['beta_1_1'][i]['brier'], variance[i]+bias[i])
        records.append({'pair': pair, 'benchmark': first['benchmark'], 'source_items': len(cells),
                        'evaluation_rate': q, 'acquisition_rate': statistics.fmean(item_means),
                        'expected_alc': expected_alc,
                        'expected_briers': {m: [p['brier'] for p in curves[m]] for m in METHODS},
                        'observed_alc': {m: statistics.fmean(s[m] for s in seed_alc.values()) for m in METHODS},
                        'observed_briers': {m: [statistics.fmean(s[m][i] for s in seed_curves.values())
                                               for i in range(len(config['budgets']))] for m in METHODS},
                        'seed_alc': seed_alc, 'weak_probabilities': weak_probabilities,
                        'variance_change': variance, 'squared_bias_change': bias})
    populations = {}
    for population, rows in [('all_local_pairs', records), ('size_80_to_1000', [r for r in records if 80 <= r['source_items'] <= 1000])]:
        populations[population] = summarize(rows, config['budgets'], config['weights'])
        populations[population]['by_benchmark'] = {b: summarize([r for r in rows if r['benchmark'] == b], config['budgets'], config['weights']) for b in benchmarks}
        populations[population]['below_0_1'] = summarize([r for r in rows if r['evaluation_rate'] < .1], config['budgets'], config['weights'])
    return records, {'stage': stage, 'benchmarks': benchmarks, 'split_unit': config['split_unit'],
                     'verified_probability_budget_records': verified, 'populations': populations,
                     'input_sha256': {n: sha(run/n) for n in ('config.json', 'scores.json', 'trajectories.json', 'manifest.json', 'independent_verification.json')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs', type=Path, nargs='+')
    args = parser.parse_args()
    protocol_path = ROOT/'configs/weaker-shrinkage.json'
    protocol = read(protocol_path)
    for section in ('method_sha256', 'analysis_sha256'):
        for name, expected in protocol[section].items():
            if sha(ROOT/name) != expected:
                raise ValueError(f'Changed since protocol freeze: {name}')
    sys.path.insert(0, str(ROOT/'.deps'))
    import pyarrow
    import pyarrow.parquet as pq
    out = ROOT/'runs'/('weaker-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    studies = []
    for i, run in enumerate(args.runs):
        records, result = compare(run.resolve(), protocol, pq)
        (out/f'pairs_{i}.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
        studies.append(result)
    result = {'status': 'VERIFIED_PAIRED_ABLATION', 'fit': False, 'parameter_search': False,
              'python': sys.version, 'pyarrow': pyarrow.__version__, 'gpu_used': False,
              'protocol_sha256': sha(protocol_path), 'studies': studies,
              'limitations': protocol['limitations']}
    (out/'summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (out/'protocol.json').write_bytes(protocol_path.read_bytes())
    print(json.dumps({'output': str(out), 'studies': [
        {k: s[k] for k in ('stage', 'benchmarks', 'split_unit', 'verified_probability_budget_records')} | {
            'alc': s['populations']['all_local_pairs']['observed_alc'],
            'half_minus_one': s['populations']['all_local_pairs']['observed_vs_beta_1_1']}
        for s in studies]}, indent=2))


if __name__ == '__main__':
    main()
