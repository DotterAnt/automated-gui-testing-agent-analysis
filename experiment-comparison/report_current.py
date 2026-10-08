"""Offline HTML, publication figures and a PDF for the current corpus."""
from __future__ import annotations
from collections import Counter,defaultdict
import html
import json
from pathlib import Path
from statistics import mean,median
import re
import zipfile
import math
import matplotlib.pyplot as plt
import numpy as np
from figures import progress_curve
from cost_current import add_cost_analysis, PARTS, PRIMARY as COST_MODELS
from model_gap_current import add_model_gap
from analyze_current import (OFFICE,PRIMARY_MODELS,ALL_MODELS,MODEL_ORDER,LABELS,COLORS,MODEL_COLORS,
                             summarize,stat,contrast,write_csv,exploration_completion)

REPORT_DATE='8 October 2026'
POOLED_MODELS=['gpt-5.5',*PRIMARY_MODELS]

def esc(x):return html.escape(str(x))
def num(x,d=2):return f'{x:,.{d}f}' if x is not None else 'unmeasured'
def model(x):
    label=x.removeprefix('gpt-').replace('-luna',' Luna').replace('-sol',' Sol')
    return label+(' / medium' if x=='gpt-5.5' else ' / light')
def model_rank(x):return (MODEL_ORDER.index(x) if x in MODEL_ORDER else len(MODEL_ORDER),x)
def ordered_runs(runs):return sorted(runs,key=lambda r:(model_rank(r['model']),r['setup'],r['app'],r['start'],r['id']))
def link(r):return f'<a href="evidence.html#{r["id"]}">{r["id"]}</a>'
def table(head,rows):return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>'

CSS='''
:root{--ink:#22323d;--muted:#536572;--line:#dce5e9;--accent:#277967}*{box-sizing:border-box}body{margin:0;background:#fafbfa;color:var(--ink);font:16px/1.6 system-ui,Segoe UI,sans-serif}header{padding:35px max(24px,calc((100% - 1180px)/2));background:#eaf2ef;border-bottom:4px solid var(--accent)}h1{font-size:38px;line-height:1.17;max-width:900px;margin:12px 0 20px}header p{max-width:940px}main{max-width:1230px;margin:auto;padding:0 25px 60px}section{padding:30px 0;border-bottom:1px solid var(--line);scroll-margin-top:15px}h2{font-size:26px;line-height:1.3;margin:0 0 20px}h3{font-size:19px}a{color:#20658a;text-underline-offset:3px}nav{display:flex;flex-wrap:wrap;gap:18px;font-size:14px}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin:26px 0}.kpis div{padding:15px 18px;background:white;border:1px solid var(--line);border-top:3px solid var(--accent)}.kpis strong{display:block;font-size:27px;line-height:1.35}.kpis span,small,.quiet{font-size:13px;color:var(--muted)}p{margin:12px 0}.note{padding:13px 18px;border-left:4px solid var(--accent);background:#eef5f2}.caution{border-color:#cc7042;background:#fff4e8}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;background:white;font-size:14px}th,td{text-align:left;padding:10px 12px;vertical-align:top;border-bottom:1px solid var(--line)}th{background:#edf2f4}tr:hover{background:#f4f8fa}figure{margin:24px 0}figure img{display:block;width:100%;height:auto}figcaption{font-size:13px;color:var(--muted);margin-top:9px}.controls{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0}select,input{padding:9px 12px;font:inherit;border:1px solid #bac9ce;background:white;border-radius:4px}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:16px;background:#eef2f4;font:12px/1.5 Consolas,monospace;max-height:500px;overflow:auto}details{margin:16px 0}summary{font-weight:600;cursor:pointer}code{overflow-wrap:anywhere;font-size:13px}[hidden]{display:none!important}@media(max-width:760px){h1{font-size:29px}.kpis{grid-template-columns:repeat(2,1fr)}main{padding:0 16px 30px}th,td{padding:8px}}@media print{nav,.controls{display:none}body{background:white}section{break-inside:auto}header{padding:20px}main{max-width:none}}
'''
def page(title,subtitle,content,script=''):
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{CSS}</style></head><body><header><small>THESIS EXPERIMENT ANALYSIS · UPDATED {REPORT_DATE.upper()}</small><h1>{esc(title)}</h1><p>{subtitle}</p><nav><a href="report.html">Analysis</a><a href="evidence.html">Run evidence</a><a href="methodology.html">Methodology</a><a href="data/sessions.csv">Sessions CSV</a><a href="data/metrics.json">Complete JSON</a><a href="../../../output/pdf/experiment-analysis-2026-10-07.pdf">PDF report</a></nav></header><main>{content}</main><script>{script}</script></body></html>'

def audits(data):
    root=Path(data['source_root']);notes=[]
    specs=[('aionly','powerpoint-13m-failed','powerpoint_gui_test.py',[(134,146),(156,166),(285,288)],'The supplied script saves the presentation and exports the PDF with Office COM, and includes a COM text repair. Runtime five-pass reporting therefore does not establish the requested GUI-only Save/Print routes.'),
           ('aionly','powerpoint-20m','powerpoint_gui_test.py',[(203,211),(220,231)],'The supplied script uses COM SaveAs and PrintOut after opening the print UI. It reports passing steps, but performs the save/print operation through the application object model.'),
           ('aionly','word-17m','word_gui_test.py',[(218,236)],'The supplied script reopens the document with Documents.Open and exports the PDF with ExportAsFixedFormat. These operations bypass the testcase GUI routes.')]
    for bucket,folder,filename,ranges,note in specs:
        r=next(r for r in data['runs'] if r['bucket']==bucket and r['folder']==folder)
        p=root/bucket/folder/filename;lines=p.read_text(encoding='utf-8-sig').split('\n')
        excerpts=[{'line':a,'text':'\n'.join(f'{i}: {lines[i-1]}' for i in range(a,min(b,len(lines))+1))} for a,b in ranges]
        notes.append({'run_id':r['id'],'file':str(p),'reason':note,'excerpts':excerpts})
    r=next(r for r in data['runs'] if r['bucket']=='native' and r['folder']=='notepad-53m-failed')
    # Recover the original source read, keeping a line citation to the log.
    from extract import read_records
    from analyze_current import text_output
    for ln,e in read_records(root/r['file'])[0]:
        v=e.get('payload',{})
        if v.get('type') not in ['function_call_output','custom_tool_call_output']:continue
        s=text_output(v.get('output',''));hit=s.find('Writing a simple PDF')
        if hit>=0:
            notes.append({'run_id':r['id'],'file':str(root/r['file']),'reason':'A captured script/source read contains file creation recovery, including "Writing a simple PDF" when the GUI print path failed. Its reported five-pass result is retained as a measured output; it is not sufficient evidence of a GUI-only print success.',
                          'excerpts':[{'line':ln,'text':s[max(0,hit-650):hit+1200]}]});break
    data['route_audits']=notes
    ai=[r for r in data['runs'] if r['included'] and r['bucket']=='aionly']
    bad={n['run_id'] for n in notes}
    data['ai_only_without_known_bypasses']=summarize([r for r in ai if r['id'] not in bad])
    data['known_bypass_ids']=sorted(bad)
    return notes

def save_figure(fig,out,name):
    fig.savefig(out/'figures'/(name+'.svg'),bbox_inches='tight')
    fig.savefig(out/'figures'/(name+'.png'),dpi=180,bbox_inches='tight');plt.close(fig)

def exploration_summary(runs):
    cohort=[r for r in runs if r['setup']=='mcp']
    values=[r['exploration_completion']['minutes'] for r in cohort if r.get('exploration_completion')]
    return {'n':len(values),'total':len(cohort),'mean_minutes':mean(values) if values else None,
            'missing_ids':[r['id'] for r in cohort if not r.get('exploration_completion')]}

def add_exploration_timings(data,out):
    """Backfill the chart cohort from source receipts without altering prior metrics."""
    from extract import read_records,stamp
    cohort=[r for r in data['runs'] if r['included'] and r['setup']=='mcp']
    for run in cohort:
        if 'exploration_completion' not in run or (run['bucket']=='newcodex' and run['exploration_completion'] is None):
            records,errors=read_records(Path(data['source_root'])/run['file'])
            if errors:raise ValueError(f'Cannot measure exploration in {run["id"]}: malformed log records')
            run['exploration_completion']=exploration_completion(records,stamp(run['start']),run['end_line'])
    data['baseline_exploration_completion']=exploration_summary([r for r in cohort if r['bucket']=='mcp'])
    rows=[]
    for run in cohort:
        receipt=run.get('exploration_completion') or {}
        rows.append({'run_id':run['id'],'application':run['app'],'model':run['model'],
                     'status':'confirmed_completion' if receipt else 'no_confirmed_completion',
                     'minutes_from_task_start':receipt.get('minutes'),'task_start':run['start'],
                     'completion_timestamp':receipt.get('timestamp'),'call_line':receipt.get('call_line'),
                     'receipt_line':receipt.get('line'),'source_file':run['file'],'source_sha256':run['sha256']})
    write_csv(out/'data'/'exploration_completion.csv',rows)

def progress_views(data):
    """Keep model/settings and shared applications fixed within each comparison."""
    included=[r for r in data['runs'] if r['included']]
    baseline=[r for r in included if r['bucket'] in ['native','mcp']]
    office=[r for r in included if r['bucket'] in ['native','mcp','aionly'] and r['app'] in OFFICE]
    return [
        {'id':'baseline-progress','title':'Native versus MCP: observed progress over time',
         'continuation':'Native versus MCP - application progress','runs':baseline,
         'groups':['native','mcp'],'apps':sorted({r['app'] for r in baseline}),
         'exploration':exploration_summary(baseline)},
        {'id':'office-progress','title':'Native, MCP and AI-only: observed progress over time',
         'continuation':'Native, MCP and AI-only - application progress','runs':office,
         'groups':['native','mcp','aionly'],'apps':list(OFFICE)}]

def progress_name(view,app):
    return view['id']+'-'+(re.sub(r'[^a-z0-9]+','-',app.lower()).strip('-') if app else 'all')

def progress_sample(view,app):
    return [r for r in view['runs'] if app is None or r['app']==app]

def progress_points(sample,groups):
    """Exact receipt-time step curves with a fixed denominator and held endpoints."""
    horizon=max(10,math.ceil(max(r['minutes'] for r in sample)/10)*10)
    times=sorted({0,horizon,*[p['minutes'] for r in sample for p in r['first_pass'].values()]})
    means={g:np.mean([progress_curve(r,times) for r in sample if r['setup']==g],axis=0)
           for g in groups}
    return times,means,horizon

def progress_display_limit(view,app):
    """Limit only the pooled ten-application display, retaining full curve data."""
    return 60 if view['id']=='baseline-progress' and app is None else None

def progress_caption(view,app):
    sample=progress_sample(view,app)
    counts='; '.join(f'{LABELS[g]} n={sum(r["setup"]==g for r in sample)}' for g in view['groups'])
    scope=app or ('All ten applications' if view['id']=='baseline-progress' else 'Excel, PowerPoint and Word pooled')
    limit=progress_display_limit(view,app)
    if limit is None:
        extent='Full time range shown'
    else:
        continuing=[r for r in sample if r['minutes']>limit]
        durations='; '.join(f'{LABELS[g]}: '+', '.join(f'{r["minutes"]:.1f} min' for r in continuing if r['setup']==g)
                            for g in view['groups'] if any(r['setup']==g for r in continuing))
        extent=f'Time axis truncated at {limit} min; right-pointing markers indicate {len(continuing)} sessions continuing beyond the cutoff ({durations}). All tasks remain included in the means and full data exports'
    caption=f'{scope}: {counts}. Thin lines are individual tasks; bold lines are pointwise task means. {extent}; each task remains in the mean after it ends.'
    timing=view.get('exploration',{})
    if limit is not None and timing.get('n'):
        caption+=f' The vertical AGTA exploration marker is the mean time from task start to the first confirmed successful Complete response: {timing["mean_minutes"]:.2f} min ({timing["n"]}/{timing["total"]} AGTA sessions). Sessions without a confirmed completion are excluded from this timing mean, but remain in the progress curves. Source receipts are exported in data/exploration_completion.csv.'
    return caption

