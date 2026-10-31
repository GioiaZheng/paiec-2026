"""Paired adaptive-prior experiment using verified saved pools; no network."""
import collections
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import sys

from acquisition_distribution import success_distributions
from adaptive_prior import posterior, predict
from evaluate_transferred_prior import ROOT, close, load_run, pq, pyarrow, read, sha, subject_key
from diagnose_shrinkage import SUBJECT_KEYS
from transferred_prior import fit_center

METHODS = ('beta_1_1', 'transferred_center', 'static_half_mixture', 'adaptive_mixture')


def predictions(successes, count, center):
    neutral = (successes + 1) / (count + 2)
    transfer = (successes + 2 * center) / (count + 2)
    adaptive, weight = posterior(successes, count, center)
    return {'beta_1_1': neutral, 'transferred_center': transfer,
            'static_half_mixture': (neutral + transfer) / 2,
            'adaptive_mixture': adaptive}, weight


def summarize(rows, budgets, seeds):
    result = {'groups': len(rows)}
    for kind in ('observed', 'expected'):
        result[kind] = {m: statistics.fmean(r[kind][m] for r in rows) for m in METHODS}
        result[kind]['delta_vs_baseline'] = result[kind]['adaptive_mixture'] - result[kind]['beta_1_1']
        result[kind]['delta_vs_static'] = result[kind]['adaptive_mixture'] - result[kind]['static_half_mixture']
        result[kind]['improved_groups'] = sum(r[kind]['adaptive_mixture'] < r[kind]['beta_1_1'] - 1e-12 for r in rows)
        result[kind]['worsened_groups'] = sum(r[kind]['adaptive_mixture'] > r[kind]['beta_1_1'] + 1e-12 for r in rows)
        result[kind]['budget_delta_vs_baseline'] = {str(n): statistics.fmean(
            r[kind+'_curves']['adaptive_mixture'][i] - r[kind+'_curves']['beta_1_1'][i] for r in rows)
            for i, n in enumerate(budgets)}
    result['seed_deltas'] = {str(s): statistics.fmean(
        r['seed_alc'][str(s)]['adaptive_mixture'] - r['seed_alc'][str(s)]['beta_1_1'] for r in rows) for s in seeds}
    result['average_transferred_weight'] = {str(n): statistics.fmean(r['weight_by_budget'][i] for r in rows)
                                            for i, n in enumerate(budgets)}
    return result


