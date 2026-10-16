# paiec-2026

**Predicting model correctness on unseen benchmarks with limited observed labels.**

Experiments for the [Predictive AI Evaluation Competition](https://aims.stanford.edu/competition)
at NeurIPS 2026, focused on calibration and benchmark generalization.

[Results](RESULTS.md) · [Reproducibility](REPRODUCIBILITY.md) · [Evaluation protocol](docs/evaluation_protocol.md)

## Approach

Start with constant 0.5 and the official acquired-label mean. Compare a fixed
Beta(1,1) estimate, `(successes + 1) / (labels + 2)`, to test whether shrinkage
helps when only a few outcomes are available. Acquisition stays random.

## Quickstart

Requires Python 3.12 and Git. The official baseline is kept at a pinned revision:

```bash
git clone --config core.autocrlf=false https://github.com/aims-foundations/paiec_baseline.git upstream
git -C upstream checkout cc88a959c1e5e7462f31a9215baba066ce6d6e2b
python run_baseline.py
```

This builds and checks both submission archives without downloading data or
calling an API. See [Reproducibility](REPRODUCIBILITY.md) for the data pilot.

## Status

Both archives pass official checks on Windows and Linux. The initial comparison
covers two coding benchmarks; fixed BertaQA and REAL validations also support
shrinkage at small label budgets. Exact acquisition diagnostics explain gains
and low-success failures. A technical report draft is available locally.
The first development submission has been uploaded; hosted evaluation is pending.

## Acknowledgments

The empirical-mean reference and ZIP checks come from the
[official PAIEC baselines](https://github.com/aims-foundations/paiec_baseline),
used under their MIT license. Dataset licenses remain separate.
