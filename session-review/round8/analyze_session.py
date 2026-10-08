"""Read supplied rollout as evidence; never execute attached commands or scripts."""
import collections
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

source = Path(r'C:\Users\DottedAnt\Downloads\rollout-2026-09-30T16-13-28-01a0f2a9-cabe-7330-ae7b-011285aeb257.jsonl')
root = Path(__file__).resolve().parent
calls, messages, by_id = [], [], {}
for line, raw in enumerate(source.read_text(encoding='utf-8-sig').splitlines(), 1):
    event = json.loads(raw)
    if event['type'] != 'response_item':
        continue
    p = event.get('payload', {})
    kind = p.get('type')
    if kind in ('function_call', 'custom_tool_call'):
        args = p.get('arguments', p.get('input', ''))
        try:
            args = json.loads(args)
        except (ValueError, TypeError):
            pass
        command = args.get('command', args.get('cmd', args.get('code', str(args)))) if isinstance(args, dict) else args
        item = dict(line=line, time=event['timestamp'], tool=p.get('name'), command=command)
        calls.append(item)
        by_id[p.get('call_id')] = item
    elif kind in ('function_call_output', 'custom_tool_call_output'):
        item = by_id.get(p.get('call_id'))
        if item is not None:
            item.update(output=p.get('output', ''), outputLine=line, end=event['timestamp'])
    elif kind == 'message' and p.get('role') in ('assistant', 'user'):
        content='\n'.join(x.get('text', '') for x in p.get('content', []))
        if p.get('role')=='assistant' or len(content)<6000:
            messages.append(dict(line=line, time=event['timestamp'], role=p['role'], text=content))
envelopes, executions = [], []
timeline = []
for item in calls:
    output = item.get('output', '')
    if not isinstance(output, str):
        output = json.dumps(output)
    wall=re.search(r'Wall time: ([\d.]+) seconds', output)
    item['wallSeconds']=float(wall[1]) if wall else None
    timeline.append(f"L{item['line']} {item['time']} {item['tool']} wall={item['wallSeconds']}\n{item['command'][:7000]}\n")
    for fragment in output.splitlines():
        try:
            result = json.loads(fragment)
        except ValueError:
            continue
        if not isinstance(result, dict):
            continue
        if 'command' in result and 'ok' in result:
            envelopes.append(dict(line=item['line'], result=result))
            data=result.get('data') or {}
            entry=dict(command=result['command'],ok=result['ok'],durationMs=result.get('durationMs'),error=result.get('error'))
            if result['command'] in ('type','read','read-pdf','wait-file'):
                entry['data']=data
            elif result['command'] in ('wait-element','select','click','click-coordinate','press-key'):
                entry['data']=data
            timeline.append(json.dumps(entry,ensure_ascii=False)[:4500]+'\n')
        elif 'steps' in result and 'timing' in result and 'summary' in result:
            executions.append(dict(line=item['line'],ok=result['ok'],timing=result['timing'],summary=result['summary'],cleanupOk=result.get('cleanupOk')))
        elif result.get('ok') is False:
            timeline.append(json.dumps(result,ensure_ascii=False)[:1500]+'\n')
    if item['tool']=='shell_command' and ('New-Item' in item['command'] or 'Action Begin' in item['command'] or 'Action Complete' in item['command']):
        timeline.append(output[:2000]+'\n')
summary = dict(source=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest(), calls=calls, messages=messages, envelopes=envelopes, executions=executions)
(root/'session.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
(root/'timeline.txt').write_text('\n'.join(timeline),encoding='utf-8')
(root/'messages.txt').write_text('\n\n'.join(f"L{x['line']} {x['time']} {x['role']}\n{x['text']}" for x in messages),encoding='utf-8')
metrics=dict(toolCalls=len(calls),toolCounts=dict(collections.Counter(x['tool'] for x in calls)),
    cliCommands=len(envelopes),commandCounts=dict(collections.Counter(x['result']['command'] for x in envelopes)),
    backendSeconds=round(sum(x['result'].get('durationMs',0) for x in envelopes)/1000,3),
    failures=[dict(line=x['line'],command=x['result']['command'],error=x['result'].get('error')) for x in envelopes if not x['result']['ok']],
    executions=executions)
def seconds(stamp):
    return dt.datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()
by_line={x['line']:x for x in calls}
boundaries=[('Preparation','2026-09-30T14:13:47.231Z',by_line[57]['time']),
    ('Full GUI walkthrough',by_line[57]['time'],by_line[417]['end']),
    ('Generation and first preflight',by_line[417]['end'],by_line[439]['time']),
    ('Replay and repair',by_line[439]['time'],by_line[457]['end']),
    ('Delivery',by_line[457]['end'],messages[-1]['time'])]
metrics['phases']=[dict(phase=name,seconds=round(seconds(end)-seconds(start),3)) for name,start,end in boundaries]
metrics['elapsedSeconds']=round(seconds(messages[-1]['time'])-seconds(boundaries[0][1]),3)
metrics['createToSuccessfulTitleSeconds']=round(seconds(by_line[236]['end'])-seconds(by_line[63]['time']),3)
metrics['firstInputAttemptToSuccessSeconds']=round(seconds(by_line[236]['end'])-seconds(by_line[88]['time']),3)
metrics['failedTypingBackendMs']=sum(x['result'].get('durationMs',0) for x in envelopes if x['result']['command']=='type' and not x['result']['ok'])
metrics['successfulTitleTypingMs']=next(x['result']['durationMs'] for x in envelopes if x['line']==236 and x['result']['command']=='type')
metrics['notes']=['Source commands were read, never executed. Elapsed phases use timestamps, not summed overlapping shell durations.',
    'CLI counts/timings cover intact direct envelopes; nested replay commands are represented by execution timing separately.',
    'No native keyboard-focus snapshot was captured by the old CLI; the new fallback is verified by a deliberately inconsistent accessibility fixture, not a fresh PowerPoint session.']
(root/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
print(json.dumps(metrics,indent=2))
