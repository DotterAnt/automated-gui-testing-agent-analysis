# Experiment comparison reports

## Current native / MCP / AI-only / model report (updated 8 October 2026)

```powershell
python experiment-comparison/analyze_current.py --source "C:\Users\DottedAnt\Downloads\results" --output analysis-output/batch-2026-10-07
python -m unittest discover -s experiment-comparison -p "test_*.py"
```

Open `analysis-output/batch-2026-10-07/report.html`. The report has per-run
evidence and methodology pages, 29 SVG/PNG figures, session/application
summary CSVs and a complete JSON export. A PDF is saved at
`output/pdf/experiment-analysis-2026-10-07.pdf`; the offline companion and PDF
are bundled in `analysis-output/experiment-analysis-2026-10-07.zip`.

Observed-progress line charts retain individual tasks and pointwise setup
means from the earlier report. Native versus MCP includes a pooled view and
all ten application views. Native/MCP/AI-only includes a pooled shared-Office
view and separate Excel, PowerPoint and Word views. The HTML application
selectors can show one view or all charts; the PDF includes every view.
The pooled ten-application Native-versus-MCP chart ends at 60 minutes, with
continuation markers and a caption identifying the longer sessions. This
display limit does not remove sessions or crop the exported curve data.
This chart also marks mean AGTA exploration completion, measured from task
start to the first confirmed successful `agta_explore` Complete response.
The marker states coverage; sessions without a confirmed completion remain
in the progress curves. Receipt timings and log citations are exported in
`data/exploration_completion.csv`.
Exact timestamp means are exported in `data/progress_curves.csv`. Every task
remains in its setup's denominator after completion, and plotted row counts
are cumulative evidence across attempts rather than single-replay outcomes.

The Office model comparison puts native and MCP side by side on a common
0-60 minute scale for Excel, PowerPoint and Word. It includes the GPT-5.5
medium-effort baseline and light/low-effort newer models in this order:
5.5, 5.6 Luna, 5.6 Sol, 6 Luna, 6 Sol, 6.1 Sol. Missing cells are left empty;
failed tasks remain marked in all-attempt means. Individual application
figures and `data/application_model_comparison.csv` are also exported.

The combined Office chart compares only GPT-5.5 medium, GPT-5.6 Luna light,
GPT-6 Luna light and GPT-6.1 Sol light, in release order. Native and MCP
bars average the three application means with equal one-third weights.
Failed attempts remain in those means; pass counts and hatching disclose
incomplete results. `data/pooled_model_comparison.csv` records application
counts, means and contributing sessions. The 8 October GPT-6 Luna MCP Word
session completes its three-application coverage. The report now includes
110 tasks from 112 logs, with 27 newer-model tasks.

The cost comparison applies Standard API prices checked on 8 October 2026
to the final cumulative token counters. These are USD token-cost equivalents,
not Codex/ChatGPT subscription bills. Ordinary input, cached reads, cache
writes and output are priced separately; write charges replace ordinary input
charges, and reasoning tokens are already included in output. Recorded cache
write counts are zero. Every included session has per-request usage below
the long-context pricing boundary. Failed attempts remain in the ledger.
The main Office cost chart uses the same equal application weights as the
runtime chart. Supplemental Sol costs retain their Excel-only scope.
Exports: `data/cost_sessions.csv`, `data/cost_comparisons.csv`,
`data/cost_by_application.csv` and the dated `data/pricing_snapshot.json`.
The static rates in `cost_current.py` must be reverified for a later price date;
future long-context sessions require request/session surcharge allocation.

The GPT-5.5 versus 6.1 investigation separates price changes from token
usage using cross-price counterfactuals and a two-factor Shapley decomposition.
It uses all 19 AGTA Office sessions, identical per-application testcase hashes
and equal application weights. Exploration timings recognize newer namespaced
calls inside exec wrappers; the original ten-application marker is unchanged.
`data/model_gap_analysis.json` and three `model_gap_*.csv` exports retain the
phase receipts, measurements and accounting decomposition. Medium versus low
effort and different client/tool versions prevent a model-only causal claim.

Only `native`, `mcp`, `aionly` and `newcodex` are discovered; `cli`, `old` and
nested `old` directories are excluded. The primary model comparison uses the
recorded 5.6 Luna, 6 Luna and 6.1 Sol identities at low effort. Supplemental
5.6 Sol and 6 Sol runs are compared on Excel. Two mislabeled 6 Luna logs are
attributed using their recorded model. Failed tasks retain runtime, token
and observed-prefix measurements. Missing-log folders remain in inventory.

The older Paint testcase is kept superseded because its PDF visual-content
expectation differs from the replacement's file-existence expectation.
An aborted Access/MCP log misfiled under AI-only is separately listed.
Focused source audits distinguish five-pass outputs from known GUI-route
bypasses; these findings do not certify every other script.

Requires Python with NumPy, Matplotlib, ReportLab and Pillow. The current
workflow supports direct tool logs and newer JavaScript exec wrappers,
including linked streaming result polls. Source logs and scripts are data;
none are executed. Older reports below are preserved as historical outputs.

## Refreshed native / MCP batch (4 October 2026)

```powershell
python experiment-comparison/analyze_batch.py --source "C:\Users\DottedAnt\Downloads\results" --output analysis-output/batch-2026-10-04
python -m unittest discover -s experiment-comparison -p "test_*.py"
```

Open `analysis-output/batch-2026-10-04/session_comparison.html`. It includes a
separate evidence page, SVG/PNG charts, and session/application/inventory CSVs
plus a JSON export. It reads the current `native` and `mcp` folders; `mcp/old`
is excluded. The old native `paint-37m` is explicitly superseded by the new
native Paint run as requested by the experimenter. The new MCP Notepad,
Paint, and Word runs are included. Remaining Word, Photos, and PowerPoint
testcase variants are retained in the primary comparison and documented,
with a matching-content sensitivity check. Missing-log folders stay in the
inventory without invented outcomes or timings.

The refreshed batch uses actual event timestamps and task turn IDs when
exported session metadata is reused. It identifies applications from
captured testcase content and deduplicates framework result reads by
execution ID. The earlier report below is preserved separately.

## Earlier native / CLI batch

Build the offline report from the supplied October result bundles:

```powershell
python experiment-comparison/build_report.py --source "C:\Users\DottedAnt\Downloads\results" --output analysis-output
python -m unittest discover -s experiment-comparison -p "test_*.py"
```

Requires Python, Matplotlib and NumPy. The entry point is `analysis-output/experiment_comparison.html`, with evidence and methodology pages, SVG/PNG figures, and CSV/JSON exports beside it. `analysis-output` is already ignored by this repository.

The source directory is read-only. Only its `native` and `cli` subdirectories are discovered; `old` is excluded. All included runs remain in the primary summaries, including earlier CLI/framework versions and a native folder labelled failed. The author’s statement that early system changes were mostly bug fixes is documented without inventing version IDs or a cutoff.

Duration ends at the last task-complete event, so later settings-only events cannot inflate it. Token counters are cumulative and never summed across samples. The progress plot uses first observed PASS receipts from script outputs/results, not source-code strings, assistant claims or inferred GUI action times. Full five-pass summaries can be recovered from truncated detail output. See the generated methodology page for definitions and limitations.

The tests cover JSONL record boundaries, truncated summaries, timestamped console rows, script-launch recognition, directory exclusion, late metadata events, corpus invariants and report links. No supplied PowerShell code or logged command is executed.
