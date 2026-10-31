# Reproducibility

## Baseline checks

Follow the README to obtain the pinned official baseline, then run:

```bash
python run_baseline.py
```

Requires the standard library and Git. Both ZIP checks, four official mean
tests and group/budget isolation checks pass. On Windows, set
`PYTHONIOENCODING=utf-8` if the workspace path contains Unicode.

Download the starting kit from the competition's **Get Started → Files** tab,
unpack it under `local/official/starting_kit`, and run:

```bash
python run_baseline.py --starter-kit local/official/starting_kit
```

Both predictors pass the kit's ZIP and sequential smoke tests. Its ZIP digest
is in [interface_checks.json](results/2026-10-16/interface_checks.json).
The kit's sample data check the interface, not predictive performance.
`--smoke-concurrency 4` passes under Ubuntu WSL with Python 3.14.4, using two
isolated workers for the kit's two sample inputs. The archives are extracted to
fresh directories before testing. This helper fails on Windows with
`pass_fds not supported on Windows`; the official kit is kept unchanged.
Windows (Python 3.12.2) and Linux builds produce the same candidate ZIP digest.
The shrinkage candidate has since completed one hosted evaluation; the
empirical-mean archive has only been checked locally.

## Replay the actual archives

After reproducing and verifying the coding item split and REAL item split below,
prepare a local fixture where PyArrow is installed:

```bash
python replay_submission.py prepare runs/<coding-item-run> runs/<real-item-run> --output local/runtime-fixture-repeats.json
```

Run the extracted archives through the unchanged starting-kit workers on Linux:

```bash
python3 replay_submission.py run --fixture local/runtime-fixture-repeats.json --concurrency 4
```

This requires only Python's standard library at replay time. On Windows, run
the second command from Ubuntu WSL in the same project directory.

The recorded fixture contains six groups across three benchmarks, totaling
962 source subject–item pairs. Selection uses counts and stable pair hashes,
preferring repeated response rows to exercise input reuse. It does not reproduce
the private draw. All six budgets mix the current labels from every selected
group; each checkpoint starts fresh workers.

Both archives reproduce every saved probability and each group's Brier/ALC
within 1e-12. Each checkpoint makes 473 unique prediction calls for 760 response
rows, reusing 287 predictions. Four workers are active. The fixture, raw outputs
and logs stay local; [aggregate evidence](results/2026-10-16/runtime_replay.json)
records hashes and checks. This is an integration check on existing data, not
additional validation evidence or a hosted-runtime test.

## Coding benchmarks

```bash
python -m pip install --target .deps -r requirements-local.txt
python evaluate_pilot.py
python verify_pilot.py runs/<guarded-run>
python analyze_pilot.py runs/<guarded-run>
python evaluate_pilot.py --split-unit item
python verify_pilot.py runs/<item-run>
```

Place `benchmarks.parquet`, `subjects.parquet`, `items.parquet` and
`responses.parquet` under `data/<benchmark>/` for `multi_swebench` and
`researchcodebench`. Obtain them through your authorized Hugging Face account
from each benchmark's `formatted_tables/` directory at measurement-db revision
`54074453da7b9911be0f48e4c560be547bc84d21`. File URLs and hashes are recorded in
[data_manifest.json](results/2026-10-16/data_manifest.json).

Each run saves its configuration, duplicate audit, pools, acquired response IDs,
per-pair probabilities and scores. The verifier checks data hashes, label budgets,
response coverage, cluster separation and row-wise Brier/ALC calculations.
Seeds are 20261016–20261018; the evaluation pool stays fixed within a split design.

Verified with Python 3.12.2 and PyArrow 23.0.1 on Windows. No GPU or API is used.
The original upstream full suite has five BLE/packaging failures out of 19;
the four empirical-mean tests pass. These are separate from the kit checks.

Datasets, credentials, dependencies and intermediate runs stay out of Git.
ResearchCodeBench's release metadata records its upstream license as unknown;
no source data are redistributed here.

## Fixed BertaQA validation

Obtain the same four tables from `bertaqa/formatted_tables/` at the pinned
revision and place them under `data/bertaqa/`. Their hashes are in
[bertaqa.json](results/2026-10-16/bertaqa.json). Then run:

