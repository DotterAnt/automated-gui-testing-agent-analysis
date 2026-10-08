"""Build a reproducible, offline native-versus-framework experiment report."""
from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
from statistics import mean, median

from extract import extract_all, summarize, GROUPS, METRICS, read_records, body
from figures import build_figures

HERE = Path(__file__).resolve().parent
DEFAULT_SOURCE = Path(r"C:\Users\DottedAnt\Downloads\results")
DEFAULT_OUTPUT = HERE.parent / "analysis-output"


def esc(value):
    return html.escape(str(value))


def number(value, digits=2):
    return f"{value:,.{digits}f}" if value is not None else "not recorded"


def pct(native, cli):
    return 100*(cli/native-1)


def source_link(data, run, line=None, label="source log"):
    url=(Path(data['source_root'])/run['file']).as_uri()
    return f'<a href="{esc(url)}">{esc(label)}{f" · line {line}" if line else ""}</a>'


def run_link(run):
    return f'<a href="experiment_evidence.html#{run["id"]}">{run["id"]}</a>'


STYLE = """
:root{--ink:#183049;--muted:#57687b;--line:#dce4ed;--blue:#2864ad;--orange:#c35b32;--paper:#fff;--bg:#f3f6fa}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);font:16px/1.65 system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink)}
header{background:#152d46;color:white;padding:50px max(28px,calc((100% - 1180px)/2)) 34px}header p{max-width:850px;color:#d5e1ee;font-size:18px}h1{font-size:clamp(30px,4vw,48px);line-height:1.12;letter-spacing:-1.2px;margin:14px 0 20px}h2{font-size:27px;line-height:1.25;margin:0 0 18px}h3{font-size:19px;margin:20px 0 8px}p{margin:12px 0}.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:2px;font-weight:750;color:#abc8e7}.wrap{max-width:1236px;padding:24px 28px 64px;margin:auto}nav{display:flex;gap:18px;flex-wrap:wrap;padding:16px 0 4px;font-size:14px}nav a{color:#d5e7ff}a{color:#195c9f;text-underline-offset:3px}section,.panel{background:white;border:1px solid var(--line);border-radius:14px;padding:28px;margin:24px 0;scroll-margin-top:20px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:8px 0 24px}.card{background:white;border:1px solid var(--line);border-top:4px solid var(--blue);border-radius:12px;padding:20px}.card.orange{border-top-color:var(--orange)}.card strong{font-size:30px;display:block;letter-spacing:-.7px;line-height:1.3;margin:7px 0}.card span{font-size:13px;color:var(--muted)}.card small{font-size:13px;display:block;color:var(--muted)}.cols{display:grid;grid-template-columns:1fr 1fr;gap:28px}.note{background:#eff5fc;border-left:4px solid var(--blue);padding:16px 20px;border-radius:3px;margin:18px 0}.caution{background:#fff6e9;border-left-color:#b4771d}.quiet{font-size:14px;color:var(--muted)}figure{margin:22px 0 12px}figure img{display:block;max-width:100%;width:100%;height:auto}figcaption{font-size:14px;color:var(--muted);margin-top:10px}table{width:100%;border-collapse:collapse;font-size:14px}th{text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:.4px;background:#edf2f8}td,th{padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.table-wrap{overflow:auto;margin:18px 0}tbody tr:hover{background:#f8fafd}.badge{display:inline-block;padding:3px 9px;font-size:12px;border-radius:20px;background:#edf3fa;white-space:nowrap}.badge.warn{background:#fff0d6;color:#775016}.native{color:var(--blue)}.cli{color:var(--orange)}.controls{display:flex;gap:18px;flex-wrap:wrap;align-items:end;margin:18px 0}.controls label{display:flex;flex-direction:column;gap:6px;font-size:13px;font-weight:650}select,input,button{font:inherit;border:1px solid #aebccd;border-radius:6px;padding:9px 12px;background:white;color:var(--ink)}input{max-width:100%;min-width:220px}button{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f5f8;padding:18px;border-radius:8px;font-size:13px;line-height:1.6;max-height:460px;overflow:auto}code{font-family:Consolas,monospace;font-size:.9em;overflow-wrap:anywhere}details{margin:14px 0}summary{cursor:pointer;font-weight:650}ul{padding-left:22px}li{margin:8px 0}.result-count{font-size:14px;color:var(--muted)}footer{font-size:13px;color:var(--muted);margin-top:30px}.run-section{border-top:4px solid var(--blue)}.run-section.cli-run{border-top-color:var(--orange)}.progress-frame[hidden]{display:none}.source-path{overflow-wrap:anywhere}
@media(max-width:820px){.cards{grid-template-columns:1fr 1fr}.cols{grid-template-columns:1fr}.wrap{padding:16px}section{padding:20px}header{padding:32px 20px}.card strong{font-size:25px}}@media(max-width:480px){.cards{grid-template-columns:1fr}}
@media print{body{background:white}header{background:white;color:#183049;padding:20px 0}header p{color:#57687b}nav,.controls{display:none}.wrap{padding:0}section,.card{break-inside:avoid}.progress-frame[hidden]{display:none}a{color:inherit}.cards{grid-template-columns:repeat(2,1fr)}}
"""


