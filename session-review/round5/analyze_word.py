"""Read the supplied session as evidence, never execute its commands."""
import collections
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

SOURCE = Path(r'C:\Users\DottedAnt\Downloads\rollout-2026-09-30T14-15-36-01a0f23d-e14e-7563-818a-40e41be0d4ee.jsonl')
ROOT = Path(__file__).resolve().parent
calls = {}
rows = []
messages = []
for line, raw in enumerate(SOURCE.read_text(encoding='utf-8-sig').splitlines(), 1):
    event = json.loads(raw)
    p = event.get('payload', {})
    if event['type'] != 'response_item':
        continue
    kind = p.get('type')
    stamp = event['timestamp']
    if kind in ('function_call', 'custom_tool_call'):
        args = p.get('arguments', p.get('input', ''))
        try:
            args = json.loads(args)
        except (ValueError, TypeError):
            pass
        cmd = args.get('command', args.get('cmd', args.get('code', str(args)))) if isinstance(args, dict) else args
        item = dict(line=line, time=stamp, tool=p.get('name'), command=cmd)
        calls[p.get('call_id')] = item
        rows.append(item)
    elif kind in ('function_call_output', 'custom_tool_call_output'):
        item = calls.get(p.get('call_id'))
        if item:
            out = p.get('output', '')
            if not isinstance(out, str):
                out = json.dumps(out)
            item.update(output=out, outputLine=line, end=stamp)
            wall = re.search(r'Wall time: ([\d.]+) seconds', out)
            item['wall'] = float(wall[1]) if wall else None
    elif kind == 'message' and p.get('role') in ('assistant', 'user'):
        content = '\n'.join(x.get('text', '') for x in p.get('content', []))
        if p.get('role') == 'assistant' or len(content) < 4000:
            messages.append(dict(line=line, time=stamp, role=p['role'], text=content))
summary = dict(source=str(SOURCE), sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(), calls=len(rows), tools=dict(collections.Counter(x['tool'] for x in rows)), wallSum=sum(x.get('wall') or 0 for x in rows), messages=messages)
(ROOT/'session.json').write_text(json.dumps(dict(summary=summary, calls=rows), indent=2), encoding='utf-8')
timeline = []
for r in rows:
    output = r.get('output', '')
    # Preserve all errors and command envelopes separately in session.json.
    excerpt = output[:1800] if not re.search(r'Exit code: 0', output) or re.search(r'"ok":false|"ok": false', output) else output[:700]
    timeline.append(f"L{r['line']} {r['time']} {r['tool']} wall={r.get('wall')} outputChars={len(output)}\n{r['command'][:4000]}\n=> {excerpt}\n")
(ROOT/'timeline.txt').write_text('\n'.join(timeline), encoding='utf-8')
(ROOT/'messages.txt').write_text('\n\n'.join(f"L{r['line']} {r['time']} {r['role']}\n{r['text']}" for r in messages), encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='messages'}, indent=2))

def seconds(stamp):
    return dt.datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()

envelopes = []
for call in rows:
    for fragment in call.get('output', '').splitlines():
        try:
            value = json.loads(fragment)
        except ValueError:
            continue
        if isinstance(value, dict) and 'command' in value and 'ok' in value:
            envelopes.append(dict(line=call['line'], result=value))
by_line = {r['line']: r for r in rows}
boundaries = [('Preparation', '2026-09-30T12:15:55.538Z', by_line[59]['time']),
              ('GUI exploration and checkpoint', by_line[59]['time'], by_line[319]['end']),
              ('Script generation and first preflight', by_line[319]['end'], by_line[357]['time']),
              ('Execution, diagnosis and repairs', by_line[357]['time'], by_line[414]['end']),
              ('Delivery', by_line[414]['end'], messages[-1]['time'])]
requests = [r for r in rows if r['tool']=='apply_patch' and re.search(r'\*\*\* Add File: .*request-\d+.*\.json', r['command'], re.I)]
metrics = dict(phases=[dict(phase=name, seconds=round(seconds(end)-seconds(start), 3)) for name, start, end in boundaries],
    elapsedSeconds=round(seconds(messages[-1]['time'])-seconds(boundaries[0][1]), 3),
    cliEnvelopes=len(envelopes), cliBackendSeconds=round(sum(e['result'].get('durationMs', 0) for e in envelopes)/1000, 3),
    commandCounts=dict(collections.Counter(e['result']['command'] for e in envelopes)),
    failures=[dict(line=e['line'], command=e['result']['command'], error=e['result']['error']) for e in envelopes if not e['result']['ok']],
    emptySelects=[dict(line=e['line'], durationMs=e['result']['durationMs']) for e in envelopes if e['result']['command']=='select' and e['result'].get('data', {}).get('count')==0],
    shellReportedSeconds=summary['wallSum'], finalSuccessfulRunShellSeconds=by_line[414]['wall'],
    finalRuntimeTiming=dict(commandCount=35, wrapperMs=31676, backendMs=31109, waitMs=11387, cleanupMs=1972, totalMs=32530, transportOverheadMs=567, otherMs=854),
    requestFileCreationCalls=len(requests), requestFileCreationLines=[r['line'] for r in requests],
    generatedExecutionLines=[357,380,414],
    observationBytes=sum(len(json.dumps(e['result'], separators=(',', ':')).encode('utf-8')) for e in envelopes if e['result']['command']=='observe'),
    evidenceNotes=['Shell wall-time sums can include parallel calls and are not elapsed session time.', 'CLI totals include only intact direct envelopes, not command records inside generated execution results.', 'Final runtime timing transcribed from the result in the output of call at source line 414. These are supplied-run timings, not timings measured after this patch.'])
previous=json.loads((ROOT.parent/'round4/metrics.json').read_text(encoding='utf-8'))
metrics['comparison']=dict(previousElapsedSeconds=previous['elapsedSeconds'], elapsedReductionPercent=round(100*(1-metrics['elapsedSeconds']/previous['elapsedSeconds']),2), previousExplorationSeconds=previous['phases'][1]['seconds'])
(ROOT/'metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
print(json.dumps(metrics, indent=2))
