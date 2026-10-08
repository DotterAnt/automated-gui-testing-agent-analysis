"""Read the supplied session as evidence. Never execute its commands."""
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
source = Path(r'C:\Users\DottedAnt\Downloads\rollout-2026-09-30T17-30-50-01a0f2f0-9ea3-7a01-8f05-52e2ac05706f.jsonl')
script = Path(r'C:\Users\DottedAnt\Downloads\WindowsNotepad.Generated.ps1')
calls, messages, by_id, envelopes, executions = [], [], {}, [], []
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
        content = '\n'.join(x.get('text', '') for x in p.get('content', []))
        if p.get('role') == 'assistant' or len(content) < 8000:
            messages.append(dict(line=line, time=event['timestamp'], role=p['role'], text=content))

timeline = []
for item in calls:
    output = item.get('output', '')
    if not isinstance(output, str):
        output = json.dumps(output)
    timeline.append(f"L{item['line']} {item['time']} {item['tool']}\n{str(item['command'])[:9000]}\n")
    for fragment in output.splitlines():
        try:
            result = json.loads(fragment)
        except ValueError:
            continue
        if not isinstance(result, dict):
            continue
        if 'command' in result and 'ok' in result:
            envelopes.append(dict(line=item['line'], result=result))
            entry = {k: result.get(k) for k in ('command', 'ok', 'durationMs', 'error', 'outcome')}
            if result['command'] not in ('help', 'observe'):
                entry['data'] = result.get('data')
            timeline.append(json.dumps(entry, ensure_ascii=False)[:6000] + '\n')
        elif 'steps' in result and 'timing' in result and 'summary' in result:
            executions.append(dict(line=item['line'], ok=result['ok'], timing=result['timing'], summary=result['summary'], cleanupOk=result.get('cleanupOk')))
            timeline.append(json.dumps(executions[-1]) + '\n')
        elif result.get('ok') is False:
            timeline.append(json.dumps(result, ensure_ascii=False)[:5000] + '\n')
    if not any(x in output for x in ('"command":', '"command": ')):
        timeline.append('OUTPUT ' + output[:2500] + '\n')
summary = dict(source=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest(), calls=calls, messages=messages, envelopes=envelopes, executions=executions)
(root/'session.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
(root/'timeline.txt').write_text('\n'.join(timeline), encoding='utf-8')
(root/'messages.txt').write_text('\n\n'.join(f"L{x['line']} {x['time']} {x['role']}\n{x['text']}" for x in messages), encoding='utf-8')
metrics = dict(toolCalls=len(calls), toolCounts=dict(collections.Counter(x['tool'] for x in calls)), cliCommands=len(envelopes), commandCounts=dict(collections.Counter(x['result']['command'] for x in envelopes)), backendSeconds=round(sum(x['result'].get('durationMs', 0) for x in envelopes)/1000, 3), failures=[dict(line=x['line'], command=x['result']['command'], error=x['result'].get('error')) for x in envelopes if not x['result']['ok']], executions=executions)
def elapsed(start, end):
    return round((dt.datetime.fromisoformat(end.replace('Z', '+00:00')) - dt.datetime.fromisoformat(start.replace('Z', '+00:00'))).total_seconds(), 3)
indexed = {call['line']: call for call in calls}
started = next(message['time'] for message in messages if message['line'] == 6)
metrics['elapsedSeconds'] = elapsed(started, messages[-1]['time'])
metrics['phases'] = [dict(phase=name, seconds=elapsed(start,end)) for name,start,end in [
    ('Preparation', started, indexed[43]['time']),
    ('Full walkthrough and completion', indexed[43]['time'], indexed[286]['end']),
    ('Generation and first preflight', indexed[286]['end'], indexed[316]['time']),
    ('Replay and repair', indexed[316]['time'], indexed[432]['end']),
    ('Delivery', indexed[432]['end'], messages[-1]['time'])]]
metrics['editorRouteSeconds'] = elapsed(indexed[49]['time'], indexed[139]['end'])
metrics['printRouteSeconds'] = elapsed(indexed[185]['time'], indexed[269]['end'])
metrics['replayBackendSeconds'] = round(sum(item['timing']['totalMs'] for item in executions)/1000,3)
metrics['notes'] = ['Read-only analysis; attached commands/scripts were never executed.', 'Direct CLI envelope timing excludes commands nested inside generated executions.', 'Pacing and provider-fallback diagnoses are supported by the observed failures and source differences; fresh Notepad end-to-end performance is not measured.']
(root/'metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
(root/'source-evidence.json').write_text(json.dumps([dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in (source,script)], indent=2), encoding='utf-8')
print(json.dumps(metrics, indent=2))