def page(title, subtitle, content, script=""):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{STYLE}</style></head><body>
<header><div class="eyebrow">GUI test authoring · experiment analysis · 1 October 2026</div><h1>{esc(title)}</h1><p>{subtitle}</p>
<nav aria-label="Report navigation"><a href="experiment_comparison.html">Comparison</a><a href="experiment_comparison.html#progress">Progress over time</a><a href="experiment_comparison.html#findings">Findings</a><a href="experiment_evidence.html">Run evidence</a><a href="experiment_methodology.html">Method &amp; limitations</a><a href="experiment-data/metrics.csv" download>Metrics CSV</a></nav></header>
<main class="wrap">{content}<footer>Read-only analysis of supplied logs and script files. Test scripts were not executed. Figures and downloadable data are bundled locally; no network, analytics, or external JavaScript is required.</footer></main>{script}</body></html>'''


def figure(name, caption):
    return f'<figure><img src="experiment-figures/{name}.svg" alt="{esc(caption)}" loading="lazy"><figcaption>{caption} <a href="experiment-figures/{name}.png" download>PNG</a> · <a href="experiment-figures/{name}.svg" download>SVG</a></figcaption></figure>'


def comparison_rows(runs):
    summaries=summarize(runs)
    spec=[("minutes","Session duration","min",1),("total_tokens","Total tokens","million",1e6),
          ("uncached_input_tokens","Uncached input tokens","thousand",1000),("output_tokens","Output tokens","thousand",1000),
          ("script_launches","Generated-script launch requests","calls",1),("patch_calls","Patch tool calls","calls",1),
          ("shell_calls","Shell tool calls","calls",1),("image_calls","Image-view tool calls","calls",1),
          ("tool_calls","All agent tool calls","calls",1),("tool_text_kib","Returned tool text","KiB",1)]
    rows=""
    for key,label,unit,scale in spec:
        n=summaries['native'][key];f=summaries['cli'][key]
        rows+=f'<tr><td>{label} <span class="quiet">({unit})</span></td><td class="num">{n["mean"]/scale:,.2f}</td><td class="num">{f["mean"]/scale:,.2f}</td><td class="num">{pct(n["mean"],f["mean"]):+.1f}%</td><td class="num">{n["median"]/scale:,.2f} / {f["median"]/scale:,.2f}</td></tr>'
    return '<div class="table-wrap"><table><thead><tr><th>Metric per session</th><th class="num">Native mean</th><th class="num">CLI + framework mean</th><th class="num">Change</th><th class="num">Medians N / F</th></tr></thead><tbody>'+rows+'</tbody></table></div>'


def sensitivity(runs):
    cases={g:{r['testcase']['sha256'] for r in runs if r['group']==g} for g in GROUPS}
    common=cases['native'] & cases['cli']
    selections=[('All supplied runs',runs),('Exact captured testcase shared by both groups',[r for r in runs if r['testcase']['sha256'] in common]),
                ('Without the native folder labelled failed',[r for r in runs if not r['folder_failed_label']]),
                ('Without the longest native session',[r for r in runs if r['id']!='N-SNIPPINGTOOL-01'])]
    result=[]
    for label,sample in selections:
        groups={g:[r for r in sample if r['group']==g] for g in GROUPS}
        n=mean(r['minutes'] for r in groups['native']);f=mean(r['minutes'] for r in groups['cli'])
        result.append({'label':label,'native_n':len(groups['native']),'cli_n':len(groups['cli']),'native_mean':n,'cli_mean':f,'change_pct':pct(n,f)})
    apps=sorted({r['app'] for r in runs})
    n=mean(mean(r['minutes'] for r in runs if r['app']==app and r['group']=='native') for app in apps)
    f=mean(mean(r['minutes'] for r in runs if r['app']==app and r['group']=='cli') for app in apps)
    result.insert(1,{'label':'Equal weight for each of the 10 applications','native_n':24,'cli_n':25,'native_mean':n,'cli_mean':f,'change_pct':pct(n,f)})
    return result


def overview(data):
    runs=data['runs'];summary=data['summary'];n=summary['native'];f=summary['cli']
    body_html=f'''<div class="cards">
