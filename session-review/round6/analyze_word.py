"""Read the supplied session as evidence, never execute its commands."""
import collections
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

SOURCE = Path(r'C:\Users\DottedAnt\Downloads\rollout-2026-09-30T15-02-47-01a0f269-10f9-77a0-ac67-16ba20eeb561.jsonl')
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

envelopes, executions, image_sizes = [], [], []
for call in rows:
    for fragment in call.get('output', '').splitlines():
        try:
            value = json.loads(fragment)
        except ValueError:
            continue
        if isinstance(value, dict) and 'command' in value and 'ok' in value:
            envelopes.append(dict(line=call['line'], result=value))
        if isinstance(value, dict) and 'steps' in value and 'timing' in value and 'summary' in value:
            executions.append(dict(line=call['line'], ok=value['ok'], timing=value['timing'], cleanupOk=value.get('cleanupOk'),
                failedSteps=[dict(stepIndex=s['stepIndex'], error=s.get('error')) for s in value['steps'] if s['status']=='FAIL']))
    if call['tool']=='view_image':
        import base64, struct
        match=re.search(r'data:image/png;base64,([A-Za-z0-9+/=]+)',call.get('output',''))
        if match:
            width,height=struct.unpack('>II',base64.b64decode(match[1])[:24][16:24])
            image_sizes.append(dict(line=call['line'],width=width,height=height))
by_line={r['line']:r for r in rows}
boundaries=[('Preparation','2026-09-30T13:02:56.003Z',by_line[51]['time']),
            ('GUI exploration and checkpoint',by_line[51]['time'],by_line[163]['end']),
            ('Script generation and first preflight',by_line[163]['end'],by_line[203]['time']),
            ('Execution, diagnosis and repairs',by_line[203]['time'],by_line[292]['end']),
            ('Delivery',by_line[292]['end'],messages[-1]['time'])]
previous=json.loads((ROOT.parent/'round5/metrics.json').read_text(encoding='utf-8'))
elapsed=round(seconds(messages[-1]['time'])-seconds(boundaries[0][1]),3)
metrics=dict(phases=[dict(phase=name,seconds=round(seconds(end)-seconds(start),3)) for name,start,end in boundaries],
    elapsedSeconds=elapsed,toolCalls=len(rows),toolCounts=summary['tools'],
    cliEnvelopes=len(envelopes),cliBackendSeconds=round(sum(e['result'].get('durationMs',0) for e in envelopes)/1000,3),
    commandCounts=dict(collections.Counter(e['result']['command'] for e in envelopes)),
    cliFailures=[dict(line=e['line'],command=e['result']['command'],error=e['result']['error']) for e in envelopes if not e['result']['ok']],
    executions=executions,finalSuccessfulRunShellSeconds=by_line[292]['wall'],
    requestFileCreationCalls=len([r for r in rows if r['tool']=='apply_patch' and re.search(r'\*\*\* Add File: .*request.*\.json',r['command'],re.I)]),
    repeatedPreflightLines=[223,252,285],extraRecoveryLines=[222,230,231,251,259,260,286],
    screenshotRegions=[dict(line=e['line'],region=e['result']['data']['region']) for e in envelopes if e['result']['command']=='screenshot'],
    embeddedImageSizes=image_sizes,
    comparison=dict(previousElapsedSeconds=previous['elapsedSeconds'],elapsedReductionPercent=round(100*(1-elapsed/previous['elapsedSeconds']),2),
        previousExplorationSeconds=previous['phases'][1]['seconds'],previousToolCalls=90),
    evidenceNotes=['Source attachments were read, not executed. Timings describe the supplied run before this patch.',
        'CLI totals include intact direct envelopes only, excluding commands nested in generated execution results.',
        'Phase boundaries use source timestamps; overlapping shell durations are not summed as elapsed time.',
        'The DPI inconsistency is directly visible in capture dimensions; its contribution to the specific missed click is an inference, supported by a local scaled-desktop reproduction.'])
(ROOT/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
print(json.dumps(metrics,indent=2))

