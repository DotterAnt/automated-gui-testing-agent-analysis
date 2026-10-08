"""Observed GPT-5.5 / 6.1 differences and a price-versus-usage decomposition."""
from pathlib import Path
from statistics import mean
import json

from analyze_current import OFFICE, write_csv
from extract import read_records
from cost_current import PARTS, RATES

MODELS = ['gpt-5.5', 'gpt-6.1-sol']
KEYS = ['minutes', 'total_tokens', 'input_tokens', 'cached_input_tokens',
        'uncached_input_tokens', 'output_tokens', 'reasoning_output_tokens',
        'script_launches', 'tool_text_kib', 'first_all_pass_minutes', 'final_replay_seconds']


def average_apps(rows, key):
    return mean(mean(r[key] for r in rows if r['app'] == app) for app in OFFICE)


def counterfactuals(old, new):
    """Hold usage fixed when repricing; average both attribution orders."""
    cells=[]
    for usage_model, usage in zip(MODELS, [old, new]):
        quantities=[usage['uncached_input_tokens'], usage['cached_input_tokens'], 0, usage['output_tokens']]
        for price_model in MODELS:
            parts=dict(zip(PARTS, [tokens*rate/1e6 for tokens,rate in zip(quantities,RATES[price_model])]))
            cells.append({'usage_model':usage_model,'price_model':price_model,**parts,'total_usd':sum(parts.values())})
    a,b,c,d=[r['total_usd'] for r in cells]
    price=((a-b)+(c-d))/2
    usage=((a-c)+(b-d))/2
    return cells, {'total_reduction_usd':a-d,'price_effect_usd':price,'usage_effect_usd':usage,
                   'price_share':price/(a-d),'usage_share':usage/(a-d),
                   'method':'two-factor Shapley: average price-first and usage-first orders',
                   'price_first_path':[a,b,d],'usage_first_path':[a,c,d]}


def add_model_gap(data,out):
    selected=[r for r in data['runs'] if r['included'] and r['setup']=='mcp'
              and r['app'] in OFFICE and r['model'] in MODELS]
    profiles=[]
    for run in selected:
        if run['usage'].get('cache_write_input_tokens',0):
            raise ValueError('Extend the model-gap decomposition for nonzero cache writes: '+run['id'])
        records,errors=read_records(Path(data['source_root'])/run['file'])
        if errors:raise ValueError('Malformed model-gap source '+run['id'])
        usage=[];compaction=[]
        for line,event in records:
            if line>run['end_line']:break
            if event.get('type')=='compacted':compaction.append(line)
            payload=event.get('payload',{})
            if payload.get('type')=='token_count':
                value=(payload.get('info') or {}).get('total_token_usage')
                if value and (not usage or value['total_tokens']!=usage[-1][1]['total_tokens']):usage.append((line,value))
        receipt=run.get('exploration_completion')
        if not receipt:raise ValueError('No confirmed exploration completion for '+run['id'])
        profiles.append({'run_id':run['id'],'model':run['model'],'app':run['app'],
                         **{key:run[key] for key in KEYS},
                         'efforts':run['efforts'],'usage_counter_updates':len(usage),
                         'compaction_record_lines':compaction,
                         'exploration_minutes':receipt['minutes'],
                         'post_exploration_minutes':run['minutes']-receipt['minutes'],
                         'completion_call_line':receipt['call_line'],'completion_receipt_line':receipt['line'],
                         'exploration_failure_receipts':len(run['exploration_failures']),
                         'script_bytes':sum(s['bytes'] for s in run['scripts']),
                         'cli_version':run['session_metadata'].get('cli_version'),
                         'testcase_sha256':run['testcase_sha256'],'source_file':run['file'],
                         'source_sha256':run['sha256'],'usage_line':run['usage']['line']})
    extra=['usage_counter_updates','exploration_minutes','post_exploration_minutes',
           'exploration_failure_receipts','script_bytes']
    averages=[{'model':model,'n':sum(r['model']==model for r in profiles),
               **{key:average_apps([r for r in profiles if r['model']==model],key) for key in KEYS+extra}}
              for model in MODELS]
    app_rows=[]
    for app in OFFICE:
        for model in MODELS:
            rows=[r for r in profiles if r['app']==app and r['model']==model]
            app_rows.append({'application':app,'model':model,'n':len(rows),
                             **{key:mean(r[key] for r in rows) for key in KEYS+extra},
                             'run_ids':[r['run_id'] for r in rows],
                             'testcase_hashes':sorted({r['testcase_sha256'] for r in rows})})
    prices,attribution=counterfactuals(*averages)
    data['model_gap_analysis']={'scope':'AGTA sessions on Excel, PowerPoint and Word',
                                'weighting':'equal application means', 'profiles':profiles,
                                'averages':averages,'applications':app_rows,
                                'counterfactuals':prices,'attribution':attribution,
                                'notes':['All 19 AGTA sessions have confirmed exploration completion and matching per-application testcase hashes.',
                                         'GPT-5.5 uses medium effort and CLI 0.142.0-alpha.6; GPT-6.1 Sol uses low effort and CLI 0.160.1.',
                                         'No compacted records occur in these 19 measured tasks; this does not rule out other undocumented context handling.',
                                         'Usage-counter updates are distinct cumulative accounting changes, not comparable GUI-action or outer-tool-call counts.',
                                         'The pricing decomposition is exact accounting; behavior and runtime differences are observational and do not isolate model-only effects.',
                                         'Repricing holds recorded tokens and behavior fixed; it does not predict a rerun with another model.']}
    write_csv(out/'data'/'model_gap_sessions.csv',profiles)
    write_csv(out/'data'/'model_gap_applications.csv',app_rows)
    write_csv(out/'data'/'model_gap_counterfactuals.csv',prices)
    (out/'data'/'model_gap_analysis.json').write_text(json.dumps(data['model_gap_analysis'],indent=2),encoding='utf-8')
