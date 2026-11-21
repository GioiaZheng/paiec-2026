"""Post-review diagnostics; no fitted predictor or new validation dataset."""
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import statistics as st

HERE = Path(__file__).resolve().parent


def percentile(xs, p):
    a = sorted(xs)
    x = (len(a)-1)*p
    lo, hi = math.floor(x), math.ceil(x)
    return a[lo] + (x-lo)*(a[hi]-a[lo])


def interval(xs):
    return [percentile(xs, .025), percentile(xs, .975)]


def bootstrap(groups, rng, reps):
    """Fixed-count stratified pairs and whole panels; ratio mean for unequal panels."""
    panels = [groups[b] for b in sorted(groups)]
    flat = [x for g in panels for x in g]
    by_benchmark = {}
    for b, g in sorted(groups.items()):
        draws = [st.fmean(rng.choices(g, k=len(g))) for _ in range(reps)]
        by_benchmark[b] = {'pairs': len(g), 'delta': st.fmean(g), 'interval': interval(draws)}
    stratified = [math.fsum(math.fsum(rng.choices(g, k=len(g))) for g in panels)/len(flat) for _ in range(reps)]
    panel_sums = [(math.fsum(g), len(g)) for g in panels]
    clusters = []
    for _ in range(reps):
        sample = rng.choices(panel_sums, k=len(panel_sums))
        clusters.append(math.fsum(x[0] for x in sample)/sum(x[1] for x in sample))
    return {'pairs': len(flat), 'benchmarks': len(groups), 'delta': st.fmean(flat),
            'pair_interval': interval(stratified), 'benchmark_interval': interval(clusters),
            'by_benchmark': by_benchmark}


def calibration(cases):
    """Each (prediction, outcome fraction) case has equal mass, not equal row count."""
    groups = defaultdict(list)
    for p, q in cases:
        groups[p].append(q)
    qbar = st.fmean(q for _, q in cases)
    reliability = resolution = 0.
    points = []
    for p, qs in sorted(groups.items()):
        w, q = len(qs)/len(cases), st.fmean(qs)
        reliability += w*(p-q)**2
        resolution += w*(q-qbar)**2
        points.append({'p': p, 'observed': q, 'weight': w, 'pair_seed_cases': len(qs)})
    uncertainty = qbar*(1-qbar)
    direct = st.fmean((1-q)*p*p + q*(1-p)**2 for p, q in cases)
    assert math.isclose(direct, reliability-resolution+uncertainty, rel_tol=0, abs_tol=1e-12)
    return {'brier': direct, 'reliability': reliability, 'resolution': resolution,
            'uncertainty': uncertainty, 'points': points}


def reweight(rows):
    low = [r for r in rows if r['evaluation_rate'] < .1]
    high = [r for r in rows if r['evaluation_rate'] >= .1]
    result = {'pairs': len(rows), 'low_pairs': len(low), 'low_share': len(low)/len(rows)}
    for kind in ['observed_alc', 'expected_alc']:
        def delta(g):
            return st.fmean(r[kind]['beta_1_1']-r[kind]['empirical_mean'] for r in g)
        lo, hi = delta(low), delta(high)
        result[kind] = {'low_delta': lo, 'other_delta': hi,
                        'zero_crossing': -hi/(lo-hi) if lo != hi else None,
                        'mixtures': [{'low_share': f, 'delta': f*lo+(1-f)*hi} for f in [0., .25, .5, .75, 1.]]}
    return result


