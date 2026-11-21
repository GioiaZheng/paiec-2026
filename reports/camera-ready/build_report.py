"""Build a separate camera-ready source from the unchanged submitted manuscript."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMES = {'multi_swebench': 'Multi-SWE-bench', 'researchcodebench': 'ResearchCodeBench',
         'bertaqa': 'BertaQA', 'real_webagents': 'REAL', 'financebench': 'FinanceBench'}
ORDER = list(NAMES)


def interval(v):
    return f'[{v[0]:+.5f}, {v[1]:+.5f}]'


def main():
    src = HERE/'source/submitted_report.tex'
    assert hashlib.sha256(src.read_bytes()).hexdigest() == '6cbb19e654abae43a274b5930e6f86213df731ccebada926bbc576d3f08e842e'
    text = src.read_text(encoding='utf-8')
    result = json.loads((HERE/'analysis/results.json').read_text())

    def replace(old, new):
        nonlocal text
        assert text.count(old) == 1, old[:90]
        text = text.replace(old, new)

    replace('Most of the benefit comes from the one-label budget.',
            'On the two coding benchmarks, the one-label budget accounts for about 84\\% of the total ALC improvement.')

    replace(r'\usepackage[preprint]{neurips_2026}',
            r'\usepackage[final,sglblindworkshop]{neurips_2026}'+'\n'+
            r'\workshoptitle{Predictive AI Evaluation Competition (PAIEC)}')
    replace(r'\usepackage{url}', r'\usepackage{url}'+'\n'+r'\usepackage{graphicx}')
    replace('\\clearpage\n\\begin{table}[ht]', '\\begin{table}[ht]')
    replace('\\clearpage\n\\subsection{Official formative feedback}', '\\subsection{Official formative feedback}')
    replace(r'\subsection{Bounded lexical reweighting}', '\\clearpage\n'+r'\subsection{Bounded lexical reweighting}')
    replace('The coding exploration keeps normalized exact copies and detected lexical near-duplicates together.',
            'A guarded split assigns detected related items to the same pool rather than splitting them independently. The coding exploration keeps normalized exact copies and detected lexical near-duplicates together.')
    replace('Population & Mean ALC & Beta ALC & Improved & Worsened',
            r'Population & \shortstack{Empirical-mean\\ALC} & Beta ALC & Improved & Worsened')
    replace('All 12 coding losses occur below 10\\% evaluation success.',
            'On these same 85 coding groups, the observed three-seed ALC is 0.25527 for the empirical mean and 0.21963 for Beta(1,1); all three seeds favor shrinkage. This is a size-compatibility check, not a replay of the hosted draw.\n\nAll 12 coding losses occur below 10\\% evaluation success.')
    replace('Aggregate gains are more stable than conclusions about every individual group.',
            'The post-review analysis locates all 15 reversals below 20\\% evaluation success, including 11 below 10\\% (Appendix~\\ref{app:postreview}). Aggregate gains are more stable than conclusions about every individual group.')
    replace('The weaker estimator still beats the empirical mean\'s observed ALC of 0.234080 and retains its small-budget advantage, but the prespecified overall criterion fails.',
            'The weaker estimator still beats the empirical mean\'s observed ALC of 0.234080 and retains its small-budget advantage, but the prespecified overall criterion fails. A post-review pair bootstrap gives a 95\\% interval of [-0.00141, +0.00801] for its difference from Beta(1,1); the result does not establish that weaker shrinkage is significantly worse.')
    replace('Code for all experiments is available at', 'Code for the original experiments is available at')
    replace('Replay with four official workers covers six groups, three benchmarks and 962 source subject-item pairs. All probabilities and pairwise Brier/ALC agree within 1e-12. Each checkpoint mixes group labels, using 473 calls for 760 response rows and reusing 287 predictions. This checks packaging and workers, not private sampling.',
            'Replay with four official workers covers six groups and three benchmarks. Probabilities and pairwise Brier/ALC agree within \\(10^{-12}\\). This checks packaging and workers, not private sampling; Appendix A records the verification workload.')
    replace('Experiments use Python 3.12.2 and PyArrow 23.0.1 on Windows; Ubuntu WSL replay uses Python 3.14.4. No GPU or paid API is used. Configurations, hashes, commands and aggregates accompany the code. Independent recomputation verifies 11,592 probability/budget records for the weaker-prior comparison across 161 groups, excluding duplicate sensitivity evidence. That module passes the kit\'s sequential smoke check.',
            'Experiments use Python 3.12.2 and PyArrow 23.0.1 on Windows; Ubuntu WSL replay uses Python 3.14.4. No GPU or paid API is used. Configurations, hashes, commands and aggregates accompany the code. Independent recomputation checks the weaker-prior comparison, whose module passes the kit\'s sequential smoke check.')
    replace('All 19 project tests pass, covering exhaustive acquisition expectations, hand-calculated lexical weights and group isolation. Independent rescoring checks 4,439,754 lexical item-budget-seed records against original response rows, including identical split designs; this is a verification workload, not a sample size. The lexical ZIP passes official local checks, and four-worker Linux replay reproduces 4,560 response-level predictions across all six budgets. No extension is uploaded to CodaBench.',
            'All 19 original project tests pass, covering exhaustive acquisition expectations, hand-calculated lexical weights and group isolation. Independent rescoring checks the lexical predictions against response rows. The lexical ZIP passes official local checks and four-worker Linux replay. No extension is uploaded to CodaBench.')
    replace('Six public benchmarks offer limited generalization evidence. No benchmark-level confidence interval, statistical significance or final result is claimed.',
            'Six public benchmarks offer limited generalization evidence. Appendix~\\ref{app:postreview} adds post-review paired bootstrap and calibration diagnostics using already observed data. Their intervals describe resampling of this small, dependent panel; they do not establish coverage for future benchmarks or a final competition result.')
    replace('Its results describe a broader local population. Filtering coding groups by size and choosing small REAL groups addresses this mismatch only partly: neither reproduces the organizer\'s balancing and random group selection.',
            'Its results describe a broader local population. The kit skips complete groups that exceed the remaining cap; truncating BertaQA to sampled subgroups would change that contract. Filtering coding groups by size and choosing small REAL groups addresses this mismatch only partly: neither reproduces the organizer\'s balancing and random group selection.')
    replace('Use the project code with Python 3.12 and the pinned reference baseline.',
            'All commands in this appendix refer to the submitted checkout \\texttt{d2d3e3c}, whose scripts live at the repository root. They are not commands for the later reorganized \\texttt{experiments/} directory. Create a separate checkout without replacing an existing one:\n\\begin{verbatim}\ngit clone --config core.autocrlf=false \\\n  https://github.com/GioiaZheng/paiec-2026.git submitted-code\ngit -C submitted-code checkout \\\n  d2d3e3c1e803880f4918f2f8065616b513731a40\ncd submitted-code\n\\end{verbatim}\nUse Python 3.12 and the pinned reference baseline.')
    replace(r'\paragraph{Artifacts.}',
            r'''\paragraph{Verification workload.}
Baseline replay covers 962 source subject-item pairs and 760 response rows,
with 473 calls and 287 reused predictions per checkpoint. The weaker-prior
check covers 11,592 probability/budget records across 161 groups. Lexical
rescoring covers 4,439,754 item-budget-seed records, including identical split
designs; Linux replay checks 4,560 response-level predictions. These counts
describe executed checks, not independent statistical sample sizes.

\paragraph{Artifacts.}''')
    # Keep the reproduction appendix usable without repeating the detailed guide.
    a0 = text.index('\\section{Reproduction outline}')
    a1 = text.index('\\clearpage\n\\section{Follow-up specification', a0)
    text = text[:a0] + r'''\section{Reproduction outline}
The commands below refer to the submitted checkout \texttt{d2d3e3c}, whose
scripts live at the root, not the later \texttt{experiments/} directory.
Create a separate checkout:
\begin{verbatim}
git clone --config core.autocrlf=false \
  https://github.com/GioiaZheng/paiec-2026.git submitted-code
git -C submitted-code checkout \
  d2d3e3c1e803880f4918f2f8065616b513731a40
cd submitted-code
\end{verbatim}
Use Python 3.12 and the pinned reference baseline. Obtain the four formatted
tables per benchmark through authorized measurement-db access at the revision
in Section 3 and place them in \texttt{data/<benchmark>/}. Manifests record
their hashes. Source tables are not redistributed; ResearchCodeBench, REAL
and FinanceBench have unknown license metadata.

\paragraph{Build and check.}
Unpack the competition starting kit under \texttt{local/official/starting\_kit}.
From the submitted checkout root:
\begin{verbatim}
python -m pip install --target .deps -r requirements-local.txt
python run_baseline.py --starter-kit local/official/starting_kit
python -m unittest test_evaluation.py test_diagnostics.py
python -m unittest test_weaker_shrinkage.py
\end{verbatim}

\paragraph{Run and verify.}
The default pilot is coding with the guarded split. Set \texttt{--protocol}
and \texttt{--split-unit} as follows for the other designs:
\begin{center}
\begin{tabular}{lll}
\toprule
Dataset & Protocol file & Split options \\
\midrule
Coding & None (default) & \texttt{near}, \texttt{item} \\
BertaQA & \path{configs/bertaqa-validation.json} & \texttt{item}, \texttt{source} \\
REAL & \path{configs/real-validation.json} & \texttt{item}, \texttt{near} \\
FinanceBench & \path{configs/weaker-shrinkage.json} & \texttt{item}, \texttt{near} \\
\bottomrule
\end{tabular}
\end{center}
\begin{verbatim}
python evaluate_pilot.py
python verify_pilot.py runs/<run-id>
python analyze_pilot.py runs/<run-id>
python compare_shrinkage.py runs/<verified-run>
\end{verbatim}
Each pilot prints its new run directory. The verifier recomputes response-level
scores and pool separation. Pass verified coding-guarded, BertaQA-source,
REAL-item and FinanceBench runs together to \texttt{compare\_shrinkage.py}
to reproduce the ablation. It checks source hashes and saved labels;
\texttt{diagnose\_shrinkage.py} supplies the original expectation analysis.
Neither fits a predictor. Replay commands for four Linux workers and input
setup are in the submitted checkout's \texttt{REPRODUCIBILITY.md}.

\paragraph{Executed verification.}
Baseline replay covers 962 source subject-item pairs and 760 response rows,
with 473 calls and 287 reused predictions per checkpoint. The weaker-prior
check covers 11,592 probability/budget records across 161 groups. Lexical
rescoring covers 4,439,754 item-budget-seed records, including identical split
designs; Linux replay checks 4,560 response-level predictions. These are
verification workloads, not independent statistical sample sizes. Private
item-level outcomes and anonymous group identities are excluded from the report.
''' + text[a1:]
    appendix = r'''
\clearpage
\section{Post-review diagnostics}\label{app:postreview}
These analyses were specified and run on 21 November 2026 in response to
review, after all reported outcomes had been inspected. They reuse the
saved pools and acquisition trajectories, do not select a predictor, and
provide no new held-out validation. The submitted estimator and numerical
results in original Tables~\ref{tab:results}--\ref{tab:retrieval} are unchanged.

\subsection{Paired uncertainty summaries}
For each method comparison, first average its paired ALC differences over
the three acquisition seeds within each subject-benchmark pair. Resample
these pair-level differences with replacement separately within each benchmark,
preserving its pair count. We use 20,000 draws, random seed 20261121, and the
2.5th and 97.5th percentiles with linear interpolation. Table~\ref{tab:intervals}
reports the differences and descriptive 95\% bootstrap intervals. No seed or
response row is treated as an independent population replicate.

\begin{table}[ht]
\centering\small
\caption{Post-review paired ALC intervals. Negative favors the first method.
Split designs match their respective original tables; BertaQA uses item
pools in the first panel and source-question pools in the second.}
\label{tab:intervals}
\begin{tabular}{lrrl}
\toprule
Benchmark & Pairs & Difference & Pair bootstrap interval \\
\midrule
\multicolumn{4}{l}{Beta(1,1) minus empirical mean (Table~\ref{tab:results})} \\
@BASE_ROWS@
\midrule
\multicolumn{4}{l}{Beta(0.5,0.5) minus Beta(1,1) (Table~\ref{tab:weaker})} \\
@WEAK_ROWS@
\bottomrule
\end{tabular}
\end{table}

The primary comparison across 145 pairs has mean difference @BASE_DELTA@
and a stratified-pair interval @BASE_CI@. Across the 161 pairs in the weaker-prior
comparison, the mean difference is @WEAK_DELTA@, with interval @WEAK_CI@.
The latter averages development and validation panels and is not a new
confirmatory test. The FinanceBench-only interval crosses zero: failing
the original replacement rule is distinct from proving inferiority.

As a dependence sensitivity check, resample whole benchmark panels instead,
retaining all their pairs and recomputing the equal-pair mean for every draw.
The corresponding intervals are @BASE_CLUSTER@ (four primary benchmarks)
and @WEAK_CLUSTER@ (five weaker-prior benchmarks). These are conditional
resampling summaries, not reliable population-coverage statements: questions
and related model configurations are shared within panels, model identities can
recur between panels, and four or five benchmarks provide little information
about between-benchmark variation. Neither procedure averages over new pool
splits, unobserved responses or acquisition trajectories beyond the three saved
seeds. The exact expectations in Section~4 average acquisition more fully,
but are likewise conditional on the saved pools.

\clearpage
\subsection{Population sensitivity and individual reversals}
The 85 coding groups with 80--1,000 source items have observed ALC 0.25527
(empirical mean) versus 0.21963 (Beta(1,1)), compared with exact expectations
0.26075 and 0.22243. Per-seed observed differences are @SEED_DELTAS@.
These groups fit individually under the kit cap. Joint inclusion still depends
on benchmark/subject balancing, random tie-breaking and the remaining budget;
the figures do not reproduce that selection. The kit admits complete groups
and skips those that do not fit. In particular, the six 9,512-item BertaQA
groups would be excluded under this contract, not randomly truncated.
We therefore do not describe a BertaQA subgroup experiment as hosted-like.

To examine composition sensitivity, let $f$ be an imposed fraction of groups
with evaluation success below 10\%. Holding equal weights within each of the
two observed strata, the reweighted difference is
\begin{equation}
\Delta(f)=f\,\overline\Delta_{q<0.1}+(1-f)\,\overline\Delta_{q\geq0.1}.
\end{equation}
This uses evaluation outcomes retrospectively and supplies no feasible
test-time selection rule. It changes the group mix, not individual predictions.

\begin{table}[ht]
\centering\small
\caption{Coding sensitivity to the imposed low-success share $f$.
Differences are Beta(1,1) minus empirical mean; positive favors the mean.}
\label{tab:reweight}
\begin{tabular}{rrrrr}
\toprule
& \multicolumn{2}{c}{All 113 coding groups} & \multicolumn{2}{c}{85 size-compatible groups} \\
$f$ & Observed & Expected & Observed & Expected \\
\midrule
@MIX_ROWS@
\bottomrule
\end{tabular}
\end{table}

The original low-success shares are 36/113 (31.9\%) and 14/85 (16.5\%).
For all coding groups, the expected difference crosses zero at $f=0.773$;
the observed-seed difference crosses at $f=0.827$. For the size-compatible
subset the corresponding crossings are 0.808 and 0.717. These are algebraic
break-even points for fixed observed stratum means, not estimated universal
thresholds. The change between populations and between sampled and expected
scores shows why a mean improvement need not persist under a harder group mix.

All 15 coding sign reversals lie between 0.99\% and 19.68\% evaluation
success: 11 below 10\%, four in [10\%, 20\%), and none at or above 20\%.
Nine show an observed gain but an expected loss; six show an observed loss
but an expected gain. They are concentrated among low-success groups rather
than spread across the success-rate range. The lowest rate is about 1\%, so
this is not evidence of a sharp boundary specifically at 10\%.

\clearpage
\subsection{Calibration at the smallest nonzero budgets}
At budgets 1 and 3, each predictor takes only two or four distinct values,
respectively. We group by these exact probabilities rather than choosing
histogram bins. Every subject-benchmark pair and acquisition seed receives
equal weight; within a pair-seed case, evaluation response rows share its
weight equally. Thus repeated runs retain their scoring role without allowing
large pools to dominate the equal-pair objective. For category $j$, let $w_j$
be its weight, $p_j$ its prediction, and $\bar y_j$ its weighted outcome rate.
With overall rate $\bar y$, the weighted decomposition is
\begin{equation}
\mathrm{Brier}=
\underbrace{\sum_j w_j(p_j-\bar y_j)^2}_{\mathrm{reliability}}
-\underbrace{\sum_j w_j(\bar y_j-\bar y)^2}_{\mathrm{resolution}}
+\underbrace{\bar y(1-\bar y)}_{\mathrm{uncertainty}}.
\end{equation}
Direct response-level scoring and this identity agree within $10^{-12}$.
Table~\ref{tab:calibration} uses the 145 pairs and split designs of
Table~\ref{tab:results}. Lower reliability is better; this finite-sample
diagnostic is not a population calibration guarantee.

\begin{table}[ht]
\centering\small
\caption{Exact-category calibration summaries, pooled across the primary four
benchmarks. Resolution and uncertainty are shared by both methods.}
\label{tab:calibration}
\begin{tabular}{rlrrrr}
\toprule
Budget & Method & Brier & Reliability & Resolution & Uncertainty \\
\midrule
@CAL_ROWS@
\bottomrule
\end{tabular}
\end{table}

\begin{figure}[ht]
\centering
\includegraphics[width=\linewidth]{figures/reliability.pdf}
\caption{Weighted outcome rate against each exact prediction value. The dashed
line denotes perfect reliability; joining points is a visual guide only.
The same outcome groups move horizontally when shrinkage is applied.}
\label{fig:reliability}
\end{figure}

Reliability decreases at both budgets in each of the four benchmarks
separately as well as in the pooled panel. Shrinkage is an injective affine
transform of the success count at a fixed budget, so it preserves category
membership and resolution exactly. These gains concern less extreme group
probabilities, not newly learned item discrimination. Pooling may conceal
subgroup miscalibration, and no binomial error bars are attached to the shared
evaluation outcomes or repeated seed cases.

\paragraph{Recomputing the additions.}
The \href{https://github.com/GioiaZheng/paiec-2026/releases/download/camera-ready-2026-11-21/paiec-camera-ready-source.zip}{camera-ready diagnostic bundle (fixed release: camera-ready-2026-11-21)}
separates these additions from the original experiments at \texttt{d2d3e3c}.
It contains the configuration, aggregate group inputs, scripts, tests and hashes.
Run \texttt{python analysis/analyze.py} from the extracted bundle using
Python 3.12 to regenerate the statistics. The optional collector checks the
pinned response tables and saved trajectories: 6,012 original probability/budget
records across 167 pair/split combinations agree. No raw item text or response
traces are included. The original code pin and CodaBench submission remain unchanged.
'''
    replacements = {}
    for prefix, label in [('BASE','baseline'),('WEAK','weaker')]:
        val = result[label]
        lines = []
        for b in ORDER:
            if b not in val['by_benchmark']:
                continue
            v = val['by_benchmark'][b]
            lines.append(f"{NAMES[b]} & {v['pairs']} & {v['delta']:+.6f} & {interval(v['interval'])} \\\\")
        replacements[prefix+'_ROWS'] = '\n'.join(lines)
        replacements[prefix+'_DELTA'] = f"{val['delta']:+.5f}"
        replacements[prefix+'_CI'] = r'\mbox{'+interval(val['pair_interval'])+'}'
        replacements[prefix+'_CLUSTER'] = r'\mbox{'+interval(val['benchmark_interval'])+'}'
    replacements['SEED_DELTAS'] = ', '.join(f"{v['beta_1_1']-v['empirical_mean']:+.5f}" for v in result['compatible_coding']['per_seed'].values())
    mixrows = []
    for i, f in enumerate([0,.25,.5,.75,1]):
        vals = [result['low_success_sensitivity'][p][kind]['mixtures'][i]['delta']
                for p in ['all_coding','compatible_coding'] for kind in ['observed_alc','expected_alc']]
        mixrows.append(f'{f:.2f} & '+' & '.join(f'{v:+.5f}' for v in vals)+r' \\')
    replacements['MIX_ROWS'] = '\n'.join(mixrows)
    calrows = []
    for n in ['1','3']:
        for m, name in [('empirical_mean','Empirical mean'),('beta_1_1','Beta(1,1)')]:
            v = result['calibration']['all'][n][m]
            calrows.append(f'{n} & {name} & '+' & '.join(f'{v[k]:.5f}' for k in ['brier','reliability','resolution','uncertainty'])+r' \\')
    replacements['CAL_ROWS'] = '\n'.join(calrows)
    for k, v in replacements.items():
        assert '@'+k+'@' in appendix
        appendix = appendix.replace('@'+k+'@', v)
    assert '@' not in appendix
    replace(r'\end{document}', appendix+'\n'+r'\end{document}')
    (HERE/'paiec_report.tex').write_text(text, encoding='utf-8', newline='\n')
    print('Built separate camera-ready LaTeX source.')


if __name__ == '__main__':
    main()
