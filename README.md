# paiec-2026

Predicting model correctness with few observed labels for the
[NeurIPS 2026 Predictive AI Evaluation Competition](https://aims.stanford.edu/competition).

The submitted method uses fixed Beta(1,1) shrinkage:
`(successes + 1) / (labels + 2)`, with random label acquisition.
Local experiments examine its small-budget gains and low-success bias.
Weaker shrinkage, transferred priors and lexical weighting did not meet the
criteria for replacing it.

[Results](RESULTS.md) · [Reproduction](REPRODUCIBILITY.md) · [Evaluation protocol](docs/evaluation_protocol.md)

## Run the checks

Requires Python 3.12 and Git. From the repository root:

```bash
git clone --config core.autocrlf=false https://github.com/aims-foundations/paiec_baseline.git upstream
git -C upstream checkout cc88a959c1e5e7462f31a9215baba066ce6d6e2b
python -m unittest discover -s tests -t . -v
python run_baseline.py
```

These checks use synthetic inputs; no dataset, GPU or API is needed.

## Contents

- `shrinkage/`: submitted predictor; `weaker_shrinkage/` and `retrieval_shrinkage/`: comparison methods.
- `experiments/`, `tests/`: frozen experiment code and unit tests.
- `configs/`, `results/`, `docs/`: protocols, aggregate results and methodology.
- `reproduce_extensions.py`: rebuilds the follow-up experiments in a new local workspace.

The report uses [code revision `d2d3e3c`](https://github.com/GioiaZheng/paiec-2026/tree/d2d3e3c1e803880f4918f2f8065616b513731a40).
Public results come from released training benchmarks; raw data and private
CodaBench feedback stay local under the [competition's sharing rules](https://aims.stanford.edu/competition).

Code: [MIT](LICENSE). The empirical-mean reference and ZIP checks come from the
[official baseline](https://github.com/aims-foundations/paiec_baseline).
See [third-party notices](THIRD_PARTY_NOTICES.md); dataset licenses are separate.
