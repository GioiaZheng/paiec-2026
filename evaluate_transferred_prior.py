"""One fixed leave-benchmark-out development comparison on existing local data."""
import collections
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.deps'))
import pyarrow
import pyarrow.parquet as pq

from diagnose_shrinkage import SUBJECT_KEYS, expected_brier as reference_expectation
from near_duplicates import audit_items, normalized
from transferred_prior import expected_brier, fit_center, predict

METHODS = ('beta_1_1', 'transferred_center')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(left, right):
    if not math.isclose(left, right, abs_tol=1e-12, rel_tol=0):
        raise AssertionError(f'Independent check disagrees: {left}, {right}')


def subject_key(subject):
    return json.dumps(subject, sort_keys=True)


def load_run(name, protocol):
    directory = ROOT / name
    config = read(directory / 'config.json')
    for field in ('revision', 'seeds', 'budgets', 'weights'):
        if config[field] != protocol[field]:
            raise ValueError(f'Changed scoring contract: {field}')
    if read(directory / 'independent_verification.json')['status'] != 'PASS':
        raise ValueError('Saved run was not independently verified')
    for source, record in read(directory / 'manifest.json').items():
        if sha(ROOT / source.replace('\\', '/')) != record['sha256']:
            raise ValueError(f'Data changed: {source}')
    trajectories = read(directory / 'trajectories.json')
    scores = read(directory / 'scores.json')
    index = {(s['pair'], s['seed'], s['method']): s for s in scores}
    if len(index) != len(scores) or len(scores) != 3 * len(trajectories):
        raise ValueError('Invalid score coverage')
    return {'name': name, 'config': config, 'trajectories': trajectories, 'scores': index,
            'sha256': {n: sha(directory / n) for n in
                       ('config.json', 'manifest.json', 'scores.json', 'trajectories.json',
                        'independent_verification.json')}}


def summarize(rows, budgets, seeds):
    result = {'groups': len(rows)}
    for kind in ('observed', 'expected'):
        result[kind] = {m: statistics.fmean(r[kind][m] for r in rows) for m in METHODS}
        differences = [r[kind]['transferred_center'] - r[kind]['beta_1_1'] for r in rows]
        result[kind]['delta'] = statistics.fmean(differences)
        result[kind]['improved_groups'] = sum(d < -1e-12 for d in differences)
        result[kind]['worsened_groups'] = sum(d > 1e-12 for d in differences)
        result[kind]['by_budget_delta'] = {
            str(n): statistics.fmean(r[f'{kind}_curves']['transferred_center'][i]
                                     - r[f'{kind}_curves']['beta_1_1'][i] for r in rows)
            for i, n in enumerate(budgets)}
    result['seed_deltas'] = {str(s): statistics.fmean(
        r['seed_alc'][str(s)]['transferred_center'] - r['seed_alc'][str(s)]['beta_1_1']
        for r in rows) for s in seeds}
    return result


