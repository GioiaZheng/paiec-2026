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
- Two coding benchmarks, BertaQA and REAL are still a small
  sample. These are local results, not official feedback or evidence of broad
  generalization. No benchmark-level confidence interval is claimed.

[Aggregate evidence](results/2026-10-16/) · [Protocol](docs/evaluation_protocol.md)
