# When shrinkage helps

Fixed Beta(1,1) reduces acquisition variance but pulls probabilities toward 0.5.
That tradeoff explains both the small-budget gains and failures on very hard
groups. This is a retrospective diagnosis of the existing predictors, not a
new method or a rule for choosing predictions from evaluation labels.

## Sampling-size sensitivity

Of the initial 113 coding groups, 54 Multi-SWE-bench and all 31 ResearchCodeBench
groups contain 80–1,000 distinct source items. These 85 groups could each fit
alone under the starting kit's complete-group draw limit. Filtering by size
does not reproduce the organizer's balancing or packing procedure.

| Coding split | Mean: three seeds | Beta: three seeds | Mean: exact expectation | Beta: exact expectation |
| --- | ---: | ---: | ---: | ---: |
| Lexical groups | 0.25527 | 0.21963 | 0.26075 | 0.22243 |
| Item IDs | 0.25586 | 0.22047 | 0.25944 | 0.22153 |

All values are Brier ALC, averaged equally over the 85 groups. Expectations
average over random acquisition while holding the saved pools fixed. They do
not average over alternative pool splits, benchmarks or future response runs.

In the lexical-group split, expected ALC improves for 73 groups and worsens for
12. All 12 losses occur below 10% evaluation success. In that low-success slice,
12 of 14 groups worsen and the average delta is +0.01146. The rate slices were
chosen retrospectively; evaluation success is unavailable at prediction time.

At budget 1, shrinkage changes expected Brier by -0.14800: a variance reduction
of 0.17094 outweighs an increase of 0.02293 in squared bias. Across the original
113 groups, 15 groups change their win/loss direction when the three sampled
trajectories are replaced by their exact expectation. Three seeds support a
pilot comparison but do not reliably identify every group's winner.

## Exact expectation conditional on the pools

Let the acquisition pool contain `N` items. For item `i`, let `mu_i` be the
fraction of its recorded outcomes equal to one. Write `m = mean(mu_i)`,
`v = mean((mu_i - m)^2)` and `u = mean(mu_i * (1 - mu_i))`. Select `n` distinct
items uniformly, then select one recorded outcome per item independently.
If `S` is the sum of these outcomes, the law of total variance gives:

```text
E[S]   = n m
Var(S) = n [(N - n) / (N - 1) v + u]
```

The first term is sampling without replacement across items. The second keeps
the variation from repeated response runs; it remains even when all items are
selected. For `N = 1`, the between-item term is zero.

For the empirical mean, `p = S/n`; for Beta(1,1), `p = (S+1)/(n+2)`. At budget
zero both use 0.5. Let `q` be the observed success fraction across all response
rows in the fixed evaluation pool. Since these predictors are constant within
each group:

```text
E[Brier] = Var(p) + (E[p] - q)^2 + q(1-q)
```

Weight these expectations at budgets 0, 1, 3, 7, 15 and 31 to obtain expected
ALC. Linearity of expectation makes this valid for nested label prefixes too;
the budgets need not be independent. The decomposition uses every local
outcome for diagnosis only. It assumes the specified local random-acquisition
policy, not independent identically distributed real-world questions.

The implementation is checked against exhaustive enumeration on small pools,
including unequal numbers of repeated outcomes and conflicting responses.
No predictor, prior, acquisition policy or submission archive was changed.

[Code](../experiments/diagnose_shrinkage.py) · [Aggregate evidence](../results/2026-10-16/shrinkage_diagnostics.json)