<div class="card"><span>Session duration · mean</span><strong>{n['minutes']['mean']:.1f} → {f['minutes']['mean']:.1f} min</strong><small>{-pct(n['minutes']['mean'],f['minutes']['mean']):.1f}% shorter with CLI + framework</small></div>
<div class="card orange"><span>Total tokens · mean</span><strong>{n['total_tokens']['mean']/1e6:.2f} → {f['total_tokens']['mean']/1e6:.2f} M</strong><small>{pct(n['total_tokens']['mean'],f['total_tokens']['mean']):.1f}% more reported tokens</small></div>
<div class="card"><span>Script launch requests · mean</span><strong>{n['script_launches']['mean']:.1f} → {f['script_launches']['mean']:.1f}</strong><small>{-pct(n['script_launches']['mean'],f['script_launches']['mean']):.1f}% fewer launch calls</small></div>
<div class="card orange"><span>Included evidence</span><strong>49 sessions</strong><small>24 native · 25 CLI + framework<br>10 applications · all GPT-5.5</small></div></div>
<div class="note"><strong>Scope.</strong> Includes all logs under <code>results/native</code> and <code>results/cli</code>. The <code>old</code> directory is excluded. Earlier CLI + framework runs remain included: the experimenter reports that these used an older system version and that changes were mostly bug fixes. Exact per-run versions and a verified change boundary are not available in this analysis.</div>
<section id="findings"><h2>What the new measurements suggest</h2><div class="cols"><div><h3>Less elapsed authoring time and rework</h3><p>CLI + framework has a lower mean authoring duration in all 10 application categories. The pooled mean is {f['minutes']['mean']:.2f} minutes versus {n['minutes']['mean']:.2f}; medians are {f['minutes']['median']:.2f} versus {n['minutes']['median']:.2f}. Fewer script launch requests and patch calls are consistent with reusable automation reducing implementation and repair work.</p><p>This is an observed association between complete authoring setups. It does not identify the isolated effect of the CLI, framework, bug fixes, or interaction policy.</p></div><div><h3>Faster does not mean fewer tokens</h3><p>Total tokens rose {pct(n['total_tokens']['mean'],f['total_tokens']['mean']):.1f}% and uncached input rose {pct(n['uncached_input_tokens']['mean'],f['uncached_input_tokens']['mean']):.1f}%, while output tokens fell {-pct(n['output_tokens']['mean'],f['output_tokens']['mean']):.1f}%. The setup appears to trade more input/context for less generated output and fewer repair iterations. Returned tool text is also larger, but the logs do not isolate its contribution to token usage.</p><p>No monetary cost claim is made. Cached and uncached input must be distinguished, and these logs do not contain billed cost.</p></div></div>
<div class="note caution"><strong>PASS is a reported result, not an independent acceptance test.</strong> All 49 sessions have a runtime output or result read reporting all five steps passed. Yet <a href="experiment_evidence.html#N-NOTEPAD-01">N-NOTEPAD-01</a>, whose folder is labelled failed, directly writes the expected text and PDF during recovery and still reports PASS. It remains in the time/token analysis and is explicitly flagged; 49/49 must not be presented as a verified success rate.</div></section>
<section id="duration"><h2>01 · Duration within each application</h2><p>Small dots show every session; diamonds show group means. Connecting ranges are observed minima and maxima, not confidence intervals. Sample sizes vary from one to six per setup/application, so the pooled means should be read alongside these categories.</p>'''
    body_html+=figure('duration-by-app','Elapsed authoring time through the last recorded task completion. This includes exploration, script development, trial runs, waiting, repairs and final reporting; it is not the runtime of the finished script.')
    body_html+='''<p>Individual runs overlap even where the group averages differ. The fastest native Excel session is faster than every CLI + framework Excel session; one CLI + framework Paint session is slower than the sole native Paint session. The measurements do not establish a universal per-run advantage.</p></section>
<section id="tokens"><h2>02 · Token use and the efficiency tradeoff</h2><p>Every point is a session and each vertical bar is a group mean. Total tokens include repeatedly supplied input, including cached input; they are not unique words read. Reasoning tokens are part of output tokens and are not added a second time.</p>'''
    body_html+=figure('tokens','Token distributions from final cumulative usage counters. Cache treatment explains why total-token and uncached-input comparisons should be shown separately.')
    body_html+=figure('tradeoff-by-app','Within-application changes in mean duration and total tokens. Negative values mean less; positive values mean more. These are descriptive group comparisons, not paired trials.')
    body_html+='</section><section id="effort"><h2>03 · Authoring effort and tool use</h2><p>Launch requests count shell tool calls that start an identified generated test script, including attempts that fail at startup. Patch calls include initial creation and failed/rejected edits; they are a proxy for editing effort, not a count of defects.</p>'
    body_html+=figure('authoring-effort','All sessions are retained. Fewer launch and patch calls coexist with slightly more shell calls in the CLI + framework setup, which also uses shell calls for exploration and structured tooling.')
    body_html+=comparison_rows(runs)
    body_html+='''<p class="quiet">Image-view calls measure images opened by the agent, not screenshots saved by scripts. Returned text is UTF-8 text from recorded tool outputs, excludes embedded image bytes, and is sensitive to logging format and truncation. A shell call can contain multiple operations.</p></section>
