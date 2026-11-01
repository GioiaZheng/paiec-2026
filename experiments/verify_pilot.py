"""Independent row-wise recomputation of a saved pilot; never modifies data."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / ".deps"))
import pyarrow.parquet as pq
import json
import math
import hashlib


def main():
    run = Path(sys.argv[1]).resolve()
    trajectories = json.loads((run / "trajectories.json").read_text())
    scores = json.loads((run / "scores.json").read_text())
    config = json.loads((run / "config.json").read_text())
    manifest = json.loads((run/'manifest.json').read_text())
    for name, source in manifest.items():
        if hashlib.sha256((ROOT/name.replace('\\','/')).read_bytes()).hexdigest() != source['sha256']:
            raise ValueError(f'Data hash mismatch: {name}')
    # Independently reconstruct connected lexical components from audited pairs.
    parent = {}
    def find(key):
        parent.setdefault(key,key)
        if parent[key] != key:
            parent[key] = find(parent[key])
        return parent[key]
    duplicates = json.loads((run/'duplicate_pairs.json').read_text()) if (run/'duplicate_pairs.json').exists() else {'pairs':[]}
    if config.get('split_unit') == 'source':
        # Independent source grouping from raw IDs, before joining lexical links.
        import re
        for b in {t['benchmark'] for t in trajectories}:
            for row in pq.read_table(ROOT/'data'/b/'items.parquet', columns=['item_id', 'raw_item_id']).to_pylist():
                match = re.fullmatch(r'(en|eu)-([0-9]+)', row['raw_item_id'])
                assert b == 'bertaqa' and match
                parent[f"{b}/{row['item_id']}"] = f'{b}/source/{match.group(2)}'
    for pair in duplicates['pairs']:
        a,b = find(pair['left']),find(pair['right'])
        parent[b] = a
    tables = {b: pq.read_table(ROOT / "data" / b / "responses.parquet").to_pylist()
              for b in {r["benchmark"] for r in trajectories}}
    subjects = {b: {r['subject_id']: r for r in pq.read_table(ROOT/'data'/b/'subjects.parquet').to_pylist()} for b in tables}
    keys = list(trajectories[0]['subject'])
    verified = 0
    for t in trajectories:
        b = t['benchmark']
        ids = {sid for sid, s in subjects[b].items()
               if {k:str(s[k]).strip() if s[k] is not None else '' for k in keys} == t['subject']}
        obs = [r for r in tables[b] if r['subject_id'] in ids and r['response'] is not None]
        by_id = {r['response_id']:r for r in obs}
        acquired = set(t['acquisition_item_ids'])
        evaluation = set(t['evaluation_item_ids'])
        assert not acquired & evaluation
        if config.get('split_unit') in ('near', 'source'):
            assert not {find(f'{b}/{i}') for i in acquired} & {find(f'{b}/{i}') for i in evaluation}
        assert acquired | evaluation == {r['item_id'] for r in obs}
        labels = [by_id[r] for r in t['revealed_response_ids']]
        assert len({r['item_id'] for r in labels}) == 31
        assert all(r['item_id'] in acquired for r in labels)
        outcomes = [r['response'] for r in obs if r['item_id'] in evaluation]
        matching = [r for r in scores if r['pair'] == t['pair'] and r['seed'] == t['seed']]
        assert len(matching) == 3
        for r in matching:
            assert len(outcomes) == r['evaluation_responses']
            recomputed = []
            for i, n in enumerate(config['budgets']):
                successes = sum(x['response'] for x in labels[:n])
                if r['method'] == 'constant_0.5':
                    p = .5
                elif r['method'] == 'empirical_mean':
                    p = successes/n if n else .5
                else:
                    assert r['method'] == 'beta_1_1'
                    p = (successes+1)/(n+2)
                assert p == r['probabilities'][i]
                brier = sum((p-y)**2 for y in outcomes)/len(outcomes)
                assert math.isclose(brier, r['briers'][i], abs_tol=1e-12)
                recomputed.append(brier)
            assert math.isclose(sum(w*x for w,x in zip(config['weights'],recomputed)), r['alc'], abs_tol=1e-12)
            verified += 1
    result = {'status':'PASS', 'pair_seed_method_records_verified':verified,
              'checks':['data hashes','row-wise Brier recomputation','ALC weights','label budgets','disjoint item pools','response coverage','audited lexical/source-group separation when enabled'],
              'limitations':'Lexical audit does not establish semantic duplicate absence or exact official platform trajectories'}
    (run/'independent_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
