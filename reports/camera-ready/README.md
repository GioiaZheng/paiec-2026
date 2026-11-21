# Camera-ready diagnostics

Gioia Zheng. *Fixed Shrinkage for Predictive AI Evaluation with Few Observed Labels*.
PAIEC 2026, OpenReview submission 29. Prepared 21 November 2026.

[Fixed release](https://github.com/GioiaZheng/paiec-2026/releases/tag/camera-ready-2026-11-21)
contains the PDF and complete source bundle. The original experiments remain
at [`d2d3e3c`](https://github.com/GioiaZheng/paiec-2026/tree/d2d3e3c1e803880f4918f2f8065616b513731a40).

The report keeps the submitted Beta(1,1) predictor and original numerical
results. Appendix C adds descriptive analyses after review, using already
observed public data. These are not new validation experiments.

## Reproduce the additions

Python 3.12; the statistics use only the standard library. From this folder:

```sh
python -m unittest discover -s analysis -p test_analysis.py -v
python analysis/analyze.py
python build_report.py
```

`analysis/inputs.json` contains group-level rates and prediction summaries,
not raw item text, individual response traces or private competition feedback.
The scripts verify the Brier decomposition and regenerate Tables 6–8 and the
reported sensitivity results. The random seed, resampling scheme, comparison
populations and limitations are in `analysis/config.json`.

To verify the inputs from the existing experiment workspace instead:

```sh
python analysis/collect_inputs.py /path/to/paiec-2026
```

This optional step requires the 20 pinned tables for five benchmarks, PyArrow
23.0.1 in that workspace's `.deps/`, and the original saved run directories
named in the configuration. It checks data hashes, disjoint pools, response
selection, saved predictions, Brier scores and exact expected ALC. It does not
download data. For reconstruction from raw tables, the original pinned project's
reproduction guide explains how to regenerate the saved experiments; generated
run names must be mapped to the same protocols before using this collector.
The aggregate-input route above is portable and needs no original run directory.

## Build the PDF

The vector plot is included. To redraw it, install ReportLab 4.4.9 and run:

```sh
python plot_calibration.py
```

The script uses Vera fonts bundled with ReportLab, with no system-font dependency.
Compile with pdfLaTeX, twice, from this folder:

```sh
pdflatex -interaction=nonstopmode -halt-on-error paiec_report.tex
pdflatex -interaction=nonstopmode -halt-on-error paiec_report.tex
```

The official NeurIPS 2026 style is unchanged. `final,sglblindworkshop` identifies
PAIEC on the title page. The source keeps the author and development disclosure.
The report has 7 main-text pages, 1 reference page and 5 appendix pages.
`source/submitted_report.tex` is an unchanged input snapshot used by the builder.

The original code remains pinned to
`d2d3e3c1e803880f4918f2f8065616b513731a40`; original CodaBench submission 992850
and both original ZIPs are unchanged. This source bundle is **not** a replacement
CodaBench submission or the previously submitted supplementary ZIP.

## Check the extracted bundle

Install `pypdf==6.21.4`, then run `python check_report.py`. This checks the
included PDF, original table values, deterministic statistics and LF JSON output.
If local `.aux` and `.log` files exist after compilation, they are checked too;
their absence is reported rather than treated as a completed compilation check.
On Windows and Linux, regenerated JSON uses LF without changing the statistics.

Code is MIT licensed. The report follows its OpenReview CC BY 4.0 license;
the official template and its dependencies retain their own notices. Publishing
this bundle does not establish a new OpenReview submission or competition result.
