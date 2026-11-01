"""Item-wise paired lexical retrieval screen on previously inspected data."""
import collections
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import random
import statistics
import sys
import time

from evaluate_transferred_prior import ROOT, close, load_run, pq, pyarrow, read, sha, subject_key
from diagnose_shrinkage import SUBJECT_KEYS
from retrieval_shrinkage.model import PreparedEvidence, features, predict, weighted_prediction

METHODS = ('beta_1_1', 'retrieval', 'shuffled_labels')


def summarize(rows, budgets, seeds):
    result = {'groups': len(rows), 'alc': {m: statistics.fmean(r['alc'][m] for r in rows) for m in METHODS}}
    result['delta_vs_baseline'] = result['alc']['retrieval'] - result['alc']['beta_1_1']
    result['delta_vs_shuffled'] = result['alc']['retrieval'] - result['alc']['shuffled_labels']
    result['improved_groups'] = sum(r['alc']['retrieval'] < r['alc']['beta_1_1'] - 1e-12 for r in rows)
    result['worsened_groups'] = sum(r['alc']['retrieval'] > r['alc']['beta_1_1'] + 1e-12 for r in rows)
    result['budget_delta'] = {str(n): statistics.fmean(r['curves']['retrieval'][i] - r['curves']['beta_1_1'][i]
                                                     for r in rows) for i, n in enumerate(budgets)}
    result['seed_deltas'] = {str(s): statistics.fmean(r['seed_alc'][str(s)]['retrieval'] - r['seed_alc'][str(s)]['beta_1_1']
                                                    for r in rows) for s in seeds}
    return result


