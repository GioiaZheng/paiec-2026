"""Summarize a fixed pilot without selecting hyperparameters or favorable seeds."""
from pathlib import Path
import collections
import json
import sys


def main():
    run = Path(sys.argv[1]).resolve()
    scores = json.loads((run/'scores.json').read_text())
    trajectories = json.loads((run/'trajectories.json').read_text())
    config = json.loads((run/'config.json').read_text())
    indexed = {(r['pair'],r['seed'],r['method']):r for r in scores}
    pairs = collections.defaultdict(list)
    seed_deltas = collections.defaultdict(list)
    for r in scores:
        if r['method'] != 'beta_1_1':
            continue
        ref = indexed[r['pair'],r['seed'],'empirical_mean']
        delta = r['alc']-ref['alc']
        pairs[r['pair']].append((r,delta))
        seed_deltas[r['seed']].append(delta)
    subjects = {t['pair']:t['subject'] for t in trajectories}
    pair_deltas = [{ 'pair':pair, 'benchmark':rows[0][0]['benchmark'],
                     'subject':subjects[pair],
                     'mean_alc_delta':sum(d for _,d in rows)/len(rows),
                     'evaluation_success_rate':sum(r['evaluation_success_rate'] for r,_ in rows)/len(rows)}
                   for pair,rows in pairs.items()]
    ref = [r for r in scores if r['method']=='empirical_mean']
    candidate = [r for r in scores if r['method']=='beta_1_1']
    per_budget = []
    for i,n in enumerate(config['budgets']):
        mean_ref = sum(r['briers'][i] for r in ref)/len(ref)
        mean_candidate = sum(r['briers'][i] for r in candidate)/len(candidate)
        per_budget.append({'budget':n,'empirical_mean':mean_ref,'beta_1_1':mean_candidate,
                           'weighted_delta':(mean_candidate-mean_ref)*config['weights'][i]})
    slices = []
    for b in sorted({r['benchmark'] for r in pair_deltas}):
        rows = [r for r in pair_deltas if r['benchmark']==b]
        slices.append({'benchmark':b,'pairs':len(rows),
                       'improved':sum(r['mean_alc_delta'] < -1e-12 for r in rows),
                       'worsened':sum(r['mean_alc_delta'] > 1e-12 for r in rows),
                       'tied':sum(abs(r['mean_alc_delta']) <= 1e-12 for r in rows)})
    total_delta = sum(x['weighted_delta'] for x in per_budget)
    result = {'per_budget':per_budget,'paired_mean_alc_delta':total_delta,
              'budget_1_fraction_of_net_improvement':per_budget[1]['weighted_delta']/total_delta if total_delta else None,
              'by_benchmark':slices,
              'by_seed':{str(k):sum(v)/len(v) for k,v in seed_deltas.items()},
              'largest_losses':sorted((r for r in pair_deltas if r['mean_alc_delta'] > 1e-12),
                                      key=lambda r:r['mean_alc_delta'],reverse=True)[:5],
              'acquisition_pool_fraction_range':[min(len(t['acquisition_item_ids'])/(len(t['acquisition_item_ids'])+len(t['evaluation_item_ids'])) for t in trajectories),
                                                 max(len(t['acquisition_item_ids'])/(len(t['acquisition_item_ids'])+len(t['evaluation_item_ids'])) for t in trajectories)],
              'interpretation':'Descriptive exploratory analysis; pairs share benchmarks and seeds share a fixed evaluation pool.'}
    (run/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