<section id="goal-evidence"><h2>Goal adherence: what is actually evidenced?</h2><div class="table-wrap"><table><thead><tr><th>Evidence dimension</th><th>Native</th><th>CLI + framework</th></tr></thead><tbody>
<tr><td>All five steps reported PASS in a runtime result</td><td>24 / 24 sessions</td><td>25 / 25 sessions</td></tr>
<tr><td>Separately supplied generated script</td><td>18 / 24 sessions</td><td>25 / 25 sessions</td></tr>
<tr><td>Cleanup reporting</td><td>Varies across custom logs and author statements; not normalized into a comparable success count</td><td>25 / 25 final result summaries report cleanupOk=true</td></tr>
<tr><td>Interaction contract</td><td>Prompt requires visible controls and forbids shortcuts/clipboard</td><td>25 / 25 final runtime policies say GuiNavigation; documented navigation/focused-input routes are permitted</td></tr>
<tr><td>Independent artifact acceptance and fresh replay</td><td>Not measured by this analysis</td><td>Not measured by this analysis</td></tr>
</tbody></table></div><p>The framework provides more uniform result and cleanup reporting, making this evidence easier to extract. Uniform reporting alone does not establish stronger assertions or more reliable tests. The known Notepad direct-output fallback demonstrates why acceptance must examine the action route and actual artifacts as well as the PASS label.</p></section>
<section id="progress"><h2>04 · Recorded progress over time</h2><p>Each thin line is a session; each bold line is the pointwise mean for that setup. A step is counted when an eligible execution output or result read first records it as PASS. Select an application to compare a more similar workflow.</p>
<div class="controls"><label>Application<select id="progress-app"><option value="all">All applications</option>'''
    apps=sorted({(r['app'],r['app_key']) for r in runs})
    body_html+=''.join(f'<option value="{key}">{app}</option>' for app,key in apps)+'</select></label></div>'
    for app,key in [('All applications','all'),*apps]:
        caption=f'{app}: cumulative distinct steps with recorded PASS results; full group denominators are retained after a session ends.'
        if key=='all':
            caption+=' Display limited to the first 60 minutes; all 49 sessions remain in the averages. Select Snipping Tool to see the longest run in full.'
        body_html+=f'<div class="progress-frame" data-progress="{key}" {"hidden" if key!="all" else ""}>'+figure('progress-'+key,caption)+'</div>'
    body_html+='''<div class="note caution"><strong>Observation time, not exact GUI completion time.</strong> Tool results often deliver several rows together. A complete five-pass summary can establish all five at once even when the detailed payload is truncated. Earlier successes survive later failures and may come from different attempts. Flat sections and jumps therefore describe evidence appearing in the log; they do not directly measure agent productivity or successful execution speed. All-app averages also mix task difficulty.</div></section>
