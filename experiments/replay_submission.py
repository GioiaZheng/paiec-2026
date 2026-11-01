"""Replay verified public-data checkpoints through extracted submission archives.

Prepare the fixture where PyArrow is installed; run it on Linux with the
unchanged starting-kit worker helper. This is an integration check, not a new
performance experiment or a replica of the private platform's sampling.
"""
import argparse
import collections
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
METHODS = {'empirical_mean': 'upstream/dist/empirical_mean.zip',
           'beta_1_1': 'dist/shrinkage.zip'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def prepare(args):
    sys.path.insert(0, str(ROOT/'.deps'))
    import pyarrow.parquet as pq
    candidates = collections.defaultdict(list)
    provenance, scores, manifest, predictor_hashes = {}, {}, {}, {}
    for run in args.runs:
        config = read(run/'config.json')
        if config['split_unit'] != 'item':
            raise ValueError('Use item splits for the runtime fixture')
        if read(run/'independent_verification.json')['status'] != 'PASS':
            raise ValueError('Source run has not passed independent verification')
        source_hashes = {name.replace('\\', '/'): digest for name, digest in config['source_sha256'].items()}
        for name in ('shrinkage/model.py', 'upstream/empirical_mean/model.py'):
            digest = source_hashes[name]
            if sha(ROOT/name) != digest or predictor_hashes.get(name, digest) != digest:
                raise ValueError('Predictor changed since the saved experiment')
            predictor_hashes[name] = digest
        for t in read(run/'trajectories.json'):
            if t['seed'] == args.seed:
                candidates[t['benchmark']].append(t)
        for s in read(run/'scores.json'):
            if s['seed'] == args.seed and s['method'] in METHODS:
                key = (s['pair'], s['method'])
                if key in scores:
                    raise ValueError('Duplicate pair/method across source runs')
                scores[key] = s
        manifest.update(read(run/'manifest.json'))
        provenance[run.name] = {name: sha(run/name) for name in (
            'config.json', 'scores.json', 'trajectories.json', 'independent_verification.json')}
    for name, entry in manifest.items():
        if sha(ROOT/name) != entry['sha256']:
            raise ValueError(f'Data hash mismatch: {name}')
    # Exercise repeated-input reuse using response counts only, never outcome
    # values or performance metrics. Private draw/balancing state is unavailable.
    def selection_key(t):
        repeated = scores[t['pair'], 'empirical_mean']['evaluation_responses'] > len(t['evaluation_item_ids'])
        return (not repeated, t['pair'])
    queues = {b: collections.deque(sorted(ts, key=selection_key))
              for b, ts in sorted(candidates.items())}
    selected, total = [], 0
    while any(queues.values()):
        for queue in queues.values():
            if queue:
                t = queue.popleft()
                size = len(t['acquisition_item_ids']) + len(t['evaluation_item_ids'])
                if 80 <= size <= args.max_items - total:
                    selected.append(t)
                    total += size
    if len({t['benchmark'] for t in selected}) < 2:
        raise ValueError('The replay must cover multiple benchmarks')
    tables = {}
    for benchmark in {t['benchmark'] for t in selected}:
        folder = ROOT/'data'/benchmark
        items = {r['item_id']: r for r in pq.read_table(folder/'items.parquet').to_pylist()}
        subjects = {r['subject_id']: r for r in pq.read_table(folder/'subjects.parquet').to_pylist()}
        responses = pq.read_table(folder/'responses.parquet').to_pylist()
        tables[benchmark] = items, subjects, responses
    fixture = {'status': 'LOCAL_RUNTIME_FIXTURE', 'seed': args.seed,
               'source_items': total, 'source_run_sha256': provenance,
               'data_manifest': manifest, 'groups': [],
               'budgets': [0, 1, 3, 7, 15, 31], 'weights': [.1, .2, .2, .2, .2, .1],
               'selection': 'Round-robin benchmarks; prefer groups with repeated evaluation response rows, then pair hash; skip whole groups that do not fit. Uses counts only, not outcomes or performance metrics.',
               'predictor_sha256': predictor_hashes,
               'archive_sha256': {m: sha(ROOT/p) for m, p in METHODS.items()}}
    for t in selected:
        items, subjects, responses = tables[t['benchmark']]
        def subject(row):
            return {k: str(row[k]).strip() if row[k] is not None else '' for k in t['subject']}
        rows = [r for r in responses if subject(subjects[r['subject_id']]) == t['subject']
                and r['response'] is not None]
        response_map = {r['response_id']: r for r in rows}
        alias = 'local_benchmark_' + hashlib.sha256(t['benchmark'].encode()).hexdigest()[:12]
        def input_for(row):
            item = items[row['item_id']]
            result = [t['subject'], {'item_content': item['content'],
                      'item_features': (item['item_features'] or '').strip(),
                      'interactors': (row['interactors'] or '').strip(), 'benchmark_id': alias}]
            if not all(isinstance(v, str) for part in result for v in part.values()):
                raise ValueError('Interface values must be strings')
            return result
        acquired = set(t['acquisition_item_ids'])
        evaluation = set(t['evaluation_item_ids'])
        if acquired & evaluation:
            raise ValueError('Overlapping pools')
        revealed = [response_map[rid] for rid in t['revealed_response_ids']]
        if len(revealed) != 31 or len({r['item_id'] for r in revealed}) != 31:
            raise ValueError('Expected 31 distinct acquired items')
        if any(r['item_id'] not in acquired for r in revealed):
            raise ValueError('Acquired response outside acquisition pool')
        evaluation_rows = sorted((r for r in rows if r['item_id'] in evaluation),
                                 key=lambda r: (r['item_id'], r['response_id']))
        group = {'pair': t['pair'], 'benchmark': t['benchmark'],
                 'source_items': len(acquired) + len(evaluation),
                 'labels': [[input_for(r), int(r['response'])] for r in revealed],
                 'rows': [{'input': input_for(r), 'label': int(r['response']),
                           'item_id': r['item_id']} for r in evaluation_rows],
                 'expected': {m: scores[t['pair'], m] for m in METHODS}}
        if any(len(evaluation_rows) != s['evaluation_responses'] for s in group['expected'].values()):
            raise ValueError('Evaluation response coverage mismatch')
        fixture['groups'].append(group)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    unique_inputs = {json.dumps(r['input'], sort_keys=True) for g in fixture['groups'] for r in g['rows']}
    if len(unique_inputs) == sum(len(g['rows']) for g in fixture['groups']):
        raise ValueError('The integration fixture must exercise repeated-input reuse')
    write(args.output, fixture)
    print(json.dumps({'fixture': str(args.output), 'groups': len(selected), 'source_items': total,
                      'benchmarks': sorted({t['benchmark'] for t in selected})}))


def replay(args):
    if sys.platform == 'win32':
        raise RuntimeError('The unchanged official worker helper requires POSIX; use Linux/WSL')
    fixture = read(args.fixture)
    sys.path.insert(0, str(args.starter_kit.resolve()/'tools'))
    from prediction_workers import write_parallel_predictions
    out = ROOT/'runs'/('replay-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    groups = fixture['groups']
    rows = [(g, row) for g in groups for row in g['rows']]
    pairs = [{'model_id': 'local_subject_'+g['pair'][:12], 'item_id': r['item_id']} for g, r in rows]
    inputs = [r['input'] for _, r in rows]
    results, logs = [], []
    def probability(value):
        p = float(value)
        if not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError('Invalid probability')
        return p
    for method, archive_name in METHODS.items():
        archive = ROOT/archive_name
        if sha(archive) != fixture['archive_sha256'][method]:
            raise ValueError('Submission archive changed after fixture preparation')
        curves = collections.defaultdict(list)
        with tempfile.TemporaryDirectory(prefix='archive-', dir=out) as directory:
            with ZipFile(archive) as bundle:
                for name in bundle.namelist():
                    if Path(name).is_absolute() or '..' in Path(name).parts or '\\' in name:
                        raise ValueError('Unsafe archive member')
                bundle.extractall(directory)
            code_hash = sha(Path(directory)/'model.py')
            source_name = 'shrinkage/model.py' if method == 'beta_1_1' else 'upstream/empirical_mean/model.py'
            if code_hash != fixture['predictor_sha256'][source_name]:
                raise ValueError('Extracted predictor differs from the evaluated source')
            for index, budget in enumerate(fixture['budgets']):
                # Every group contributes its current prefix, including groups
                # unrelated to the prediction target. No future labels are sent.
                labels = [label for g in reversed(groups) for label in g['labels'][:budget]]
                output = out/f'{method}-{budget}.csv'
                stats = {}
                start = time.monotonic()
                write_parallel_predictions(Path(directory)/'model.py', pairs, inputs, labels, output,
                    concurrency=args.concurrency, deadline=start+300, per_call_timeout=30,
                    log=logs.append, validate_score=probability,
                    worker_env={'PREDICTIVE_EVAL_LOCAL_SMOKE_TEST': '1'}, stats=stats)
                elapsed = time.monotonic()-start
                if stats['prediction_reuse_count'] <= 0:
                    raise ValueError('Repeated-input reuse was not exercised')
                with output.open(newline='', encoding='utf-8') as handle:
                    predictions = list(csv.DictReader(handle))
                if len(predictions) != len(rows):
                    raise ValueError('Incomplete prediction output')
                errors = collections.defaultdict(list)
                for expected_pair, (group, row), actual in zip(pairs, rows, predictions):
                    if any(actual[k] != expected_pair[k] for k in ('model_id', 'item_id')):
                        raise ValueError('Prediction output order changed')
                    p = probability(actual['predicted_probability'])
                    expected = group['expected'][method]['probabilities'][index]
                    if not math.isclose(p, expected, rel_tol=0, abs_tol=1e-12):
                        raise ValueError('Archive prediction differs from the verified pilot')
                    errors[group['pair']].append((p-row['label'])**2)
                for group in groups:
                    brier = statistics.fmean(errors[group['pair']])
                    if not math.isclose(brier, group['expected'][method]['briers'][index], rel_tol=0, abs_tol=1e-12):
                        raise ValueError('Row-wise Brier differs from the verified pilot')
                    curves[group['pair']].append(brier)
                results.append({'method': method, 'budget': budget, 'mixed_labels': len(labels),
                                'response_rows': len(rows), 'seconds': elapsed, **stats})
                print(f'{method} budget={budget}: PASS, {stats}, {elapsed:.2f}s', flush=True)
        for group in groups:
            alc = sum(w*b for w, b in zip(fixture['weights'], curves[group['pair']]))
            if not math.isclose(alc, group['expected'][method]['alc'], rel_tol=0, abs_tol=1e-12):
                raise ValueError('ALC differs from the verified pilot')
    evidence = {'status': 'PASS', 'kind': 'PUBLIC_DATA_ARCHIVE_REPLAY', 'official_submission': False,
                'hosted_image_tested': False, 'platform': platform.platform(), 'python': sys.version,
                'concurrency': args.concurrency, 'groups': len(groups), 'source_items': fixture['source_items'],
                'benchmarks': sorted({g['benchmark'] for g in groups}),
                'fixture_sha256': sha(args.fixture), 'archive_sha256': fixture['archive_sha256'],
                'source_run_sha256': fixture['source_run_sha256'], 'selection': fixture['selection'],
                'source_sha256': {'replay_submission.py': sha(Path(__file__)),
                    'starting_kit/tools/prediction_workers.py': sha(args.starter_kit/'tools/prediction_workers.py')},
                'checks': ['All row probabilities match saved pilot', 'All per-group Brier/ALC match saved pilot',
                           'Mixed-group evidence at all six budgets', 'Fresh official workers per checkpoint',
                           'Repeated-input reuse', 'Extracted archive matches evaluated predictor'],
                'limitations': ['Integration fixture only; neither new validation data nor official feedback.',
                    'Does not simulate private group selection, streaming acquisition or hosted sandbox/resource allocation.'],
                'checkpoints': results}
    write(out/'evidence.json', evidence)
    (out/'workers.log').write_text('\n'.join(logs)+'\n', encoding='utf-8')
    print(f'Evidence: {out}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('runs', type=Path, nargs='+')
    prep.add_argument('--seed', type=int, default=20261016)
    prep.add_argument('--max-items', type=int, default=1000)
    prep.add_argument('--output', type=Path, default=ROOT/'local/runtime-fixture.json')
    run = commands.add_parser('run')
    run.add_argument('--fixture', type=Path, default=ROOT/'local/runtime-fixture.json')
    run.add_argument('--starter-kit', type=Path, default=ROOT/'local/official/starting_kit')
    run.add_argument('--concurrency', type=int, choices=range(1, 17), default=4)
    args = parser.parse_args()
    if args.command == 'prepare' and not 80 <= args.max_items <= 1000:
        parser.error('--max-items must be between 80 and 1000')
    prepare(args) if args.command == 'prepare' else replay(args)


if __name__ == '__main__':
    main()
