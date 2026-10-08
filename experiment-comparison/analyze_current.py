"""Reproducible read-only analysis of native, MCP, AI-only and new Codex logs.

Never imports or executes supplied scripts or commands. Older reports are kept.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import re
from statistics import mean, median, stdev

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from extract import (APPS, read_records, body, json_values, json_field, stamp,
                     testcase_from_outputs, observed_steps, first_attempt_steps,
                     execution_headers, normalized, state)

ROOTS=['native','mcp','aionly','newcodex']
OFFICE=['Excel','PowerPoint','Word']
PRIMARY_MODELS=['gpt-5.6-luna','gpt-6-luna','gpt-6.1-sol']
ALL_MODELS=['gpt-5.6-luna','gpt-5.6-sol','gpt-6-luna','gpt-6-sol','gpt-6.1-sol']
MODEL_ORDER=['gpt-5.5',*ALL_MODELS]
LABELS={'native':'Native','mcp':'MCP + thesis framework','aionly':'AI-only reimplementation'}
COLORS={'native':'#3373ad','mcp':'#db6945','aionly':'#3b947f'}
MODEL_COLORS=['#bd7045','#5387bd','#388879','#8d72aa','#d1a64a']

def text_output(value,depth=0):
    """Unwrap tool text/exec stdout envelopes without including image data."""
    if depth>8:return ''
    if isinstance(value,list):return '\n'.join(text_output(x,depth+1) for x in value)
    if isinstance(value,dict):
        if value.get('type') in ['image','input_image','audio']:return ''
        if isinstance(value.get('text'),str):return text_output(value['text'],depth+1)
        if isinstance(value.get('content'),list):return text_output(value['content'],depth+1)
        if isinstance(value.get('output'),(str,list)):return text_output(value['output'],depth+1)
        return json.dumps(value,ensure_ascii=False)
    if not isinstance(value,str):return ''
    s=re.sub(r'\x1b\[[0-9;?]*[A-Za-z]','',body(value))
    parts=[];wrapped=False
    for v in json_values(s):
        if isinstance(v,dict) and (isinstance(v.get('content'),list) or isinstance(v.get('output'),(str,list))):
            parts.append(text_output(v,depth+1));wrapped=True
        else:parts.append(json.dumps(v,ensure_ascii=False))
    # json_values itself unwraps content, so keep ordinary text as well.
    if wrapped:return '\n'.join(parts)
    return s

def arguments(p):
    a=p.get('arguments',p.get('input',''))
    if isinstance(a,str):
        try:return json.loads(a)
        except ValueError:return a
    return a

def command_text(a):
    if isinstance(a,dict):return str(a.get('cmd',a.get('command',a.get('code',a))))
    if not isinstance(a,str):return str(a)
    # Common JS exec wrappers retain literal shell arguments. Decode them so
    # quoted PowerShell paths match the same launch detector as older logs.
    found=[]
    for m in re.finditer(r'\b(?:cmd|command)["\']?\s*:\s*("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')',a):
        try:found.append(json.loads(m[1]) if m[1].startswith('"') else m[1][1:-1])
        except ValueError:pass
    return '\n'.join(found) if found else a

def result_read(command):
    return bool(re.search(r'Get-Content|Import-Csv|read_text|json\.load|\btype\b',command,re.I)
                and re.search(r'(?:result|summary|report|run-log|evidence\.log|run\.log)[\w.*-]*\.(?:json|csv|txt|log)',command,re.I)
                and not re.search(r'(?:Get-Content|read_text)[^;\n]*\.(?:ps1|py)',command,re.I))

def launch(command,names):
    if re.search(r'-ValidateOnly\b|-PreflightOnly\b',command,re.I):return False
    if re.search(r'apply_patch|^\*\*\*',command,re.I):return False
    command=re.sub(r'@[\'\"]\r?\n.*?\r?\n[\'\"]@','',command,flags=re.S)
    if re.search(r'Set-Content|WriteAllText|write_text',command,re.I):
        tail=list(re.finditer(r'(?:;|\n)\s*((?:powershell(?:\.exe)?\b|pwsh\b|&\s+[\'\"]).*)',command,re.I))
        if not tail:return False
        command=tail[-1][1]
    for m in re.finditer(r'(?:-File\s+|&\s+)(?:\'([^\']+\.ps1)\'|"([^"]+\.ps1)"|([^\s;]+\.ps1))',command,re.I):
        name=Path(next(g for g in m.groups() if g).replace('\\','/')).name.lower()
        if name in names:return True
    if any(name.endswith('.py') and name.lower() in command.lower() for name in names):
        return bool(re.search(r'python(?:\.exe)?|dependencies[/\\]python',command,re.I)) and not bool(re.search(r'Get-Content|read_text',command,re.I))
    return bool(re.search(r'python[^\n]*-m\s+desktop_agent\.cli\s+run',command,re.I))

def extra_states(text,actions):
    """Indexed custom report schemas and native console forms."""
    found=observed_steps(text,actions)
    def walk(v):
        if isinstance(v,dict):
            if v.get('qualifying') is False or v.get('runKind')=='Diagnostic':return
            lower={str(k).lower():x for k,x in v.items()}
            s=state(lower.get('status',lower.get('result',lower.get('passed'))))
            ident=lower.get('id',lower.get('stepid',lower.get('index',lower.get('step'))))
            m=re.fullmatch(r'(?:S|Step\s*)?([1-5])',str(ident),re.I)
            if s and m:found[int(m[1])]=s
            for k,x in v.items():
                if k.lower() in ['steps','results','stepresults','report']:walk(x)
        elif isinstance(v,list):
            for x in v:walk(x)
    for v in json_values(text):walk(v)
    for line in text.split('\n'):
        if len(line)>1800 or line.lstrip().startswith(('#','+','-','{','"','def ','function ')):continue
        m=re.search(r'\b(?:S|Step\s*)([1-5])\s*[:\-]?\s*(PASS(?:ED)?|FAIL(?:ED)?|SKIP(?:PED)?)\b',line,re.I)
        if m:found[int(m[1])]=state(m[2])
        if re.search(r'\b(?:all (?:5|five) (?:test )?steps (?:have )?(?:pass(?:ed)?|succeeded)|(?:passed|results|pass)\s*[:=]?\s*5\s*/\s*5)\b',line,re.I):
            found.update(dict.fromkeys(range(1,6),'PASS'))
    return found

def walk_dicts(v):
    if isinstance(v,dict):
        yield v
        for k,x in v.items():
            if k not in ['guide','template','workflow','nextAction','next','route','recordedSteps']:yield from walk_dicts(x)
    elif isinstance(v,list):
        for x in v:yield from walk_dicts(x)

def exploration_completion(records,start,end_line):
    """First confirmed Complete response, timed from the plotted task start."""
    calls={}
    for line,event in records:
        if line>end_line:break
        payload=event.get('payload',{});kind=payload.get('type')
        if event.get('type')!='response_item':continue
        if kind in ['function_call','custom_tool_call']:
            calls[payload.get('call_id')]=(line,payload.get('name',''),arguments(payload))
        elif kind in ['function_call_output','custom_tool_call_output']:
            call_line,tool,args=calls.get(payload.get('call_id'),(None,'',None))
            direct=tool.endswith('agta_explore') and isinstance(args,dict) and args.get('action')=='Complete'
            wrapped=isinstance(args,str) and bool(re.search(r'\b(?:tools\.)?(?:\w+__)?agta_explore\s*\(',args)) and bool(re.search(r'["\']?action["\']?\s*:\s*["\']Complete["\']',args))
            if not (direct or wrapped):continue
            for value in json_values(text_output(payload.get('output',''))):
                if not isinstance(value,dict):continue
                workflow=value.get('workflow',{})
                if value.get('ok') is True and isinstance(workflow,dict) and workflow.get('explorationComplete') is True:
                    return {'minutes':(stamp(event['timestamp'])-start).total_seconds()/60,
                            'timestamp':event['timestamp'],'call_line':call_line,'line':line,
                            'run_root':args.get('runRoot') if isinstance(args,dict) else value.get('runRoot')}
    return None

def extract(path,root):
    rec,errors=read_records(path)
    rel=path.relative_to(root);parts=rel.parts;bucket=parts[0]
    setup=('native' if 'native' in parts[2:-1] else 'mcp') if bucket=='newcodex' else bucket
    folder=path.parent.name;folder_model=parts[1] if bucket=='newcodex' else None
    fallback=next((k for k in APPS if folder.lower().startswith(k)),None)
    calls=[];outputs=[];by_id={};messages=[];users=[];contexts=[];tokens=[];tasks=[];meta={}
    current_turn=None
    for line,e in rec:
        p=e.get('payload',{});k=p.get('type');ts=e.get('timestamp')
        if e['type']=='session_meta':meta={x:p.get(x) for x in ['id','cli_version','source','originator','model_provider']}
        if e['type']=='turn_context':contexts.append({'line':line,'model':p.get('model'),'effort':p.get('effort',p.get('reasoning_effort'))})
        if k in ['task_started','task_complete','turn_aborted']:
            tasks.append({'line':line,'timestamp':ts,'type':k,'turn_id':p.get('turn_id'),'duration_ms':p.get('duration_ms')})
            if k=='task_started':current_turn=p.get('turn_id')
        if k=='token_count' and p.get('info',{}).get('total_token_usage'):
            tokens.append({'line':line,'turn_id':current_turn,**p['info']['total_token_usage']})
        if k=='user_message':users.append({'line':line,'text':p.get('message','')})
        if e['type']=='response_item' and k=='message':
            s='\n'.join(x.get('text','') for x in p.get('content',[]) if isinstance(x,dict))
            if p.get('role')=='assistant':messages.append({'line':line,'phase':p.get('phase'),'text':s})
            if p.get('role')=='user' and not s.startswith(('<environment_context>','<external_')):users.append({'line':line,'text':s})
        if e['type']=='response_item' and k in ['function_call','custom_tool_call']:
            a=arguments(p);item={'line':line,'timestamp':ts,'tool':p.get('name',''),'args':a,'command':command_text(a),'call_id':p.get('call_id')}
            calls.append(item);by_id[p.get('call_id')]=item
        if e['type']=='response_item' and k in ['function_call_output','custom_tool_call_output']:
            c=by_id.get(p.get('call_id'),{})
            raw=p.get('output','');raw_text=raw if isinstance(raw,str) else '\n'.join(x.get('text','') for x in raw if isinstance(x,dict))
            outputs.append({'line':line,'timestamp':ts,'call_line':c.get('line'),'tool':c.get('tool',''),'command':c.get('command',''),
                            'args':c.get('args'),'text':text_output(raw),
                            'session_ids':re.findall(r'"session_id"\s*:\s*(\d+)|session ID\s+(\d+)|SESSION_ID=(\d+)',raw_text),
                            'cell_ids':re.findall(r'Script running with cell ID\s+([\w-]+)',raw_text)})
    # Primary task is first task, excluding later artifact-location follow-ups.
    started=next((t for t in tasks if t['type']=='task_started'),None)
    terminal=next((t for t in tasks if t['type'] in ['task_complete','turn_aborted'] and (not started or t['turn_id']==started['turn_id'])),None)
    start=stamp(started['timestamp'] if started else rec[0][1]['timestamp'])
    end_line=terminal['line'] if terminal else rec[-1][0]
    end=stamp(terminal['timestamp'] if terminal else rec[-1][1]['timestamp'])
    pcalls=[c for c in calls if c['line']<=end_line];pout=[o for o in outputs if o['line']<=end_line]
    finals=[m for m in messages if m['line']<=end_line and m['phase'] in ['final_answer','final']]
    final=finals[-1] if finals else next((m for m in reversed(messages) if m['line']<=end_line),None)
    scripts=[{'file':str(p.relative_to(root)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
             for p in sorted(path.parent.iterdir()) if p.is_file() and p.suffix.lower() in ['.ps1','.py']]
    names={Path(s['file']).name.lower() for s in scripts}
    for m in messages:
        names.update(x.lower() for x in re.findall(r'([\w.-]+\.(?:ps1|py))\b',m['text']))
    # Restrict inferred names to observed invocation paths, not source text.
    for c in pcalls:
        if re.search(r'Set-Content|WriteAllText|write_text',c['command'],re.I):continue
        names.update(Path(x.replace('\\','/')).name.lower() for x in re.findall(r'(?:-File\s+|&\s+)[\'\"]?([^\'\"\s;]+\.ps1)',c['command'],re.I)
                     if re.search(r'test|generated|gui',x,re.I) and not re.search(r'potato|exploration',x,re.I))
    # Authoring help is sometimes called inside functions.exec.
    case_out=[{**o,'tool':'agta_help' if 'agta_help' in str(o['args']) or o['tool'].endswith('agta_help') else o['tool']} for o in pout]
    case=testcase_from_outputs(case_out)
    if case:
        first=normalized(case['rows'][0]['Action'])
        fallback=next((k for k,v in APPS.items() if first=='open'+normalized(v)),fallback)
    if fallback is None:raise ValueError(f'Unknown application: {rel}')
    actions=[r['Action'] for r in case['rows']] if case else ['Open '+APPS[fallback], 'Create Test '+{'word':'Document','excel':'Workbook','powerpoint':'Presentation'}.get(fallback,'Item'),
                    'Save Test '+{'word':'Document','excel':'Workbook','powerpoint':'Presentation'}.get(fallback,'Item'),
                    'Open Created '+{'word':'Document','excel':'Workbook','powerpoint':'Presentation'}.get(fallback,'Item'),
                    'Print Test '+{'word':'Document','excel':'Workbook','powerpoint':'Presentation'}.get(fallback,'Item')]
    # Session counters can reset or a restored task can start above zero.
    # Report recorded cumulative consumption, flag ambiguity separately.
    ptokens=[t for t in tokens if t['line']<=end_line]
    usage=ptokens[-1] if ptokens else {}
    resets=[b['line'] for a,b in zip(ptokens,ptokens[1:]) if b.get('total_tokens',0)<a.get('total_tokens',0)]
    models=sorted({c['model'] for c in contexts if c['line']<=end_line and c['model']})
    efforts=sorted({c['effort'] for c in contexts if c['line']<=end_line and c['effort']})
    observations=[];executions=[];first_pass={};live=[];error_receipts={};mcp_ms=[];evidence=[];runtime_errors=[]
    launch_calls=[c for c in pcalls if launch(c['command'],names)]
    launch_lines={c['line'] for c in launch_calls}
    eligible_sessions=set();eligible_cells=set()
    for o in pout:
        s=o['text'];a=o['args'];cmd=o['command'];elapsed=(stamp(o['timestamp'])-start).total_seconds()/60
        is_live=o['tool'].endswith('agta_replay') or ('agta_explore' in str(a) and bool(re.search(r'"?action"?\s*:\s*["\']Replay',str(a)))) or (isinstance(a,dict) and a.get('action')=='Replay')
        poll_sessions=re.findall(r'["\']?session_id["\']?\s*:\s*(\d+)',str(a))
        poll_cells=re.findall(r'["\']?cell_id["\']?\s*:\s*["\']([\w-]+)',str(a))
        eligible=o['call_line'] in launch_lines or result_read(cmd) or is_live or bool(eligible_sessions.intersection(poll_sessions)) or bool(eligible_cells.intersection(poll_cells))
        if eligible:
            eligible_sessions.update(x for pair in o['session_ids'] for x in pair if x)
            eligible_cells.update(o['cell_ids'])
        if eligible:
            states=extra_states(s,actions)
            diagnostic=json_field(s,'qualifying') is False or json_field(s,'runKind')=='Diagnostic'
            if diagnostic:states={}
            if not states and re.search(r'\b(?:Exception|FullyQualifiedErrorId|RuntimeException|ParserError|failed|not created)\b',s,re.I):
                runtime_errors.append({'line':o['line'],'minutes':elapsed,'text':s[:2200]})
                evidence.append({'line':o['line'],'kind':'runtime error','text':s[:6000]})
            if states:
                observations.append({'line':o['line'],'call_line':o['call_line'],'minutes':elapsed,'states':states,'kind':'script launch' if o['call_line'] in launch_lines else 'result read / replay'})
                evidence.append({'line':o['line'],'kind':'runtime result','text':s[:14000]})
                for i,status in states.items():
                    if status=='PASS':first_pass.setdefault(str(i),{'line':o['line'],'minutes':elapsed})
            if is_live:
                for i in first_attempt_steps(s,actions):live.append({'step':i,'line':o['line'],'minutes':elapsed})
            parsed=[]
            for v in json_values(s):
                if isinstance(v,dict) and v.get('executionId') and isinstance(v.get('summary'),dict) and v.get('qualifying') is not False and v.get('runKind')!='Diagnostic':
                    parsed.append({'line':o['line'],'minutes':elapsed,**{k:v.get(k) for k in ['executionId','ok','summary','cleanupOk','interactionPolicy','timing','steps']}})
            if not parsed:parsed=[{'line':o['line'],'minutes':elapsed,**v} for v in execution_headers(s)]
            if not parsed and re.search(r'(?m)^\s*Qualifying\s*:\s*True\s*$',s,re.I):
                ident=re.search(r'(?m)^\s*ExecutionId\s*:\s*(\S+)\s*$',s,re.I)
                fields={k:int(v) for k,v in re.findall(r'(?m)^\s*(Total|Passed|Failed|Skipped)\s*:\s*(\d+)\s*$',s)}
                cleanup=re.search(r'(?m)^\s*CleanupOk\s*:\s*(True|False)\s*$',s,re.I)
                if ident and 'Total' in fields and 'Passed' in fields:
                    parsed=[{'line':o['line'],'minutes':elapsed,'executionId':ident[1],'ok':None,'summary':{k.lower():v for k,v in fields.items()},'cleanupOk':cleanup[1].lower()=='true' if cleanup else None,'timing':None,'console_header':True}]
            executions.extend(parsed)
        if 'agta_' in o['tool'] or 'agta_' in str(a):
            values=list(json_values(s));timings=[]
            for v in walk_dicts(values):
                if isinstance(v.get('mcpTiming'),dict) and isinstance(v['mcpTiming'].get('requestMs'),(int,float)):timings.append(v['mcpTiming']['requestMs'])
                if v.get('ok') is False and v.get('error') and v.get('explorationCommandId'):
                    err=v['error'];error_receipts[v['explorationCommandId']]={'line':o['line'],'command':v.get('command'),'type':err.get('type') if isinstance(err,dict) else None,'message':err.get('message') if isinstance(err,dict) else str(err)}
            if timings:mcp_ms.append({'line':o['line'],'request_ms':max(timings)})
    dedup={}
    for e in executions:dedup[e['executionId']]=e
    executions=sorted(dedup.values(),key=lambda e:e['line'])
    full=[o for o in observations if len(o['states'])==5 and set(o['states'].values())=={'PASS'}]
    last_states=observations[-1]['states'] if observations else {}
    best=max((sum(s=='PASS' for s in o['states'].values()) for o in observations),default=None)
    status='observed full pass' if full else 'observed partial / failed' if observations or runtime_errors else 'no qualifying outcome observed'
    model=models[0] if len(models)==1 else 'mixed / unknown'
    flag=[]
    if folder_model and folder_model.removesuffix('-light') != model.removeprefix('gpt-'):flag.append('Folder model differs from recorded model')
    if case is None:flag.append('Full testcase text not recovered; conventional action names used for result matching')
    if errors:flag.append('Malformed JSONL records')
    if resets:flag.append('Token counter reset; cumulative total not directly comparable')
    if len({t['turn_id'] for t in tasks if t['type']=='task_started'})>1:flag.append('Later follow-up turn excluded from primary metrics')
    if 'failed' in folder.lower() and full:flag.append('Failed folder label conflicts with observed full pass')
    final_timing=(executions[-1].get('timing') or {}).get('totalMs') if executions else None
    if full and executions and executions[-1].get('summary',{}).get('passed')!=5:final_timing=None
    r={'file':str(rel).replace('\\','/'),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'folder':folder,'bucket':bucket,'setup':setup,'folder_model':folder_model,
       'app_key':fallback,'app':APPS[fallback],'model':model,'models':models,'efforts':efforts,'session_metadata':meta,
       'task_id':started['turn_id'] if started else None,'tasks':tasks,'start':start.isoformat(),'end':end.isoformat(),'end_line':end_line,
       'minutes':(end-start).total_seconds()/60,'raw_log_span_minutes':(stamp(rec[-1][1]['timestamp'])-stamp(rec[0][1]['timestamp'])).total_seconds()/60,
       'active_turn_minutes':terminal.get('duration_ms')/60000 if terminal and terminal.get('duration_ms') else None,'terminal':terminal['type'] if terminal else 'no terminal',
       'source_records':len(rec),'parse_errors':errors,'usage':usage,'token_reset_lines':resets,'total_tokens':usage.get('total_tokens'),'input_tokens':usage.get('input_tokens'),
       'cached_input_tokens':usage.get('cached_input_tokens'),'uncached_input_tokens':usage.get('input_tokens',0)-usage.get('cached_input_tokens',0) if usage else None,
       'output_tokens':usage.get('output_tokens'),'reasoning_output_tokens':usage.get('reasoning_output_tokens'),'tool_calls':len(pcalls),
       'outer_tool_counts':dict(Counter(c['tool'] for c in pcalls)),'script_launches':len(launch_calls),'launches':[{k:c[k] for k in ['line','command','timestamp']} for c in launch_calls],
       'tool_text_kib':sum(len(o['text'].encode('utf-8')) for o in pout)/1024,'scripts':scripts,'testcase':case,'testcase_sha256':case['sha256'] if case else None,
       'status':status,'success':bool(full),'first_all_pass_minutes':full[0]['minutes'] if full else None,'first_pass':first_pass,'best_passed_steps':best,
       'last_states':last_states,'observations':observations,'executions':executions,'live_first_attempt_successes':live,'exploration_failures':list(error_receipts.values()),'mcp_timings':mcp_ms,
       'exploration_completion':exploration_completion(rec,start,end_line) if setup=='mcp' else None,
       'final_replay_seconds':final_timing/1000 if final_timing is not None else None,
       'final':final,'evidence':evidence,'runtime_errors':runtime_errors,'flags':flag,'included':True,'exclusion_reason':None,'users':[{'line':u['line'],'text':u['text'][:1800]} for u in users if '# My request' in u['text']]}
    return r

def discover(root,include_old_paint=False):
    paths=sorted(p for g in ROOTS for p in (root/g).rglob('*.jsonl') if 'old' not in {x.lower() for x in p.relative_to(root/g).parts})
    runs=[];seen={};inventory=[]
    for p in paths:
        r=extract(p,root)
        if r['sha256'] in seen:r['included']=False;r['exclusion_reason']='Byte-identical copied log: '+seen[r['sha256']]
        else:seen[r['sha256']]=r['file']
        if r['bucket']=='aionly' and r['app']=='Access' and any('agta_' in t for t in r['outer_tool_counts']):
            r['included']=False;r['exclusion_reason']='Misfiled aborted Access/MCP task; not an AI-only Office experiment'
        if r['bucket']=='native' and r['folder']=='paint-37m' and not include_old_paint:
            r['included']=False;r['exclusion_reason']='Previously documented superseded Paint run; retained for sensitivity'
        runs.append(r)
    for g in ROOTS:
        for folder in sorted((root/g).rglob('*')):
            if not folder.is_dir() or 'old' in {x.lower() for x in folder.relative_to(root/g).parts}:continue
            files=[x for x in folder.iterdir() if x.is_file()]
            if not files and any(x.is_dir() for x in folder.iterdir()):continue
            logs=[x for x in files if x.suffix=='.jsonl']
            inventory.append({'folder':str(folder.relative_to(root)).replace('\\','/'),'files':[x.name for x in files],'log_count':len(logs),'status':'has logs' if logs else 'script only / no log'})
    runs.sort(key=lambda r:(r['bucket'],r['model'],r['setup'],r['app'],r['start']))
    for i,r in enumerate(runs,1):r['id']=f'R{i:03d}'
    return runs,inventory

def stat(values):
    v=[x for x in values if x is not None and math.isfinite(x)]
    return {'n':len(v),'mean':mean(v),'median':median(v),'sd':stdev(v) if len(v)>1 else None,'min':min(v),'max':max(v)} if v else {'n':0,'mean':None,'median':None,'sd':None,'min':None,'max':None}

def summarize(rs):
    passed=[r for r in rs if r['success']]
    return {'n':len(rs),'successes':len(passed),'success_rate':len(passed)/len(rs) if rs else None,'apps':sorted({r['app'] for r in rs}),
            **{k:stat([r[k] for r in rs]) for k in ['minutes','total_tokens','uncached_input_tokens','output_tokens','script_launches','tool_calls','best_passed_steps','first_all_pass_minutes','final_replay_seconds']},
            'successful_minutes':stat([r['minutes'] for r in passed]),'total_observed_minutes':sum(r['minutes'] for r in rs),
            'spent_minutes_per_success':sum(r['minutes'] for r in rs)/len(passed) if passed else None,
            'status_counts':dict(Counter(r['status'] for r in rs))}

def contrast(rs,left,right,key='setup',apps=None,seed=7102026):
    a=[r for r in rs if r[key]==left];b=[r for r in rs if r[key]==right]
    common=sorted(set(r['app'] for r in a)&set(r['app'] for r in b))
    if apps is not None:common=[x for x in apps if x in common]
    if not common:return None
    ma=mean(mean(r['minutes'] for r in a if r['app']==app) for app in common)
    mb=mean(mean(r['minutes'] for r in b if r['app']==app) for app in common)
    rng=np.random.default_rng(seed);diff=np.zeros(4000)
    for app in common:
        av=[r['minutes'] for r in a if r['app']==app];bv=[r['minutes'] for r in b if r['app']==app]
        diff+=rng.choice(bv,(4000,len(bv)),replace=True).mean(axis=1)-rng.choice(av,(4000,len(av)),replace=True).mean(axis=1)
    diff/=len(common)
    ci=[float(x) for x in np.percentile(diff,[2.5,97.5])]
    if rs and all(r['bucket']=='newcodex' for r in rs):ci=None
    return {'left':left,'right':right,'apps':common,'left_n':sum(r['app'] in common for r in a),'right_n':sum(r['app'] in common for r in b),
            'left_mean':ma,'right_mean':mb,'difference_minutes':mb-ma,'change_pct':100*(mb/ma-1),'bootstrap_difference_ci':ci,
            'left_successes':sum(r['app'] in common and r['success'] for r in a),'right_successes':sum(r['app'] in common and r['success'] for r in b)}

def analyze(runs,inventory,root):
    rs=[r for r in runs if r['included']]
    baseline=[r for r in rs if r['bucket'] in ['native','mcp'] and r['model']=='gpt-5.5']
    office=[r for r in rs if r['bucket'] in ['native','mcp','aionly'] and r['model']=='gpt-5.5' and r['app'] in OFFICE]
    newer=[r for r in rs if r['bucket']=='newcodex']
    comparisons=[]
    for label,sample,a,b in [('GPT-5.5 all common apps',baseline,'native','mcp'),('GPT-5.5 shared Office apps',office,'native','mcp'),
                           ('AI-only versus native on Office',office,'native','aionly'),('AI-only versus MCP on Office',office,'mcp','aionly')]:
        v=contrast(sample,a,b)
        if v:comparisons.append({'label':label,**v})
    commoncases=set(r['testcase_sha256'] for r in baseline if r['setup']=='native' and r['testcase_sha256']) & set(r['testcase_sha256'] for r in baseline if r['setup']=='mcp' and r['testcase_sha256'])
    v=contrast([r for r in baseline if r['testcase_sha256'] in commoncases],'native','mcp')
    if v:comparisons.append({'label':'GPT-5.5 exact captured testcase content',**v})
    withpaint=baseline+[r for r in runs if r['exclusion_reason'] and r['folder']=='paint-37m']
    v=contrast(withpaint,'native','mcp')
    if v:comparisons.append({'label':'GPT-5.5 including superseded Paint sensitivity',**v})
    for model in ALL_MODELS:
        v=contrast([r for r in newer if r['model']==model],'native','mcp')
        if v:comparisons.append({'label':model+' native versus MCP',**v})
    for model in ['gpt-5.6-luna','gpt-6-luna','gpt-5.6-sol','gpt-6-sol']:
        for setup in ['mcp','native']:
            v=contrast([r for r in newer if r['setup']==setup],model,'gpt-6.1-sol',key='model')
            if v:comparisons.append({'label':setup+': '+model+' versus gpt-6.1-sol',**v})
    v=contrast([r for r in newer if r['setup']=='mcp'],'gpt-5.6-luna','gpt-6-luna',key='model')
    if v:comparisons.append({'label':'mcp: gpt-5.6-luna versus gpt-6-luna',**v})
    for model in PRIMARY_MODELS:
        v=contrast([r for r in office+newer if r['setup']=='mcp'],'gpt-5.5',model,key='model')
        if v:comparisons.append({'label':'MCP older-model reference: gpt-5.5 versus '+model,**v,'bootstrap_difference_ci':None})
    summary=[]
    for bucket,model,setup in sorted({(r['bucket'],r['model'],r['setup']) for r in rs}):
        summary.append({'bucket':bucket,'model':model,'setup':setup,**summarize([r for r in rs if (r['bucket'],r['model'],r['setup'])==(bucket,model,setup)])})
    applications=[]
    for bucket,model,setup,app in sorted({(r['bucket'],r['model'],r['setup'],r['app']) for r in rs}):
        applications.append({'bucket':bucket,'model':model,'setup':setup,'app':app,**summarize([r for r in rs if (r['bucket'],r['model'],r['setup'],r['app'])==(bucket,model,setup,app)])})
    variants=[]
    for app in sorted({r['app'] for r in rs}):
        d=defaultdict(list)
        for r in rs:
            if r['app']==app and r['testcase']:d[r['testcase_sha256']].append(r)
        variants.append({'app':app,'variants':[{'sha256':h,'run_ids':[r['id'] for r in sample],'rows':sample[0]['testcase']['rows']} for h,sample in d.items()]})
    return {'schema_version':2,'generated_at':datetime.now(timezone.utc).isoformat(),'source_root':str(root),'included_roots':ROOTS,'excluded_roots':['old','cli','nested old'],
            'runs':runs,'inventory':inventory,'summary':summary,'application_summary':applications,'comparisons':comparisons,'testcase_variants':variants}

def write_csv(path,rows):
    if not rows:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})

def export(data,out):
    d=out/'data';d.mkdir(parents=True,exist_ok=True)
    (d/'metrics.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    keys=['id','included','exclusion_reason','bucket','setup','model','folder_model','efforts','app','folder','file','sha256','task_id','start','end','minutes','raw_log_span_minutes','terminal','success','status','best_passed_steps','first_all_pass_minutes','total_tokens','cached_input_tokens','uncached_input_tokens','output_tokens','reasoning_output_tokens','script_launches','tool_calls','final_replay_seconds','testcase_sha256','flags']
    write_csv(d/'sessions.csv',[{k:r[k] for k in keys} for r in data['runs']])
    write_csv(d/'inventory.csv',data['inventory'])
    write_csv(d/'comparisons.csv',data['comparisons'])
    for name in ['summary','application_summary']:
        rows=[]
        for s in data[name]:
            rows.append({k:s[k] for k in ['bucket','model','setup']+(['app'] if name=='application_summary' else [])+['n','successes','success_rate','total_observed_minutes','spent_minutes_per_success']}|
                        {f'{m}_{x}':s[m][x] for m in ['minutes','successful_minutes','total_tokens','uncached_input_tokens','output_tokens','script_launches','best_passed_steps'] for x in ['mean','median','min','max','n']})
        write_csv(d/(name+'.csv'),rows)

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--include-old-paint',action='store_true');p.add_argument('--data-only',action='store_true')
    a=p.parse_args();runs,inv=discover(a.source,a.include_old_paint);data=analyze(runs,inv,a.source);a.output.mkdir(parents=True,exist_ok=True);export(data,a.output)
    print(json.dumps({'logs':len(runs),'included':sum(r['included'] for r in runs),'summary':[{k:s[k] for k in ['bucket','model','setup','n','successes','minutes']} for s in data['summary']],
                      'unresolved':[{k:r[k] for k in ['id','file','status','best_passed_steps','flags']} for r in runs if r['included'] and not r['success']]},indent=2))
    if not a.data_only:
        from report_current import build
        build(data,a.output)

if __name__=='__main__':main()