def main():
    freeze = read(ROOT / 'local/adaptive-prior-freeze.json')
    for name, expected in freeze['source_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f'Changed since protocol freeze: {name}')
    protocol = read(ROOT / 'configs/adaptive-prior.json')
    parent_protocol = read(ROOT / protocol['parent_protocol'])
    parent_dir = ROOT / protocol['parent_run']
    parent_review = read(ROOT / 'local/optimization-review-2026-10-31.json')
    for name, expected in parent_review['evidence_sha256'].items():
        if sha(parent_dir / name) != expected:
            raise ValueError(f'Parent evidence changed: {name}')
    parent = read(parent_dir / 'summary.json')
    parent_rows = {(r['run'], r['pair']): r for r in read(parent_dir / 'pairs.json')}
    for name, expected in parent['data_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f'Data changed since lexical audit: {name}')
    if read(parent_dir / 'lexical_audit.json')['cross_benchmark_pairs']:
        raise ValueError('Unresolved cross-benchmark overlap')
    runs = [load_run(name, parent_protocol) for name in parent_protocol['primary_runs'] + parent_protocol['sensitivity_runs']]
    for run in runs:
        if run['sha256'] != parent['run_sha256'][run['name']]:
            raise ValueError('Saved trajectory evidence changed')
    cells, rates = {}, {}
    for benchmark in parent_protocol['benchmarks']:
        allowed = {subject_key(t['subject']) for run in runs for t in run['trajectories'] if t['benchmark'] == benchmark}
        subjects = {r['subject_id']: {k: str(r[k]).strip() if r[k] is not None else '' for k in SUBJECT_KEYS}
                    for r in pq.read_table(ROOT / 'data' / benchmark / 'subjects.parquet').to_pylist()}
        groups = collections.defaultdict(lambda: collections.defaultdict(list))
        for row in pq.read_table(ROOT / 'data' / benchmark / 'responses.parquet').to_pylist():
            if row['response'] is None:
                continue
            if row['response'] not in (0, 1):
                raise ValueError('Nonbinary response')
            key = subject_key(subjects[row['subject_id']])
            if key in allowed:
                groups[key][row['item_id']].append(row)
        if set(groups) != allowed or any(len(g) < 80 for g in groups.values()):
            raise ValueError('Changed eligible group coverage')
        cells[benchmark] = groups
        rates[benchmark] = [statistics.fmean(r['response'] for rows in g.values() for r in rows)
                            for _, g in sorted(groups.items())]
    priors = {b: fit_center(rates, b) for b in rates}
    for b, (center, training) in priors.items():
        close(center, parent['fold_priors'][b]['center'])
        if training != parent['fold_priors'][b]['training_benchmarks']:
            raise ValueError('Changed training-fold membership')
    output = ROOT / 'runs' / ('adaptive-prior-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir()
    records, checked = [], 0
    budgets, weights, seeds = (parent_protocol[k] for k in ('budgets', 'weights', 'seeds'))
    for run in runs:
        by_pair = collections.defaultdict(list)
        for t in run['trajectories']:
            by_pair[t['pair']].append(t)
        for pair, ts in sorted(by_pair.items()):
            first = ts[0]
            group = cells[first['benchmark']][subject_key(first['subject'])]
            center = priors[first['benchmark']][0]
            acquired, evaluation = set(first['acquisition_item_ids']), set(first['evaluation_item_ids'])
            if acquired & evaluation or acquired | evaluation != set(group):
                raise ValueError('Invalid pool split')
            outcomes = [r['response'] for i in sorted(evaluation) for r in group[i]]
            q = statistics.fmean(outcomes)
            item_rates = [statistics.fmean(r['response'] for r in group[i]) for i in sorted(acquired)]
            distributions = success_distributions(item_rates, budgets)
            # Expectations are diagnostics only; no distribution or evaluation rate enters predict().
            expected_curves = {m: [] for m in METHODS}
            for n in budgets:
                prediction_table = [predictions(s, n, center)[0] for s in range(n + 1)]
                for method in METHODS:
                    expected_curves[method].append(math.fsum(mass * (
                        q * (1 - prediction_table[s][method])**2 + (1 - q) * prediction_table[s][method]**2)
                        for s, mass in enumerate(distributions[n])))
            response_index = {r['response_id']: r for rows in group.values() for r in rows}
            seed_curves, seed_alc, seed_weights = {}, {}, {}
            if sorted(t['seed'] for t in ts) != seeds:
                raise ValueError('Changed seed coverage')
            for t in ts:
                if (set(t['acquisition_item_ids']) != acquired or set(t['evaluation_item_ids']) != evaluation
                        or t['subject'] != first['subject'] or t['benchmark'] != first['benchmark']):
                    raise ValueError('Changed group or pools')
                labels = [response_index[i] for i in t['revealed_response_ids']]
                if len(labels) != 31 or [r['item_id'] for r in labels] != t['acquisition_item_ids'][:31]:
                    raise ValueError('Invalid acquisition trajectory')
                target = [t['subject'], {'benchmark_id': t['benchmark']}]
                evidence = [[target, int(r['response'])] for r in labels]
                seed = str(t['seed'])
                seed_curves[seed] = {m: [] for m in METHODS}
                seed_weights[seed] = []
                saved = run['scores'][(pair, t['seed'], 'beta_1_1')]
                for i, n in enumerate(budgets):
                    values, weight = predictions(int(sum(r['response'] for r in labels[:n])), n, center)
                    close(values['adaptive_mixture'], predict(target, evidence[:n], center))
                    seed_weights[seed].append(weight)
                    for method, p in values.items():
                        brier = math.fsum((p - y)**2 for y in outcomes) / len(outcomes)
                        close(brier, q * (1-p)**2 + (1-q) * p*p)
                        if method == 'beta_1_1':
                            close(p, saved['probabilities'][i])
                            close(brier, saved['briers'][i])
                        seed_curves[seed][method].append(brier)
                        checked += 1
                seed_alc[seed] = {m: math.fsum(w*b for w, b in zip(weights, seed_curves[seed][m])) for m in METHODS}
            row = {'pair': pair, 'benchmark': first['benchmark'], 'run': run['name'],
                   'split_unit': run['config']['split_unit'], 'source_items': len(group),
                   'center': center, 'evaluation_rate': q,
                   'expected_curves': expected_curves,
                   'expected': {m: math.fsum(w*b for w, b in zip(weights, expected_curves[m])) for m in METHODS},
                   'observed': {m: statistics.fmean(v[m] for v in seed_alc.values()) for m in METHODS},
                   'observed_curves': {m: [statistics.fmean(v[m][i] for v in seed_curves.values()) for i in range(6)] for m in METHODS},
                   'seed_alc': seed_alc,
                   'weight_by_budget': [statistics.fmean(v[i] for v in seed_weights.values()) for i in range(6)]}
            previous = parent_rows[(run['name'], pair)]
            for kind in ('observed', 'expected'):
                for method in ('beta_1_1', 'transferred_center'):
                    close(row[kind][method], previous[kind][method])
                    for a, b in zip(row[kind+'_curves'][method], previous[kind+'_curves'][method]):
                        close(a, b)
            records.append(row)
        print('Verified run:', run['name'], flush=True)
    summaries = {}
    for design in ('primary_item', 'guarded_sensitivity'):
        rows = [r for r in records if r['run'] in parent_protocol['primary_runs']]
        if design == 'guarded_sensitivity':
            rows = [r for r in rows if r['benchmark'] in ('real_webagents', 'financebench')]
            rows += [r for r in records if r['run'] in parent_protocol['sensitivity_runs']]
        by_benchmark = {b: summarize([r for r in rows if r['benchmark'] == b], budgets, seeds) for b in rates}
        summaries[design] = {'all_pairs': summarize(rows, budgets, seeds), 'by_benchmark': by_benchmark,
                             'equal_benchmark': {k: {m: statistics.fmean(s[k][m] for s in by_benchmark.values())
                                                      for m in (*METHODS, 'delta_vs_baseline', 'delta_vs_static')}
                                                 for k in ('observed', 'expected')},
                             'size_80_to_1000': summarize([r for r in rows if r['source_items'] <= 1000], budgets, seeds)}
    primary = summaries['primary_item']
    screening = {
        'equal_pair_improves': all(primary['all_pairs'][k]['delta_vs_baseline'] < 0 for k in ('observed', 'expected')),
        'equal_benchmark_improves': all(primary['equal_benchmark'][k]['delta_vs_baseline'] < 0 for k in ('observed', 'expected')),
        'four_benchmarks_improve': sum(all(s[k]['delta_vs_baseline'] < 0 for k in ('observed', 'expected'))
                                      for s in primary['by_benchmark'].values()) >= 4,
        'guarded_direction_preserved': all(summaries['guarded_sensitivity']['equal_benchmark'][k]['delta_vs_baseline'] < 0
                                           for k in ('observed', 'expected'))}
    result = {'status': 'COMPLETED_DEVELOPMENT_SCREEN', 'created_utc': datetime.now(timezone.utc).isoformat(),
              'python': sys.version, 'pyarrow': pyarrow.__version__, 'gpu_used': False, 'network_used': False,
              'source_sha256': freeze['source_sha256'], 'data_sha256': parent['data_sha256'],
              'parent_summary_sha256': sha(parent_dir / 'summary.json'),
              'lexical_audit_sha256': sha(parent_dir / 'lexical_audit.json'),
              'verified_probability_budget_records': checked, 'screening_checks': screening,
              'screen_passed': all(screening.values()), 'summaries': summaries, 'limitations': protocol['limitations']}
    for filename, value in (('pairs.json', records), ('summary.json', result), ('protocol.json', protocol)):
        (output / filename).write_text(json.dumps(value, indent=2), encoding='utf-8')
    brief = {'output': str(output), 'screen_passed': result['screen_passed'], 'screening_checks': screening,
             'equal_benchmark': primary['equal_benchmark'], 'all_pairs': primary['all_pairs']}
    (ROOT / 'local/adaptive-prior-output.json').write_text(json.dumps(brief, indent=2), encoding='utf-8')
    print(json.dumps(brief, indent=2))


if __name__ == '__main__':
    main()
