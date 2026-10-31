# Results

Local public-data comparisons, 16 October 2026. Lower Brier ALC is better.

## Exploratory coding benchmarks

| Method | Multi-SWE-bench | ResearchCodeBench | All pairs |
| --- | ---: | ---: | ---: |
| Constant 0.5 | 0.25000 | 0.25000 | 0.25000 |
| Acquired-label mean | 0.20334 | 0.27213 | 0.22221 |
| Beta(1,1) shrinkage | 0.18215 | 0.22999 | 0.19527 |

This split keeps exact and lexical near-duplicates together. Scores average
equally over 113 subject–benchmark pairs and three fixed acquisition seeds.
No prior parameters were fitted or tuned; acquisition is shared across methods.

## What changed

About 84% of the net ALC improvement comes from budget 1, where pooled Brier
falls from 0.33635 to 0.22323. At budget 31 the difference is only 0.00021.
Across the three acquisition seeds, shrinkage's mean ALC delta is negative in
each run: -0.02929, -0.02724 and -0.02428.

The benefit is not universal: 81 pairs improve and 32 worsen after averaging
seeds. The largest losses occur in low-success groups. For example, the
ResearchCodeBench/Codestral Mamba group has an evaluation success rate of 1.56%
and an ALC increase of 0.02899. Shrinking toward 0.5 overestimates such groups.
These are descriptive observations, not causal or cross-benchmark guarantees.

## Split sensitivity

An item-level 50/50 split, closer to the official sampling unit, gives pooled
ALCs of 0.25000, 0.21789 and 0.19367 respectively. Shrinkage improves over the
mean in both designs. The guarded split is a robustness check, not an exact
platform simulation: clustering can shift the acquisition fraction to 35–69%.
The two designs change both pools and acquired labels, so their difference does
not isolate the effect of duplicate removal.

## BertaQA validation

The same three predictors were then evaluated on cultural-knowledge questions.
The [configuration](configs/bertaqa-validation.json) was fixed before reading
outcomes. A label-blind schema check added source-question grouping to account
for parallel English/Basque questions and different few-shot contexts.

| Method | Item split (primary) | Source-question split |
| --- | ---: | ---: |
| Constant 0.5 | 0.25000 | 0.25000 |
| Acquired-label mean | 0.26291 | 0.27178 |
| Beta(1,1) shrinkage | 0.22409 | 0.22645 |

Both designs average six subject configurations and three acquisition seeds.
All six configurations improve after averaging seeds; each seed's aggregate
delta also favors shrinkage. About 80% of the primary split's net improvement
comes from budget 1. At budgets 7 and 15, shrinkage is slightly worse than the
mean in that split. The predictor and prior were not changed.

The release has 51,760 prompt variants for 4,756 parallel source questions.
Item splitting places 2,316–2,433 source groups on both sides for each subject.
The guarded design keeps translations, prompt variants and detected lexical
matches together; no audited source group crosses its pools. Shared few-shot
examples are excluded from the lexical comparison. This checks known question
identity and lexical overlap, not every possible semantic relation.

Both designs pass independent recomputation of all 54 pair/seed/method records.
This is one prospective local validation, now inspected, not an untouched
holdout for future changes. Each subject has 9,512 items, larger than the kit's
1,000-source-item draw limit, so this measures a broader local population rather
than the hosted draw. The guarded and item splits use different pools and labels;
their score difference is not a causal estimate of leakage.

[BertaQA evidence](results/2026-10-16/bertaqa.json)

## REAL validation

REAL adds web-agent tasks at a size compatible with the single-group draw
limit. The [protocol](configs/real-validation.json) was fixed before outcomes
were downloaded. Of 33 subject configurations, 26 have at least 80 observed
items; the remaining seven are excluded by the competition's eligibility rule.
Eligible groups contain 89–233 items.

| Method | Three acquisition seeds | Exact acquisition expectation |
| --- | ---: | ---: |
| Constant 0.5 | 0.25000 | 0.25000 |
| Acquired-label mean | 0.24595 | 0.23569 |
| Beta(1,1) shrinkage | 0.21036 | 0.20500 |

After averaging the three seeds, 22 groups improve and four worsen. Under exact
acquisition expectation conditional on these pools, 21 improve and five worsen.
About 82% of the sampled net improvement comes from budget 1. No predictor was
changed. These expectations are local diagnostics, not independent test scores.

The audit finds no exact or 0.9-Jaccard lexical duplicates. Item and guarded
splits consequently produce identical pools and scores; they are one piece of
evidence, not two replications. The tables contain 334 repeated subject–item
cells, including 91 with differing outcomes. Sampling one recorded outcome per
acquired item and scoring all evaluation outcomes preserves this variation.
Both runs pass independent recomputation of 234 records each.

[REAL evidence](results/2026-10-16/real.json)

## Acquisition variance and failures

Restricting the initial coding pilot to its 85 groups with 80–1,000 source items
preserves the improvement: expected ALC is 0.26075 for the mean and 0.22243 for
Beta(1,1) in the lexical-group split. The expectation removes acquisition-seed
variation while keeping the pools fixed. Twelve groups still worsen; all have
evaluation success below 10%. This supports a variance-versus-bias explanation,
not universal improvement. See [the derivation and diagnostics](docs/shrinkage_analysis.md).

## Weaker fixed shrinkage

The [follow-up protocol](configs/weaker-shrinkage.json) fixes Beta(0.5,0.5)
before reading FinanceBench outcomes. The four previously inspected benchmarks
are development reanalyses. All methods share pools, budgets and acquired labels.
No parameter search or new hosted submission is used.