<section id="sensitivity"><h2>05 · How much do the conclusions depend on the sample?</h2><p>The main analysis retains every included run, including older system versions, the labelled failure, and the 115.9-minute native Snipping Tool session. These transparent sensitivity summaries change the weighting or omit specified observations to show their influence.</p>
<div class="table-wrap"><table><thead><tr><th>Duration comparison</th><th class="num">n N / F</th><th class="num">Native mean</th><th class="num">CLI + framework mean</th><th class="num">Change</th></tr></thead><tbody>'''
    for row in data['sensitivity']:
        body_html+=f'<tr><td>{row["label"]}</td><td class="num">{row["native_n"]} / {row["cli_n"]}</td><td class="num">{row["native_mean"]:.2f} min</td><td class="num">{row["cli_mean"]:.2f} min</td><td class="num">{row["change_pct"]:+.1f}%</td></tr>'
    body_html+='''</tbody></table></div><p>The direction of the duration difference persists under these checks. They do not correct differences in interaction rules, system version, collection order, or human assistance. The exact-testcase row excludes five native Word sessions with a simpler CSV and one native PowerPoint session with different expected text. It matches testcase specifications, not model seeds or desktop state.</p>'''
    body_html+=figure('collection-timeline','Collection dates (UTC) show that the two setups were mostly measured at different times. Earlier CLI + framework versions are included, with no guessed version cutoff.')
    body_html+='''</section><section id="runs"><h2>06 · Explore the individual runs</h2><p>Follow any run ID for its provenance, captured testcase, launch commands, step observations and final author statement.</p><div class="controls"><label>Application<select id="run-app"><option value="all">All applications</option>'''
    body_html+=''.join(f'<option value="{key}">{app}</option>' for app,key in apps)
    body_html+='''</select></label><label>Setup<select id="run-group"><option value="all">Both setups</option><option value="native">Native (baseline)</option><option value="cli">CLI + framework</option></select></label><label>Search<input id="run-search" type="search" placeholder="Run ID or folder"></label><button id="run-reset" type="button">Reset</button></div><p id="run-count" class="result-count" aria-live="polite">49 sessions shown</p><div class="table-wrap"><table><thead><tr><th>Run / source folder</th><th>Application</th><th>Setup</th><th class="num">Minutes</th><th class="num">Total tokens (M)</th><th class="num">Launches</th><th class="num">Patches</th><th>Evidence note</th></tr></thead><tbody id="run-table">'''
    for r in runs:
        notes=[]
        if r['folder_failed_label']:notes.append('Labelled failed · direct-output fallback')
        if not r['testcase']['has_data']:notes.append('Simpler CSV')
        if r['id']=='N-POWERPOINT-03':notes.append('Different expected text')
        if len(r['users'])>1:notes.append('User continuation')
        if r['raw_log_span_minutes']-r['minutes']>1:notes.append('Post-task event excluded')
        if not r['scripts']:notes.append('No separate script copy')
        body_html+=f'<tr data-app="{r["app_key"]}" data-group="{r["group"]}"><td>{run_link(r)}<br><span class="quiet">{esc(r["folder"])}</span></td><td>{r["app"]}</td><td class="{r["group"]}">{GROUPS[r["group"]]}</td><td class="num">{r["minutes"]:.2f}</td><td class="num">{r["total_tokens"]/1e6:.2f}</td><td class="num">{r["script_launches"]}</td><td class="num">{r["patch_calls"]}</td><td>{esc("; ".join(notes)) or "Five-step PASS recorded"}</td></tr>'
    body_html+='''</tbody></table></div></section><section><h2>What a stronger follow-up would test</h2><p>Freeze and record the CLI/framework versions, align testcase contents and permitted interaction routes, reset the desktop between sessions, randomize setup order, and repeat each application with balanced counts. Retain failed attempts and output artifacts. Apply independent checks for saved content, reopen persistence, printed content and cleanup, then replay the final scripts in fresh environments. Record UTC step start/end events separately from the authoring log.</p><p>That experiment could distinguish faster authoring from better test correctness and replay reliability. The present report supports the authoring-efficiency hypothesis while revealing a higher input-token burden and a need for stronger acceptance checks.</p></section>'''
    script='''<script>
const progressSelect=document.getElementById('progress-app');
progressSelect.addEventListener('change',()=>{for(const item of document.querySelectorAll('[data-progress]'))item.hidden=item.dataset.progress!==progressSelect.value});
const appSelect=document.getElementById('run-app'),groupSelect=document.getElementById('run-group'),search=document.getElementById('run-search');
function filterRuns(){let count=0;for(const row of document.querySelectorAll('#run-table tr')){const shown=(appSelect.value==='all'||row.dataset.app===appSelect.value)&&(groupSelect.value==='all'||row.dataset.group===groupSelect.value)&&row.textContent.toLowerCase().includes(search.value.trim().toLowerCase());row.hidden=!shown;if(shown)count++}document.getElementById('run-count').textContent=`${count} of 49 sessions shown`}
appSelect.addEventListener('change',filterRuns);groupSelect.addEventListener('change',filterRuns);search.addEventListener('input',filterRuns);
document.getElementById('run-reset').addEventListener('click',()=>{appSelect.value='all';groupSelect.value='all';search.value='';filterRuns()});
</script>'''
    return page('Native vs. CLI + framework','49 authoring sessions across 10 desktop applications. Shorter sessions and fewer iterations, alongside higher input-token use.',body_html,script)


def method(data):
    content=f'''<section><h2>Corpus and inclusion</h2><p class="source-path">Source root: <code>{esc(data['source_root'])}</code>. All 24 JSONL logs under <code>native</code> and all 25 under <code>cli</code> are included. The <code>old</code> directory is excluded by an explicit directory allow-list and is not part of any chart, denominator or evidence extract.</p><p>The 49 logs are distinct by SHA-256. All report GPT-5.5 and contain a five-row testcase read. There are 43 separately supplied PowerShell scripts; the six missing script copies do not cause their logs to be excluded. Source hashes and relative paths are in <a href="experiment-data/metrics.json">metrics.json</a>.</p>
