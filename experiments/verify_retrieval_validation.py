"""Independently rescore every saved item prediction against original response rows."""
import collections
import gzip
import itertools
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.deps'))
import pyarrow.parquet as pq
from diagnose_shrinkage import SUBJECT_KEYS
from evaluate_transferred_prior import close, read, sha, subject_key

METHOD_FIELDS = {'beta_1_1': 'baseline', 'retrieval': 'retrieval', 'shuffled_labels': 'shuffled'}
BUDGETS = [0, 1, 3, 7, 15, 31]
WEIGHTS = [.1, .2, .2, .2, .2, .1]


def main():
    output = Path(read(ROOT / 'local/retrieval-validation-output.json')['output'])
    summary = read(output / 'summary.json')
    for name, expected in summary['data_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('Data changed before independent verification')
    if sha(output / 'predictions.jsonl.gz') != summary['prediction_sha256']:
        raise ValueError('Prediction archive changed')
    records = read(output / 'pairs.json')
    trajectories = {}
    for run in sorted({r['run'] for r in records}):
        for t in read(ROOT / run / 'trajectories.json'):
            trajectories[(run, t['pair'], t['seed'])] = t
    cells, response_index = {}, {}
    for b in sorted({r['benchmark'] for r in records}):
        subjects = {r['subject_id']: subject_key({k: str(r[k]).strip() if r[k] is not None else '' for k in SUBJECT_KEYS})
                    for r in pq.read_table(ROOT / 'data' / b / 'subjects.parquet').to_pylist()}
        groups = collections.defaultdict(lambda: collections.defaultdict(list))
        response_index[b] = {}
        for row in pq.read_table(ROOT / 'data' / b / 'responses.parquet').to_pylist():
            if row['response'] is not None:
                groups[subjects[row['subject_id']]][row['item_id']].append(row['response'])
                response_index[b][row['response_id']] = row
        cells[b] = groups
    curves, seen_chunks, diagnostics = {}, set(), {}
    checked_predictions = 0
    with gzip.open(output / 'predictions.jsonl.gz', 'rt', encoding='utf-8') as stream:
        decoded = (json.loads(line) for line in stream)
        key = lambda r: (r['run'], r['pair'], r['seed'], r['budget'])
        for chunk, rows in itertools.groupby(decoded, key):
            if chunk in seen_chunks:
                raise ValueError('Repeated noncontiguous prediction chunk')
            seen_chunks.add(chunk)
            run, pair, seed, n = chunk
            t = trajectories[(run, pair, seed)]
            b = t['benchmark']
            if n not in BUDGETS:
                raise ValueError('Unexpected label budget')
            outcomes = cells[b][subject_key(t['subject'])]
            labels = [response_index[b][i]['response'] for i in t['revealed_response_ids'][:n]]
            baseline = (1 + sum(labels)) / (n + 2)
            allowed_items = set(t['evaluation_item_ids'])
            seen_items = set()
            errors = {m: [] for m in METHOD_FIELDS}
            alignment, squared_shift = [], []
            for r in rows:
                item_id = r['item_id']
                if item_id in seen_items or item_id not in allowed_items:
                    raise ValueError('Duplicate item or prediction outside evaluation pool')
                seen_items.add(item_id)
                actual = outcomes[item_id]
                if r['responses'] != len(actual) or r['successes'] != sum(actual):
                    raise ValueError('Cached outcome counts disagree with original rows')
                close(r['baseline'], baseline)
                for method, field in METHOD_FIELDS.items():
                    p = r[field]
                    if not math.isfinite(p) or not 0 <= p <= 1:
                        raise ValueError('Invalid probability')
                    if n in (0, 1):
                        close(p, baseline)
                    errors[method].extend((p-y)**2 for y in actual)
                change = r['retrieval'] - baseline
                alignment.extend(2 * change * (baseline-y) for y in actual)
                squared_shift.extend(change*change for _ in actual)
                checked_predictions += 1
            if seen_items != allowed_items:
                raise ValueError('Missing evaluation predictions')
            index = (run, pair, seed)
            curves.setdefault(index, {})[n] = {m: statistics.fmean(v) for m, v in errors.items()}
            diagnostics[chunk] = {'alignment_term': statistics.fmean(alignment),
                                  'squared_shift_term': statistics.fmean(squared_shift)}
            close(sum(diagnostics[chunk].values()), curves[index][n]['retrieval'] - curves[index][n]['beta_1_1'])
    if checked_predictions != summary['prediction_records'] or len(seen_chunks) != len(trajectories)*len(BUDGETS):
        raise ValueError('Incomplete prediction coverage')
    checked_aggregates = 0
    for r in records:
        seeds = [int(s) for s in r['seed_alc']]
        for method in METHOD_FIELDS:
            seed_alc = []
            for seed in seeds:
                points = curves[(r['run'], r['pair'], seed)]
                alc = math.fsum(w*points[n][method] for w, n in zip(WEIGHTS, BUDGETS))
                close(alc, r['seed_alc'][str(seed)][method])
                seed_alc.append(alc)
                checked_aggregates += 1
            close(statistics.fmean(seed_alc), r['alc'][method])
            for i, n in enumerate(BUDGETS):
                close(statistics.fmean(curves[(r['run'], r['pair'], s)][n][method] for s in seeds), r['curves'][method][i])
    protocol = summary['evaluation_design']
    for design, saved in summary['summaries'].items():
        selected = [r for r in records if r['run'] in protocol['primary_runs']]
        if design == 'guarded_sensitivity':
            selected = [r for r in selected if r['benchmark'] in ('real_webagents', 'financebench')]
            selected += [r for r in records if r['run'] in protocol['sensitivity_runs']]
        for method in METHOD_FIELDS:
            close(statistics.fmean(r['alc'][method] for r in selected), saved['all_pairs']['alc'][method])
            per_benchmark = []
            for b, row in saved['by_benchmark'].items():
                mean = statistics.fmean(r['alc'][method] for r in selected if r['benchmark'] == b)
                close(mean, row['alc'][method])
                per_benchmark.append(mean)
            close(statistics.fmean(per_benchmark), saved['equal_benchmark']['alc'][method])
    diagnostic_rows = []
    for r in records:
        seeds = [int(s) for s in r['seed_alc']]
        diagnostic_rows.append({'run': r['run'], 'pair': r['pair'], 'benchmark': r['benchmark'],
                                'alc_decomposition': {term: statistics.fmean(
                                    sum(w*diagnostics[(r['run'], r['pair'], s, n)][term] for w, n in zip(WEIGHTS, BUDGETS))
                                    for s in seeds) for term in ('alignment_term', 'squared_shift_term')}})
    (output / 'retrieval_diagnostics.json').write_text(json.dumps({
        'interpretation': 'Observed Brier change equals 2*delta*(baseline-y) + delta^2, where delta=retrieval-baseline. This is an algebraic diagnostic, not an acquisition-variance or causal decomposition.',
        'pairs': diagnostic_rows}, indent=2), encoding='utf-8')
    evidence = {'status': 'PASS', 'item_prediction_records': checked_predictions,
                'budget_chunks': len(seen_chunks), 'pair_seed_method_alcs': checked_aggregates,
                'verification': 'Read original response rows; checked exact evaluation-item coverage, repeated responses, zero/one-label invariants, item-wise Brier and saved aggregate scores.',
                'source_sha256': sha(Path(__file__)), 'summary_sha256': sha(output / 'summary.json'),
                'prediction_sha256': sha(output / 'predictions.jsonl.gz')}
    (output / 'independent_verification.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
