"""Publication-friendly SVG/PNG figures; no network or browser dependency."""
from pathlib import Path
import math
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

COLORS = {"native": "#2864ad", "cli": "#c35b32"}
LABELS = {"native": "Native (baseline)", "cli": "CLI + framework"}


def save(fig, out, name):
    fig.tight_layout()
    fig.savefig(out / f"{name}.svg", bbox_inches="tight", metadata={"Date": None})
    fig.savefig(out / f"{name}.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def progress_curve(run, times):
    milestones = [p["minutes"] for p in run["first_pass"].values()]
    return np.array([sum(t >= point for point in milestones) for t in times])


def strip(ax, runs, metric, scale, title, label):
    for j, group in enumerate(LABELS):
        sample = [r for r in runs if r["group"] == group]
        values = [r[metric]/scale for r in sample]
        y = 1-j
        ax.scatter(values, np.linspace(y-.2,y+.2,len(sample)), s=32, alpha=.65,
                   color=COLORS[group], edgecolor="white", lw=.6, zorder=3)
        avg = mean(values)
        ax.plot([avg,avg],[y-.31,y+.31],color=COLORS[group],lw=3)
        ax.text(avg,y-.43,f"mean {avg:,.2f}",ha="center",fontsize=9)
    ax.set(yticks=[1,0],yticklabels=list(LABELS.values()),ylim=(-.65,1.5),xlabel=label)
    ax.set_xlim(left=0,right=max(r[metric]/scale for r in runs)*1.13)
    ax.set_title(title,loc="left",weight="bold",pad=12)
    ax.grid(axis="x",alpha=.16)
    ax.tick_params(axis="y",length=0)


def build_figures(runs, out):
    out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,
                         "axes.spines.right":False,"axes.spines.left":False,"axes.edgecolor":"#cbd4e0",
                         "figure.facecolor":"white","axes.facecolor":"white","svg.fonttype":"none",
                         "svg.hashsalt":"native-framework-2026-10-01","text.color":"#1d3048"})
    apps = sorted({r["app"] for r in runs})
    fig,ax=plt.subplots(figsize=(11.5,7.6))
    for a,app in enumerate(apps):
        for group,offset in [("native",-.17),("cli",.17)]:
            sample=[r for r in runs if r["app"]==app and r["group"]==group]
            values=[r["minutes"] for r in sample]
            y=a+offset
            ax.plot([min(values),max(values)],[y,y],color=COLORS[group],lw=1,alpha=.4)
            ax.scatter(values,np.linspace(y-.06,y+.06,len(values)),color=COLORS[group],s=30,alpha=.55,zorder=3)
            ax.scatter(mean(values),y,marker="D",color=COLORS[group],s=65,edgecolor="white",zorder=4,
                       label=LABELS[group] if a==0 else None)
            ax.text(122,y,f"{mean(values):.1f}  (n={len(values)})",fontsize=9,va="center",color=COLORS[group])
    ax.set(yticks=range(len(apps)),yticklabels=apps,xlabel="Authoring session duration (minutes)",xlim=(0,146))
    ax.invert_yaxis();ax.set_xticks(range(0,121,20));ax.grid(axis="x",alpha=.15)
    ax.legend(loc="lower left",bbox_to_anchor=(0,1.015),ncol=2,frameon=False)
    ax.text(122,-.75,"Mean · sample size",fontsize=9)
    save(fig,out,"duration-by-app")

    fig,axes=plt.subplots(3,1,figsize=(11.5,8.2))
    for ax,args in zip(axes,[("total_tokens",1e6,"Total tokens","Millions of input + output tokens"),
                               ("uncached_input_tokens",1000,"Uncached input tokens","Thousands of input tokens, excluding cached input"),
                               ("output_tokens",1000,"Output tokens","Thousands of output tokens, including reasoning output")]):
        strip(ax,runs,*args)
    save(fig,out,"tokens")

    fig,axes=plt.subplots(3,1,figsize=(11.5,8.2))
    for ax,args in zip(axes,[("script_launches",1,"Generated-script launch requests","Tool calls that launch a recognized test script"),
                               ("patch_calls",1,"Patch tool calls","Includes initial creation, rejected patches and helper edits"),
                               ("shell_calls",1,"Shell tool calls","One call may contain multiple commands")]):
        strip(ax,runs,*args)
    save(fig,out,"authoring-effort")

    fig,ax=plt.subplots(figsize=(11.5,5.8))
    for offset,key,label,color in [(-.19,"minutes","Duration",COLORS["native"]),(.19,"total_tokens","Total tokens",COLORS["cli"])]:
        changes=[]
        for app in apps:
            avgs={g:mean(r[key] for r in runs if r["app"]==app and r["group"]==g) for g in LABELS}
            changes.append(100*(avgs['cli']/avgs['native']-1))
        ax.barh(np.arange(len(apps))+offset,changes,height=.34,label=label,color=color)
    ax.axvline(0,color="#24364d",lw=.9)
    ax.set(yticks=range(len(apps)),yticklabels=apps,xlabel="CLI + framework change relative to native mean (%)")
    ax.invert_yaxis();ax.grid(axis="x",alpha=.15);ax.legend(loc="lower right",frameon=False)
    save(fig,out,"tradeoff-by-app")

    for app in [None,*apps]:
        selected=[r for r in runs if app is None or r["app"]==app]
        horizon=max(20,math.ceil(max(r["minutes"] for r in selected)/10)*10)
        times=sorted({0,horizon,*[p['minutes'] for r in selected for p in r['first_pass'].values()]})
        fig,ax=plt.subplots(figsize=(11.5,5.3))
        for r in selected:
            line,=ax.step(times,progress_curve(r,times),where="post",color=COLORS[r['group']],alpha=.22,lw=1,
                         linestyle="--" if r['group']=='native' else "-")
            line.set_gid(r['id'])
        for group in LABELS:
            sample=[r for r in selected if r['group']==group]
            curve=np.mean([progress_curve(r,times) for r in sample],axis=0)
            ax.step(times,curve,where="post",lw=3.2,color=COLORS[group],
                    linestyle="--" if group=='native' else "-",label=f"{LABELS[group]} mean · n={len(sample)}")
        # Limit only the pooled view; retain every run in the means and keep
        # application-specific views at their full observed time range.
        display_end = 60 if app is None else horizon
        ax.set(xlim=(0,display_end),ylim=(-.12,5.3),yticks=range(6),xlabel="Minutes from session start",
               ylabel="Distinct steps with a recorded PASS")
        ax.legend(loc="lower right",frameon=True,facecolor="white",framealpha=1)
        ax.grid(alpha=.15)
        save(fig,out,"progress-"+(selected[0]['app_key'] if app else 'all'))

    fig,ax=plt.subplots(figsize=(11.5,4.8))
    from datetime import datetime
    for group in LABELS:
        sample=[r for r in runs if r['group']==group]
        ax.scatter([datetime.fromisoformat(r['start']) for r in sample],[r['minutes'] for r in sample],
                   s=44,color=COLORS[group],alpha=.75,label=LABELS[group],edgecolor="white")
    import matplotlib.dates as mdates
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    ax.set(xlabel="Session date (UTC)",ylabel="Authoring duration (minutes)")
    ax.legend(frameon=False);ax.grid(alpha=.15)
    save(fig,out,"collection-timeline")