<h3>Version handling</h3><p>The experimenter states that some early CLI + framework sessions used an older version and that changes were mostly bug fixes. All these sessions are retained. This statement is provenance supplied by the experimenter, not a verified commit-level change audit. No version labels, cutover date or causal effect of bug fixes are inferred from folder names or chronological order. Version heterogeneity limits repeatability and may influence failures and timing.</p></section>
<section><h2>Definitions and extraction rules</h2><div class="table-wrap"><table><thead><tr><th>Measure</th><th>Rule</th><th>Limit</th></tr></thead><tbody>
<tr><td>Session duration</td><td>First recorded UTC timestamp to the last <code>task_complete</code> timestamp; fall back to the last record only if completion is missing.</td><td>Includes waits, repairs, user-response time and final reporting. Not active compute time or final-script runtime.</td></tr>
<tr><td>Raw log span</td><td>First to last record, retained separately.</td><td>N-SNIPPINGTOOL-02 has a settings event 294.71 minutes after task completion. Its task took 47.53 minutes; the 342.24-minute raw file span is not used as authoring time.</td></tr>
<tr><td>Tokens</td><td>Last cumulative <code>total_token_usage</code> counter; input, cached input and output kept separate. Uncached input = input − cached input.</td><td>No counter decreases were detected. Repeated counters are not summed. Reasoning output is already included in output. No pricing estimate.</td></tr>
<tr><td>Tool calls</td><td>Count <code>response_item</code> function/custom tool calls once; event-message duplicates and tool outputs do not add calls.</td><td>Different tools and shell command batches can represent different amounts of work.</td></tr>
<tr><td>Script launch requests</td><td>Shell calls with <code>-File</code> or invocation operator <code>&amp;</code> targeting a script named in the supplied files or final author message.</td><td>Counts launch requests, including startup failures; excludes static validator/exploration scripts. Multiple launches in one shell call count once. Not a failure count.</td></tr>
<tr><td>Patch calls</td><td>Calls to the patch tool, including creation and rejected edits.</td><td>Shell-based edits are not captured; helper files can be included. Not a count of bugs or semantic changes.</td></tr>
<tr><td>Observed step progress</td><td>First eligible runtime output/result read that names a step as PASS, or explicitly reports a complete five-of-five summary. Use outer log receipt time for both setups.</td><td>Cumulative across attempts; later failures do not lower the count. A count of five need not come from one attempt.</td></tr>
<tr><td>All-five result</td><td>Five passed rows in one observation, an explicit five-of-five console result, or a complete structured summary with total=passed=5 and failed=0.</td><td>Still generated-test reporting, not independent proof of content or route correctness.</td></tr>
<tr><td>Group averages</td><td>Arithmetic session means, medians and observed ranges. Progress means keep all original group members and carry achieved values after completion.</td><td>Unequal counts and small per-app samples; no significance test, population success estimate or causal claim.</td></tr>
</tbody></table></div><p>Framework exploration receipts are not counted as generated-script PASS results. This matters because the framework requires a walkthrough before script generation: the progress curve is not a measure of all GUI work performed during authoring.</p><p>JSONL is split only on LF, preserving Unicode control characters embedded in valid tool-output strings. All 49 files parse without dropped records. Six final framework envelopes have truncated detail text; their intact summary, policy, timing and execution identity fields are recoverable. Their missing detailed assertion sections are not invented.</p></section>
<section><h2>Comparability limits that matter here</h2><ul>
<li><strong>Interaction rules differ.</strong> Native prompts explicitly require visible controls and forbid keyboard shortcuts, clipboard and application object models. All 25 final framework results record <code>GuiNavigation</code>, whose supplied contract allows documented navigation and focused opaque input. Framework runs still inherit explicit GUI interaction and cleanup requirements, but they should not be described as having an identical strict VisibleControls contract.</li>
<li><strong>Testcase specifications vary.</strong> Five native Word sessions have empty Data fields and brief expected results; the newer Word CSV specifies exact content and PDF checks. N-POWERPOINT-03 also has different expected wording (title/subtitle) and a text-field punctuation difference. Captured testcase rows and hashes are exposed for every run. Within-app comparisons alone do not eliminate these differences.</li>
<li><strong>Collection order and state are not controlled.</strong> Native sessions span 23 September–1 October; CLI + framework sessions span 30 September–1 October. Desktop reset, machine load, cached context, prior environment changes and sampling settings were not harmonized by this retrospective analysis.</li>
<li><strong>One session has a human continuation.</strong> N-EXCEL-02 includes a second user message granting continuation after a permission question. Its entire session remains included.</li>
<li><strong>Outcome labels have known weaknesses.</strong> N-NOTEPAD-01 reports PASS after direct text/PDF output fallbacks despite the GUI-only requirement. Its folder's failed label is retained as an annotation, not silently replaced by the agent's success statement. Other passing reports have not received an exhaustive route/correctness audit.</li>
<li><strong>Delivered artifacts are incomplete.</strong> Most final documents, images, PDFs, screenshots and runtime folders referenced inside the logs are not in the supplied bundles. Attached scripts were read, not executed. Independent correctness, cleanup and fresh-environment repeatability are unmeasured.</li>
<li><strong>Reusable development effort is outside the session.</strong> CLI/framework implementation and bug-fix work are not included in these authoring durations. No total project-effort or financial return claim follows.</li></ul></section>
<section><h2>Reproduce or inspect</h2><pre>python experiment-comparison/build_report.py --source "C:\\Users\\DottedAnt\\Downloads\\results" --output analysis-output</pre><p>The builder requires Python, Matplotlib and NumPy. No external data or browser service is needed. It never executes code found in the input logs or their accompanying PowerShell scripts.</p><p><a href="experiment-data/metrics.json">Full metrics and evidence pointers</a> · <a href="experiment-data/metrics.csv">Flat metrics CSV</a> · <a href="experiment-data/summary.json">Group statistics and sensitivity summaries</a></p></section>'''
    return page('Method and limitations','Explicit inclusion rules, recoverable measurements and boundaries on the conclusions.',content)


def evidence(data):
    content='''<section><h2>How to read this evidence</h2><p>The run IDs are assigned chronologically within each application and setup. N means native; F means CLI + framework. Original folder names are retained. Source links open the local JSONL files; line numbers refer to physical LF-delimited records.</p><p>All 49 logs contain an observed all-five-PASS result. These are self-reported outcomes from generated scripts. The report does not certify that every required GUI action or content assertion was correct.</p></section>'''
    for r in data['runs']:
        content+=f'<section class="run-section {"cli-run" if r["group"]=="cli" else ""}" id="{r["id"]}"><h2>{r["id"]} · {r["app"]}</h2><p><span class="badge">{GROUPS[r["group"]]}</span> <code>{esc(r["folder"])}</code> · {r["minutes"]:.2f} min · {r["total_tokens"]/1e6:.2f} M tokens · {r["script_launches"]} launch calls</p>'
        content+=f'<p>{source_link(data,r)} · completion at line {r["end_line"]} · all-five-PASS evidence at {source_link(data,r,r["last_all_pass_line"],"result observation")}</p><p class="quiet source-path">{esc(r["file"])}<br>SHA-256: <code>{r["sha256"]}</code><br>UTC: {r["start"]} → {r["end"]}</p>'
        if r['folder_failed_label']:
            rows,_=read_records(Path(data['source_root'])/r['file'])
            recovery=next(({'line':i,'text':body(e['payload']['output'])} for i,e in reversed(rows) if e.get('payload',{}).get('type')=='function_call_output' and isinstance(e['payload'].get('output'),str) and 'Save dialog recovery: writing UTF-8' in e['payload']['output']),None)
            content+='<div class="note caution"><strong>Known requirement violation despite PASS.</strong> The supplied folder is labelled failed. The runtime evidence says the fallback writes the text file directly, uses file content for reopen verification, and writes a simple PDF instead of completing the missing GUI routes. This violates the native prompt’s prohibition on directly creating expected outputs. Retained in all primary measurements.</div>'
            if recovery:content+=f'<details><summary>Recovery evidence · line {recovery["line"]}</summary><pre>{esc(recovery["text"])}</pre></details>'
        if not r['testcase']['has_data']:content+='<div class="note caution">This native Word run uses the simpler five-row CSV with empty Data fields. It is included in the full analysis and excluded from the exact-testcase sensitivity subset.</div>'
        if r['id']=='N-POWERPOINT-03':content+='<div class="note caution">Captured expected results mention a title and subtitle, while other PowerPoint sessions specify one text string. The supplied Data field also has a punctuation difference. Excluded only from the exact-testcase sensitivity subset.</div>'
        if r['id']=='N-SNIPPINGTOOL-02':content+='<div class="note">Task completion is at 47.53 minutes. A later thread-settings event extends the raw file span to 342.24 minutes and is excluded from authoring duration. The final author also discloses an autosave fallback; this route is not independently accepted here.</div>'
        if r['group']=='cli':content+='<p class="quiet">Earlier system versions are included in this cohort (mostly bug fixes, according to the experimenter). No exact version is assigned to this run without a verified per-run snapshot.</p>'
        content+='<details><summary>Captured testcase, prompt and user continuations</summary>'
        content+=f'<p>CSV observation: line {r["testcase"]["line"]}; normalized rows SHA-256: <code>{r["testcase"]["sha256"]}</code></p><div class="table-wrap"><table><thead><tr><th>Action</th><th>Data</th><th>Expected result</th></tr></thead><tbody>'
        for row in r['testcase']['rows']:content+=f'<tr><td>{esc(row["Action"])}</td><td>{esc(row.get("Data",""))}</td><td>{esc(row["Expected Result"])}</td></tr>'
        content+='</tbody></table></div>'
        for user in r['users']:content+=f'<p>User message, line {user["line"]}</p><pre>{esc(user["text"])}</pre>'
        content+='</details><details><summary>Measurements and recorded step observations</summary><div class="table-wrap"><table><tbody>'
        for key in METRICS:content+=f'<tr><th>{esc(key)}</th><td class="num">{number(r[key])}</td></tr>'
        content+=f'<tr><th>raw_log_span_minutes</th><td class="num">{r["raw_log_span_minutes"]:.2f}</td></tr></tbody></table></div><p>First observed PASS for each distinct step (receipt time):</p><ol>'
        for i,row in enumerate(r['testcase']['rows'],1):
            point=r['first_pass'].get(str(i));content+=f'<li>{esc(row["Action"])}: {number(point["minutes"])} min, line {point["line"]}</li>' if point else f'<li>{esc(row["Action"])}: not observed</li>'
        content+='</ol><div class="table-wrap"><table><thead><tr><th>Log line</th><th class="num">Minutes</th><th>Step statuses (1–5)</th><th>Source</th></tr></thead><tbody>'
        for obs in r['observations']:content+=f'<tr><td>{obs["line"]}</td><td class="num">{obs["minutes"]:.2f}</td><td>{esc(" · ".join(f"{i}:{s}" for i,s in sorted(obs["states"].items(),key=lambda x:int(x[0]))))}</td><td>{obs["source"]}</td></tr>'
        content+='</tbody></table></div></details>'
        if r['executions']:
            last=r['executions'][-1]
            content+=f'<details><summary>Last structured framework result · line {last["line"]}</summary><p>{"Detail payload was truncated; intact summary fields are retained. Missing assertions are not filled in." if last["truncated"] else "Complete result envelope parsed."} The policy and cleanup fields are runtime assessments, not independent verification.</p><pre>{esc(json.dumps(last,indent=2))}</pre></details>'
        content+='<details><summary>Supplied scripts and launch-command evidence</summary>'
        for script in r['scripts']:
            content+=f'<p><a href="{esc((Path(data["source_root"])/script["file"]).as_uri())}">{esc(Path(script["file"]).name)}</a> · {script["lines"]} lines · SHA-256 <code>{script["sha256"]}</code></p>'
        if not r['scripts']:content+='<p>No separately supplied PowerShell file; script-authoring evidence is present in the session log.</p>'
        for call in r['launches']:content+=f'<p>Launch call, line {call["line"]}</p><pre>{esc(call["command"])}</pre>'
        content+='</details>'
        if r['final']:content+=f'<details><summary>Final author statement · line {r["final"]["line"]}</summary><p class="quiet">Quoted log content; claims are not automatically accepted as independent evidence.</p><pre>{esc(r["final"]["text"])}</pre></details>'
        content+='</section>'
    return page('Evidence for all 49 sessions','Traceable measurements, captured testcase variants and explicit outcome qualifications.',content)


def build(source, output, skip_figures=False):
    output.mkdir(parents=True,exist_ok=True)
    data_dir=output/'experiment-data';data_dir.mkdir(exist_ok=True)
    data=extract_all(source)
    data['summary']=summarize(data['runs'])
    data['by_application']={app:summarize([r for r in data['runs'] if r['app']==app]) for app in sorted({r['app'] for r in data['runs']})}
    data['sensitivity']=sensitivity(data['runs'])
    (data_dir/'metrics.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (data_dir/'summary.json').write_text(json.dumps({k:data[k] for k in ('summary','by_application','sensitivity')},indent=2)+'\n',encoding='utf-8')
    fields=['id','group','app','folder','file','sha256','start','end','raw_log_span_minutes',*METRICS,'first_all_pass_minutes','folder_failed_label']
    with (data_dir/'metrics.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(data['runs'])
    if not skip_figures:build_figures(data['runs'],output/'experiment-figures')
    (output/'experiment_comparison.html').write_text(overview(data),encoding='utf-8')
    (output/'experiment_methodology.html').write_text(method(data),encoding='utf-8')
    (output/'experiment_evidence.html').write_text(evidence(data),encoding='utf-8')
    print(f"Built {len(data['runs'])} sessions, 10 applications: {output/'experiment_comparison.html'}")
    print(json.dumps(data['sensitivity'],indent=2))
    return data


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--skip-figures',action='store_true')
    args=parser.parse_args();build(args.source,args.output,args.skip_figures)