def main():
    started = time.perf_counter()
    frozen = read(ROOT / 'local/retrieval-shrinkage-freeze.json')
    for name, expected in frozen['source_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f'Changed since freeze: {name}')
    protocol = read(ROOT / 'configs/retrieval-shrinkage.json')
    parent_protocol = read(ROOT / protocol['parent_protocol'])
    parent_dir = ROOT / protocol['parent_run']
    review = read(ROOT / 'local/optimization-review-2026-10-31.json')
    for name, expected in review['evidence_sha256'].items():
        if sha(parent_dir / name) != expected:
            raise ValueError('Parent evidence changed')
    parent = read(parent_dir / 'summary.json')
    for name, expected in parent['data_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('Data changed since audited splits')
    if read(parent_dir / 'lexical_audit.json')['cross_benchmark_pairs']:
        raise ValueError('Unresolved cross-benchmark matches')
    runs = [load_run(name, parent_protocol) for name in parent_protocol['primary_runs'] + parent_protocol['sensitivity_runs']]
    for run in runs:
        if run['sha256'] != parent['run_sha256'][run['name']]:
            raise ValueError('Saved runs changed')
    items, vectors, cells = {}, {}, {}
    for benchmark in parent_protocol['benchmarks']:
        trajectories = [t for run in runs for t in run['trajectories'] if t['benchmark'] == benchmark]
        allowed = {subject_key(t['subject']) for t in trajectories}
        used = {i for t in trajectories for field in ('acquisition_item_ids', 'evaluation_item_ids') for i in t[field]}
        items[benchmark] = {r['item_id']: r['content'] for r in pq.read_table(ROOT / 'data' / benchmark / 'items.parquet').to_pylist()
                            if r['item_id'] in used}
        if set(items[benchmark]) != used:
            raise ValueError('Missing item content')
        vectors[benchmark] = {i: features(content) for i, content in items[benchmark].items()}
        subjects = {r['subject_id']: {k: str(r[k]).strip() if r[k] is not None else '' for k in SUBJECT_KEYS}
                    for r in pq.read_table(ROOT / 'data' / benchmark / 'subjects.parquet').to_pylist()}
        groups = collections.defaultdict(lambda: collections.defaultdict(list))
        for row in pq.read_table(ROOT / 'data' / benchmark / 'responses.parquet').to_pylist():
            if row['response'] is None:
                continue
            if row['response'] not in (0, 1):
                raise ValueError('Nonbinary outcome')
            key = subject_key(subjects[row['subject_id']])
            if key in allowed:
                groups[key][row['item_id']].append(row)
        if set(groups) != allowed:
            raise ValueError('Missing subject group')
        cells[benchmark] = groups
    output = ROOT / 'runs' / ('retrieval-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir()
    budgets, weights, seeds = (parent_protocol[k] for k in ('budgets', 'weights', 'seeds'))
    records, prediction_count, direct_checks = [], 0, 0
    prediction_path = output / 'predictions.jsonl.gz'
    with gzip.open(prediction_path, 'wt', encoding='utf-8', compresslevel=1) as trace:
        for run in runs:
            by_pair = collections.defaultdict(list)
            for t in run['trajectories']:
                by_pair[t['pair']].append(t)
            for pair, ts in sorted(by_pair.items()):
                first = ts[0]
                benchmark = first['benchmark']
                group = cells[benchmark][subject_key(first['subject'])]
                acquired, evaluation = set(first['acquisition_item_ids']), set(first['evaluation_item_ids'])
                if acquired & evaluation or acquired | evaluation != set(group):
                    raise ValueError('Invalid split')
                by_response = {r['response_id']: r for rows in group.values() for r in rows}
                counts = {i: (len(group[i]), sum(r['response'] for r in group[i])) for i in sorted(evaluation)}
                total = sum(v[0] for v in counts.values())
                if sorted(t['seed'] for t in ts) != seeds:
                    raise ValueError('Changed seed coverage')
                seed_curves, seed_alc = {}, {}
                for t in ts:
                    if (set(t['acquisition_item_ids']) != acquired or set(t['evaluation_item_ids']) != evaluation
                            or t['subject'] != first['subject'] or t['benchmark'] != benchmark):
                        raise ValueError('Changed pools or group')
                    observed = [by_response[i] for i in t['revealed_response_ids']]
                    if len(observed) != 31 or [r['item_id'] for r in observed] != t['acquisition_item_ids'][:31]:
                        raise ValueError('Invalid acquisition sequence')
                    seed = str(t['seed'])
                    seed_curves[seed] = {m: [] for m in METHODS}
                    saved = run['scores'][(pair, t['seed'], 'beta_1_1')]
                    evidence = [[[t['subject'], {'benchmark_id': benchmark, 'item_content': items[benchmark][r['item_id']]}],
                                 int(r['response'])] for r in observed]
                    for index, n in enumerate(budgets):
                        labels = [int(r['response']) for r in observed[:n]]
                        shuffled = list(labels)
                        rng_seed = int(hashlib.sha256(f'{pair}:{seed}:{n}:retrieval-null-v1'.encode()).hexdigest(), 16)
                        random.Random(rng_seed).shuffle(shuffled)
                        baseline = (1 + sum(labels)) / (n + 2)
                        close(baseline, saved['probabilities'][index])
                        prepared = PreparedEvidence([vectors[benchmark][r['item_id']] for r in observed[:n]]) if n > 1 else None
                        losses = {m: [] for m in METHODS}
                        for j, (item_id, (count, positives)) in enumerate(counts.items()):
                            if prepared is None:
                                candidate = null = baseline
                            else:
                                similarities = prepared.similarities(vectors[benchmark][item_id])
                                candidate = weighted_prediction(similarities, labels)
                                null = weighted_prediction(similarities, shuffled)
                            values = {'beta_1_1': baseline, 'retrieval': candidate, 'shuffled_labels': null}
                            for method, p in values.items():
                                if not math.isfinite(p) or not 0 <= p <= 1:
                                    raise ValueError('Invalid prediction')
                                losses[method].append(positives * (1-p)**2 + (count-positives) * p*p)
                            if t['seed'] == seeds[0] and j in (0, len(counts)-1):
                                target = [t['subject'], {'benchmark_id': benchmark, 'item_content': items[benchmark][item_id]}]
                                close(candidate, predict(target, evidence[:n]))
                                for method, p in values.items():
                                    close(losses[method][-1], math.fsum((p-r['response'])**2 for r in group[item_id]))
                                direct_checks += 1
                            trace.write(json.dumps({'run': run['name'], 'pair': pair, 'seed': t['seed'], 'budget': n,
                                                    'item_id': item_id, 'responses': count, 'successes': positives,
                                                    'baseline': baseline, 'retrieval': candidate, 'shuffled': null}, separators=(',', ':')) + '\n')
                            prediction_count += 1
                        for method in METHODS:
                            brier = math.fsum(losses[method]) / total
                            if method == 'beta_1_1':
                                close(brier, saved['briers'][index])
                            seed_curves[seed][method].append(brier)
                    seed_alc[seed] = {m: math.fsum(w*b for w, b in zip(weights, seed_curves[seed][m])) for m in METHODS}
                records.append({'pair': pair, 'benchmark': benchmark, 'run': run['name'], 'split_unit': run['config']['split_unit'],
                                'source_items': len(group), 'evaluation_items': len(counts), 'evaluation_responses': total,
                                'alc': {m: statistics.fmean(v[m] for v in seed_alc.values()) for m in METHODS},
                                'curves': {m: [statistics.fmean(v[m][i] for v in seed_curves.values()) for i in range(6)] for m in METHODS},
                                'seed_alc': seed_alc})
            print('Scored item-level predictions:', run['name'], flush=True)
    summaries = {}
    for design in ('primary_item', 'guarded_sensitivity'):
        rows = [r for r in records if r['run'] in parent_protocol['primary_runs']]
        if design == 'guarded_sensitivity':
            rows = [r for r in rows if r['benchmark'] in ('real_webagents', 'financebench')]
            rows += [r for r in records if r['run'] in parent_protocol['sensitivity_runs']]
        by_benchmark = {b: summarize([r for r in rows if r['benchmark'] == b], budgets, seeds) for b in cells}
        macro = {'alc': {m: statistics.fmean(v['alc'][m] for v in by_benchmark.values()) for m in METHODS},
                 'delta_vs_baseline': statistics.fmean(v['delta_vs_baseline'] for v in by_benchmark.values()),
                 'delta_vs_shuffled': statistics.fmean(v['delta_vs_shuffled'] for v in by_benchmark.values()),
                 'seed_deltas': {str(s): statistics.fmean(v['seed_deltas'][str(s)] for v in by_benchmark.values()) for s in seeds}}
        summaries[design] = {'all_pairs': summarize(rows, budgets, seeds), 'by_benchmark': by_benchmark,
                             'equal_benchmark': macro,
                             'size_80_to_1000': summarize([r for r in rows if r['source_items'] <= 1000], budgets, seeds)}
    primary = summaries['primary_item']
    checks = {'equal_pair_improves': primary['all_pairs']['delta_vs_baseline'] < 0,
              'equal_benchmark_improves': primary['equal_benchmark']['delta_vs_baseline'] < 0,
              'four_benchmarks_improve': sum(v['delta_vs_baseline'] < 0 for v in primary['by_benchmark'].values()) >= 4,
              'guarded_direction_preserved': summaries['guarded_sensitivity']['equal_benchmark']['delta_vs_baseline'] < 0,
              'all_primary_seeds_improve': all(v < 0 for v in primary['equal_benchmark']['seed_deltas'].values()),
              'beats_shuffled_control': all(s['equal_benchmark']['delta_vs_shuffled'] < 0 for s in summaries.values())}
    result = {'status': 'COMPLETED_ITEM_LEVEL_DEVELOPMENT_SCREEN', 'created_utc': datetime.now(timezone.utc).isoformat(),
              'seconds': time.perf_counter()-started, 'python': sys.version, 'pyarrow': pyarrow.__version__,
              'gpu_used': False, 'network_used': False, 'source_sha256': frozen['source_sha256'],
              'data_sha256': parent['data_sha256'], 'parent_summary_sha256': sha(parent_dir/'summary.json'),
              'prediction_records': prediction_count, 'public_predict_and_direct_response_checks': direct_checks,
              'prediction_sha256': sha(prediction_path), 'summaries': summaries,
              'screening_checks': checks, 'screen_passed': all(checks.values()), 'limitations': protocol['limitations']}
    for name, value in (('pairs.json', records), ('summary.json', result), ('protocol.json', protocol)):
        (output / name).write_text(json.dumps(value, indent=2), encoding='utf-8')
    brief = {'output': str(output), 'screen_passed': result['screen_passed'], 'screening_checks': checks,
             'seconds': result['seconds'], 'prediction_records': prediction_count,
             'equal_benchmark': primary['equal_benchmark'], 'all_pairs': primary['all_pairs']}
    (ROOT / 'local/retrieval-shrinkage-output.json').write_text(json.dumps(brief, indent=2), encoding='utf-8')
    print(json.dumps(brief, indent=2))


if __name__ == '__main__':
    main()
