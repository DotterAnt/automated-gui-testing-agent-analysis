"""Extract the supplied aborted rollout as data; never execute its commands."""
import hashlib
import json
from pathlib import Path

source = Path(r'C:\Users\DottedAnt\Downloads\rollout-2026-09-30T15-39-36-01a0f28a-c6eb-7c03-89be-2f0b26af1dd2.jsonl')
root = Path(__file__).resolve().parent
calls, messages, by_id = [], [], {}
for line, raw in enumerate(source.read_text(encoding='utf-8-sig').splitlines(), 1):
    event = json.loads(raw)
    if event['type'] != 'response_item':
        continue
    payload = event.get('payload', {})
    kind = payload.get('type')
    if kind in ('function_call', 'custom_tool_call'):
        args = payload.get('arguments', payload.get('input', ''))
        try:
            args = json.loads(args)
        except (ValueError, TypeError):
            pass
        command = args.get('command', args.get('cmd', args.get('code', str(args)))) if isinstance(args, dict) else args
        item = dict(line=line, time=event['timestamp'], tool=payload.get('name'), command=command)
        calls.append(item)
        by_id[payload.get('call_id')] = item
    elif kind in ('function_call_output', 'custom_tool_call_output'):
        item = by_id.get(payload.get('call_id'))
        if item is not None:
            item.update(output=payload.get('output', ''), outputLine=line, end=event['timestamp'])
    elif kind == 'message' and payload.get('role') == 'assistant':
        messages.append(dict(line=line, time=event['timestamp'], text='\n'.join(x.get('text', '') for x in payload.get('content', []))))
summary = dict(source=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest(), calls=calls, messages=messages)
(root / 'session.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
text = []
for item in calls:
    text.append(f"L{item['line']} {item['time']} {item['tool']}\n{item['command']}\n")
    output = item.get('output', '')
    if not isinstance(output, str):
        output = json.dumps(output)
    for fragment in output.splitlines():
        try:
            result = json.loads(fragment)
        except ValueError:
            continue
        if isinstance(result, dict) and result.get('command') in ('type', 'wait-file', 'read'):
            text.append(json.dumps(result, ensure_ascii=False) + '\n')
        elif isinstance(result, dict) and result.get('ok') is False:
            text.append(json.dumps(result, ensure_ascii=False) + '\n')
    if item['tool'] == 'shell_command' and ('New-Item' in item['command'] or 'Action Begin' in item['command']):
        text.append(output + '\n')
(root / 'commands.txt').write_text('\n'.join(text), encoding='utf-8')
(root / 'messages.txt').write_text('\n\n'.join(f"L{x['line']} {x['time']}\n{x['text']}" for x in messages), encoding='utf-8')
print(json.dumps(dict(source=str(source), sha256=summary['sha256'], calls=len(calls))))