def main():
    protocol_path = ROOT / 'configs/transferred-prior.json'
    protocol = read(protocol_path)
    frozen = read(ROOT / 'local/transferred-prior-freeze.json')
    for name, expected in frozen['source_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f'Changed after freeze: {name}')
    output = ROOT / 'runs' / ('transferred-prior-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir()
    runs = [load_run(name, protocol) for name in protocol['primary_runs'] + protocol['sensitivity_runs']]
    primary = runs[:len(protocol['primary_runs'])]
    cells, rates, texts, data_hashes, source_summaries = {}, {}, {}, {}, {}
    for benchmark in protocol['benchmarks']:
        trajectories = [t for run in primary for t in run['trajectories'] if t['benchmark'] == benchmark]
        eligible = {subject_key(t['subject']) for t in trajectories}
        subjects = {s['subject_id']: {k: str(s[k]).strip() if s[k] is not None else '' for k in SUBJECT_KEYS}
                    for s in pq.read_table(ROOT / 'data' / benchmark / 'subjects.parquet').to_pylist()}
        grouped = collections.defaultdict(lambda: collections.defaultdict(list))
        response_ids = set()
        for r in pq.read_table(ROOT / 'data' / benchmark / 'responses.parquet').to_pylist():
            if r['response'] is None:
                continue
            if r['response'] not in (0, 1) or r['response_id'] in response_ids:
                raise ValueError('Invalid response or duplicate response ID')
            response_ids.add(r['response_id'])
            key = subject_key(subjects[r['subject_id']])
            if key in eligible:
                grouped[key][r['item_id']].append(r)
        if set(grouped) != eligible or any(len(group) < 80 for group in grouped.values()):
            raise ValueError('Group coverage or eligibility differs from saved run')
        cells[benchmark] = grouped
        rates[benchmark] = [statistics.fmean(r['response'] for rows in group.values() for r in rows)
                            for _, group in sorted(grouped.items())]
        source_summaries[benchmark] = {'groups': len(rates[benchmark]),
                                       'mean_group_success': statistics.fmean(rates[benchmark])}
        used = {i for group in grouped.values() for i in group}
        covered = set()
        for row in pq.read_table(ROOT / 'data' / benchmark / 'items.parquet').to_pylist():
            if row['item_id'] not in used:
                continue
            covered.add(row['item_id'])
            if benchmark == 'bertaqa':
                messages = json.loads(row['content'])
                if messages[-1]['role'] != 'user':
                    raise ValueError('Unexpected BertaQA prompt format')
                key, text = benchmark + '/' + row['raw_item_id'], messages[-1]['content']
            else:
                key, text = benchmark + '/' + row['item_id'], row['content']
            if key in texts and normalized(texts[key]) != normalized(text):
                raise ValueError('Conflicting question identity')
            texts[key] = text
        if covered != used:
            raise ValueError('Missing used item text')
        for table in ('benchmarks', 'items', 'subjects', 'responses'):
            path = ROOT / 'data' / benchmark / (table + '.parquet')
            data_hashes[path.relative_to(ROOT).as_posix()] = sha(path)
    _, audit = audit_items(texts)
    audit['cross_benchmark_pairs'] = [p for p in audit['pairs'] if p['left'].split('/')[0] != p['right'].split('/')[0]]
    (output / 'lexical_audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    if audit['cross_benchmark_pairs']:
        raise ValueError(f'Cross-benchmark duplicates require review; see {output}')
    priors = {b: fit_center(rates, b) for b in protocol['benchmarks']}
    records, checks = [], 0
    for run in runs:
        grouped_trajectories = collections.defaultdict(list)
        for t in run['trajectories']:
            grouped_trajectories[t['pair']].append(t)
        for pair, trajectories in sorted(grouped_trajectories.items()):
            first = trajectories[0]
            benchmark = first['benchmark']
            group = cells[benchmark][subject_key(first['subject'])]
            acquired, evaluation = set(first['acquisition_item_ids']), set(first['evaluation_item_ids'])
            if acquired & evaluation or acquired | evaluation != set(group):
                raise ValueError('Pools overlap or do not cover the eligible group')
            if sorted(t['seed'] for t in trajectories) != protocol['seeds']:
                raise ValueError('Seed coverage differs')
            by_id = {r['response_id']: r for rows in group.values() for r in rows}
            outcomes = [r['response'] for i in sorted(evaluation) for r in group[i]]
            q = statistics.fmean(outcomes)
            item_rates = [statistics.fmean(r['response'] for r in group[i]) for i in sorted(acquired)]
            center, training = priors[benchmark]
            if benchmark in training:
                raise AssertionError('Held-out benchmark leaked into fit')
            seed_curves, seed_alc = {}, {}
            for t in trajectories:
                if (set(t['acquisition_item_ids']) != acquired or set(t['evaluation_item_ids']) != evaluation
                        or t['subject'] != first['subject'] or t['benchmark'] != benchmark):
                    raise ValueError('Pools or group changed between seeds')
                labels = [by_id[i] for i in t['revealed_response_ids']]
                if len(labels) != 31 or [r['item_id'] for r in labels] != t['acquisition_item_ids'][:31]:
                    raise ValueError('Invalid acquisition trajectory')
                target = [t['subject'], {'benchmark_id': benchmark}]
                evidence = [[target, int(r['response'])] for r in labels]
                seed = str(t['seed'])
                seed_curves[seed], seed_alc[seed] = {}, {}
                for method, mu in (('beta_1_1', .5), ('transferred_center', center)):
                    curve = []
                    saved = run['scores'][(pair, t['seed'], 'beta_1_1')]
                    for i, n in enumerate(protocol['budgets']):
                        p = predict(target, evidence[:n], mu)
                        close(p, (sum(r['response'] for r in labels[:n]) + 2 * mu) / (n + 2))
                        # Direct response-row computation, independent of aggregate shortcut.
                        brier = math.fsum((p - y)**2 for y in outcomes) / len(outcomes)
                        close(brier, q * (1 - p)**2 + (1 - q) * p*p)
                        if method == 'beta_1_1':
                            close(p, saved['probabilities'][i])
                            close(brier, saved['briers'][i])
                            if saved['evaluation_responses'] != len(outcomes):
                                raise ValueError('Response count differs from verified run')
                        curve.append(brier)
                        checks += 1
                    seed_curves[seed][method] = curve
                    seed_alc[seed][method] = math.fsum(w*b for w, b in zip(protocol['weights'], curve))
                    if method == 'beta_1_1':
                        close(seed_alc[seed][method], saved['alc'])
            expected = {m: [expected_brier(item_rates, q, n, mu) for n in protocol['budgets']]
                        for m, mu in (('beta_1_1', .5), ('transferred_center', center))}
            for i, n in enumerate(protocol['budgets']):
                close(expected['beta_1_1'][i], reference_expectation(item_rates, q, n, 'beta_1_1')['brier'])
            records.append({'pair': pair, 'benchmark': benchmark, 'run': run['name'],
                            'split_unit': run['config']['split_unit'], 'source_items': len(group),
                            'evaluation_rate': q, 'center': center, 'training_benchmarks': training,
                            'observed': {m: statistics.fmean(s[m] for s in seed_alc.values()) for m in METHODS},
                            'expected': {m: math.fsum(w*b for w, b in zip(protocol['weights'], expected[m])) for m in METHODS},
                            'observed_curves': {m: [statistics.fmean(c[m][i] for c in seed_curves.values())
                                                    for i in range(6)] for m in METHODS},
                            'expected_curves': expected, 'seed_alc': seed_alc})
    summaries = {}
    for design in ('primary_item', 'guarded_sensitivity'):
        rows = [r for r in records if r['run'] in protocol['primary_runs']]
        if design == 'guarded_sensitivity':
            rows = [r for r in rows if r['benchmark'] in ('real_webagents', 'financebench')]
            rows += [r for r in records if r['run'] in protocol['sensitivity_runs']]
        by_benchmark = {b: summarize([r for r in rows if r['benchmark'] == b], protocol['budgets'], protocol['seeds'])
                        for b in protocol['benchmarks']}
        summaries[design] = {'all_pairs': summarize(rows, protocol['budgets'], protocol['seeds']),
                             'by_benchmark': by_benchmark,
                             'equal_benchmark': {kind: {m: statistics.fmean(s[kind][m] for s in by_benchmark.values())
                                                        for m in (*METHODS, 'delta')} for kind in ('observed', 'expected')},
                             'size_80_to_1000': summarize([r for r in rows if r['source_items'] <= 1000],
                                                          protocol['budgets'], protocol['seeds'])}
    primary_summary = summaries['primary_item']
    screening = {
        'equal_pair_improves': all(primary_summary['all_pairs'][k]['delta'] < 0 for k in ('observed', 'expected')),
        'equal_benchmark_improves': all(primary_summary['equal_benchmark'][k]['delta'] < 0 for k in ('observed', 'expected')),
        'four_benchmarks_improve': sum(all(s[k]['delta'] < 0 for k in ('observed', 'expected'))
                                      for s in primary_summary['by_benchmark'].values()) >= 4,
        'guarded_direction_preserved': all(summaries['guarded_sensitivity']['equal_benchmark'][k]['delta'] < 0
                                           for k in ('observed', 'expected'))}
    result = {'status': 'COMPLETED_DEVELOPMENT_SCREEN', 'created_utc': datetime.now(timezone.utc).isoformat(),
              'source_sha256': frozen['source_sha256'], 'data_sha256': data_hashes,
              'run_sha256': {r['name']: r['sha256'] for r in runs}, 'python': sys.version,
              'pyarrow': pyarrow.__version__, 'gpu_used': False, 'network_used': False,
              'verified_probability_budget_records': checks, 'cross_benchmark_lexical_matches': 0,
              'training_source_summary': source_summaries,
              'fold_priors': {b: {'center': p[0], 'training_benchmarks': p[1]} for b, p in priors.items()},
              'summaries': summaries, 'screening_checks': screening,
              'screen_passed': all(screening.values()), 'limitations': protocol['limitations']}
    for filename, value in (('pairs.json', records), ('summary.json', result), ('protocol.json', protocol)):
        (output / filename).write_text(json.dumps(value, indent=2), encoding='utf-8')
    brief = {'output': str(output), 'screening_checks': screening,
             'screen_passed': result['screen_passed'],
             'by_benchmark': {b: {k: s[k] for k in ('observed', 'expected')}
                              for b, s in primary_summary['by_benchmark'].items()},
             'all_pairs': primary_summary['all_pairs'],
             'equal_benchmark': primary_summary['equal_benchmark'],
             'verified_probability_budget_records': checks}
    (ROOT / 'local/transferred-prior-output.json').write_text(json.dumps(brief, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(output), 'screen_passed': result['screen_passed'],
                      'screening_checks': screening, 'equal_benchmark': primary_summary['equal_benchmark'],
                      'verified_probability_budget_records': checks}, indent=2))


if __name__ == '__main__':
    main()
