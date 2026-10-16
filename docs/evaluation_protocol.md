# Evaluation protocol

Compare constant 0.5, the official acquired-label mean, and fixed Beta(1,1)
shrinkage. No fitting, prior selection, paid API or custom acquisition is used.
The two public coding benchmarks are exploratory; additional benchmarks must
be frozen before any later tuning or confirmatory evaluation.

The subsequent [BertaQA configuration](../configs/bertaqa-validation.json) fixes
the same predictors and seeds before outcomes are inspected. Its primary split
uses item IDs; its sensitivity split groups source questions. BertaQA has now
been evaluated and must not be reused as an untouched holdout for later tuning.

The [REAL configuration](../configs/real-validation.json) likewise fixes the
predictors before outcomes are downloaded. Its eligible groups fit the kit's
single-group size limit. Item and lexical-group splits are identical here,
so they count as one validation. REAL is now inspected too.

## Evidence and scoring

Group subjects by all eight visible configuration fields. Predictors receive
only the published interface fields and the labels revealed at the current
budget. They do not receive grading criteria, target reference answers or traces.
Provided few-shot demonstrations are allowed item context, not target labels.
The current three predictors are constant within each subject–benchmark pair;
the evaluator's aggregate shortcut is valid only for these predictors.

Use one sampled recorded response per acquired item. Keep every repeated
response of an evaluation item in the score, reusing its probability. Budget
prefixes are nested at 0, 1, 3, 7, 15 and 31. Brier ALC uses weights
0.1, 0.2, 0.2, 0.2, 0.2 and 0.1; average pairs equally, then average the three
acquisition seeds. Seeds reuse a fixed evaluation pool and are not independent
dataset replications.

## Splits and duplicates

The guarded design groups normalized exact copies and lexical near-duplicates
before splitting. Similarity is token 5-shingle Jaccard >= 0.9, with connected
components kept together. Short texts use all available tokens. The audit uses
no labels. Its rare-shingle candidate filter is checked against exhaustive
comparisons on generated fixtures. It cannot detect arbitrary paraphrases.

Shuffle clusters with split seed 20261016 and split their count in half, giving
an odd extra cluster to acquisition. This preserves groups but does not guarantee
a 50/50 item balance. The item-level sensitivity design instead splits distinct
item IDs 50/50, with an odd extra item assigned to acquisition. Repeated response
rows never cross either split. Neither design reproduces private platform IDs
or persistent snapshot-update assignments.

BertaQA needs a source-aware guard: `en-<id>` and `eu-<id>` identify parallel
versions of one question, repeated with different few-shot examples. Validate
the ID format, shared question metadata and one final question per language/ID.
Group those variants, then merge additional 0.9-Jaccard matches between unique
final user questions. Few-shot demonstrations do not enter this lexical audit.
These groups define the sensitivity split only; the primary split remains item
based. The original lexical policy remains unchanged for the coding benchmarks.

After splitting, shuffle individual acquisition items using seeds 20261016,
20261017 and 20261018, then reveal one random response for each of the first
31 items. All methods share the same trajectory. This samples uniformly within
the local acquisition pool; the official runtime uses a deterministic streaming
selection rule with the same without-replacement distribution.

## Interpretation

Report all budgets, pair-level losses and split sensitivity. Do not tune against
these results and then call the same benchmarks a holdout. This small benchmark
sample is insufficient for broad generalization claims or a useful benchmark-level
confidence interval. Keep local results, official formative feedback and final
test scores separate.

For these constant-within-group predictors, an offline diagnostic also computes
the exact expectation over random acquisition conditional on the saved pools.
It uses all recorded outcomes for error analysis, never to select predictions
or tune a prior. See the [derivation](shrinkage_analysis.md) for its assumptions.
