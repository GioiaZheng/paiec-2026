"""Verify saved comparisons against pinned response tables; export group summaries."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics as st
import sys

HERE = Path(__file__).resolve().parent
KEYS = ('normalized_name', 'provider', 'release_date', 'access_date', 'harness',
        'harness_version', 'reasoning_effort', 'subject_features_extra')
ALPHAS = {'empirical_mean': 0., 'beta_1_1': 1., 'beta_0_5_0_5': .5}


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def close(a, b):
    if not math.isclose(a, b, rel_tol=0, abs_tol=1e-12):
        raise AssertionError((a, b))


def subject(s):
    return json.dumps({k: str(s[k]).strip() if s[k] is not None else '' for k in KEYS}, sort_keys=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    args = parser.parse_args()
    root = args.project.resolve()
    sys.path.insert(0, str(root / '.deps'))
    import pyarrow.parquet as pq
    cfg = read(HERE / 'config.json')
    sources, cache, allrows = {}, {}, []
    checked = 0

    def tracked(path):
        sources[path.relative_to(root).as_posix()] = sha(path)
        return read(path)

    # These saved summaries provide an independent check of both observed and
    # exact ALC values, including the previously implemented weaker prior.
    prior = {}
    for i, (split, names) in enumerate([
        ('near', ['multi_swebench', 'researchcodebench']), ('source', ['bertaqa']),
        ('item', ['real_webagents']), ('item', ['financebench'])]):
        path = root / 'runs/weaker-20261016T113721519313Z' / f'pairs_{i}.json'
        for r in tracked(path):
            assert r['benchmark'] in names
            prior[r['pair'], split] = r
    for i, split in [(0, 'near'), (2, 'item'), (4, 'item')]:
        path = root / 'runs/diagnosis-20261016T103151664089Z' / f'pairs_{i}.json'
        for r in tracked(path):
            old = prior.get((r['pair'], split))
            if old:
                for m in ('empirical_mean', 'beta_1_1'):
                    close(old['observed_alc'][m], r['observed_alc'][m])
                    close(old['expected_alc'][m], r['expected_alc'][m])
            else:
                prior[r['pair'], split] = r

    for name in cfg['primary_runs'] + cfg['other_runs']:
        run = root / 'runs' / name
        rc = tracked(run / 'config.json')
        assert rc['budgets'] == cfg['budgets'] and rc['weights'] == cfg['weights']
        assert tracked(run / 'independent_verification.json')['status'] == 'PASS'
        for rel, meta in tracked(run / 'manifest.json').items():
            path = root / rel.replace('\\', '/')
            digest = sha(path)
            assert digest == meta['sha256'], rel
            sources[path.relative_to(root).as_posix()] = digest
        ts = tracked(run / 'trajectories.json')
        scores = {(s['pair'], s['seed'], s['method']): s for s in tracked(run / 'scores.json')}
        bypair = defaultdict(list)
        for t in ts:
            bypair[t['pair']].append(t)
        for pair, trajectories in sorted(bypair.items()):
            first = trajectories[0]
            b = first['benchmark']
            if b not in cache:
                subjects = {s['subject_id']: subject(s) for s in pq.read_table(root / 'data' / b / 'subjects.parquet').to_pylist()}
                groups, response_ids = defaultdict(lambda: defaultdict(list)), {}
                for r in pq.read_table(root / 'data' / b / 'responses.parquet', columns=['response_id', 'subject_id', 'item_id', 'response']).to_pylist():
                    if r['response'] is None:
                        continue
                    assert r['response'] in (0, 1)
                    key = subjects[r['subject_id']]
                    groups[key][r['item_id']].append(r['response'])
                    assert r['response_id'] not in response_ids
                    response_ids[r['response_id']] = (key, r['item_id'], r['response'])
                cache[b] = groups, response_ids
            groups, ids = cache[b]
            key = subject(first['subject'])
            cells = groups[key]
            acquisition, evaluation = set(first['acquisition_item_ids']), set(first['evaluation_item_ids'])
            assert not acquisition & evaluation and acquisition | evaluation == set(cells)
            assert sorted(t['seed'] for t in trajectories) == sorted(rc['seeds'])
            ys = [y for i in sorted(evaluation) for y in cells[i]]
            q = st.fmean(ys)
            mus = [st.fmean(cells[i]) for i in sorted(acquisition)]
            N, mu = len(mus), st.fmean(mus)
            v = st.fmean((x-mu)**2 for x in mus)
            u = st.fmean(x*(1-x) for x in mus)
            row = {'pair': pair, 'benchmark': b, 'split': rc['split_unit'], 'run': name,
                   'source_items': len(cells), 'evaluation_rate': q, 'evaluation_responses': len(ys),
                   'observed_alc': {}, 'expected_alc': {}, 'seeds': []}
            for t in sorted(trajectories, key=lambda x: x['seed']):
                assert set(t['acquisition_item_ids']) == acquisition and set(t['evaluation_item_ids']) == evaluation
                labels = [ids[i] for i in t['revealed_response_ids']]
                assert len(labels) == 31 and len({x[1] for x in labels}) == 31
                assert all(x[0] == key and x[1] in acquisition for x in labels)
                seed = {'seed': t['seed'], 'probabilities': {}, 'briers': {}, 'alc': {}}
                for m, a in ALPHAS.items():
                    ps = [.5 if n == 0 else (sum(x[2] for x in labels[:n])+a)/(n+2*a) for n in cfg['budgets']]
                    bs = [(p*p*(len(ys)-sum(ys)) + (1-p)**2*sum(ys))/len(ys) for p in ps]
                    alc = math.fsum(w*x for w, x in zip(cfg['weights'], bs))
                    seed['probabilities'][m], seed['briers'][m], seed['alc'][m] = ps, bs, alc
                    if m != 'beta_0_5_0_5':
                        saved = scores[pair, t['seed'], m]
                        close(q, saved['evaluation_success_rate'])
                        assert saved['evaluation_responses'] == len(ys)
                        for p, p0, loss, loss0 in zip(ps, saved['probabilities'], bs, saved['briers']):
                            close(p, p0); close(loss, loss0); checked += 1
                        close(alc, saved['alc'])
                row['seeds'].append(seed)
            for m, a in ALPHAS.items():
                row['observed_alc'][m] = st.fmean(s['alc'][m] for s in row['seeds'])
                expected = []
                for n in cfg['budgets']:
                    if n == 0:
                        expected.append(.25)
                    else:
                        pm = (n*mu+a)/(n+2*a)
                        pv = n*((N-n)/(N-1)*v+u)/(n+2*a)**2
                        expected.append(pv+(pm-q)**2+q*(1-q))
                row['expected_alc'][m] = math.fsum(w*x for w, x in zip(cfg['weights'], expected))
                saved = prior[pair, rc['split_unit']]
                if m in saved['observed_alc']:
                    close(row['observed_alc'][m], saved['observed_alc'][m])
                    close(row['expected_alc'][m], saved['expected_alc'][m])
            allrows.append(row)
    result = {'status': 'VERIFIED_FROM_PINNED_RESPONSE_TABLES', 'records': allrows,
              'saved_probability_budget_records_checked': checked, 'source_sha256': sources,
              'config_sha256': sha(HERE / 'config.json'), 'collector_sha256': sha(Path(__file__))}
    (HERE / 'inputs.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({'pairs_including_split_variants': len(allrows), 'verified_probability_budget_records': checked}))


if __name__ == '__main__':
    main()
