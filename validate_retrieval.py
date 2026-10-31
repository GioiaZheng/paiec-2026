"""Item-wise paired lexical retrieval screen on previously inspected data."""
import argparse
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('item_run')
    parser.add_argument('guarded_run')
    args = parser.parse_args()
    started = time.perf_counter()
    frozen = read(ROOT / 'local/retrieval-validation-freeze.json')
    for name, expected in frozen['source_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f'Changed after validation freeze: {name}')
    protocol = read(ROOT / 'configs/retrieval-validation.json')
    for name, expected in protocol['metadata_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('Metadata changed after selection')
    if read(ROOT / 'local/truthfulqa-label-blind-audit.json')['cross_benchmark_matches']:
        raise ValueError('Cross-benchmark overlap requires review')
    runs = [load_run(name, protocol) for name in (args.item_run, args.guarded_run)]
    for run, split in zip(runs, ('item', 'near')):
        if run['config']['split_unit'] != split or {t['benchmark'] for t in run['trajectories']} != {'truthfulqa_mc'}:
            raise ValueError('Unexpected validation benchmark or split')
        if run['config']['protocol_sha256'] != sha(ROOT / 'configs/retrieval-validation.json'):
            raise ValueError('Baseline pools were not built with the frozen validation protocol')
    parent_protocol = dict(protocol, primary_runs=[args.item_run], sensitivity_runs=[args.guarded_run])
    manifest = read(ROOT / args.item_run / 'manifest.json')
    parent = {'data_sha256': {name.replace(chr(92), '/'): value['sha256'] for name, value in manifest.items()}}
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
    output = ROOT / 'runs' / ('retrieval-validation-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
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
    for design, run_name in (('primary_item', args.item_run), ('guarded_sensitivity', args.guarded_run)):
        rows = [r for r in records if r['run'] == run_name]
        aggregate = summarize(rows, budgets, seeds)
        summaries[design] = {'all_pairs': aggregate, 'by_benchmark': {'truthfulqa_mc': aggregate},
                             'equal_benchmark': {k: aggregate[k] for k in ('alc','delta_vs_baseline','delta_vs_shuffled','seed_deltas')}}
    primary = summaries['primary_item']['all_pairs']
    guarded = summaries['guarded_sensitivity']['all_pairs']
    checks = {'primary_improves': primary['delta_vs_baseline'] < 0,
              'guarded_improves': guarded['delta_vs_baseline'] < 0,
              'all_primary_seeds_improve': all(d < 0 for d in primary['seed_deltas'].values()),
              'all_guarded_seeds_improve': all(d < 0 for d in guarded['seed_deltas'].values()),
              'beats_shuffled_control': primary['delta_vs_shuffled'] < 0 and guarded['delta_vs_shuffled'] < 0}
    result = {'status': 'COMPLETED_FROZEN_PUBLIC_VALIDATION', 'created_utc': datetime.now(timezone.utc).isoformat(),
              'seconds': time.perf_counter()-started, 'python': sys.version, 'pyarrow': pyarrow.__version__,
              'source_sha256': frozen['source_sha256'], 'data_sha256': parent['data_sha256'],
              'evaluation_design': {'primary_runs': [args.item_run], 'sensitivity_runs': [args.guarded_run]},
              'input_sha256': {r['name']: r['sha256'] for r in runs},
              'gpu_used': False, 'network_used': False,
              'prediction_records': prediction_count, 'public_predict_and_direct_response_checks': direct_checks,
              'prediction_sha256': sha(prediction_path), 'summaries': summaries,
              'validation_checks': checks, 'validation_passed': all(checks.values()), 'limitations': protocol['limitations']}
    for name, value in (('pairs.json', records), ('summary.json', result), ('protocol.json', protocol)):
        (output/name).write_text(json.dumps(value,indent=2),encoding='utf-8')
    brief = {'output': str(output), 'validation_passed': result['validation_passed'], 'validation_checks': checks,
             'seconds': result['seconds'], 'prediction_records': prediction_count,
             'primary': primary, 'guarded': guarded}
    (ROOT / 'local/retrieval-validation-output.json').write_text(json.dumps(brief,indent=2),encoding='utf-8')
    print(json.dumps(brief,indent=2))


if __name__ == '__main__':
    main()