def progress_figure(view,app,times,means,horizon):
    sample=progress_sample(view,app)
    styles={'native':'--','mcp':'-','aionly':':'}
    limit=progress_display_limit(view,app)
    timing=view.get('exploration',{})
    has_exploration_marker=limit is not None and bool(timing.get('n'))
    fig,ax=plt.subplots(figsize=(11.3,5.6 if has_exploration_marker else 4.9 if limit else 4.6))
    for group in view['groups']:
        cohort=[r for r in sample if r['setup']==group]
        for r in cohort:
            line,=ax.step(times,progress_curve(r,times),where='post',color=COLORS[group],
                         linestyle=styles[group],alpha=.14 if app else .065,lw=.8)
            line.set_gid(r['id'])
            if limit is not None and r['minutes']>limit:
                value=progress_curve(r,[limit])[0]
                marker,=ax.plot(limit,value,marker='>',color=COLORS[group],markersize=7,
                               linestyle='none',clip_on=False,zorder=5)
                marker.set_gid('continuation-'+r['id'])
        ax.step(times,means[group],where='post',color=COLORS[group],linestyle=styles[group],
                lw=2.7,label=f'{LABELS[group]} mean (n={len(cohort)})')
    title=app or ('All ten applications' if view['id']=='baseline-progress' else 'Shared Office applications')
    ax.set(xlim=(0,limit if limit is not None else horizon),ylim=(-.04,5.2),yticks=range(6),
           xlabel='Minutes from authoring task start',ylabel='Rows with observed PASS evidence',
           title=f'{title} / GPT-5.5, medium effort')
    if has_exploration_marker:
        average=timing['mean_minutes'];marker_color='#a84626'
        marker=ax.axvline(average,ymin=-.19,color=marker_color,linestyle=':',lw=1.5,zorder=3,
                         clip_on=False)
        marker.set_gid('agta-exploration-completion-mean')
        marker.set_in_layout(False)
    ax.legend(loc='lower right',framealpha=.95,fontsize=9);ax.grid(alpha=.16);ax.set_axisbelow(True)
    if limit is not None:
        ax.axvline(limit,color='#687781',linestyle=':',lw=1.2,clip_on=False)
        continuing=[r for r in sample if r['minutes']>limit]
        details='; '.join(f'{"Native" if g=="native" else "MCP"}: '+', '.join(f'{r["minutes"]:.1f} min' for r in continuing if r['setup']==g)
                          for g in view['groups'] if any(r['setup']==g for r in continuing))
        fig.text(.5,.065,f'Time axis truncated at {limit} min. Right-pointing markers show individual sessions continuing beyond the cutoff.',
                 ha='center',fontsize=8.5)
        fig.text(.5,.025,f'Beyond {limit} min: {details}. All {len(sample)} tasks remain included in the means.',ha='center',fontsize=8.5)
        fig.tight_layout(rect=(0,.23 if has_exploration_marker else .12,1,1))
        if has_exploration_marker:
            ax.text(average-.6,-.19,f'AGTA exploration completed\nmean {average:.2f} min\n({timing["n"]}/{timing["total"]} sessions)',
                    transform=ax.get_xaxis_transform(),ha='right',multialignment='right',va='center',color=marker_color,fontsize=9,
                    clip_on=False)
    else:
        fig.tight_layout()
    return fig

def progress_figures(data,out):
    exports=[]
    for view in progress_views(data):
        for app in [None,*view['apps']]:
            sample=progress_sample(view,app);times,means,horizon=progress_points(sample,view['groups'])
            fig=progress_figure(view,app,times,means,horizon)
            for group in view['groups']:
                cohort=[r for r in sample if r['setup']==group]
                for t,value in zip(times,means[group]):
                    exports.append({'comparison':view['id'],'application':app or 'all','setup':group,
                                    'minutes':t,'mean_observed_rows':float(value),'tasks':len(cohort)})
            save_figure(fig,out,progress_name(view,app))
    write_csv(out/'data'/'progress_curves.csv',exports)

def progress_section(view):
    baseline=view['id']=='baseline-progress'
    return {'id':view['id'],'title':view['title'],'continuation':view['continuation'],
            'paragraphs':[
                ('Compare all 35 native and 39 MCP tasks together, or select one of the ten applications below. '
                 if baseline else 'Compare native, MCP and AI-only on their shared Excel, PowerPoint and Word tasks only: 16 native, 16 MCP and 9 AI-only tasks. ')
                +'These charts restore the earlier report\'s line format with the current included results. All tasks in these views record GPT-5.5 with medium effort.',
                'A line counts distinct rows when PASS evidence first appears in qualifying script outputs or result reads. Several rows can arrive together, and earlier successes can come from different attempts. The curves show cumulative evidence rather than one successful replay. Bold means retain every task after it finishes. Pooled means weight tasks equally; application views avoid mixing different workflows. Known GUI-route issues remain disclosed in the acceptance section.'],
            'tables':[],
            'figs':[(progress_name(view,app),progress_caption(view,app)) for app in [None,*view['apps']]],
            'progress_apps':[('all','All applications' if baseline else 'Shared Office applications'),
                             *[(app,app) for app in view['apps']]]}

def application_model_rows(data):
    selected=[r for r in data['runs'] if r['included'] and r['app'] in OFFICE
              and r['bucket'] in ['native','mcp','newcodex'] and r['setup'] in ['mcp','native']]
    rows=[]
    for app in OFFICE:
        for mod in MODEL_ORDER:
            for setup in ['mcp','native']:
                cohort=[r for r in selected if r['app']==app and r['model']==mod and r['setup']==setup]
                if not cohort:continue
                rows.append({'application':app,'model':mod,'setup':setup,'n':len(cohort),
                             'mean_minutes':mean(r['minutes'] for r in cohort),
                             'min_minutes':min(r['minutes'] for r in cohort),
                             'max_minutes':max(r['minutes'] for r in cohort),
                             'successes':sum(r['success'] for r in cohort),
                             'run_ids':[r['id'] for r in cohort]})
    return rows

def pooled_model_rows(data):
    """Average the three application means; keep failed runs and disclose counts."""
    cells=application_model_rows(data);rows=[]
    for mod in POOLED_MODELS:
        for setup in ['mcp','native']:
            selected=[c for c in cells if c['model']==mod and c['setup']==setup]
            by_app={c['application']:c for c in selected}
            complete=set(by_app)==set(OFFICE)
            n=sum(c['n'] for c in selected)
            rows.append({'model':mod,'setup':setup,'n':n,'successes':sum(c['successes'] for c in selected),
                         'applications':list(by_app),'application_counts':{app:by_app[app]['n'] for app in OFFICE if app in by_app},
                         'application_mean_minutes':{app:by_app[app]['mean_minutes'] for app in OFFICE if app in by_app},
                         'mean_minutes':mean(by_app[app]['mean_minutes'] for app in OFFICE) if complete else None,
                         'task_weighted_mean_minutes':sum(c['mean_minutes']*c['n'] for c in selected)/n if n else None,
                         'weighting':'equal application means (1/3 each)' if complete else 'incomplete application coverage',
                         'run_ids':[run_id for c in selected for run_id in c['run_ids']]})
    return rows

