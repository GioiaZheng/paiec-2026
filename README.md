# paiec-2026

**Predicting model correctness on unseen benchmark items with limited observed labels.**

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
and low-success failures.
The shrinkage candidate has completed its first hosted development evaluation.
The paired comparisons reported here remain local experiments.
A fixed Beta(0.5,0.5) ablation reduces low-success bias but worsens overall ALC
on the new FinanceBench validation. Beta(1,1) remains the baseline; see [Results](RESULTS.md).

## Follow-up experiments

Transferred priors and bounded lexical weighting did not meet the fixed
robustness and validation criteria. Beta(1,1) remains the candidate.
[Reproduce the follow-ups](docs/extensions-reproduction.md) from pinned data in
a new directory; the driver does not need the original saved runs.

## Acknowledgments

The empirical-mean reference and ZIP checks come from the
[official PAIEC baselines](https://github.com/aims-foundations/paiec_baseline),
used under their MIT license. Dataset licenses remain separate.

## License

Code is available under the [MIT license](LICENSE). See
[third-party notices](THIRD_PARTY_NOTICES.md) for the adapted baseline.
