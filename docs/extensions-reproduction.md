# Follow-up experiments

The follow-ups test a transferred prior, adaptive prior mixing and bounded
lexical weighting of acquired labels. Beta(1,1) remains the candidate: transfer
fails the benchmark-level robustness screen, and the lexical method's small
TruthfulQA gain reverses under one of three acquisition seeds.

## Reproduce

Use Python 3.12 and a full Git clone. Install the pinned local dependencies and obtain the reference
baseline as described in [Reproducibility](../REPRODUCIBILITY.md). Download the
four formatted tables (`benchmarks`, `items`, `subjects`, `responses`) for these
six benchmarks from measurement-db revision
`54074453da7b9911be0f48e4c560be547bc84d21`:

- `multi_swebench`
- `researchcodebench`
- `bertaqa`
- `real_webagents`
- `financebench`
- `truthfulqa_mc`

Place the Parquet files under `data/<benchmark>/`, then run:

```bash
python -X utf8 reproduce_extensions.py --data data --output local/replication
```

The output directory must not exist. The driver verifies all 24 data hashes and
the recorded source hashes before copying inputs into the new directory.
It restores files from `experiments/` and `tests/` to their original paths;
the original driver is read from submitted revision
`d2d3e3c1e803880f4918f2f8065616b513731a40`. The recorded manifest is unchanged. It
normalizes source text to LF so Windows/Git newline conversion does not break
the source checks; data files are checked byte for byte. It
rebuilds the acquisition/evaluation pools, runs the comparisons and independently
rescores the lexical predictions. It does not read the original run directories
or saved item predictions. The experiment subprocesses use the copied source
files and the installed PyArrow dependency.

`replication.json` reports `PASS` only when the rebuilt summaries and selection
decisions match the recorded aggregates within an absolute tolerance of `1e-12`.
Logs and full results remain in the output directory. A failed step raises an
error and leaves its log for inspection; it never overwrites an earlier run.

This uses local CPU and disk, with no download, GPU or API call. The lexical
comparisons are the slowest step. The output includes copies of the data and
item-level traces, so keep the replication directory local.

## What the check establishes

This is a numerical replication of already observed experiments, not another
independent validation. Its input snapshots are explicitly marked as replication
hashes. The original choices, label budgets, seeds, methods and decision rules
remain in the configuration files; only run-directory references are adapted in
the new workspace.

The reference JSON contains aggregate results and data/source hashes, not raw
questions, labels, model identifiers or private feedback. Raw tables are not
redistributed. Dataset licenses remain separate from this repository's MIT
code license.

The new experiments have no hosted submission. The existing CodaBench result is
for the original Beta(1,1) archive.