def main():
    cfg = json.loads((HERE/'config.json').read_text())
    data = json.loads((HERE/'inputs.json').read_text())
    assert data['status'] == 'VERIFIED_FROM_PINNED_RESPONSE_TABLES'
    rows = data['records']
    primary = [r for r in rows if r['run'] in cfg['primary_runs']]
    weaker = [r for r in rows if r['benchmark'] != 'bertaqa' or r['split'] == 'source']
    assert len(primary) == 145 and len(weaker) == 161
    rng = random.Random(cfg['seed'])
    out = {'status': cfg['status'], 'predictor_changed': False, 'bootstrap_replicates': cfg['bootstrap_replicates']}
    for label, population, candidate, reference in [('baseline', primary, 'beta_1_1', 'empirical_mean'),
                                                    ('weaker', weaker, 'beta_0_5_0_5', 'beta_1_1')]:
        gs = defaultdict(list)
        for r in population:
            gs[r['benchmark']].append(r['observed_alc'][candidate]-r['observed_alc'][reference])
        out[label] = bootstrap(gs, rng, cfg['bootstrap_replicates'])
    coding = [r for r in primary if r['benchmark'] in ('multi_swebench', 'researchcodebench')]
    compatible = [r for r in coding if 80 <= r['source_items'] <= 1000]
    assert len(coding) == 113 and len(compatible) == 85
    out['compatible_coding'] = {k: {m: st.fmean(r[k][m] for r in compatible) for m in ['empirical_mean', 'beta_1_1']} for k in ['observed_alc', 'expected_alc']}
    out['compatible_coding']['per_seed'] = {s: {m: st.fmean(next(t for t in r['seeds'] if t['seed'] == s)['alc'][m] for r in compatible) for m in ['empirical_mean', 'beta_1_1']} for s in [20261016, 20261017, 20261018]}
    out['low_success_sensitivity'] = {'all_coding': reweight(coding), 'compatible_coding': reweight(compatible)}
    reversals = []
    for r in coding:
        observed = r['observed_alc']['beta_1_1']-r['observed_alc']['empirical_mean']
        expected = r['expected_alc']['beta_1_1']-r['expected_alc']['empirical_mean']
        if observed*expected < 0:
            reversals.append({'benchmark': r['benchmark'], 'evaluation_rate': r['evaluation_rate'],
                              'observed_delta': observed, 'expected_delta': expected})
    assert len(reversals) == 15
    out['sign_reversals'] = {'count': len(reversals), 'minimum_rate': min(r['evaluation_rate'] for r in reversals),
                             'maximum_rate': max(r['evaluation_rate'] for r in reversals),
                             'observed_gain_expected_loss': sum(r['observed_delta'] < 0 for r in reversals),
                             'observed_loss_expected_gain': sum(r['observed_delta'] > 0 for r in reversals),
                             'bins': [{'range': [lo, hi], 'count': sum(lo <= r['evaluation_rate'] < hi for r in reversals)}
                                      for lo, hi in [(0,.1),(.1,.2),(.2,.4),(.4,.6),(.6,1.000001)]],
                             'groups': reversals}
    out['calibration'] = {}
    for b in ['all'] + sorted({r['benchmark'] for r in primary}):
        pop = primary if b == 'all' else [r for r in primary if r['benchmark'] == b]
        out['calibration'][b] = {}
        for budget in (1, 3):
            index = cfg['budgets'].index(budget)
            methods = {}
            for m in ('empirical_mean', 'beta_1_1'):
                cases = [(s['probabilities'][m][index], r['evaluation_rate']) for r in pop for s in r['seeds']]
                methods[m] = calibration(cases)
                saved = st.fmean(s['briers'][m][index] for r in pop for s in r['seeds'])
                assert math.isclose(saved, methods[m]['brier'], rel_tol=0, abs_tol=1e-12)
            # Both mappings are injective functions of the same success count;
            # category membership and resolution must therefore be unchanged.
            assert math.isclose(methods['empirical_mean']['resolution'], methods['beta_1_1']['resolution'], abs_tol=1e-12)
            out['calibration'][b][budget] = methods
    out['source_sha256'] = {n: hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in ['inputs.json', 'config.json', 'analyze.py', 'collect_inputs.py']}
    (HERE/'results.json').write_text(json.dumps(out, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: v for k, v in out.items() if k not in ['calibration','source_sha256']}, indent=2))


if __name__ == '__main__':
    main()
