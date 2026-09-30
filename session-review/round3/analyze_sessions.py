"""Read supplied rollout logs and scripts as data only. No logged code is executed."""
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parent
SOURCES = [Path(r'C:\Users\DottedAnt\Downloads\results'), Path(r'C:\diplomamunka\experiments')]

def analyze(path):
    raw = path.read_bytes()
    events, malformed = [], []
    for line, text in enumerate(raw.decode('utf-8-sig').split('\n'), 1):
        if not text.strip():
            continue
        try:
            events.append(json.loads(text))
        except ValueError as e:
            malformed.append(dict(line=line, error=str(e)))
            events.append({}) # Preserve original source line numbers.
    calls, outputs, messages, commands, writes = {}, [], [], [], []
    for line, event in enumerate(events, 1):
        p = event.get('payload', {})
        if event.get('type') != 'response_item':
            continue
        kind = p.get('type', '')
        timestamp = event.get('timestamp')
        if kind in ('function_call', 'custom_tool_call'):
            arg = p.get('arguments', p.get('input', ''))
            try:
                arg = json.loads(arg)
            except (ValueError, TypeError):
                pass
            cmd = arg.get('command', arg.get('cmd', arg.get('code', ''))) if isinstance(arg, dict) else arg
            c = dict(line=line, timestamp=timestamp, tool=p.get('name'), command=cmd)
            calls[p.get('call_id')] = c
            if re.search(r'\*\*\* (?:Add|Update) File:.*\.ps1|Set-Content.*(?:Generated|GuiTest).*\.ps1', cmd, re.I):
                writes.append(dict(line=line, timestamp=timestamp))
        elif kind in ('function_call_output', 'custom_tool_call_output'):
            out = p.get('output', '')
            if not isinstance(out, str):
                continue
            call = calls.get(p.get('call_id'), {})
            wall = re.search(r'Wall time: ([\d.]+) seconds', out)
            outputs.append(dict(line=line, timestamp=timestamp, call=call, wall=float(wall[1]) if wall else None, text=out))
            for fragment in out.splitlines():
                try:
                    envelope = json.loads(fragment)
                except ValueError:
                    continue
                if isinstance(envelope, dict) and 'command' in envelope and 'ok' in envelope:
                    data = envelope.get('data') or {}
                    commands.append(dict(line=line, call_line=call.get('line'), timestamp=timestamp,
                                         command=envelope['command'], ok=envelope['ok'], error=envelope.get('error'),
                                         durationMs=envelope.get('durationMs'), wall=float(wall[1]) if wall else None,
                                         count=data.get('count'), data=data))
        elif kind == 'message' and p.get('role') == 'assistant':
            text = '\n'.join(x.get('text', '') for x in p.get('content', []) if isinstance(x, dict))
            messages.append(dict(line=line, timestamp=timestamp, text=text))
    timestamps = [e['timestamp'] for e in events if e.get('timestamp')]
    elapsed = (dt.datetime.fromisoformat(timestamps[-1].replace('Z', '+00:00')) - dt.datetime.fromisoformat(timestamps[0].replace('Z', '+00:00'))).total_seconds()
    # Raw shell excerpts include command context, so a reviewer can distinguish a real failure from quoted source.
    evidence = []
    for o in outputs:
        if re.search(r'Get-Content|\brg\b', o['call'].get('command', '')):
            continue
        hits = [s[:1600] for s in o['text'].splitlines() if re.search(r'"ok":false|Exception|timed out|timeout|not a confirmed|requires an enabled|cannot|forbids|failed|not found|unavailable|not supported', s, re.I)]
        if hits:
            evidence.append(dict(line=o['line'], call=o['call'], wall=o['wall'], excerpts=hits[:8]))
    envelopes_per_output = collections.Counter(c['line'] for c in commands)
    overhead = [c['wall'] - c['durationMs']/1000 for c in commands if c['wall'] is not None and c['durationMs'] is not None and envelopes_per_output[c['line']] == 1]
    scripts = []
    for script in path.parent.glob('*.ps1') if path.parent != SOURCES[1] else []:
        txt = script.read_text(encoding='utf-8-sig')
        scripts.append(dict(file=str(script), lines=len(txt.splitlines()), sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
                            review_lines=[dict(line=i, text=s) for i,s in enumerate(txt.splitlines(),1) if re.search(r'COMObject|OleDb|SqlClient|SendKeys|Add-Type|SetValue|ValuePattern|Start-Process|ReadAllBytes|WriteAll|Set-Content|Out-File|Start-Sleep|hotkey|click-coordinate|Policy|explor',s,re.I)]))
    return dict(file=str(path), label=path.parent.name if path.parent != SOURCES[1] else path.stem,
                sha256=hashlib.sha256(raw).hexdigest(), elapsed_seconds=elapsed, malformed_lines=malformed,
                calls=dict(collections.Counter(c['tool'] for c in calls.values())),
                cli_commands=dict(collections.Counter(c['command'] for c in commands)), cli_failures=sum(not c['ok'] for c in commands),
                cli_backend_seconds=sum(c['durationMs'] or 0 for c in commands)/1000,
                median_shell_minus_backend_seconds=statistics.median(overhead) if overhead else None,
                writes=writes, commands=commands, evidence=evidence, messages=messages, scripts=scripts,
                source_read_calls=[c for c in calls.values() if re.search(r'Get-Content|\brg\b',c['command'])],
                script_execution_calls=[c for c in calls.values() if re.search(r'-File.*(?:Generated|GuiTest|Test-Microsoft).*\.ps1',c['command'],re.I) and not re.search(r'Test-GeneratedScript\.ps1|Get-Content',c['command'],re.I)])

if __name__ == '__main__':
    results, hashes = [], {}
    for source in SOURCES:
        for path in sorted(source.rglob('*.jsonl')):
            result = analyze(path)
            if result['sha256'] in hashes:
                result['duplicate_of'] = hashes[result['sha256']]
            hashes[result['sha256']] = result['file']
            results.append(result)
    (ROOT/'metrics.json').write_text(json.dumps(results, indent=2, ensure_ascii=False),encoding='utf-8')
    for r in results:
        print(f"{r['label']:40} {r['elapsed_seconds']/60:6.1f}m CLI={sum(r['cli_commands'].values()):3} failures={r['cli_failures']:2} backend={r['cli_backend_seconds']:6.1f}s reads={len(r['source_read_calls']):3} exec={len(r['script_execution_calls']):2} {'DUPLICATE' if r.get('duplicate_of') else ''}")
    for r in results:
        if 'cli-frm' in r['label'] and not r.get('duplicate_of'):
            lines=[f"{r['label']} {r['file']}", '\nMESSAGES']
            lines.extend(f"L{x['line']} {x['timestamp']} {x['text']}" for x in r['messages'])
            lines.append('\nFAILURE EVIDENCE')
            for e in r['evidence']:
                lines.append(f"L{e['line']} call L{e['call'].get('line')} {e['call'].get('command','')[:1500]}\n"+'\n'.join(e['excerpts']))
            (ROOT/(r['label']+'.txt')).write_text('\n'.join(lines),encoding='utf-8')