| Benchmark | Role | Groups | Mean ALC | Beta(1,1) | Beta(0.5,0.5) |
| --- | --- | ---: | ---: | ---: | ---: |
| Multi-SWE-Bench | Development | 82 | 0.203341 | 0.182148 | 0.182152 |
| ResearchCodeBench | Development | 31 | 0.272125 | 0.229991 | 0.236628 |
| BertaQA | Development | 6 | 0.271776 | 0.226454 | 0.234033 |
| REAL | Development | 26 | 0.245946 | 0.210362 | 0.214798 |
| FinanceBench | New public validation | 16 | 0.234080 | 0.202287 | 0.205503 |

Lower is better. Scores average the same three acquisition seeds. Coding uses
lexical groups, BertaQA uses source-question groups, and REAL and FinanceBench
use item splits. These rows cover all local eligible groups; the BertaQA and
some coding groups exceed the hosted draw cap. Size-filtered summaries are
included in the evidence file.

On FinanceBench, the weaker prior worsens observed ALC by **0.003215**, with
six groups improving and ten worsening. All three acquisition seeds have the
same aggregate direction. Exact conditional expected ALC also worsens, from
0.195384 to 0.197041. The prespecified overall-improvement criterion fails.

The two groups with evaluation success below 10% improve: observed ALC falls
from 0.113542 to 0.104443, and expected ALC from 0.107401 to 0.096816. However,
the empirical mean's expected ALC in this slice is still lower, at 0.094770.
This is an outcome-defined diagnostic, not a usable rule for choosing a prior.

Across all 16 groups at budget 1, weaker shrinkage reduces expected squared
bias by 0.016975 but adds 0.023299 prediction variance, increasing expected
Brier by 0.006324. It retains a small-budget benefit over the empirical mean,
but gives up too much variance reduction to improve overall ALC. **Keep
Beta(1,1) as the baseline.**

All 150 items and 2,400 responses pass key, join, binary-label and coverage
checks; all 16 configurations are eligible. No grades are missing, no response
cells repeat, and no exact or 0.9-Jaccard duplicate questions are found. The
guarded split produces identical trajectories and scores, so it is not a
second replication. The evaluation does not establish document-level or
semantic independence. FinanceBench is now inspected data for future work.

[Ablation evidence](results/2026-10-16/weaker_shrinkage.json)

## Checks and limits

- The coding pilot's lexical audit found 65 duplicate clusters using token 5-shingle Jaccard
  similarity >= 0.9. No cross-benchmark match was found at that threshold.
  This does not rule out semantic paraphrases.
- All responses of an item remain together. Repeated outcomes are scored
  separately; target reference answers and grading fields are excluded.
  BertaQA's supplied few-shot examples remain in the allowed item text, which
  these predictors ignore.
- Both coding split designs pass independent row-wise recomputation of 1,017 records each.
  Both predictors pass the official ZIP and sequential smoke checks. The
  parallel helper fails on Windows because it uses POSIX file descriptors.
  Both extracted archives pass the unchanged helper under Ubuntu WSL, using
  two isolated workers for its two sample inputs. This is not the hosted image.
- A larger archive replay uses four official isolated workers and mixed labels
  from six groups across the three size-compatible benchmarks. All six budgets
  match saved probabilities and row-wise Brier/ALC; repeated-input reuse is
  exercised. This checks the executable archives, not a new performance claim.
  [Replay evidence](results/2026-10-16/runtime_replay.json)
- Two coding benchmarks, BertaQA, REAL and FinanceBench are still a small
  sample. These are local results, not official feedback or evidence of broad
  generalization. No benchmark-level confidence interval is claimed.

[Aggregate evidence](results/2026-10-16/) · [Protocol](docs/evaluation_protocol.md)

## Prior transfer and lexical weighting

These follow-ups use the five previously inspected benchmarks as development
data. The center of the transferred prior is fitted without the entire target
benchmark. Lower Brier ALC is better.

| Method | Equal-pair ALC | Equal-benchmark ALC |
| --- | ---: | ---: |
| Beta(1,1) | 0.198355 | 0.209376 |
| Transferred center | 0.196179 | 0.211976 |
| Fixed mixture | 0.197093 | 0.210236 |
| Adaptive mixture | 0.197112 | 0.210257 |

The pair-weighted score improves, but the benchmark-weighted robustness check
worsens. BertaQA exposes a large transfer error; adaptive mixing reduces this
error without removing it. Both candidates fail their development criteria.

Lexical weighting keeps the Beta(1,1) pseudo-counts and gives similar acquired
questions slightly greater weight. All fitting uses the matching revealed
prefix. Zero/one-label predictions remain identical to the baseline.

| Population | Groups | Beta(1,1) | Lexical | Shuffled labels |
| --- | ---: | ---: | ---: | ---: |
| Development, item | 161 | 0.198355 | 0.198029 | 0.198412 |
| TruthfulQA, new validation | 150 | 0.227169 | 0.227132 | 0.227166 |

TruthfulQA was selected and the method/rule frozen before reading its outcomes.
Its mean gain is small, and one of three acquisition seeds gets worse, so the
fixed stability rule fails. The item and guarded splits coincide and count as
one validation. The shuffled-label control uses one deterministic permutation
per group, seed and budget; it is not a significance test. This does not prove
the method cannot help, but does not support replacing the baseline under the
chosen rule. No extension has a hosted evaluation.

The clean replication rebuilds the pools and matches all recorded aggregate
summaries within `1e-12`; it is a reproducibility check, not new validation.
See [the reproduction guide](docs/extensions-reproduction.md) and
[aggregate reference](results/2026-10-31/extensions-reference.json).
