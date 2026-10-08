"""Offline, evidence-linked analysis of the October native / MCP task bundles.

Input files are data: no supplied script or logged command is executed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import html
import json
import math
from pathlib import Path
import re
from statistics import mean, median

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from extract import APPS, body, extract_run, json_values, normalized, read_records, stats
from figures import progress_curve

GROUPS = {'native': 'Native baseline', 'mcp': 'CLI + framework / MCP'}
COLORS = {'native': '#346cad', 'mcp': '#bd593b'}
METRICS = ['minutes', 'total_tokens', 'input_tokens', 'cached_input_tokens',
           'uncached_input_tokens', 'output_tokens', 'script_launches', 'patch_calls',
           'shell_calls', 'image_calls', 'tool_calls', 'tool_text_kib',
           'first_all_pass_minutes', 'script_bytes', 'exploration_requested_commands']


def escaped(value):
    return html.escape(str(value))


def decode_args(payload):
    value = payload.get('arguments', payload.get('input', ''))
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def dictionaries(value):
    if isinstance(value, dict):
        yield value
        for key, child in value.items():
            # Returned advice and captured source are not execution evidence.
            if key not in {'workflow', 'guide', 'template', 'nextAction', 'next'}:
                yield from dictionaries(child)
    elif isinstance(value, list):
        for child in value:
            yield from dictionaries(child)


def supplements(run, path):
    records, _ = read_records(path)
    calls = {}
    phases, explore_actions, explore_commands = [], Counter(), Counter()
    failures, timings, source_hits = [], [], []
    meta, task_ids, efforts, patched_files = {}, [], set(), Counter()
    for line, event in records:
        p = event.get('payload', {})
        kind = p.get('type')
        if event.get('type') == 'session_meta':
            meta = {k: p.get(k) for k in ('id', 'timestamp', 'model_provider', 'source', 'originator', 'cli_version')}
        if kind == 'task_started' and p.get('turn_id'):
            task_ids.append(p['turn_id'])
        if event.get('type') == 'turn_context':
            efforts.add(str(p.get('effort', p.get('reasoning_effort', 'not recorded'))))
        if event.get('type') != 'response_item':
            continue
        if kind in {'function_call', 'custom_tool_call'}:
            args = decode_args(p)
            tool = p.get('name', '')
            calls[p.get('call_id')] = {'tool': tool, 'args': args, 'line': line}
            if tool.endswith('agta_explore') and isinstance(args, dict):
                action = args.get('action', 'unknown')
                explore_actions[action] += 1
                phases.append({'line': line, 'timestamp': event['timestamp'], 'action': action})
                if action == 'Batch':
                    for request in args.get('requests', []):
                        explore_commands[request.get('command', 'unknown')] += 1
            if tool.endswith('apply_patch'):
                for target in re.findall(r'^\*\*\* (?:Add|Update|Delete) File: (.+)$', str(args), re.M):
                    patched_files[target.strip()] += 1
        if kind not in {'function_call_output', 'custom_tool_call_output'} or not isinstance(p.get('output'), str):
            continue
        call = calls.get(p.get('call_id'), {})
        tool = call.get('tool', '')
        args = call.get('args', {})
        text = body(p['output'])
        if tool.endswith(('agta_explore', 'agta_help', 'agta_inspect', 'agta_validate')):
            values = list(json_values(text))
            # Count timing once per returned tool output, rather than every
            # nested command or the duplicated mcp_tool_call_end event.
            ms = [v['mcpTiming']['requestMs'] for v in dictionaries(values)
                  if isinstance(v.get('mcpTiming'), dict) and isinstance(v['mcpTiming'].get('requestMs'), (int, float))]
            if ms:
                timings.append({'line': line, 'tool': tool, 'request_ms': max(ms)})
            if tool.endswith('agta_explore') and isinstance(args, dict) and args.get('action') != 'Status':
                seen = set()
                for value in dictionaries(values):
                    if value.get('ok') is not False or not value.get('error'):
                        continue
                    error = value['error']
                    if isinstance(error, dict):
                        message, category = error.get('message', str(error)), error.get('type', 'unspecified')
                    else:
                        message, category = str(error), 'workflow / request'
                    ident = value.get('explorationCommandId') or json.dumps([category, message], sort_keys=True)
                    if ident in seen:
                        continue
                    seen.add(ident)
                    failures.append({'line': line, 'call_line': call.get('line'), 'action': args.get('action'),
                                     'command': value.get('command'), 'type': category, 'message': message,
                                     'receipt_id': value.get('explorationCommandId')})
        # Review hits retain bounded quotations from outputs/patches, never
        # instructions from logs. They are leads, not automatic violations.
        if run['folder_failed_label'] and kind == 'function_call_output':
            for match in re.finditer(r'(?:Save dialog recovery|Open dialog recovery|Print dialog recovery)[^\r\n]*', text):
                source_hits.append({'line': line, 'text': match.group()[:800]})
    # Script names can differ from folder labels. Classify using the observed
    # CSV's opening action, retaining the folder for traceability.
    action = normalized(run['testcase']['rows'][0]['Action'])
    app_key = next((key for key, name in APPS.items() if action == 'open' + normalized(name)), run['app_key'])
    run.update({'folder_app_key': run['app_key'], 'app_key': app_key, 'app': APPS[app_key],
                'session_metadata': meta, 'task_ids': task_ids, 'reasoning_efforts': sorted(efforts),
                'exploration_actions': dict(explore_actions), 'exploration_commands': dict(explore_commands),
                'exploration_requested_commands': sum(explore_commands.values()),
                'exploration_failures': failures, 'mcp_timings': timings,
                'patched_files': dict(patched_files), 'review_hits': source_hits,
                'script_bytes': sum(s['bytes'] for s in run['scripts']) if run['scripts'] else None,
                'exploration_phase_events': phases})
    dedup = {}
    for execution in run['executions']:
        key = execution['executionId']
        if key not in dedup or (dedup[key]['truncated'] and not execution['truncated']):
            dedup[key] = execution
    run['executions'] = sorted(dedup.values(), key=lambda e: e['line'])
    run['replay_successes'] = sum(e.get('ok') is True and e.get('summary', {}).get('passed') == 5 for e in run['executions'])
    run['replay_failures'] = sum(e.get('ok') is False for e in run['executions'])
    run['final_replay_ms'] = (run['executions'][-1].get('timing') or {}).get('totalMs') if run['executions'] else None
    return run


def discover(root):
    runs, inventory, excluded = [], [], []
    for group in GROUPS:
        for folder in sorted((root/group).iterdir()):
            if not folder.is_dir():
                continue
            if folder.name.lower() == 'old':
                archived = list(folder.glob('*/*.jsonl'))
                excluded.append({'path': str(folder.relative_to(root)), 'reason': 'Archived directory; excluded from the requested current batch.', 'logs': len(archived)})
                continue
            logs = sorted(folder.glob('*.jsonl'))
            files = sorted(p.name for p in folder.iterdir() if p.is_file())
            item = {'group': group, 'folder': folder.name, 'files': files, 'log_count': len(logs)}
            if group == 'native' and folder.name == 'paint-37m':
                item['status'] = 'superseded'
                excluded.append({'path': str(folder.relative_to(root)), 'reason': 'Replaced by the new native Paint run at the user\'s explicit request.', 'logs': len(logs)})
            elif not logs:
                item['status'] = 'no session log'
            else:
                item['status'] = 'included'
                for path in logs:
                    runs.append(supplements(extract_run(path, root), path))
            inventory.append(item)
    runs.sort(key=lambda r: (r['app'], r['group'], r['start'], r['folder']))
    counter = Counter()
    for run in runs:
        key = run['group'], run['app_key']
        counter[key] += 1
        run['id'] = f"{'N' if run['group']=='native' else 'M'}-{run['app_key'].upper()}-{counter[key]:02d}"
    if len({r['sha256'] for r in runs}) != len(runs):
        raise ValueError('Byte-identical logs were discovered; review duplicate bundles before reporting.')
    return runs, inventory, excluded


def comparison(runs):
    summary = {g: {key: stats([r[key] for r in runs if r['group'] == g]) for key in METRICS} for g in GROUPS}
    for g in GROUPS:
        sample = [r for r in runs if r['group'] == g]
        summary[g]['n'] = len(sample)
        summary[g]['reported_all_pass'] = sum(r['first_all_pass_minutes'] is not None for r in sample)
        summary[g]['token_sums'] = {key: sum(r[key] or 0 for r in sample) for key in ['total_tokens', 'input_tokens', 'output_tokens', 'cached_input_tokens', 'uncached_input_tokens']}
    return summary


def change(a, b):
    return 100*(b/a-1) if a else None


def sensitivity(runs):
    cases = {g: {r['testcase']['sha256'] for r in runs if r['group'] == g} for g in GROUPS}
    common = cases['native'] & cases['mcp']
    longest = max((r for r in runs if r['group'] == 'native'), key=lambda r: r['minutes'])
    longest_m = max((r for r in runs if r['group'] == 'mcp'), key=lambda r: r['minutes'])
    variants = [('All included runs (primary)', runs),
                ('Identical captured testcase content only', [r for r in runs if r['testcase']['sha256'] in common]),
                ('Without native folder labelled failed', [r for r in runs if not r['folder_failed_label']]),
                ('Without longest native run', [r for r in runs if r['id'] != longest['id']]),
                ('Without longest run in each setup', [r for r in runs if r['id'] not in {longest['id'], longest_m['id']}])]
    result = []
    for label, sample in variants:
        s = comparison(sample)
        a, b = s['native']['minutes']['mean'], s['mcp']['minutes']['mean']
        result.append({'label': label, 'native_n': s['native']['n'], 'mcp_n': s['mcp']['n'],
                       'native_mean': a, 'mcp_mean': b, 'change_pct': change(a, b),
                       'native_token_mean': s['native']['total_tokens']['mean'], 'mcp_token_mean': s['mcp']['total_tokens']['mean']})
    apps = sorted({r['app'] for r in runs})
    a, b = [mean(mean(r['minutes'] for r in runs if r['group'] == g and r['app'] == app) for app in apps) for g in GROUPS]
    result.insert(1, {'label': 'Equal weight for each application', 'native_n': sum(r['group']=='native' for r in runs),
                     'mcp_n': sum(r['group']=='mcp' for r in runs), 'native_mean': a, 'mcp_mean': b, 'change_pct': change(a, b)})
    return result


def testcase_variants(runs):
    variants = defaultdict(dict)
    for r in runs:
        key = r['testcase']['sha256']
        value = variants[r['app']].setdefault(key, {'sha256': key, 'rows': r['testcase']['rows'], 'runs': [], 'source_line': r['testcase']['line']})
        value['runs'].append(r['id'])
    result = []
    for app, versions in variants.items():
        if len(versions) < 2:
            continue
        current = next(v for v in versions.values() if any(i.startswith('M-') for i in v['runs']))
        differences = []
        for v in versions.values():
            if v is current:
                continue
            for index, (a, b) in enumerate(zip(v['rows'], current['rows']), 1):
                for field in sorted(set(a)|set(b)):
                    if a.get(field) != b.get(field):
                        differences.append({'variant': v['sha256'], 'runs': v['runs'], 'step': index, 'field': field, 'other': a.get(field), 'mcp': b.get(field)})
        result.append({'app': app, 'variants': list(versions.values()), 'differences': differences})
    return result


def source_href(data, run, line=None):
    path = Path(data['source_root']) / run['file']
    return path.as_uri() + (f'#L{line}' if line else '')


def evidence_link(run, label=None):
    return f'<a href="session_evidence.html#{run["id"]}">{escaped(label or run["id"])}</a>'


def table(headers, rows):
    return '<div class="scroll"><table><thead><tr>' + ''.join(f'<th>{escaped(h)}</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join(f'<td>{cell}</td>' for cell in row)+'</tr>' for row in rows)+'</tbody></table></div>'


CSS = '''
:root{--ink:#25343d;--muted:#586772;--line:#d9e1e5;--native:#346cad;--mcp:#bd593b}
*{box-sizing:border-box}body{margin:0;color:var(--ink);background:#fff;font:16px/1.6 system-ui,Segoe UI,sans-serif}
header{border-bottom:3px solid #337569;background:#f0f6f3;padding:30px max(24px,calc((100% - 1180px)/2))}
header p{max-width:960px}h1{font-size:34px;line-height:1.2;margin:8px 0 18px}h2{font-size:25px;line-height:1.3;margin:0 0 20px}h3{font-size:19px}main{max-width:1230px;margin:auto;padding:8px 25px 55px}
nav{display:flex;gap:22px;flex-wrap:wrap;font-size:14px}a{color:#216493;text-underline-offset:3px}section{padding:32px 0;border-bottom:1px solid var(--line);scroll-margin-top:20px}p{margin:12px 0}small,.quiet{font-size:13px;color:var(--muted)}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:20px;margin:28px 0}.metric{padding:8px 18px 10px 0;border-right:1px solid var(--line)}.metric strong{display:block;font-size:26px;line-height:1.3;margin:8px 0}.metric span{font-size:13px;color:var(--muted)}
.note{padding:12px 18px;background:#f1f5f8;border-left:4px solid #346cad;margin:20px 0}.caution{background:#fff5e8;border-left-color:#bd593b}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px 12px;vertical-align:top;border-bottom:1px solid var(--line);text-align:left}th{background:#f0f4f5;font-weight:600}tbody tr:hover{background:#f7f9fa}figure{margin:20px 0}figure img{width:100%;height:auto;display:block}figcaption{font-size:13px;color:var(--muted)}
.controls{display:flex;gap:14px;flex-wrap:wrap;align-items:end;margin:20px 0}.controls label{display:flex;flex-direction:column;gap:5px;font-size:13px}select,input,button{font:inherit;padding:8px 12px;border:1px solid #a9b6bf;border-radius:4px;background:white;color:var(--ink)}input{width:230px;max-width:100%}button{cursor:pointer}pre{font:13px/1.5 Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;padding:16px;background:#f2f5f6;max-height:450px;overflow:auto}code{overflow-wrap:anywhere}details{margin:15px 0}summary{cursor:pointer;font-weight:600}.native{color:var(--native)}.mcp{color:var(--mcp)}.badge{font-size:12px;padding:3px 7px;background:#eef3f5;white-space:nowrap}[hidden]{display:none!important}
@media(max-width:700px){h1{font-size:27px}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.metric strong{font-size:22px}main{padding:8px 17px 30px}th,td{padding:8px}section{padding:25px 0}}@media print{nav,.controls{display:none}section{break-inside:auto}details{display:block}header{padding:20px}main{max-width:none}a{color:inherit}}
'''


def page(title, subtitle, content, script=''):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escaped(title)}</title><style>{CSS}</style></head><body><header><small>SESSION EXPERIMENT REPORT · 4 OCTOBER 2026</small><h1>{escaped(title)}</h1><p>{subtitle}</p><nav><a href="session_comparison.html">Comparison</a><a href="session_evidence.html">Per-run evidence</a><a href="data/metrics.json">JSON data</a><a href="data/sessions.csv">Session CSV</a><a href="data/application_summary.csv">Application CSV</a></nav></header><main>{content}</main><script>{script}</script></body></html>'''


def figures(data, out):
    out.mkdir(exist_ok=True)
    runs = data['runs']
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False,
                         'axes.spines.right': False, 'axes.labelcolor': '#25343d', 'figure.facecolor': 'white',
                         'savefig.facecolor': 'white', 'svg.hashsalt': 'october2026-native-mcp'})
    apps = sorted({r['app'] for r in runs})
    rng = np.random.default_rng(1042026)

    def save(fig, name):
        fig.savefig(out/f'{name}.svg', bbox_inches='tight')
        fig.savefig(out/f'{name}.png', bbox_inches='tight', dpi=170)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(11.3, 6.5))
    for y, app in enumerate(apps):
        for group, offset in [('native', -.17), ('mcp', .17)]:
            values = [r['minutes'] for r in runs if r['app']==app and r['group']==group]
            jitter = rng.uniform(-.055, .055, len(values))
            ax.scatter(values, y+offset+jitter, color=COLORS[group], s=33, alpha=.72, label=GROUPS[group] if y==0 else None)
            ax.plot([mean(values)]*2, [y+offset-.1, y+offset+.1], color=COLORS[group], lw=3)
    ax.set(yticks=range(len(apps)), yticklabels=apps, xlabel='Elapsed authoring time (minutes)', title='All runs and within-application means')
    ax.invert_yaxis(); ax.grid(axis='x', alpha=.18); ax.legend(loc='lower right'); fig.tight_layout(); save(fig, 'duration')

    fig, axes = plt.subplots(1, 3, figsize=(11.3, 4.1))
    for ax, key, scale, title in zip(axes, ['total_tokens', 'uncached_input_tokens', 'output_tokens'], [1e6, 1000, 1000], ['Total tokens (millions)', 'Uncached input (thousands)', 'Output (thousands)']):
        for x, group in enumerate(GROUPS):
            values = [r[key]/scale for r in runs if r['group']==group]
            ax.scatter(x+rng.uniform(-.15,.15,len(values)), values, s=23, color=COLORS[group], alpha=.65)
            ax.plot([x-.24,x+.24], [mean(values)]*2, color=COLORS[group], lw=3)
        ax.set(xticks=[0,1], xticklabels=['Native','MCP'], title=title); ax.grid(axis='y',alpha=.18)
    fig.tight_layout(); save(fig, 'tokens')

    fig, axes = plt.subplots(1, 2, figsize=(11.3, 4.2))
    for ax, key, title in zip(axes, ['script_launches','patch_calls'], ['Generated-script launch requests', 'Patch tool calls']):
        for x, group in enumerate(GROUPS):
            values=[r[key] for r in runs if r['group']==group]
            ax.scatter(x+rng.uniform(-.15,.15,len(values)),values,s=25,color=COLORS[group],alpha=.66)
            ax.plot([x-.24,x+.24],[mean(values)]*2,color=COLORS[group],lw=3)
        ax.set(xticks=[0,1],xticklabels=['Native','MCP'],title=title);ax.grid(axis='y',alpha=.18)
    fig.tight_layout();save(fig,'iterations')

    for app in [None, *apps]:
        selected = [r for r in runs if app is None or r['app'] == app]
        horizon = max(20, math.ceil(max(r['minutes'] for r in selected)/10)*10)
        # Plot exact observation times. Crop only the pooled display; the
        # long runs remain in its means and in the full per-application views.
        times = sorted({0, horizon, *[p['minutes'] for r in selected for p in r['first_pass'].values()]})
        fig, ax = plt.subplots(figsize=(11.3, 4.4))
        for group in GROUPS:
            sample = [r for r in selected if r['group'] == group]
            curves = []
            for r in sample:
                curve = progress_curve(r, times)
                curves.append(curve)
                line, = ax.step(times, curve, where='post', color=COLORS[group],
                                alpha=.15 if app else .065, lw=.9,
                                linestyle='--' if group == 'native' else '-')
                line.set_gid(r['id'])
            ax.step(times, np.mean(curves, axis=0), where='post', color=COLORS[group], lw=2.6,
                    linestyle='--' if group == 'native' else '-',
                    label=f'{GROUPS[group]} mean · n={len(sample)}')
        display_end = 60 if app is None else horizon
        ax.set(xlim=(0, display_end), xlabel='Minutes after first log event',
               ylabel='Rows with observed PASS evidence', ylim=(-.05, 5.2), yticks=range(6),
               title=f'{app or "All applications"} · observed row completion')
        ax.legend(loc='lower right'); ax.grid(alpha=.16)
        fig.tight_layout(); save(fig, 'progress' if app is None else 'progress-' + selected[0]['app_key'])


def figure(name, caption):
    return f'<figure><img src="figures/{name}.svg" alt="{escaped(caption)}"><figcaption>{escaped(caption)}</figcaption></figure>'


def build_overview(data):
    runs, s = data['runs'], data['summary']
    n, m = s['native'], s['mcp']
    duration_change=change(n['minutes']['mean'],m['minutes']['mean'])
    content=f'''<div class="metrics"><div class="metric"><span>Mean authoring duration</span><strong>{n['minutes']['mean']:.2f} → {m['minutes']['mean']:.2f} min</strong><small>{-duration_change:.1f}% lower with MCP</small></div><div class="metric"><span>Mean total tokens</span><strong>{n['total_tokens']['mean']/1e6:.2f} → {m['total_tokens']['mean']/1e6:.2f} M</strong><small>{change(n['total_tokens']['mean'],m['total_tokens']['mean']):+.1f}% change</small></div><div class="metric"><span>Mean generated-script launches</span><strong>{n['script_launches']['mean']:.2f} → {m['script_launches']['mean']:.2f}</strong><small>Requests to run the generated script</small></div><div class="metric"><span>Measured task runs</span><strong>{len(runs)} runs · 10 apps</strong><small>{n['n']} native · {m['n']} MCP · GPT-5.5</small></div></div>
<section id="conclusions"><h2>Findings</h2><p>The CLI + framework / MCP setup has lower mean elapsed authoring time in this batch: {m['minutes']['mean']:.2f} minutes compared with {n['minutes']['mean']:.2f} for the native baseline, a reduction of {-duration_change:.1f}%. Medians are {m['minutes']['median']:.2f} and {n['minutes']['median']:.2f} minutes. Mean generated-script launch requests and patch calls are also lower, consistent with less implementation and repair work.</p>
<p>The improvement concerns complete authoring setups. It includes the CLI, framework, MCP interface, reusable runtime, authoring instructions, and collected desktop conditions. The logs cannot identify the separate causal contribution of each component.</p>
<p>The time reduction comes with greater input/context use. Total tokens change by {change(n['total_tokens']['mean'],m['total_tokens']['mean']):+.1f}%; uncached input by {change(n['uncached_input_tokens']['mean'],m['uncached_input_tokens']['mean']):+.1f}%; and output by {change(n['output_tokens']['mean'],m['output_tokens']['mean']):+.1f}%. This supports a narrower interpretation: the framework reduces generated implementation and elapsed repair work while returning more context. It does not establish lower financial cost.</p>
<div class="note caution"><strong>Reported PASS is not independent acceptance.</strong> Runtime outputs/result reads report all five rows passed in {n['reported_all_pass']}/{n['n']} native and {m['reported_all_pass']}/{m['n']} MCP runs. The native Notepad folder labelled failed contains documented recovery that directly writes the expected text/PDF and substitutes a file read for GUI reopening. Its PASS report is unsuitable as verified GUI success. It remains in time/token measurements and is flagged below. A fully independent acceptance-success rate is unavailable.</div></section>'''
    spec=[('minutes','Authoring duration','min',1),('total_tokens','Total tokens','M',1e6),('uncached_input_tokens','Uncached input','k',1000),('cached_input_tokens','Cached input','M',1e6),('output_tokens','Output tokens','k',1000),('script_launches','Generated-script launch requests','',1),('patch_calls','Patch calls','',1),('shell_calls','Shell calls','',1),('image_calls','Image inspection calls','',1),('tool_calls','All explicit tool calls','',1),('tool_text_kib','Returned textual tool output','KiB',1)]
    rows=[]
    for key,label,unit,scale in spec:
        a,b=n[key],m[key]
        rows.append([label, f"{a['mean']/scale:.2f} {unit}",f"{b['mean']/scale:.2f} {unit}",f"{change(a['mean'],b['mean']):+.1f}%",f"{a['median']/scale:.2f} / {b['median']/scale:.2f}"])
    content+='<section id="overall"><h2>Overall measurements</h2>'+table(['Metric','Native mean','MCP mean','Change','Medians: native / MCP'],rows)
    content+=f"<p>Totals for this equally sized sample are {n['token_sums']['total_tokens']/1e6:.2f} M native tokens and {m['token_sums']['total_tokens']/1e6:.2f} M MCP tokens. Session time totals are {sum(r['minutes'] for r in runs if r['group']=='native')/60:.2f} and {sum(r['minutes'] for r in runs if r['group']=='mcp')/60:.2f} hours. These are logged wall-clock spans, including waits and any human interruptions; they are not active compute time.</p></section>"
    content+='<section id="applications"><h2>Application comparison</h2>'+figure('duration','Dots are individual task runs. Short vertical marks are group means. Small application samples and broad ranges limit generalization.')
    rows=[]
    for app in data['application_summary']:
        a,b=app['native'],app['mcp']
        rows.append([escaped(app['app']), f"{a['n']} / {b['n']}",f"{a['minutes']['mean']:.2f}",f"{b['minutes']['mean']:.2f}",f"{change(a['minutes']['mean'],b['minutes']['mean']):+.1f}%",f"{a['total_tokens']['mean']/1e6:.2f} / {b['total_tokens']['mean']/1e6:.2f}",f"{a['script_launches']['mean']:.1f} / {b['script_launches']['mean']:.1f}"])
    wins=sum(app['mcp']['minutes']['mean'] < app['native']['minutes']['mean'] for app in data['application_summary'])
    content+=table(['Application','n: native / MCP','Native min','MCP min','Time change','Tokens M: native / MCP','Launches: native / MCP'],rows)
    content+=f'<p>MCP has the lower mean duration in {wins} of 10 application categories. The pooled mean gives repeated applications more weight. The sensitivity table also gives every application equal weight. OneNote and native Paint have a single measured run each, so their mean is one observation.</p></section>'
    photos=next(a for a in data['application_summary'] if a['app']=='Photos')
    photos_change=change(photos['native']['minutes']['mean'],photos['mcp']['minutes']['mean'])
    content=content[:-len('</section>')]+f'<p><strong>Photos is the exception:</strong> MCP averages {photos["mcp"]["minutes"]["mean"]:.2f} minutes versus {photos["native"]["minutes"]["mean"]:.2f} native ({photos_change:+.1f}%). The MCP Photos runs also have the stricter PDF-content testcase, and the longer run contains repeated Save As / selector failures. This prevents a claim of a universal per-application advantage. Paint now compares matching testcase content: one new native run against two MCP runs.</p></section>'
    content+='<section id="tokens"><h2>Tokens and iteration work</h2>'+figure('tokens','Final cumulative token counters; horizontal marks show means. Reasoning tokens are already included in output tokens.')+figure('iterations','Launch requests are not verified full executions. Patch calls count tool invocations, not changed lines or unique revisions.')
    content+=f"<p>Returned textual tool output averages {n['tool_text_kib']['mean']:.1f} KiB native versus {m['tool_text_kib']['mean']:.1f} KiB MCP. This excludes image pixels and opaque image encodings as a usable measure of image cost. Explicit image inspection calls also miss images returned inline by MCP, so they do not establish that the MCP setup inspected fewer images.</p>"
    mcpruns=[r for r in runs if r['group']=='mcp']
    attempts=sum(len(r['executions']) for r in mcpruns); successes=sum(r['replay_successes'] for r in mcpruns); failures=sum(r['replay_failures'] for r in mcpruns)
    first_pass=sum(bool(r['executions']) and r['executions'][0].get('ok') is True for r in mcpruns)
    content+=f'<p>The MCP logs expose {attempts} distinct full replay result records: {successes} successful and {failures} failed. {first_pass}/{len(mcpruns)} runs have a successful first observed replay result. This metric concerns saved-script replay after exploration; it does not count exploratory GUI failures. Native scripts use heterogeneous result formats, so a comparable verified replay-failure rate is not reported.</p>'
    final_times=[r['final_replay_ms']/1000 for r in mcpruns if r['final_replay_ms'] is not None]
    content+=f'<p>Final MCP replay runtime is available for {len(final_times)}/{len(mcpruns)} runs: mean {mean(final_times):.1f} seconds, median {median(final_times):.1f} seconds. It is separate from total authoring time and has no consistently recorded native counterpart.</p></section>'
    content+='<section id="progress"><h2>Observed row completion</h2><div class="controls"><label>Application<select id="progress-app"><option value="all">All applications</option>'
    progress_apps = sorted({(r['app'], r['app_key']) for r in runs})
    content+=''.join(f'<option value="{escaped(key)}">{escaped(app)}</option>' for app, key in progress_apps)+'</select></label></div>'
    for app, key in [('All applications', 'all'), *progress_apps]:
        caption=f'{app}: cumulative first PASS receipts from eligible script outputs/results. Thin lines are individual runs; bold lines are setup means. Rows reported together appear as jumps; earlier successes can originate from different attempts.'
        if key == 'all':
            caption+=f' Display limited to 0–60 minutes; all {len(runs)} runs remain in the averages. Application views show their full observed range.'
        name = 'progress' if key == 'all' else 'progress-' + key
        content+=f'<div class="progress-frame" data-progress="{escaped(key)}" {"hidden" if key != "all" else ""}>'+figure(name, caption)+'</div>'
    content+=f"<p>The first observed all-five-PASS result appears after {n['first_all_pass_minutes']['mean']:.2f} minutes on average for native and {m['first_all_pass_minutes']['mean']:.2f} minutes for MCP. Observation timestamps describe when evidence reaches the session log, not the exact time a GUI state was achieved. Completed runs remain at five in the average curve.</p></section>"
    content+='<section id="testcases"><h2>Testcase differences retained in the primary analysis</h2><p>Following the experimenter’s instruction, the remaining Word, Photos, and PowerPoint variants are included in the main comparison. The new native Paint run replaces the earlier native Paint run and matches the current MCP Paint testcase. The extra MCP Paint run is retained as collected; it does not replace a missing Photos run.</p>'
    notes={'Word':'Five native Word runs have empty Data fields and general expected results. Native word6-43m and all current MCP Word runs specify exact document text, filenames, reopening, and PDF content. This is a material specificity difference, retained at the experimenter’s request.',
           'Photos':'Native photos-17m and photos-35m require PDF existence only. Native photos-40m and MCP Photos require a fitting layout without cropping plus a successfully opened PDF showing the complete rotated wallpaper. There is also a comma/semicolon wording difference in row 1.',
           'PowerPoint':'Native powerpoint3-28m uses title/subtitle wording in rows 4–5 and has stray punctuation in row 2. Other native PowerPoint runs and MCP use complete-text wording. The captured row-level differences are preserved below.'}
    for variant in data['testcase_variants']:
        content+=f"<h3>{escaped(variant['app'])}</h3><p>{escaped(notes.get(variant['app'], 'Captured testcase text differs.'))}</p>"
        rows=[]
        for version in variant['variants']:
            rows.append([version['sha256'][:12],', '.join(evidence_link(next(r for r in runs if r['id']==rid)) for rid in version['runs'])])
        content+=table(['Canonical testcase hash','Runs'],rows)
        diffs=[[str(d['step']),escaped(d['field']),escaped(d['other']),escaped(d['mcp'])] for d in variant['differences']]
        content+='<details><summary>Exact captured row differences</summary>'+table(['Row','Field','Other native variant','Current MCP specification'],diffs)+'</details>'
    content+='<p>Access, Edge, Excel, Notepad, OneNote, Snipping Tool, and the replacement Paint testcase have identical captured row content across setups. The assumption that other differences balance out is not independently demonstrated; the matching-content sensitivity analysis shows whether the duration conclusion depends on retaining them.</p></section>'
    content+='<section id="sensitivity"><h2>Sensitivity to testcase content, weighting, and long runs</h2>'
    rows=[[escaped(x['label']),f"{x['native_n']} / {x['mcp_n']}",f"{x['native_mean']:.2f}",f"{x['mcp_mean']:.2f}",f"{x['change_pct']:+.1f}%"] for x in data['sensitivity']]
    content+=table(['Subset / weighting','n: native / MCP','Native mean min','MCP mean min','Change'],rows)
    content+='<p>The matching-content row selects testcase hashes present in both setups; it does not pair runs by random seed, collection date, application state, or execution order. Outlier exclusions are explicit descriptive checks, not grounds for removing those observations from the primary result. No inferential significance or causal effect is claimed.</p></section>'
    content+='<section id="recovery"><h2>Recovery patterns and evidence quality</h2>'
    worst=sorted(mcpruns,key=lambda r:r['replay_failures'],reverse=True)[:6]
    rows=[]
    for r in worst:
        errors=[f['error'] for e in r['executions'] for f in (e.get('summary') or {}).get('failedSteps',[]) if f.get('error')]
        examples=list(dict.fromkeys(errors))[:2]
        rows.append([evidence_link(r,r['folder']),f"{r['minutes']:.2f}",str(r['replay_failures']),str(r['script_launches']),'<br>'.join(escaped(e) for e in examples)])
    content+=table(['MCP run','Minutes','Failed result records','Launch requests','Examples from runtime failedSteps'],rows)
    content+='<p>These result messages support recurrent issues with window identity/ownership, selectors or incomplete provider traversal, filename/dialog transitions, input verification, and PDF/image assertions. They locate failed automation checks; a timeout or missing guessed control alone does not establish an application defect.</p>'
    failed=next((r for r in runs if r['folder_failed_label']),None)
    if failed:
        content+=f'<div class="note caution"><strong>Native Notepad exception:</strong> {evidence_link(failed,failed["folder"])} reports all five rows passed, but the captured evidence log records direct UTF-8 text-file creation, file-based reopening verification, and synthetic PDF generation during recovery. This is an observed bypass of the requested GUI actions, rather than a failure inferred only from the folder name. The sensitivity table shows the comparison without this run.</div>'
    clean=sum(r['executions'] and r['executions'][-1].get('cleanupOk') is True for r in mcpruns)
    policy=sum(r['executions'] and (r['executions'][-1].get('interactionPolicy') or {}).get('mode')=='GuiNavigation' for r in mcpruns)
    compliant=sum(r['executions'] and (r['executions'][-1].get('interactionPolicy') or {}).get('compliant') is True for r in mcpruns)
    content+=f'<p>Final MCP result records report cleanupOk=true for {clean}/{len(mcpruns)} runs, GuiNavigation mode for {policy}/{len(mcpruns)}, and policy compliant=true for {compliant}/{len(mcpruns)}. These are framework-reported assessments; external activity is not sandboxed and result records alone cannot independently prove all asserted content.</p></section>'
    covered={g:sum(bool(r['scripts']) for r in runs if r['group']==g) for g in GROUPS}
    content=content[:-len('</section>')]+f'<p>Copied generated scripts are available for {covered["native"]}/{n["n"]} native and {covered["mcp"]}/{m["n"]} MCP task bundles. The log-based duration/token measurements cover every included run, but a comprehensive static audit of the native scripts is therefore incomplete.</p></section>'
    content+='<section id="inventory"><h2>Corpus accounting</h2>'
    rows=[]
    for g in GROUPS:
        inv=[i for i in data['inventory'] if i['group']==g]
        rows.append([GROUPS[g],str(len(inv)),str(sum(i['status']=='included' for i in inv)),str(sum(i['status']=='no session log' for i in inv)),str(sum(i['status']=='superseded' for i in inv))])
    content+=table(['Setup','Current folders','Included folders','No log','Superseded'],rows)
    missing=[i for i in data['inventory'] if i['status']=='no session log']
    content+=table(['Folder with no log','Files present','Treatment'],[[escaped(i['group']+'/'+i['folder']),escaped(', '.join(i['files']) or '(empty)'), 'Unmeasured; no duration, tokens, or outcome inferred from its name.'] for i in missing])
    content+=table(['Excluded path','Reason','Logs'],[[escaped(e['path']),escaped(e['reason']),str(e['logs'])] for e in data['excluded']])
    reused=data['reused_session_ids']
    content+=f'<p>All {len(runs)} included log hashes are distinct, every JSONL record parses, and cumulative token counters have no observed decreases. {len(reused)} exported session ID is reused across four MCP task bundles. Those bundles have distinct task-start turn IDs, nonoverlapping event ranges, and small separate initial token counters. They are retained as distinct task episodes. Filenames and session metadata alone therefore should not define run identity.</p></section>'
    content+='<section id="runs"><h2>Run register</h2><div class="controls"><label>Application<select id="app"><option value="all">All applications</option>'+''.join(f'<option value="{escaped(a)}">{escaped(a)}</option>' for a in sorted({r['app'] for r in runs}))+'</select></label><label>Setup<select id="group"><option value="all">Both setups</option><option value="native">Native</option><option value="mcp">MCP</option></select></label><label>Search<input id="search" placeholder="Folder or run ID"></label><button id="reset">Reset</button></div><p id="count" class="quiet"></p><div class="scroll"><table><thead><tr><th>Run / folder</th><th>Application</th><th>Setup</th><th>Minutes</th><th>Tokens M</th><th>Launches</th><th>Patches</th><th>Evidence note</th></tr></thead><tbody id="register">'
    for r in runs:
        note='GUI recovery bypass documented' if r['folder_failed_label'] else ('CSV differs; retained' if any(r['id'] in v['runs'] for case in data['testcase_variants'] for v in case['variants']) else 'Captured testcase matches')
        content+=f'<tr data-app="{escaped(r["app"])}" data-group="{r["group"]}"><td>{evidence_link(r)}<br><small>{escaped(r["folder"])}</small></td><td>{escaped(r["app"])}</td><td>{r["group"]}</td><td>{r["minutes"]:.2f}</td><td>{r["total_tokens"]/1e6:.2f}</td><td>{r["script_launches"]}</td><td>{r["patch_calls"]}</td><td>{note}</td></tr>'
    content+='</tbody></table></div></section>'
    content+='''<section id="methodology"><h2>Measurement definitions and limits</h2><ul>
<li><strong>Source scope:</strong> direct session JSONL files under native and mcp. The archive is excluded. The earlier native Paint is superseded at the user’s request. Folders without session logs remain visible in inventory but not numerical summaries.</li>
<li><strong>Duration:</strong> first actual log-event timestamp to the last task_complete event; if completion is absent, to the last recorded event. Payload session metadata timestamps and folder “minutes” labels are not used. Raw log spans and terminal-event line numbers remain in the JSON export.</li>
<li><strong>Tokens:</strong> last cumulative total_token_usage sample, never a sum of successive cumulative counters. Uncached input equals input minus cached input. Output already includes reasoning output. Total tokens are repeated model input plus output, not unique text. Cost cannot be determined from this corpus alone.</li>
<li><strong>Launch requests:</strong> shell calls invoking a supplied/generated script name; validation-only and source reads are excluded. One request can fail before replay or yield a bounded/truncated output. Probe scripts with other names are not counted as launches of the final generated script.</li>
<li><strong>Tool calls:</strong> response-item function/custom calls; mirrored event messages are not counted twice. Tool-search events are not counted. Patch calls and shell calls describe different implementation workflows, so they are supporting process measures.</li>
<li><strong>PASS provenance:</strong> structured step results, console rows, or complete five-pass summaries from eligible launches and result reads. Assistant final claims and source-code PASS strings are excluded. Truncated detail can still yield a complete summary. Diagnostic/nonqualifying replay results are excluded from full-test success.</li>
<li><strong>Replay attempts:</strong> framework result records deduplicated by executionId within a task bundle. Failure counts use ok=false. Final cleanup/policy flags are framework-reported, not external acceptance tests.</li>
<li><strong>CSV matching:</strong> exact canonical Action/Data/Expected Result row content, not raw file bytes. Two native Photos CSV outputs have trailing empty fields and an unquoted comma in an expected-result field; their explicit recovery joins those expected-result cells and is recorded in the data.</li>
<li><strong>Comparability:</strong> observational, uneven repetitions by application, no randomized or paired collection, some retained testcase differences, different authoring rules and reusable infrastructure. Model labels are GPT-5.5, but infrastructure versions are not uniformly identified. One native Excel task has an additional human authorization message; idle gaps and waiting remain in duration.</li>
<li><strong>Acceptance limits:</strong> copied scripts are available only for part of the native corpus; raw application artifacts and images are not independently replayed or comprehensively reviewed. No supplied PowerShell code or logged command is executed for this report.</li>
</ul></section>'''
    script='''
const progressSelect=document.querySelector('#progress-app');
const progressFrames=[...document.querySelectorAll('.progress-frame')];
function updateProgress(){progressFrames.forEach(frame=>{frame.hidden=frame.dataset.progress!==progressSelect.value})}
progressSelect.addEventListener('change',updateProgress);
updateProgress();
const rows=[...document.querySelectorAll('#register tr')];
function filter(){const a=document.querySelector('#app').value,g=document.querySelector('#group').value,q=document.querySelector('#search').value.toLowerCase();let n=0;rows.forEach(r=>{r.hidden=!((a==='all'||r.dataset.app===a)&&(g==='all'||r.dataset.group===g)&&r.textContent.toLowerCase().includes(q));if(!r.hidden)n++});document.querySelector('#count').textContent=n+' of '+rows.length+' task runs shown'}
document.querySelectorAll('#app,#group,#search').forEach(e=>e.addEventListener('input',filter));
document.querySelector('#reset').addEventListener('click',()=>{document.querySelector('#app').value='all';document.querySelector('#group').value='all';document.querySelector('#search').value='';filter()});
filter();
'''
    return page('Native versus CLI + framework / MCP', 'An updated analysis of the supplied task logs, including the new Notepad, Paint, and Word MCP runs and the replacement native Paint run.', content, script)


def build_evidence(data):
    content='<p>Each entry preserves source paths, hashes, captured testcases, runtime result references, and launch requests. Source links open local JSONL files; displayed line numbers identify the exact record even if a viewer ignores the #L fragment.</p>'
    for r in data['runs']:
        content+=f'<section id="{r["id"]}"><h2>{escaped(r["id"])} · {escaped(r["folder"])}</h2><p>{escaped(r["app"])} · {GROUPS[r["group"]]} · {r["minutes"]:.3f} min · {r["total_tokens"]:,} total tokens</p>'
        content+=f'<p><a href="{escaped(source_href(data,r))}">Source session JSONL</a><br><code>{escaped(r["file"])}</code><br><small>SHA256: {r["sha256"]}</small></p>'
        content+=table(['Start event','Task completion / end','Raw span min','Largest event gap min','Recorded task IDs'],[[escaped(r['start']),escaped(r['end']),f"{r['raw_log_span_minutes']:.2f}",f"{r['max_event_gap_minutes']:.2f}",escaped(', '.join(r['task_ids']))]])
        content+=f'<details><summary>Captured testcase · log line {r["testcase"]["line"]} · hash {r["testcase"]["sha256"][:12]}</summary>'+table(['Row','Action','Data','Expected Result'],[[str(i),escaped(row['Action']),escaped(row.get('Data','')),escaped(row['Expected Result'])] for i,row in enumerate(r['testcase']['rows'],1)])+'</details>'
        if r['testcase'].get('normalization_note'):
            content+=f'<p class="quiet">CSV recovery: {escaped(r["testcase"]["normalization_note"])}</p>'
        content+='<details><summary>Observed runtime/result evidence</summary>'
        content+=table(['Log line','Observation min','PASS / FAIL / SKIP rows','Source'],[[f'<a href="{escaped(source_href(data,r,o["line"]))}">{o["line"]}</a>',f"{o['minutes']:.3f}",escaped(json.dumps(o['states'],sort_keys=True)),escaped(o['source'])] for o in r['observations']])+'</details>'
        if r['executions']:
            content+='<details><summary>Distinct framework replay result records</summary>'+table(['Line','Execution ID','ok','Summary','Cleanup','Truncated detail'],[[str(e['line']),escaped(e['executionId']),str(e.get('ok')),escaped(json.dumps(e['summary'],ensure_ascii=False)),str(e.get('cleanupOk')),str(e['truncated'])] for e in r['executions']])+'</details>'
        if r['exploration_failures']:
            content+='<details><summary>Exploration failures (returned receipts/request failures)</summary>'+table(['Line','Action','Command','Type','Message'],[[str(f['line']),escaped(f['action']),escaped(f['command']),escaped(f['type']),escaped(f['message'])] for f in r['exploration_failures']])+'</details>'
        if r['review_hits']:
            content+='<div class="note caution"><strong>Recorded GUI bypass recovery:</strong>'+table(['Source line','Captured runtime evidence-log text'],[[str(h['line']),escaped(h['text'])] for h in r['review_hits']])+'</div>'
        content+='<details><summary>Generated-script launch requests</summary>'+table(['Call line','Timestamp','Command'],[[str(c['line']),escaped(c['timestamp']),f'<code>{escaped(c["command"])}</code>'] for c in r['launches']])+'</details>'
        content+='<details><summary>Scripts, tool counts, and metadata</summary><pre>'+escaped(json.dumps({k:r[k] for k in ['scripts','tool_counts','exploration_actions','exploration_commands','patched_files','session_metadata','reasoning_efforts','usage']},indent=2,ensure_ascii=False))+'</pre></details>'
        if r['final']:
            content+=f'<details><summary>Assistant final message · line {r["final"]["line"]} · claim only</summary><pre>{escaped(r["final"]["text"])}</pre></details>'
        content+='</section>'
    return page('Per-run source evidence', 'Auditable measurements for every included task bundle. Runtime output is reported evidence; it is not an independent acceptance test.', content)


def export(data, out):
    directory=out/'data';directory.mkdir(exist_ok=True)
    (directory/'metrics.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    fields=['id','group','app','folder','file','sha256','minutes','raw_log_span_minutes','start','end']+METRICS[1:]+['replay_successes','replay_failures','final_replay_ms','first_all_pass_minutes','folder_failed_label']
    fields=list(dict.fromkeys(fields))
    with (directory/'sessions.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        writer.writerows({key:r.get(key) for key in fields} for r in data['runs'])
    with (directory/'application_summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['app','native_n','mcp_n','native_minutes_mean','mcp_minutes_mean','duration_change_pct','native_tokens_mean','mcp_tokens_mean','token_change_pct']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for app in data['application_summary']:
            a,b=app['native'],app['mcp']
            writer.writerow({'app':app['app'],'native_n':a['n'],'mcp_n':b['n'],'native_minutes_mean':a['minutes']['mean'],'mcp_minutes_mean':b['minutes']['mean'],'duration_change_pct':change(a['minutes']['mean'],b['minutes']['mean']), 'native_tokens_mean':a['total_tokens']['mean'],'mcp_tokens_mean':b['total_tokens']['mean'],'token_change_pct':change(a['total_tokens']['mean'],b['total_tokens']['mean'])})
    with (directory/'inventory.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['group','folder','status','log_count','files']);writer.writeheader()
        writer.writerows({**i,'files':'; '.join(i['files'])} for i in data['inventory'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.source.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    runs,inventory,excluded=discover(root)
    reused=defaultdict(list)
    for r in runs:
        reused[r['session_metadata'].get('id')].append(r['id'])
    data={'schema_version':2,'source_root':str(root),'generated_at_local':datetime.now().astimezone().isoformat(),
          'instructions':'Include remaining testcase variants; replace old native Paint; retain new MCP Notepad/Paint/Word runs.',
          'runs':runs,'inventory':inventory,'excluded':excluded,'summary':comparison(runs),
          'application_summary':[{'app':app,**comparison([r for r in runs if r['app']==app])} for app in sorted({r['app'] for r in runs})],
          'testcase_variants':testcase_variants(runs),'sensitivity':sensitivity(runs),
          'reused_session_ids':{k:v for k,v in reused.items() if k and len(v)>1}}
    export(data,out);figures(data,out/'figures')
    (out/'session_comparison.html').write_text(build_overview(data),encoding='utf-8')
    (out/'session_evidence.html').write_text(build_evidence(data),encoding='utf-8')
    print(json.dumps({'report':str(out/'session_comparison.html'),'counts':{g:data['summary'][g]['n'] for g in GROUPS},'means':{g:data['summary'][g]['minutes']['mean'] for g in GROUPS},'source_parse_errors':sum(len(r['parse_errors']) for r in runs)},indent=2))


if __name__=='__main__':
    main()