```bash
python evaluate_pilot.py --protocol configs/bertaqa-validation.json --split-unit item
python verify_pilot.py runs/<item-run>
python analyze_pilot.py runs/<item-run>
python evaluate_pilot.py --protocol configs/bertaqa-validation.json --split-unit source
python verify_pilot.py runs/<source-run>
python analyze_pilot.py runs/<source-run>
python -m unittest test_evaluation.py
```

The runner checks frozen predictor hashes before reading outcomes. The repository
enforces LF line endings; the README clone command preserves upstream bytes too.
Source grouping
uses the parallel question ID in `raw_item_id`, and audits the final user message
without the shared five-shot context. Source IDs are used only to construct the
local split; they never enter the predictor. Four focused audit tests pass.

Older result manifests retain the original script hashes. After the evaluator
was extended, rerunning the coding comparison reproduced its summary exactly;
[regression.json](results/2026-10-16/regression.json) records that check.

## REAL validation and error diagnosis

Obtain the same four tables from `real_webagents/formatted_tables/` at the fixed
revision and place them under `data/real_webagents/`. The inventory calls this
benchmark `real`; both entries point to paper `Un1sWxmZuI`. File hashes are in
[real.json](results/2026-10-16/real.json). The release records its license as
unknown, so source data remain local.

```bash
python evaluate_pilot.py --protocol configs/real-validation.json --split-unit item
python verify_pilot.py runs/<real-item-run>
python analyze_pilot.py runs/<real-item-run>
python evaluate_pilot.py --protocol configs/real-validation.json --split-unit near
python verify_pilot.py runs/<real-near-run>
python analyze_pilot.py runs/<real-near-run>
python diagnose_shrinkage.py runs/<coding-guarded-run> runs/<coding-item-run> runs/<bertaqa-item-run> runs/<bertaqa-source-run> runs/<real-item-run> runs/<real-near-run>
python -m unittest test_evaluation.py test_diagnostics.py
```

The diagnostic reads verified runs and checks source-table hashes before
computing exact conditional expectations. It saves summaries and per-group
decompositions in a new `runs/diagnosis-*/` directory. Six focused tests pass,
including exhaustive acquisition enumeration with repeated outcomes. Expectations
use local evaluation labels for analysis only and never change predictions.

## Weaker-prior ablation

Obtain the four formatted FinanceBench tables from the same pinned revision,
under `data/financebench/`. Their hashes are in
[weaker_shrinkage.json](results/2026-10-16/weaker_shrinkage.json). The source
license is recorded as unknown; data are not redistributed.

```bash
python -m unittest test_evaluation.py test_diagnostics.py test_weaker_shrinkage.py
python evaluate_pilot.py --protocol configs/weaker-shrinkage.json --split-unit item
python verify_pilot.py runs/<finance-item-run>
python evaluate_pilot.py --protocol configs/weaker-shrinkage.json --split-unit near
python verify_pilot.py runs/<finance-near-run>
python compare_shrinkage.py runs/<coding-guarded-run> runs/<bertaqa-source-run> runs/<real-item-run> runs/<finance-item-run> runs/<finance-near-run>
```

The original evaluator supplies the three reference methods. The comparison
script evaluates `weaker_shrinkage/model.py` on the same saved labels, checks
its predictions against an independent formula, recomputes every reference
score row by row, and records exact acquisition expectations separately.
It verifies frozen method and analysis hashes before reading outcomes.

The comparison saves per-group results and a summary under `runs/weaker-*/`.
Eight focused tests pass, including exhaustive acquisition enumeration for
the weaker prior and isolation across all eight subject fields. The new module
also passes the unchanged starting kit's two-input sequential smoke test.
That smoke score is an interface check, not experiment evidence. The original
Beta(1,1) module and submitted archive are unchanged.

## Follow-up experiments

[Follow-up reproduction](docs/extensions-reproduction.md) covers transferred
priors, adaptive mixing and lexical weighting. It rebuilds all public-data pools
and verifies the saved aggregate results in a new workspace. No private feedback
or item-level data are included in the repository.