def pooled_model_figure(data,out):
    from matplotlib.patches import Patch
    rows=pooled_model_rows(data)
    fig,ax=plt.subplots(figsize=(11.3,5.8))
    for cell in rows:
        x=POOLED_MODELS.index(cell['model'])+(['mcp','native'].index(cell['setup'])-.5)*.36
        value=cell['mean_minutes']
        if value is None:
            ax.text(x,1,'Missing app',ha='center',rotation=90,fontsize=9);continue
        partial=cell['successes']<cell['n']
        # SVG hatch strokes share the patch edge color; contrast with the fill
        # is required because SVG applies opacity to the whole pattern.
        ax.bar(x,value,.36,color=COLORS[cell['setup']],alpha=.8,hatch='///' if partial else '',
               edgecolor='#173f60' if partial else COLORS[cell['setup']])
        ax.text(x,value+.6,f'{value:.2f} min\n{cell["successes"]}/{cell["n"]} passes',ha='center',va='bottom',fontsize=10)
    maximum=max(c['mean_minutes'] for c in rows if c['mean_minutes'] is not None)
    ax.set(xticks=range(len(POOLED_MODELS)),
           xticklabels=[f'GPT-{model(m).split(" / ")[0]}\n'+('medium effort' if m=='gpt-5.5' else 'light / low effort') for m in POOLED_MODELS],
           ylim=(0,math.ceil((maximum+6)/10)*10),ylabel='Mean authoring duration (minutes)',
           title='Excel, PowerPoint and Word combined: MCP versus native')
    ax.grid(axis='y',alpha=.16);ax.set_axisbelow(True)
    handles=[Patch(facecolor=COLORS[g],alpha=.8,label=LABELS[g]) for g in ['mcp','native']]
    handles.append(Patch(facecolor='white',edgecolor='#173f60',hatch='///',label='Includes incomplete / failed attempts'))
    fig.legend(handles=handles,loc='lower center',ncol=3,bbox_to_anchor=(.5,.07),fontsize=10)
    fig.text(.5,.025,'Each application receives one-third weight. All attempts are included; pass counts are recorded five-step outputs.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.17,1,1));save_figure(fig,out,'office-pooled-primary-models')
    write_csv(out/'data'/'pooled_model_comparison.csv',rows)

def cost_figures(data,out):
    from matplotlib.patches import Patch
    component_colors=['#c8895d','#6c9bb7','#8e78a6','#58a38b']
    component_labels=['Ordinary input','Cached input reads','Cache writes','Output (incl. reasoning)']
    cost=data['cost_analysis']
    def bar(ax,x,row,width=.36):
        bottom=0;partial=row['successes']<row['n']
        for part,color in zip(PARTS,component_colors):
            value=row['mean_'+part]
            if not value:continue
            ax.bar(x,value,width,bottom=bottom,color=color,
                   hatch='///' if partial else '',edgecolor='#173f60' if partial else color)
            bottom+=value
        ax.text(x,bottom+.09,f'${bottom:.3f}\n{row["successes"]}/{row["n"]} passes',ha='center',va='bottom',fontsize=9)
    handles=[Patch(facecolor=color,label=label) for part,color,label in zip(PARTS,component_colors,component_labels)
             if any(r['mean_'+part]>0 for r in cost['cohorts'])]
    handles.append(Patch(facecolor='white',edgecolor='#173f60',hatch='///',label='Includes incomplete / failed attempts'))
    rows=[r for r in cost['equal_application'] if r['scope']=='three Office applications' and r['model'] in COST_MODELS and r['setup'] in ['mcp','native']]
    fig,ax=plt.subplots(figsize=(11.8,5.8));ticks=[];ticklabels=[]
    for row in rows:
        x=COST_MODELS.index(row['model'])+(['mcp','native'].index(row['setup'])-.5)*.36
        bar(ax,x,row);ticks.append(x);ticklabels.append('AGTA' if row['setup']=='mcp' else 'Native')
    for i,mod in enumerate(COST_MODELS):
        ax.text(i,-.12,'GPT-'+model(mod).replace(' / ','\n'),transform=ax.get_xaxis_transform(),ha='center',va='top',fontsize=10)
    ax.set(xticks=ticks,xticklabels=ticklabels,ylim=(0,4.8),ylabel='Mean API-equivalent cost (USD / session)',
           title='Excel, PowerPoint and Word: token costs at Standard API prices')
    ax.grid(axis='y',alpha=.16);ax.set_axisbelow(True)
    fig.legend(handles=handles,loc='lower center',ncol=4,bbox_to_anchor=(.5,.045),fontsize=9)
    fig.text(.5,.012,'Equal application weights; all attempts included. Prices checked 8 October 2026. Recorded cache writes: 0.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.23,1,1));save_figure(fig,out,'office-model-costs')
    fig,axes=plt.subplots(1,2,figsize=(11.8,5.3),sharey=True)
    for ax,scope,setups,title in zip(axes,['all included sessions','three Office applications'],
            [['native','mcp'],['native','mcp','aionly']],['All ten applications / session means','Shared Office applications / equal app weights']):
        source=cost['cohorts'] if scope=='all included sessions' else cost['equal_application']
        selected=[next(r for r in source if r['scope']==scope and r['model']=='gpt-5.5' and r['setup']==s) for s in setups]
        for i,row in enumerate(selected):bar(ax,i,row,.58)
        ax.set(xticks=range(len(setups)),xticklabels=[{'native':'Native','mcp':'AGTA','aionly':'AI-only'}[s] for s in setups],
               ylim=(0,6.7),title=title)
        ax.grid(axis='y',alpha=.16);ax.set_axisbelow(True)
    axes[0].set_ylabel('Mean API-equivalent cost (USD / session)')
    fig.suptitle('GPT-5.5 medium: token costs by setup',fontweight='bold',fontsize=14)
    fig.legend(handles=handles[:-1],loc='lower center',ncol=3,bbox_to_anchor=(.5,.045),fontsize=9)
    fig.text(.5,.012,'Current Standard API-equivalent prices; runtime passes do not independently certify GUI-route compliance.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.14,1,.94));save_figure(fig,out,'baseline-setup-costs')

def model_gap_figure(data,out):
    rows=data['model_gap_analysis']['counterfactuals']
    fig,ax=plt.subplots(figsize=(11.3,4.8))
    labels=[]
    for i,row in enumerate(rows):
        observed=row['usage_model']==row['price_model']
        color='#6c9bb7' if i==0 else '#58a38b' if i==3 else '#cba66c'
        ax.bar(i,row['total_usd'],.63,color=color,hatch='' if observed else '...',edgecolor='#536572')
        ax.text(i,row['total_usd']+.07,f'${row["total_usd"]:.3f}\n'+('Recorded combination' if observed else 'Repriced usage'),ha='center',fontsize=10)
        labels.append(f'GPT-{model(row["usage_model"]).split(" / ")[0]} usage\nGPT-{model(row["price_model"]).split(" / ")[0]} rates')
    ax.set(xticks=range(len(rows)),xticklabels=labels,ylim=(0,4.6),
           ylabel='Mean API-equivalent cost (USD / session)',
           title='GPT-5.5 versus 6.1 Sol: separating prices from token usage')
    ax.grid(axis='y',alpha=.16);ax.set_axisbelow(True)
    fig.text(.5,.018,'Same three Office applications with equal weights. Repricing holds token usage fixed; it does not predict another model\'s behavior.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.075,1,1));save_figure(fig,out,'model-gap-cost-decomposition')

def application_model_figures(data,out):
    rows=application_model_rows(data);lookup={r['id']:r for r in data['runs']}
    limit=math.ceil((max(r['max_minutes'] for r in rows)+3)/10)*10
    def draw(ax,app):
        for mod in MODEL_ORDER:
            cells=[r for r in rows if r['application']==app and r['model']==mod]
            if not cells:
                ax.text(MODEL_ORDER.index(mod),2,'No logs',color='#647783',ha='center',fontsize=8)
                continue
            for j,setup in enumerate(['mcp','native']):
                x=MODEL_ORDER.index(mod)+(j-.5)*.34
                cell=next((r for r in cells if r['setup']==setup),None)
                if cell is None:
                    ax.text(x,1.5,'No log',color='#647783',ha='center',rotation=90,fontsize=8)
                    continue
                ax.bar(x,cell['mean_minutes'],.34,color=COLORS[setup],alpha=.68,
                       label=LABELS[setup]+' mean' if mod==MODEL_ORDER[0] else None)
                cohort=[lookup[run_id] for run_id in cell['run_ids']]
                for k,r in enumerate(cohort):
                    ax.scatter(x+(k-(len(cohort)-1)/2)*.04,r['minutes'],
                               marker='o' if r['success'] else 'X',c=COLORS[setup],edgecolor='white',s=55,zorder=4)
        ax.scatter([],[],marker='o',c='#536572',edgecolor='white',s=55,label='Observed five-step pass')
        ax.scatter([],[],marker='X',c='#536572',edgecolor='white',s=55,label='Incomplete / failed')
        ax.set(xticks=range(len(MODEL_ORDER)),xticklabels=[model(m).replace(' / ','\n') for m in MODEL_ORDER],
               ylim=(0,limit),title=app)
        ax.tick_params(axis='x',labelsize=10);ax.grid(axis='y',alpha=.16);ax.set_axisbelow(True)
    def legend(ax):
        handles,labels=ax.get_legend_handles_labels()
        order=[labels.index(label) for label in ['MCP + thesis framework mean','Native mean','Observed five-step pass','Incomplete / failed']]
        return [handles[i] for i in order],[labels[i] for i in order]
    fig,axes=plt.subplots(1,3,figsize=(16.2,6.4),sharey=True)
    for ax,app in zip(axes,OFFICE):draw(ax,app)
    axes[0].set_ylabel('Authoring duration (minutes)')
    fig.legend(*legend(axes[0]),loc='lower center',ncol=4,fontsize=10,bbox_to_anchor=(.5,.01))
    fig.suptitle('MCP and native authoring time across Office applications',fontweight='bold',fontsize=15)
    fig.tight_layout(rect=(0,.12,1,.94));save_figure(fig,out,'office-all-models')
    for app in OFFICE:
        fig,ax=plt.subplots(figsize=(11.6,5.6));draw(ax,app)
        ax.set_ylabel('Authoring duration (minutes)');ax.set_title(app+': MCP and native authoring time by model')
        ax.legend(*legend(ax),loc='upper right',ncol=2,fontsize=9);fig.tight_layout()
        save_figure(fig,out,app.lower()+'-all-models')
    write_csv(out/'data'/'application_model_comparison.csv',rows)

def figures(data,out):
    (out/'figures').mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold','axes.labelcolor':'#23363e','text.color':'#23363e','svg.fonttype':'none'})
    rs=[r for r in data['runs'] if r['included']]
    baseline=[r for r in rs if r['bucket'] in ['native','mcp']]
    apps=sorted({r['app'] for r in baseline})
    fig,ax=plt.subplots(figsize=(11,5.6));x=np.arange(len(apps));w=.36
    for j,g in enumerate(['native','mcp']):
        vals=[mean(r['minutes'] for r in baseline if r['app']==app and r['setup']==g) for app in apps]
        ax.bar(x+(j-.5)*w,vals,w,color=COLORS[g],label=LABELS[g])
        for i,v in enumerate(vals):ax.text(x[i]+(j-.5)*w,v+.8,f'{v:.1f}',ha='center',fontsize=8)
    ax.set_xticks(x,apps,rotation=25,ha='right');ax.set_ylabel('Mean authoring duration (minutes)');ax.set_title('GPT-5.5 / medium: native versus MCP by application');ax.legend();ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    save_figure(fig,out,'baseline-applications')
    office=[r for r in rs if r['bucket'] in ['native','mcp','aionly'] and r['app'] in OFFICE]
    fig,axes=plt.subplots(1,3,figsize=(11,4.4),sharey=True)
    for ax,app in zip(axes,OFFICE):
        for j,g in enumerate(['native','mcp','aionly']):
            s=[r for r in office if r['app']==app and r['setup']==g];vals=[r['minutes'] for r in s]
            ax.bar(j,mean(vals),color=COLORS[g],alpha=.8,width=.62)
            ax.scatter(np.linspace(j-.17,j+.17,len(vals)),vals,c=COLORS[g],edgecolors='white',zorder=3,s=40)
            ax.text(j,mean(vals)+1.4,f'n={len(vals)}',ha='center',fontsize=9)
        ax.set_xticks(range(3),['Native','MCP','AI-only'],rotation=25);ax.set_title(app);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    axes[0].set_ylabel('Authoring duration (minutes)');fig.suptitle('AI-only comparison on the same three Office applications',fontweight='bold');fig.tight_layout()
    save_figure(fig,out,'office-setups')
    newer=[r for r in rs if r['bucket']=='newcodex']
    fig,axes=plt.subplots(1,2,figsize=(11.4,5.3),sharey=True)
    for ax,setup in zip(axes,['mcp','native']):
        for j,m in enumerate(PRIMARY_MODELS):
            for i,app in enumerate(OFFICE):
                s=[r for r in newer if r['model']==m and r['setup']==setup and r['app']==app]
                if not s:continue
                xx=i+(j-1)*.21
                for k,r in enumerate(s):ax.scatter(xx+(k-(len(s)-1)/2)*.065,r['minutes'],marker='o' if r['success'] else 'X',s=75,c=MODEL_COLORS[j],edgecolor='white',zorder=4)
                ax.plot([xx-.055,xx+.055],[mean(r['minutes'] for r in s)]*2,color=MODEL_COLORS[j],linewidth=2)
        ax.set_xticks(range(3),OFFICE,rotation=15);ax.set_title(LABELS[setup]);ax.grid(axis='y',alpha=.16);ax.set_axisbelow(True)
    axes[0].set_ylabel('Recorded authoring duration (minutes)')
    handles=[plt.Line2D([0],[0],marker='o',color='none',markerfacecolor=MODEL_COLORS[j],label=model(m)) for j,m in enumerate(PRIMARY_MODELS)]
    handles += [plt.Line2D([0],[0],marker='X',color='#555',linestyle='none',label='Incomplete / failed')]
    fig.legend(handles=handles,loc='lower center',ncol=4,bbox_to_anchor=(.5,-.03));fig.suptitle('Primary newer models: individual runs and application means',fontweight='bold');fig.tight_layout(rect=(0,.07,1,.95))
    save_figure(fig,out,'primary-model-runtimes')
    application_model_figures(data,out)
    pooled_model_figure(data,out)
    fig,axes=plt.subplots(1,2,figsize=(11,5))
    for ax,metric,title in zip(axes,['total_tokens','uncached_input_tokens'],['Cumulative input + output','Uncached input']):
        for j,m in enumerate(PRIMARY_MODELS):
            for i,g in enumerate(['mcp','native']):
                s=[r for r in newer if r['model']==m and r['setup']==g]
                ax.bar(j+(i-.5)*.32,mean(r[metric] for r in s)/1e6,.32,color=MODEL_COLORS[j],hatch='' if g=='mcp' else '///',alpha=.8)
        ax.set_xticks(range(3),[model(m) for m in PRIMARY_MODELS],rotation=25,ha='right');ax.set_title(title);ax.set_ylabel('Mean tokens (millions)');ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('Resource use: solid = MCP; hatched = native (all recorded attempts)',fontweight='bold');fig.tight_layout()
    save_figure(fig,out,'model-tokens')
    fig,axes=plt.subplots(1,3,figsize=(12,6.4),sharex=True)
    for ax,m in zip(axes,PRIMARY_MODELS):
        sample=sorted([r for r in newer if r['model']==m],key=lambda r:(r['setup'],r['app'],r['start']))
        for y,r in enumerate(sample):
            ax.plot([0,r['minutes']],[y,y],color=COLORS[r['setup']],alpha=.35,lw=5)
            marks=defaultdict(list)
            for step,p in r['first_pass'].items():marks[round(p['minutes'],3)].append(int(step))
            clusters=[]
            for t,steps in sorted(marks.items()):
                ax.scatter(t,y,color=COLORS[r['setup']],s=28,zorder=3)
                if clusters and t-clusters[-1][-1][0]<=3.3 and t-clusters[-1][0][0]<=5.5:
                    clusters[-1].append((t,steps))
                else:clusters.append([(t,steps)])
            for cluster in clusters:
                steps=sorted({step for _,group in cluster for step in group})
                label=f'{steps[0]}-{steps[-1]}' if len(steps)>1 and steps==list(range(steps[0],steps[-1]+1)) else ','.join(str(x) for x in steps)
                ax.text(mean(t for t,_ in cluster),y+.18,label,fontsize=9,ha='center')
            ax.scatter(r['minutes'],y,marker='o' if r['success'] else 'X',c=COLORS[r['setup']],s=65,zorder=4)
        ax.set_yticks(range(len(sample)),[f'{r["id"]} {r["setup"]}\n{r["app"]}' for r in sample],fontsize=9);ax.invert_yaxis();ax.set_title(model(m));ax.set_xlabel('Minutes from task start');ax.grid(axis='x',alpha=.15)
    fig.suptitle('Observed progress, including failed authoring sessions',fontweight='bold');fig.tight_layout(rect=(0,0,1,.95))
    save_figure(fig,out,'model-progress')
    fig,ax=plt.subplots(figsize=(10.7,5.1));offset=0;ticks=[];labels=[]
    for j,m in enumerate(PRIMARY_MODELS):
        for g in ['mcp','native']:
            s=[r for r in newer if r['model']==m and r['setup']==g];q=summarize(s);success=q['success_rate']*100
            ax.barh(offset,success,color=COLORS[g]);ax.text(max(success,1)+1,offset,f'{q["successes"]}/{q["n"]}',va='center');ticks.append(offset);labels.append(model(m)+' / '+g);offset+=1
        offset+=.4
    ax.set_yticks(ticks,labels);ax.invert_yaxis();ax.set_xlim(0,112);ax.set_xlabel('Sessions with an observed five-step pass (%)');ax.set_title('Completion is a separate outcome from authoring speed');ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    save_figure(fig,out,'model-success')
    progress_figures(data,out)

def figure(name,caption):
    timing_link='<p class="quiet"><a href="data/exploration_completion.csv">Exploration completion timings and source receipts (CSV)</a></p>' if name=='baseline-progress-all' and 'data/exploration_completion.csv' in caption else ''
    return f'<figure><img src="figures/{name}.svg" alt="{esc(caption)}"><figcaption>{esc(caption)}</figcaption>{timing_link}</figure>'

def methodology():
    return [
    ('Scope and unit','Only native, mcp, aionly and newcodex are discovered. Top-level old, cli and every nested old directory are excluded. A unit is the first authoring task in a supplied session log. A later artifact-location follow-up is excluded from its timing, tokens and outcomes. Byte-identical copies would be excluded. Reused session IDs alone do not imply duplicates; task turn IDs and actual timestamps identify tasks.'),
    ('Duration','Authoring duration runs from the actual first task_started timestamp to its task_complete or turn_aborted timestamp. Without a terminal event, the last recorded event is used and labeled. Folder minute labels and reused session_meta timestamps are not measurements. Full raw spans are exported. Tool waits, user waiting and failed iterations remain in duration. This is elapsed authoring time, distinct from generated-script replay time.'),
    ('Outcomes and partial progress','Five-step success requires one qualifying runtime output or result read with all five steps passed. Assistant final claims, source strings and exploration RecordSteps are excluded. Streaming/poll outputs are linked to their originating script by session/cell IDs. Diagnostic/nonqualifying results cannot become full passes. Best observed passing-step count is a lower bound from a single result observation, not a sum across attempts; unmeasured prefixes are unknown. First-pass times mark when evidence reached the log, rather than the exact GUI action time.'),
    ('Progress line charts','Each task curve counts distinct CSV rows whose first qualifying PASS receipt has appeared by the plotted minute. The count is cumulative across attempts; later failures do not erase earlier evidence, and reaching five on this curve is not itself proof of a single five-pass replay. Means use all original tasks at every time point and hold achieved values after task completion. Exact receipt timestamps define the steps without interpolation. The pooled ten-application Native-versus-MCP chart displays only 0-60 minutes; right-pointing markers identify sessions continuing beyond that cutoff. This is a display limit only: all sessions and full-duration means remain in the data exports. Individual application and shared-Office progress charts show the full time range. The pooled curves are task-weighted, so application counts can differ across setups. Per-application views provide the closer comparison. These charts use only the GPT-5.5 medium-effort baseline/AI-only cohorts; newer models are analyzed separately. Full means are exported in data/progress_curves.csv.'),
    ('AGTA exploration completion','The ten-application line chart marks the arithmetic mean elapsed time from the same authoring-task start used on its x-axis to the first successful agta_explore Complete response. The response must report ok=true and workflow.explorationComplete=true, and must occur within the primary task. Failed Complete requests, source-code text, assistant claims and later follow-up turns do not qualify. The elapsed time includes preparation, planning, exploration and cleanup before completion; it is not pure GUI interaction time or final script validation time. Sessions with no confirmed completion remain in the progress curves but are excluded from this timing mean, with coverage stated beside the marker. Session timings, missing receipts, log lines and source hashes are exported in data/exploration_completion.csv.'),
    ('Outcome versus route compliance','Runtime pass reporting is measured consistently, but does not prove that the requested GUI-only operations occurred. A focused source audit documents definite COM/file-creation bypasses in four runs. Other runs have not received a complete independent route audit. Framework cleanup and policy flags are framework-reported checks; external activity is not sandboxed. No supplied script, GUI testcase or logged command was executed for this analysis.'),
    ('Model/settings classification','Recorded turn_context.model identifies the model. Two logs placed in 5.6-luna-light record gpt-6-luna and are attributed to it. All newer logs record effort=low; light is the experiment folder label. GPT-5.5 native/MCP/AI-only logs record medium. The primary newer comparison uses 5.6 Luna, 6 Luna and 6.1 Sol. 5.6 Sol and 6 Sol are supplemental Excel-only runs. Comparing Luna with Sol changes model family as well as version.'),
    ('Tokens','Use the last cumulative total_token_usage sample within the primary task; never sum cumulative snapshots. Total equals input plus output; reasoning output is included in output. Uncached input equals input minus cached input and includes any cache-write tokens. Tokens reflect repeated model input; a cache-heavy total is not unique context or a direct cost measure. Reset counters are flagged; none occur here.'),
    ('API-equivalent token cost','Apply the Standard USD token rates checked on 8 October 2026, preserved with official source URLs in data/pricing_snapshot.json. Ordinary input equals input minus cached reads minus cache writes. Cost is (ordinary input x input rate + cached reads x read rate + cache writes x write rate + output x output rate) / 1,000,000. Cache-write charges replace ordinary input charges; reasoning output is already included in output. Every recorded newer-model cache-write counter is zero; GPT-5.5 has no separate write premium. The largest recorded request is 245,777 input tokens, below the 272,000-token long-context threshold, so no long-context surcharge applies. Per-request maxima and log lines are exported in cost_sessions.csv. No service tier is recorded in the inspected turn contexts, so Standard is a reference assumption. These estimates are not Codex/ChatGPT subscription bills; hosted-tool fees, regional premiums, taxes, infrastructure and initial framework/AI-only construction costs are excluded. GPT-5.6 Sol uses the published promotional rate, available at least through 21 November 2026. Equal-application comparisons average application means; cohort cost breakdowns average sessions. All failed attempts are included. Total observed cost divided by observed successes is a batch accounting ratio, not the expected future retry cost; it is undefined with zero successes. The no-cache counterfactual reprices the same recorded input at ordinary rates, with unchanged output and behavior; it is not a prediction of uncached runtime.'),
    ('GPT-5.5 versus 6.1 decomposition','The matched AGTA investigation uses all 16 GPT-5.5 and three GPT-6.1 Sol Office sessions, with identical canonical testcase hashes within each application. Each application receives one-third weight. Cross-price counterfactuals apply either model price vector to either recorded token vector; no other behavior changes. Price and usage attribution averages the price-first and usage-first paths (a two-factor Shapley decomposition), so the two USD effects add exactly to the observed estimated-cost reduction. It is an accounting decomposition, not a causal model of agent behavior. Distinct cumulative usage changes are counted after deduplicating identical token_count totals; they are accounting updates rather than a standardized GUI-action or outer-tool-call count. Exploration completion also recognizes namespaced agta_explore calls inside newer exec wrappers and requires the successful completion receipt. Post-exploration time ends at the primary task boundary and includes generation, repairs, replay and final response. Compaction counts use explicit compacted records only. Reasoning settings and client/tool formats differ; runtime differences do not isolate model-only effects.'),
    ('Process metrics','Script-launch requests recognize observed invocation names and create-then-run commands, excluding validation/preflight-only runs and source writes without invocation. A launch is a request, not necessarily a completed test. Probe and final script names may both be counted if observed as test scripts. Outer tool requests are exported, but newer functions.exec wrapping and polling differs from the older direct tool format, so cross-generation tool counts are not comparable GUI-action counts.'),
    ('Replay records','Deduplicate qualifying framework result reads by executionId inside each session. Summaries, cleanup/policy fields and totalMs are read only from qualifying execution results. Final replay timing is reported separately from authoring. There is no uniformly recorded native/AI-only replay-duration measure; do not substitute folder labels or authoring duration.'),
    ('Comparisons and uncertainty','Primary setup comparisons include all recorded attempts. Report pooled means and medians, application-specific values, and equal-application-weight means to control uneven repetition counts. AI-only comparisons are restricted to Excel, PowerPoint and Word. Exact canonical testcase content is a sensitivity check. Baseline 95% bootstrap intervals use 4,000 deterministic within-application resamples; singleton cells remain fixed, so intervals are conditional descriptions, not causal guarantees. Newer model cells mostly have one run, making repeat variability unestimable; no model-ranking confidence claim is made.'),
    ('Failures and efficiency','A short failed task is not a successful runtime. Successful-session durations and total observed authoring minutes per observed success are separate metrics. With zero successes, time-per-success is undefined, not zero or infinity. Sessions stopped without completion are bounded observations, not estimated time-to-eventual-success. Failed prefixes and consumed tokens remain in the analysis.'),
    ('Testcase recovery','Canonical hashes compare Action, Data and Expected Result fields. Malformed native Photos CSV exports are explicitly normalized as in the previous extractor. One new native 6 Sol Excel log does not preserve full CSV row content; action names are inferred conventionally only for matching observed results, and that run is excluded from exact-content sensitivity. The older Paint run is superseded because its PDF visual-content expectation differs from the replacement existence-only expectation.'),
    ('Generalizability','The corpus is observational, selected and unevenly repeated. Experiment environments, infrastructure versions, prompts, application state and cleanup behavior are not uniformly controlled. AI-only means reuse of an independently AI-implemented tool in the authoring logs; its initial implementation time is absent. Framework construction time is also absent. Baseline five-pass reporting is high in both setups, with known route exceptions. Evidence supports comparative authoring behavior in this corpus rather than universal reliability or causal model-version improvements.')]

def sections(data):
    rs=[r for r in data['runs'] if r['included']];baseline=[r for r in rs if r['bucket'] in ['native','mcp']];new=[r for r in rs if r['bucket']=='newcodex'];office=[r for r in rs if r['bucket'] in ['native','mcp','aionly'] and r['app'] in OFFICE]
    n=summarize([r for r in baseline if r['setup']=='native']);m=summarize([r for r in baseline if r['setup']=='mcp']);equal=data['comparisons'][0]
    ai=summarize([r for r in rs if r['bucket']=='aionly']);c56=next(c for c in data['comparisons'] if c['label']=='mcp: gpt-5.6-luna versus gpt-6.1-sol');c6=next(c for c in data['comparisons'] if c['label']=='mcp: gpt-6-luna versus gpt-6.1-sol')
    cards=f'<div class="kpis"><div><span>Measured tasks</span><strong>{len(rs)}</strong><small>{len(data["runs"])} discovered; {len(data["runs"])-len(rs)} separately listed</small></div><div><span>GPT-5.5 pooled authoring time</span><strong>{n["minutes"]["mean"]:.1f} → {m["minutes"]["mean"]:.1f} min</strong><small>{100*(1-m["minutes"]["mean"]/n["minutes"]["mean"]):.1f}% lower with MCP</small></div><div><span>New 6.1 Sol / MCP</span><strong>6.80 min</strong><small>3/3 five-step passes; low effort</small></div><div><span>5.6 Luna / native</span><strong>0/4 full passes</strong><small>Failed attempts retained</small></div></div>'
    result=[]
    findings=[f'The main GPT-5.5 comparison contains {n["n"]} native and {m["n"]} MCP tasks across ten applications. MCP lowers the pooled mean from {n["minutes"]["mean"]:.2f} to {m["minutes"]["mean"]:.2f} minutes ({100*(1-m["minutes"]["mean"]/n["minutes"]["mean"]):.1f}%). Equal application weighting gives {equal["left_mean"]:.2f} versus {equal["right_mean"]:.2f} minutes ({-equal["change_pct"]:.1f}% lower). Both report five-step passes in every included log; this does not establish universal GUI-route compliance.',
    f'AI-only has nine relevant Office tasks, all with observed five-pass outputs. Its equal-application mean is {ai["minutes"]["mean"]:.2f} minutes, about twice MCP on these same Office applications. Three supplied AI-only scripts visibly bypass GUI routes with Office COM; keep their runtime measurements, but do not describe all nine as valid GUI-only successes.',
    f'6.1 Sol light is the fastest observed MCP configuration in the newer batch: 5.26 minutes for Excel, 9.54 for PowerPoint and 5.60 for Word. Its mean is {c56["right_mean"]:.2f} minutes, {-c56["change_pct"]:.1f}% below 5.6 Luna and {-c6["change_pct"]:.1f}% below 6 Luna on the three shared applications. Each newer primary-model cell has one MCP run; these are descriptive differences.',
    'Recorded 5.6 Luna native tasks achieve no full pass in four sessions despite repeated launches. The same model completes all three MCP sessions. Recorded 6 Luna native has three passes and three failures, while 6.1 Sol has three passes out of three. The two 6 Luna failures filed under 5.6 are reassigned using log metadata. Short failed sessions are not ranked as successful speedups.',
    'Supplemental 5.6 Sol and 6 Sol results cover Excel only. They help compare Sol-family behavior, but cannot stand in for three-application model results. The older GPT-5.5 corpus uses medium effort while newcodex uses low; version, family, effort and runtime environment are not isolated causal variables.']
    result.append({'id':'findings','title':'Findings','paragraphs':findings,'tables':[],'figs':[]})
    inv=[['native',str(n['n']),'GPT-5.5 / medium','10'],['mcp',str(m['n']),'GPT-5.5 / medium','10'],['aionly',str(ai['n']),'GPT-5.5 / medium','3'],['newcodex',str(len(new)),'Five recorded models / low','3']]
    excluded=[[link(r),esc(r['file']),esc(r['exclusion_reason'])] for r in data['runs'] if not r['included']]
    result.append({'id':'scope','title':'Corpus and inclusion decisions','paragraphs':[f'The source directory is read-only. The old and cli roots, including mcp/old, are outside this report. {sum(not i["log_count"] for i in data["inventory"])} leaf folders lack session logs, including the empty 6 Luna word-20m folder and a 5.6 Luna native failed folder; their labels are not used to invent durations or outcomes. The new 6 Luna word-10m session is included. All {len(data["runs"])} logs parse without malformed records, no token resets are observed, and no authoring turn ID is duplicated.','The 37-minute Paint run is retained in the inventory and sensitivity check, and superseded in primary results. Its fifth-row expectation requires the opened PDF to show the complete three-line image on one page. The replacement only requires a nonempty PDF.'],
                   'tables':[(['Source','Included tasks','Recorded settings','Applications'],inv),(['Excluded log','Source path','Reason'],excluded)],'figs':[]})
    app_rows=[]
    faster=0
    for app in sorted({r['app'] for r in baseline}):
        a=summarize([r for r in baseline if r['setup']=='native' and r['app']==app]);b=summarize([r for r in baseline if r['setup']=='mcp' and r['app']==app])
        faster+=b['minutes']['mean']<a['minutes']['mean']
        app_rows.append([app,str(a['n']),num(a['minutes']['mean']),num(a['minutes']['median']),str(b['n']),num(b['minutes']['mean']),num(b['minutes']['median']),f'{100*(b["minutes"]["mean"]/a["minutes"]["mean"]-1):+.1f}%'])
    result.append({'id':'baseline','title':'Native versus MCP: the main thesis comparison','paragraphs':[f'Pooled medians are {n["minutes"]["median"]:.2f} minutes native and {m["minutes"]["median"]:.2f} minutes MCP. Standard deviations are {n["minutes"]["sd"]:.2f} and {m["minutes"]["sd"]:.2f} minutes. The pooled reduction is {n["minutes"]["mean"]/m["minutes"]["mean"]:.2f} times faster authoring in this corpus.',
    f'MCP is faster in {faster} of ten observed application means. The updated Photos mean is 27.04 minutes MCP versus 30.97 native; its additional faster run changes the earlier batch comparison. Testcase variants and GUI save/selector recovery remain relevant. OneNote, Edge and some other cells have very few repetitions, so application estimates should be read with their sample counts.',
    'The observed native Notepad folder labeled failed contains a five-pass output but also a file-creation recovery. This is retained in runtime and reported-outcome statistics, with the route audit disclosed below.'],
    'tables':[(['App','Native n','Mean min','Median min','MCP n','Mean min','Median min','MCP change'],app_rows)],'figs':[('baseline-applications','Bars are application means from all included GPT-5.5 tasks. Uneven repetition counts are disclosed in the table; Paint uses the replacement testcase.')]})
    result.append(progress_section(progress_views(data)[0]))
    offrows=[]
    for app in OFFICE:
        for g in ['native','mcp','aionly']:
            s=summarize([r for r in office if r['app']==app and r['setup']==g]);offrows.append([app,LABELS[g],str(s['n']),num(s['minutes']['mean']),num(s['minutes']['median']),f'{s["successes"]}/{s["n"]}',num(s['total_tokens']['mean']/1e6)])
    nativeoff=mean(mean(r['minutes'] for r in office if r['setup']=='native' and r['app']==app) for app in OFFICE);mcpoff=mean(mean(r['minutes'] for r in office if r['setup']=='mcp' and r['app']==app) for app in OFFICE)
    result.append({'id':'aionly','title':'AI-only reimplementation versus the thesis framework','paragraphs':[f'Use Excel, PowerPoint and Word for this comparison: the AI-only corpus has three runs per application. Equal-application authoring means are {nativeoff:.2f} minutes native, {mcpoff:.2f} minutes MCP and {ai["minutes"]["mean"]:.2f} minutes AI-only. AI-only is {100*(1-ai["minutes"]["mean"]/nativeoff):.1f}% below native and {100*(ai["minutes"]["mean"]/mcpoff-1):.1f}% above MCP. Its median is {ai["minutes"]["median"]:.2f} minutes; the 57.48-minute PowerPoint run strongly affects its mean.',
    'These logs measure testcase authoring using an already available AI-only tool. They do not record the time spent generating its initial implementation from the single prompt. Both the thesis framework and AI-only tool have reusable construction work outside this authoring comparison.',
    'Three AI-only scripts perform requested operations through Office COM rather than the GUI. Excluding those known bypasses leaves six runs; this is a sensitivity check and does not certify the remaining scripts. The folder aionly/excel-14m-failed is actually an aborted Access/MCP task and is excluded from these Office comparisons.'],
    'tables':[(['App','Setup','n','Mean min','Median min','Five-pass outputs','Mean tokens M'],offrows)],'figs':[('office-setups','Bars show application means; dots show every relevant task. All nine AI-only runtimes are retained despite known route problems in three supplied scripts.')]})
    result.append(progress_section(progress_views(data)[1]))
    modern=[]
    for mod in PRIMARY_MODELS:
        for g in ['mcp','native']:
            s=summarize([r for r in new if r['model']==mod and r['setup']==g]);modern.append([model(mod),g,str(s['n']),f'{s["successes"]}/{s["n"]}',num(s['minutes']['mean']),num(s['minutes']['median']),num(s['successful_minutes']['mean']),num(s['spent_minutes_per_success'])])
    c_luna=next(c for c in data['comparisons'] if c['label']=='mcp: gpt-5.6-luna versus gpt-6-luna')
    word6=next(r for r in new if r['model']=='gpt-6-luna' and r['setup']=='mcp' and r['app']=='Word')
    result.append({'id':'models','title':'Primary newer-model comparison','paragraphs':['All included newcodex logs record low reasoning effort, corresponding to the folders labeled light. Model attribution uses the recorded identifier. 5.6 Luna, 6 Luna and 6.1 Sol each now have one MCP observation per Office application. The empty 6 Luna word-20m folder is still not a measurement.',
    f'The added 8 October 6 Luna Word session ({word6["id"]}) takes {word6["minutes"]:.2f} minutes and records an observed five-step pass. It closes the previous missing Word MCP cell; its {word6["script_launches"]} script-launch requests remain in the iteration metrics.',
    f'6.1 Sol MCP averages {c56["right_mean"]:.2f} minutes on all three Office applications. Compare it to {c56["left_mean"]:.2f} minutes for 5.6 Luna ({-c56["change_pct"]:.1f}% lower) and {c6["left_mean"]:.2f} minutes for 6 Luna ({-c6["change_pct"]:.1f}% lower), using the same three applications in both comparisons.',
    f'6 Luna does not improve over 5.6 Luna in the combined MCP comparison: across Excel, PowerPoint and Word, its mean is {c_luna["right_mean"]:.2f} versus {c_luna["left_mean"]:.2f} minutes ({c_luna["change_pct"]:.1f}% longer). Application results vary, and the new Word run is faster than its 5.6 Luna counterpart. As an older-model reference, GPT-5.5 MCP averages 12.19 minutes on the three Office applications versus 6.80 for 6.1 Sol, about 44% lower for 6.1. That comparison also changes medium to low effort and the collection environment.',
    'Native failure durations stay in all-attempt means. The successful-session mean and observed minutes spent per success reveal why raw runtime alone is misleading. Time-per-success is an accounting ratio over this collected batch, not an estimate of an expected future retry process.',
    '6.1 Sol native completes the three applications in 17.41-22.67 minutes. 6 Luna native successful sessions take roughly 39-43 minutes, but its failed sessions are much shorter. 5.6 Luna never reaches a full native pass here; its successful-session runtime is undefined.'],
    'tables':[(['Model','Setup','n','Five-pass outputs','All mean min','Median min','Success-only mean','Spent min / success'],modern)],
    'figs':[('primary-model-runtimes','Circles are observed five-pass sessions; crosses are incomplete/failed sessions. Short ticks mark per-application means. All three primary models now have MCP coverage for Excel, PowerPoint and Word.'),('model-success','All four recorded 5.6 Luna native tasks failed; all three of its MCP tasks passed. Small samples describe this corpus and do not establish population success probabilities.')]})
    pooled=pooled_model_rows(data)
    pooled_table=[[model(c['model']),LABELS[c['setup']],str(c['n']),f'{c["successes"]}/{c["n"]}',num(c['mean_minutes']),
                   '; '.join(f'{app}: {count}' for app,count in c['application_counts'].items())] for c in pooled]
    result.append({'id':'office-pooled-models','title':'Combined Office comparison: four model configurations',
                   'paragraphs':['This chart combines Excel, PowerPoint and Word for GPT-5.5 medium, GPT-5.6 Luna light, GPT-6 Luna light and GPT-6.1 Sol light, in release order. Each bar averages the three application means with one-third weight each, so unequal repetition counts do not change the application mix. All attempts, including failed native authoring sessions, contribute their recorded duration.',
                   'Pass counts describe recorded five-step outputs, with known route-compliance limitations retained elsewhere in the report. A short failed attempt consumes less time but does not demonstrate faster successful authoring. GPT-5.5 uses medium effort and the newer configurations use low effort, labeled light.'],
                   'tables':[(['Model','Setup','Sessions','Five-pass outputs','Equal-app mean min','Sessions by application'],pooled_table)],
                   'figs':[('office-pooled-primary-models','Bars average the means for the same three Office applications. Labels show duration and observed five-pass counts; hatching identifies bars containing incomplete/failed attempts. No AI-only or supplemental 5.6 Sol / 6 Sol runs enter this chart.')],
                   'fig_first':True,'downloads':[('data/pooled_model_comparison.csv','Download combined model comparison data')]})
    byapp=[]
    for mod in PRIMARY_MODELS:
        for g in ['mcp','native']:
            for app in OFFICE:
                sample=[r for r in new if r['model']==mod and r['setup']==g and r['app']==app]
                if not sample:byapp.append([model(mod),g,app,'0','unmeasured','unmeasured','no log']);continue
                s=summarize(sample);byapp.append([model(mod),g,app,str(s['n']),num(s['minutes']['mean']),f'{s["successes"]}/{s["n"]}',', '.join(link(r) for r in sample)])
    result.append({'id':'modelapps','title':'Newer models by application','paragraphs':['Each cell retains every supplied task, including all failed native attempts and the two metadata-corrected 6 Luna runs. Compare the same application and setup. The small supplemental Sol sample is presented separately rather than mixed into Luna means.'],
                   'tables':[(['Model','Setup','App','n','Mean min','Five-pass outputs','Evidence'],byapp)],'figs':[]})
    supp=[]
    for cell in application_model_rows(data):
        supp.append([cell['application'],model(cell['model']),cell['setup'],str(cell['n']),num(cell['mean_minutes']),num(cell['min_minutes'])+'-'+num(cell['max_minutes']),f'{cell["successes"]}/{cell["n"]}'])
    comparison_caption='Native and MCP share a single axis within each application, and all three panels use the same 0-60 minute scale. Bars are all-attempt means; circles mark observed five-step passes and crosses mark incomplete/failed tasks. Missing logs have no bars. GPT-5.5 uses medium effort; newer models use light/low effort.'
    result.append({'id':'sol','title':'Model comparison across Excel, PowerPoint and Word','paragraphs':['Compare native and MCP directly on the same time scale for each Office application. Model order is 5.5, 5.6 Luna, 5.6 Sol, 6 Luna, 6 Sol and 6.1 Sol. GPT-5.5 results come from the included baseline native/MCP runs and use medium effort; the newer logs use low effort, labeled light. Differences remain descriptive because version, model family and effort are not isolated.',
    'The 5.6 Sol and 6 Sol logs cover Excel only. Their PowerPoint and Word cells are left empty. The new 6 Luna MCP Word session is included. Failed native Luna tasks retain their consumed time and are marked with crosses; a shorter failed attempt is not a successful speedup.',
    'The Excel MCP runs take 14.98 minutes with 5.6 Sol, 13.06 with 6 Sol and 5.26 with 6.1 Sol. Each is a single successful run.',
    'Native 5.6 Sol has two successful runs of 13.06 and 51.29 minutes. Its mean of 32.18 hides this spread; neither the fastest nor the slowest alone should be presented as its typical runtime. Native 6 Sol takes 20.73 minutes and 6.1 Sol takes 22.67 minutes in their single Excel runs, so the MCP model ordering does not repeat universally in native authoring.'],
    'tables':[(['App','Model','Setup','n','Mean min','Range min','Five-pass outputs'],supp)],
    'figs':[('office-all-models',comparison_caption)],'fig_first':True,
    'downloads':[('data/application_model_comparison.csv','Download model comparison data')],
    'pdf_figs':[(app.lower()+'-all-models',app+': '+comparison_caption) for app in OFFICE]})
    failures=[r for r in new if not r['success']];rows=[]
    for r in failures:
        reason='Save/dialog or UI Automation failure'
        txt=' '.join(x['text'] for x in r['runtime_errors'])
        if 'Workbook was not created' in txt:reason='Save workflow did not create workbook'
        if 'here-string' in txt:reason+='; PowerShell parsing problems also observed'
        if r['folder']=='word-5m-failed':reason='Window readiness / UI Automation stalled; later results absent'
        rows.append([link(r),model(r['model']),r['app'],num(r['minutes']),num(r['best_passed_steps'],0),str(r['script_launches']),reason])
    spent56=sum(r['minutes'] for r in failures if r['model']=='gpt-5.6-luna')
    result.append({'id':'failures','title':'Failures, partial progress and the 5.6 Luna anomaly','paragraphs':[f'The four recorded 5.6 Luna native tasks consume {spent56:.2f} minutes in total without producing a full five-step pass. One Word run provides observed passing receipts for steps 1 and 2. Three other failed logs expose runtime errors without a recoverable complete step table; their prefix length is unmeasured, not zero.',
    'The repeated native obstacle is saving or navigating Office dialogs. Evidence includes unsupported UI Automation patterns, workbook-not-created errors, parser mistakes and stalled automation. These are authoring/integration failures observed in these sessions; a timeout on a guessed selector is not proof of an Office application defect.',
    'Two failures stored in 5.6-luna-light are actually gpt-6-luna: the 17-minute Excel and 5-minute Word sessions. They remain in 6 Luna statistics. Another 6 Luna Word task reports two passing steps then fails at Save As. Later successful Word/PowerPoint/Excel tasks are included independently.',
    'Progress markers below show first observed PASS receipts from qualifying runs. A final five-pass summary can reveal all steps at once; the graph does not invent exact per-action times. Every failed task ends at its recorded boundary, with its total consumed time and tokens retained.'],
    'tables':[(['Run','Recorded model','App','Min','Best observed passes / 5','Launch requests','Observed failure context'],rows)],'figs':[('model-progress','Dots mark when each CSV step first had a visible PASS receipt. Nearby receipts share a step label; dots retain their recorded positions. Endpoint circles denote five-pass tasks; crosses denote failed/incomplete tasks. Unknown prefixes have no fabricated markers.')]})
    resources=[]
    for s in sorted(data['summary'],key=lambda s:(model_rank(s['model']),s['setup'],s['bucket'])):
        resources.append([model(s['model']) if s['bucket']=='newcodex' else 'GPT-5.5 / medium',s['setup'],str(s['n']),num(s['total_tokens']['mean']/1e6),num(s['uncached_input_tokens']['mean']/1000),num(s['output_tokens']['mean']/1000),num(s['script_launches']['mean'])])
    replayrows=[]
    for bucket,mod in [('mcp','gpt-5.5')]+[('newcodex',mod) for mod in ALL_MODELS]:
        sample=[r for r in rs if r['bucket']==bucket and r['model']==mod and r['setup']=='mcp'];ex=[e for r in sample for e in r['executions']]
        good=[e for e in ex if e.get('summary',{}).get('passed')==5];bad=[e for e in ex if e.get('ok') is False];timings=[r['final_replay_seconds'] for r in sample if r['final_replay_seconds'] is not None]
        replayrows.append([mod,str(len(sample)),str(len(ex)),str(len(good)),str(len(bad)),str(sum(e.get('summary',{}).get('passed')==5 and e.get('cleanupOk') is False for e in ex)),num(mean(timings) if timings else None)+f' (n={len(timings)})'])
    result.append({'id':'resources','title':'Tokens, iteration effort and replay runtime','paragraphs':['Token totals are cumulative model consumption, with repeated cached input. Uncached input and output are also shown because a large cached-input total can coexist with a lower elapsed duration. The following cost section applies category-specific API prices to these counters.',
    'The newer MCP sessions still require repairs: 5.6 Luna has substantially more saved-script launches in its Excel and PowerPoint sessions than 6.1 Sol. Native launch counts remain large even in some successful Sol/Luna sessions. A launch request can fail before testcase execution; it is not a counted full replay.',
    'Framework replay results are deduplicated by execution ID. Five passing steps and cleanup success are distinct: a newer 5.6 Luna PowerPoint task reports five passing steps with a cleanup warning. Five-pass and ok=false record counts can therefore overlap. Final replay runtimes are tens of seconds and do not replace the several-minute authoring metric. Outer tool-call counts are exported but not ranked across the old and new log formats.'],
    'tables':[(['Settings','Setup','n','Mean total tokens M','Uncached input K','Output K','Mean launches'],resources),(['MCP model','Tasks','Observed replay IDs','5-pass IDs','ok=false','5 passes / cleanup false','Mean final replay s'],replayrows)],
    'figs':[('model-tokens','All recorded attempts are included. Hatching identifies native authoring. Totals include cached repeated input, and failed native attempts remain in both measures.')]})
    costs=data['cost_analysis'];balanced=costs['equal_application'];cohorts=costs['cohorts']
    primary=[r for r in balanced if r['scope']=='three Office applications' and r['model'] in COST_MODELS and r['setup'] in ['mcp','native']]
    primaryrows=[[model(r['model']),'AGTA' if r['setup']=='mcp' else 'Native',f'{r["successes"]}/{r["n"]}',num(r['mean_minutes']),f'${r["mean_total_usd"]:.4f}'] for r in primary]
    base={r['setup']:r for r in cohorts if r['model']=='gpt-5.5'}
    officecost={r['setup']:r for r in balanced if r['model']=='gpt-5.5' and r['scope']=='three Office applications'}
    latest={r['setup']:r for r in primary if r['model']=='gpt-6.1-sol'}
    result.append({'id':'costs','title':'API-equivalent cost comparison',
        'paragraphs':['Input, cached input and output carry different rates. This comparison uses the recorded usage and current Standard API prices in USD, checked on 8 October 2026. It estimates equivalent token charges, rather than the actual cost of these Codex/ChatGPT subscription sessions. No service tier is recorded in the inspected turn contexts.',
        f'Across all ten GPT-5.5 applications, the session-mean estimate is ${base["native"]["mean_total_usd"]:.3f} native versus ${base["mcp"]["mean_total_usd"]:.3f} AGTA: AGTA is {100*(base["mcp"]["mean_total_usd"]/base["native"]["mean_total_usd"]-1):.1f}% higher despite its shorter authoring time. Restricting both setups to the same three Office applications and giving each application equal weight yields ${officecost["native"]["mean_total_usd"]:.3f} native versus ${officecost["mcp"]["mean_total_usd"]:.3f} AGTA, only {100*(officecost["mcp"]["mean_total_usd"]/officecost["native"]["mean_total_usd"]-1):.1f}% higher. AI-only is ${officecost["aionly"]["mean_total_usd"]:.3f} on those applications; its known GUI-route bypasses still apply.',
        f'GPT-6.1 Sol AGTA averages ${latest["mcp"]["mean_total_usd"]:.3f} versus ${latest["native"]["mean_total_usd"]:.3f} native, a {100*(1-latest["mcp"]["mean_total_usd"]/latest["native"]["mean_total_usd"]):.1f}% reduction, alongside its 66.5% authoring-time reduction. Its AGTA cost is {100*(1-latest["mcp"]["mean_total_usd"]/officecost["mcp"]["mean_total_usd"]):.1f}% below GPT-5.5 AGTA on the shared Office applications. That change combines different prices, token usage, model family and reasoning settings.',
        'Luna has much lower token prices than Sol. Its cost advantage therefore does not imply the fastest authoring. The low GPT-5.6 Luna native cost describes four failed attempts with zero full passes; no cost per successful native solution can be estimated from that sample. GPT-6 Luna native includes three failed and three successful attempts. Completion counts accompany every comparison.'],
        'tables':[(['Model / effort','Setup','Five-pass outputs','Equal-app mean min','Equal-app mean USD'],primaryrows)],
        'figs':[('office-model-costs','Each application has one-third weight, matching the combined Office runtime chart. Stacks separate ordinary input, cache reads and output; recorded cache writes are zero. Hatching marks incomplete/failed attempts. All labels show API-equivalent USD, not subscription charges.'),
                ('baseline-setup-costs','The left panel uses all ten applications with session weighting (native n=35; AGTA n=39). The right panel uses equal weights for Excel, PowerPoint and Word (native n=16; AGTA n=16; AI-only n=9). Different weighting and application coverage are explicitly shown; both panels share the same cost scale.')],
        'downloads':[('data/cost_comparisons.csv','Download cost comparisons'),('data/cost_sessions.csv','Download per-session cost ledger'),('data/cost_by_application.csv','Download costs by application')]})
    rate_rows=[[f'<a href="{r["source"]}">{model(r["model"])}</a>',f'${r["ordinary_input"]:g}',f'${r["cached_read"]:g}',f'${r["cache_write"]:g}' if r['cache_write'] is not None else 'ordinary input rate',f'${r["output"]:g}'] for r in costs['pricing']['models']]
    costrows=[[model(r['model']),{'mcp':'AGTA','native':'Native','aionly':'AI-only'}[r['setup']],f'{r["successes"]}/{r["n"]}',
               *[f'${r["mean_"+part]:.4f}' for part in ['ordinary_input_usd','cached_read_usd','output_usd']],f'${r["mean_total_usd"]:.4f}',
               f'${r["spent_usd_per_observed_success"]:.4f}' if r['successes'] else 'undefined'] for r in cohorts]
    result.append({'id':'cost-details','title':'Cost breakdown, rates and accounting',
        'paragraphs':['Rates below are USD per million tokens at Standard short-context pricing. Model names link to their official rate pages. GPT-5.6 Sol uses the published promotional price. Cached reads cost one-tenth of ordinary input for most tested models and one-twentieth for GPT-6.1 Sol; output has a substantially higher per-token rate.',
        'Cost = ((input - cached reads - cache writes) x ordinary-input rate + cached reads x cached-read rate + cache writes x write rate + output x output rate) / 1,000,000. Cache writes are a separate input category, not an extra charge added to ordinary input. The newer logs expose that counter, but it is zero in every included session. Reasoning tokens are already included in output and are charged once.',
        f'All {len(costs["ledger"])} included sessions have per-request token samples; the maximum is {costs["max_request_input_tokens"]:,} input tokens, below the 272,000-token long-context boundary. Millions of cumulative input tokens do not themselves trigger long-context pricing. Source hashes, final cumulative usage lines and request-size audit lines are preserved in the ledger.',
        'The breakdown below uses session means for each entire cohort, so GPT-5.5 native and AGTA cover ten applications, AI-only covers three, and supplemental 5.6 Sol / 6 Sol cover Excel only. It must not replace the matched Office comparison above. Spent USD per observed success includes the cost of failed attempts and uses the actual batch totals; it is not an expected future retry price. Hosted-tool fees, regional premiums, taxes, infrastructure and initial tool/framework implementation are excluded.'],
        'tables':[(['Model / effort','Input','Cached read','Cache write','Output'],rate_rows),
                  (['Model / effort','Setup','Passes / n','Ordinary input','Cache reads','Output','Total / session','Spent / success'],costrows),
                  (['Official source','Link'],[['Standard API pricing',f'<a href="{costs["pricing"]["source"]}">OpenAI API pricing</a>'],['Cache classification and write charges',f'<a href="{costs["pricing"]["cache_source"]}">OpenAI prompt caching guide</a>']])],
        'figs':[],'downloads':[('data/pricing_snapshot.json','Download dated price snapshot and assumptions')]})
    gap=data['model_gap_analysis'];old,latestavg=gap['averages'];attrib=gap['attribution'];cross=gap['counterfactuals']
    measures=[('Authoring time','minutes',1,' min'),('Total tokens','total_tokens',1e6,' M'),
              ('Cached input reads','cached_input_tokens',1e6,' M'),('Uncached input','uncached_input_tokens',1000,' K'),
              ('Output incl. reasoning','output_tokens',1000,' K'),('Reasoning subset','reasoning_output_tokens',1000,' K'),
              ('Distinct usage-counter updates','usage_counter_updates',1,''),('Exploration completion','exploration_minutes',1,' min'),
              ('Time after exploration','post_exploration_minutes',1,' min'),('Script-launch requests','script_launches',1,''),
              ('Final script replay','final_replay_seconds',1,' s'),('Tool text','tool_text_kib',1,' KiB')]
    measurerows=[[label,num(old[key]/divisor)+unit,num(latestavg[key]/divisor)+unit,f'{100*(latestavg[key]/old[key]-1):+.1f}%'] for label,key,divisor,unit in measures]
    crossrows=[[model(r['usage_model']),model(r['price_model']),f'${r["total_usd"]:.4f}',
                'Recorded combination' if r['usage_model']==r['price_model'] else 'Repriced usage'] for r in cross]
    appgaprows=[[r['application'],model(r['model']),str(r['n']),num(r['minutes']),num(r['exploration_minutes']),num(r['script_launches']),num(r['total_tokens']/1e6),
                 ', '.join(f'<a href="evidence.html#{rid}">{rid}</a>' for rid in r['run_ids'])] for r in gap['applications']]
    nativecost={r['model']:r for r in balanced if r['scope']=='three Office applications' and r['setup']=='native'}
    result.append({'id':'why61','title':'Why GPT-6.1 Sol differs from GPT-5.5',
        'paragraphs':['This investigation holds the application mix fixed to Excel, PowerPoint and Word and uses equal application weights. All 16 GPT-5.5 AGTA sessions and all three GPT-6.1 Sol AGTA sessions have matching canonical testcase hashes within each application and observed five-pass outputs. The comparison is between GPT-5.5 medium effort and GPT-6.1 Sol low effort; it is not a controlled model-only experiment.',
        f'The estimated cost falls from ${cross[0]["total_usd"]:.3f} to ${cross[3]["total_usd"]:.3f} ({100*(1-cross[3]["total_usd"]/cross[0]["total_usd"]):.1f}% lower). Most of that gap comes from prices: ordinary input falls from $5 to $2 per million, cached reads from $0.50 to $0.10, and output from $30 to $10. Repricing the old 5.5 usage at 6.1 prices alone yields ${cross[1]["total_usd"]:.3f}. Repricing the new 6.1 usage at 5.5 prices yields ${cross[2]["total_usd"]:.3f}.',
        f'Averaging both possible attribution orders assigns ${attrib["price_effect_usd"]:.3f} ({100*attrib["price_share"]:.1f}%) of the absolute USD reduction to lower prices and ${attrib["usage_effect_usd"]:.3f} ({100*attrib["usage_share"]:.1f}%) to the changed token mix. These shares describe accounting effects, not percentages of the runtime improvement. Total AGTA tokens fall only {100*(1-latestavg["total_tokens"]/old["total_tokens"]):.1f}%; uncached input and output fall much more.',
        f'Authoring falls from {old["minutes"]:.2f} to {latestavg["minutes"]:.2f} minutes. Confirmed exploration completion falls from {old["exploration_minutes"]:.2f} to {latestavg["exploration_minutes"]:.2f} minutes, accounting descriptively for {100*(old["exploration_minutes"]-latestavg["exploration_minutes"])/(old["minutes"]-latestavg["minutes"]):.1f}% of the elapsed-time gap. Time after exploration falls from {old["post_exploration_minutes"]:.2f} to {latestavg["post_exploration_minutes"]:.2f} minutes. Final replay itself is similar ({old["final_replay_seconds"]:.1f} versus {latestavg["final_replay_seconds"]:.1f} seconds), so the large gain is in preparation, exploration and authoring rather than faster execution of the final GUI testcase.',
        'The newer sessions record much less reasoning and shorter generated output. Excel needs one script launch versus a 5.5 mean of 3.2; Word needs one in both generations. PowerPoint is an exception to a simple fewer-tokens/fewer-retries explanation: its 6.1 run uses 5.70 million total tokens versus the 5.5 application mean of 5.10 million, and three script launches versus 2.6, while still finishing faster. Its low USD cost is therefore strongly price-driven.',
        f'Native provides a second counterexample to universal token efficiency: across the same three applications its total-token mean rises from {nativecost["gpt-5.5"]["mean_total_tokens"]/1e6:.2f} to {nativecost["gpt-6.1-sol"]["mean_total_tokens"]/1e6:.2f} million, while estimated cost falls from ${nativecost["gpt-5.5"]["mean_total_usd"]:.3f} to ${nativecost["gpt-6.1-sol"]["mean_total_usd"]:.3f}. These native cohorts include documented testcase variants and are an application-matched illustration rather than the exact-content AGTA comparison above.',
        'The logs change CLI version from 0.142.0-alpha.6 to 0.160.1, direct tool calls to exec wrappers, and exposed authoring-help text; generated scripts also differ. No explicit compacted record occurs in the 19 matched AGTA tasks. None exceeds the long-context pricing threshold, and recorded cache writes are zero. These checks rule out those recorded cost-accounting explanations, but do not isolate the effects of framework changes, lower reasoning effort, backend latency or sampling variability. One 6.1 run per application is insufficient to attribute all runtime gains to the model itself.'],
        'tables':[(['Metric / equal-app mean','GPT-5.5 medium','GPT-6.1 Sol light','Change'],measurerows),
                  (['Recorded token usage','Applied price rates','Mean USD','Interpretation'],crossrows),
                  (['Application','Model','n','Mean min','Exploration min','Launches','Total tokens M','Evidence'],appgaprows)],
        'figs':[('model-gap-cost-decomposition','Cross-price bars keep recorded token usage fixed. Dotted bars are hypothetical repricings; the first and last bars use each recorded model\'s own current Standard API rates. Prices and usage together explain the accounting difference; these bars do not simulate agent behavior.')],
        'downloads':[('data/model_gap_analysis.json','Download the full price-versus-usage investigation'),('data/model_gap_sessions.csv','Download session measurements and phase receipts'),('data/model_gap_applications.csv','Download per-application investigation data'),('data/model_gap_counterfactuals.csv','Download cross-price counterfactuals')]})
    sens=[]
    for c in data['comparisons'][:6]:
        ci=c['bootstrap_difference_ci'];sens.append([c['label'],str(c['left_n'])+'/'+str(c['right_n']),num(c['left_mean']),num(c['right_mean']),f'{c["change_pct"]:+.1f}%',f'{ci[0]:.2f} to {ci[1]:.2f}'])
    clean=data['ai_only_without_known_bypasses']
    result.append({'id':'sensitivity','title':'Sensitivity checks and testcase comparability','paragraphs':[f'Identical captured testcase content retains 27 native and 39 MCP tasks. The equal-application MCP reduction remains about 55%. Reintroducing the superseded Paint result retains the direction of the main finding. These checks support the observed setup difference, although they do not eliminate other collection confounds.',
    'The baseline AI-only/native bootstrap difference includes zero; a lower AI-only point estimate should not be stated as a settled performance advantage. The AI-only/MCP difference remains positive in this descriptive resampling. Singleton application cells stay fixed, so these intervals omit unobserved variation.',
    f'Removing the three known AI-only COM bypasses leaves {clean["n"]} tasks with a pooled mean of {clean["minutes"]["mean"]:.2f} minutes. Remaining tasks have not been fully route-certified; this restriction changes application weights and should not replace the three-application primary comparison.',
    'Newer model timing differences have mostly one observation per application/setup, so within-cell repeat variability cannot be estimated. The differing Luna/Sol families and low/medium effort settings further limit causal interpretation.'],
    'tables':[(['Equal-app comparison','Left/right n','Left min','Right min','Right change','95% bootstrap difference min'],sens)],'figs':[]})
    auditrows=[[f'<a href="evidence.html#{a["run_id"]}">{a["run_id"]}</a>',esc(a['reason'])] for a in data['route_audits']]
    result.append({'id':'audit','title':'Observed passes versus GUI-route acceptance','paragraphs':['Known route problems are listed separately from measured task completion. They explain why failed folder labels or five-pass console summaries cannot be used alone as the thesis acceptance criterion. The review is focused, not a full external validation of every generated script.','Three of nine AI-only tasks have explicit Office COM action bypasses in the supplied scripts. A native Notepad task contains direct file/PDF creation recovery. Framework policy and cleanup receipts offer stronger internal structure, while their flags still do not establish independent end-to-end acceptance.'],
                   'tables':[(['Run','Source-backed route problem'],auditrows)],'figs':[]})
    return cards,result

def overview(data,cards,ss):
    content=cards+'<nav>'+''.join(f'<a href="#{s["id"]}">{esc(s["title"].split(":")[0])}</a>' for s in ss)+'</nav>'
    for s in ss:
        content+=f'<section id="{s["id"]}"><h2>{esc(s["title"])}</h2>'+''.join('<p>'+esc(p)+'</p>' for p in s['paragraphs'])
        if s.get('fig_first'):
            for name,caption in s['figs']:content+=figure(name,caption)
        for h,rows in s['tables']:content+=table(h,rows)
        if 'progress_apps' in s:
            content+=f'<div class="controls"><label for="{s["id"]}-app">Application </label><select class="progress-picker" id="{s["id"]}-app" data-progress-picker="{s["id"]}">'
            content+=''.join(f'<option value="{esc(key)}">{esc(label)}</option>' for key,label in s['progress_apps'])
            content+='<option value="each">Show all charts</option></select><a href="data/progress_curves.csv" download>Download curve data</a></div>'
            for (app,_),(name,caption) in zip(s['progress_apps'],s['figs']):
                content+=f'<div class="progress-frame" data-progress-view="{s["id"]}" data-progress-app="{esc(app)}"'+(' hidden' if app!='all' else '')+'>'+figure(name,caption)+'</div>'
            content+='<noscript><style>.progress-frame[hidden]{display:block!important}</style></noscript>'
        elif not s.get('fig_first'):
            for name,caption in s['figs']:content+=figure(name,caption)
        for href,label in s.get('downloads',[]):content+=f'<p><a href="{esc(href)}" download>{esc(label)}</a></p>'
        content+='</section>'
    rows=''
    for r in ordered_runs(data['runs']):
        rows+=f'<tr data-bucket="{r["bucket"]}" data-setup="{r["setup"]}" data-model="{r["model"]}" data-app="{r["app"]}" data-status="{"pass" if r["success"] else "partial"}"><td>{link(r)}</td><td>{esc(r["bucket"])}<br>{esc(r["setup"])}</td><td>{esc(r["model"])}</td><td>{esc(r["app"])}</td><td>{num(r["minutes"])}</td><td>{"5/5 observed" if r["success"] else num(r["best_passed_steps"],0)+" / 5 observed"}</td><td>{num(r["total_tokens"]/1e6 if r["total_tokens"] else None)}</td><td>{esc(r["folder"])}</td><td>{"Included" if r["included"] else esc(r["exclusion_reason"])}</td></tr>'
    controls='<div class="controls">'
    for key,title in [('bucket','Corpus'),('setup','Setup'),('model','Model'),('app','Application')]:
        values=sorted({r[key] for r in data['runs']},key=model_rank if key=='model' else None)
        controls+=f'<label>{title} <select id="filter-{key}"><option value="">All</option>'+''.join(f'<option>{esc(v)}</option>' for v in values)+'</select></label>'
    controls+=' <label>Outcome <select id="filter-status"><option value="">All</option><option value="pass">Observed 5/5</option><option value="partial">Partial / failed</option></select></label><input id="search" placeholder="Search folder or run"><span id="row-count"></span></div>'
    content+='<section id="sessions"><h2>Every discovered session</h2><p>Filters change the inventory table only; analysis figures and summary tables above retain their stated samples.</p>'+controls+'<div class="scroll"><table id="runs"><thead><tr><th>Evidence</th><th>Corpus / setup</th><th>Recorded model</th><th>App</th><th>Minutes</th><th>Outcome</th><th>Tokens M</th><th>Folder</th><th>Inclusion</th></tr></thead><tbody>'+rows+'</tbody></table></div></section>'
    script='''const keys=['bucket','setup','model','app','status'];function filter(){let n=0;document.querySelectorAll('#runs tbody tr').forEach(r=>{const ok=keys.every(k=>!document.getElementById('filter-'+k).value||r.dataset[k]===document.getElementById('filter-'+k).value)&&r.textContent.toLowerCase().includes(document.getElementById('search').value.toLowerCase());r.hidden=!ok;if(ok)n++;});document.getElementById('row-count').textContent=n+' sessions';}keys.forEach(k=>document.getElementById('filter-'+k).addEventListener('change',filter));document.getElementById('search').addEventListener('input',filter);filter();'''
    script+='''document.querySelectorAll('.progress-picker').forEach(select=>{function show(){document.querySelectorAll('[data-progress-view="'+select.dataset.progressPicker+'"]').forEach(frame=>{frame.hidden=select.value!=='each'&&frame.dataset.progressApp!==select.value;});}select.addEventListener('change',show);show();});'''
    return page('Native, MCP, AI-only and newer-model experiments','A refreshed analysis of authoring runtime, observed outcomes, partial failures and resource use. The main results are native and MCP; AI-only and the low-effort model batch have separate comparisons.',content,script)

def evidence(data):
    content='<section><h2>Evidence conventions</h2><p>Each entry links to the original supplied log and reports its SHA-256 fingerprint. L-number references identify original JSONL records. Runtime excerpts are captured tool outputs; assistant final messages remain labeled claims. Supplied code is diagnostic data and is never executed.</p></section>'
    root=Path(data['source_root']);audit={a['run_id']:a for a in data['route_audits']}
    for r in ordered_runs(data['runs']):
        p=root/r['file'];content+=f'<section id="{r["id"]}"><h2>{r["id"]} · {esc(r["app"])} · {esc(r["model"])} · {esc(r["setup"])}</h2><p><code>{esc(r["file"])}</code><br><a href="{p.as_uri()}">Original session log</a> · <a href="report.html#sessions">Return to inventory</a></p><p>SHA-256: <code>{r["sha256"]}</code></p>'
        content+=table(['Metric','Observed value'],[['Inclusion',esc(r['exclusion_reason'] or 'included')],['Authoring duration',num(r['minutes'])+' minutes'],['Outcome',esc(r['status'])],['Best step count',num(r['best_passed_steps'],0)],['Tokens',num(r['total_tokens'],0)],['Task turn ID',esc(r['task_id'])],['Recorded effort',esc(', '.join(r['efforts']))],['Terminal event',esc(r['terminal'])+f' · L{r["end_line"]}'],['Flags',esc('; '.join(r['flags']) or 'none')]])
        if r['testcase']:
            content+='<details><summary>Captured testcase · L'+str(r['testcase']['line'])+'</summary>'+table(['Step','Action','Data','Expected result'],[[str(i),esc(x['Action']),esc(x.get('Data','')),esc(x['Expected Result'])] for i,x in enumerate(r['testcase']['rows'],1)])+'</details>'
        obs=r['observations'];content+='<details><summary>Observed result timeline ('+str(len(obs))+' records)</summary>'+table(['Log record','Minutes','Passing steps','Failed/skipped steps'],[[f'L{o["line"]}',num(o['minutes']),esc(', '.join(str(k) for k,v in o['states'].items() if v=='PASS')),esc(', '.join(f'{k}: {v}' for k,v in o['states'].items() if v!='PASS'))] for o in obs])+'</details>'
        # Keep final outcome and first partial/error for concise auditability.
        ev=r['evidence'];selected=ev[:1]+([ev[-1]] if len(ev)>1 else [])
        for e in selected:content+=f'<details><summary>{esc(e["kind"])} · L{e["line"]}</summary><pre>{esc(e["text"])}</pre></details>'
        if r['final']:content+=f'<details><summary>Assistant final claim · L{r["final"]["line"]} (not outcome evidence)</summary><pre>{esc(r["final"]["text"])}</pre></details>'
        if r['id'] in audit:
            a=audit[r['id']];content+='<div class="note caution">'+esc(a['reason'])+'</div><p><a href="'+Path(a['file']).as_uri()+'">Audit source</a></p>'
            for e in a['excerpts']:content+=f'<details><summary>Route audit source · L{e["line"]}</summary><pre>{esc(e["text"])}</pre></details>'
        if r['exploration_failures']:content+='<details><summary>Unique exploration failure receipts</summary>'+table(['Record','Command','Type','Message'],[[str(e['line']),esc(e['command']),esc(e['type']),esc(e['message'])] for e in r['exploration_failures']])+'</details>'
        content+='</section>'
    return page('Per-run source evidence',f'All {len(data["runs"])} discovered logs, including partial failures, excluded/misplaced inputs and route-audit excerpts.',content)

def pdf(data,out,ss):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak,KeepTogether
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    dest=out.parent.parent/'output'/'pdf';dest.mkdir(parents=True,exist_ok=True);path=dest/'experiment-analysis-2026-10-07.pdf'
    for n,f in [('Arial','arial.ttf'),('Arial-Bold','arialbd.ttf')]:pdfmetrics.registerFont(TTFont(n,str(Path('C:/Windows/Fonts')/f)))
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='BodyCustom',fontName='Arial',fontSize=9.4,leading=14,spaceAfter=9,textColor=colors.HexColor('#243640')))
    styles.add(ParagraphStyle(name='TitleCustom',fontName='Arial-Bold',fontSize=28,leading=33,spaceAfter=18,textColor=colors.HexColor('#216956')))
    styles.add(ParagraphStyle(name='HeadingCustom',fontName='Arial-Bold',fontSize=17,leading=22,spaceAfter=14,keepWithNext=True,textColor=colors.HexColor('#216956')))
    styles.add(ParagraphStyle(name='MethodHeadingCustom',fontName='Arial-Bold',fontSize=13.5,leading=18,spaceAfter=8,keepWithNext=True,textColor=colors.HexColor('#216956')))
    styles.add(ParagraphStyle(name='SmallCustom',fontName='Arial',fontSize=7.2,leading=10,spaceAfter=7,textColor=colors.HexColor('#536572')))
    styles.add(ParagraphStyle(name='CellCustom',fontName='Arial',fontSize=7,leading=9))
    styles.add(ParagraphStyle(name='HeadCellCustom',fontName='Arial-Bold',fontSize=7,leading=9,textColor=colors.white))
    width=A4[0]-84;story=[]
    def para(s,style='BodyCustom'):
        clean=re.sub('<[^>]+>','',s);clean=html.unescape(clean).replace('→','to').replace('·',' / ').replace('−','-').replace('–','-').replace('—','-')
        return Paragraph(esc(clean),styles[style])
    def tbl(head,rows):
        n=len(head);weights=[1]*n
        if n==2:weights=[1,4]
        if n==3:weights=[.7,2.5,3]
        if n>=7:weights[0]=1.8
        if n>=7 and 'Evidence' in head[-1]:weights[-1]=1.5
        widths=[width*w/sum(weights) for w in weights]
        t=Table([[para(h,'HeadCellCustom') for h in head]]+[[para(str(c),'CellCustom') for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#287964')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f0f5f4')]),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#287964'))]));return t
    story+=[para('THESIS EXPERIMENT ANALYSIS / UPDATED '+REPORT_DATE.upper(),'SmallCustom'),para('Native, MCP, AI-only and newer-model experiments','TitleCustom'),para('Runtime, observed outcomes, partial failures and resource use'),Spacer(1,10)]
    for p in ss[0]['paragraphs']:story.append(para(p))
    included=[r for r in data['runs'] if r['included']];counts=Counter(r['bucket'] for r in included)
    story+=[Spacer(1,10),para('Source: '+data['source_root'],'SmallCustom'),para(f'{len(included)} included tasks from {len(data["runs"])} logs. Main comparison: {counts["native"]} native and {counts["mcp"]} MCP tasks. AI-only: {counts["aionly"]} relevant tasks. New Codex: {counts["newcodex"]} tasks. Old and CLI folders excluded.','SmallCustom'),para('Companion HTML provides interactive inventory filters, full per-run source evidence and CSV/JSON exports. Run identifiers in this PDF resolve to the same identifiers in evidence.html.','SmallCustom')]
    for s in ss[1:]:
        story+=[PageBreak(),para(s['title'],'HeadingCustom')]
        for p in s['paragraphs']:story.append(para(p))
        for table_index,(head,rows) in enumerate(s['tables']):
            if s['id']=='why61' and table_index==0:
                story+=[PageBreak(),para(s['title']+' - measurements','HeadingCustom')]
            if s['id']=='cost-details' and table_index==1:
                story+=[PageBreak(),para('Session cost breakdown','HeadingCustom'),
                        para('Session means for each complete cohort; supplemental 5.6 Sol and 6 Sol cover Excel only. All failed attempts are included. Spent per success divides actual batch cost by observed five-pass outputs.','SmallCustom')]
            story+=[tbl(head,rows),Spacer(1,11)]
        pdf_figs=s.get('pdf_figs',s['figs'])
        if pdf_figs and s['id'] in ['models','sol','failures','resources','costs','why61']:
            story+=[PageBreak(),para(s['title']+' - figures','HeadingCustom')]
        for figure_index,(name,caption) in enumerate(pdf_figs):
            if ('progress_apps' in s or 'pdf_figs' in s) and figure_index>0 and figure_index%2==0:
                story+=[PageBreak(),para(s.get('continuation',s['title']+' - figures'),'HeadingCustom')]
            img=Image(str(out/'figures'/(name+'.png')));ratio=img.imageHeight/img.imageWidth
            height=min(width*ratio,300);iw=height/ratio
            story.append(KeepTogether([Image(str(out/'figures'/(name+'.png')),width=iw,height=height),Spacer(1,5),para(caption,'SmallCustom')]))
            if figure_index<len(pdf_figs)-1:story.append(Spacer(1,10))
    story+=[PageBreak(),para('Measurement definitions and limitations','HeadingCustom')]
    for title,body in methodology():story+=[para(title,'MethodHeadingCustom'),para(body)]
    story+=[PageBreak(),para('Appendix: all newer-model sessions','HeadingCustom')]
    new=ordered_runs([r for r in data['runs'] if r['bucket']=='newcodex'])
    story.append(tbl(['Run','Model','Setup','App','Minutes','Observed pass'],[[r['id'],model(r['model']),r['setup'],r['app'],num(r['minutes']),'5/5' if r['success'] else num(r['best_passed_steps'],0)+'/5'] for r in new]))
    story+=[Spacer(1,14),para('Evidence source and reproducibility','HeadingCustom'),para(f'All input fingerprints, record line references, tasks, counters, testcase hashes and result observations are preserved in data/metrics.json. data/sessions.csv contains all {len(data["runs"])} logs with inclusion flags; the other CSVs contain the setup/application summaries and comparisons. Route audit excerpts are included in evidence.html.','BodyCustom')]
    def footer(c,doc):
        c.saveState();c.setStrokeColor(colors.HexColor('#d1dddd'));c.line(42,40,A4[0]-42,40);c.setFont('Arial',7);c.setFillColor(colors.HexColor('#536572'));c.drawString(42,28,'Experiment analysis / '+REPORT_DATE);c.drawRightString(A4[0]-42,28,f'{doc.page}');c.restoreState()
    SimpleDocTemplate(str(path),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=52,title='Thesis experiment analysis - '+REPORT_DATE,author='Experiment analysis').build(story,onFirstPage=footer,onLaterPages=footer)
    return path

def build(data,out):
    add_exploration_timings(data,out)
    add_cost_analysis(data,out)
    add_model_gap(data,out)
    audits(data);figures(data,out);cost_figures(data,out);model_gap_figure(data,out);cards,ss=sections(data)
    (out/'report.html').write_text(overview(data,cards,ss),encoding='utf-8')
    (out/'evidence.html').write_text(evidence(data),encoding='utf-8')
    meth='<section><h2>Definitions</h2>'+''.join(f'<h3>{esc(t)}</h3><p>{esc(b)}</p>' for t,b in methodology())+'</section>'
    meth+='<section><h2>Missing-log inventory</h2>'+table(['Folder','Available files'],[[esc(i['folder']),esc(', '.join(i['files']) or 'empty folder')] for i in data['inventory'] if not i['log_count']])+'</section>'
    meth+='<section><h2>Captured testcase variants</h2>'
    for v in data['testcase_variants']:
        meth+='<details><summary>'+esc(v['app'])+f' · {len(v["variants"])} captured variants</summary>'
        for variant in v['variants']:meth+='<p><code>'+variant['sha256']+'</code><br>'+esc(', '.join(variant['run_ids']))+'</p>'+table(['Action','Data','Expected result'],[[esc(r['Action']),esc(r.get('Data','')),esc(r['Expected Result'])] for r in variant['rows']])
        meth+='</details>'
    meth+='</section>';(out/'methodology.html').write_text(page('Methodology and comparability','Definitions, exclusions, bounded observations and all captured testcase variants.',meth),encoding='utf-8')
    (out/'data'/'metrics.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    write_csv(out/'data'/'route_audits.csv',[{'run_id':a['run_id'],'file':a['file'],'reason':a['reason']} for a in data['route_audits']])
    pdfpath=pdf(data,out,ss)
    # Bundle the offline companion and place the PDF alongside it for sharing.
    import shutil
    shutil.copy2(pdfpath,out/'experiment-analysis-2026-10-07.pdf')
    for p in out.glob('*.html'):
        s=p.read_text(encoding='utf-8').replace('../../../output/pdf/experiment-analysis-2026-10-07.pdf','experiment-analysis-2026-10-07.pdf');p.write_text(s,encoding='utf-8')
    with zipfile.ZipFile(out.parent/'experiment-analysis-2026-10-07.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in out.rglob('*'):
            if p.is_file():z.write(p,str(p.relative_to(out)))
    print(json.dumps({'report':str(out/'report.html'),'pdf':str(pdfpath),'route_audits':len(data['route_audits']),'figures':len(list((out/'figures').glob('*.svg')))}))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();data=json.loads((a.output/'data'/'metrics.json').read_text(encoding='utf-8'));build(data,a.output)
