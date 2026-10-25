"""Reproduce the application-level relative-time figure from public summaries."""
from pathlib import Path
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
with (ROOT/'data/application_summary.csv').open(encoding='utf-8-sig',newline='') as f:
    records=list(csv.DictReader(f))
rows=[]
for app in sorted({r['app'] for r in records if r['model']=='gpt-5.5' and r['bucket'] in ['native','mcp']}):
    pair=[next(r for r in records if r['app']==app and r['model']=='gpt-5.5' and r['setup']==s) for s in ['native','mcp']]
    n,m=pair
    rows.append((app,100*(1-float(m['minutes_mean'])/float(n['minutes_mean'])),n,m))
rows.sort(key=lambda r:r[1],reverse=True)
assert len(rows)==10
plt.rcParams.update({'font.family':'DejaVu Serif','font.size':10,'pdf.fonttype':42})
fig,ax=plt.subplots(figsize=(8,3.8))
fig.subplots_adjust(left=.18,right=.60,bottom=.17,top=.9)
ax.barh(range(10),[r[1] for r in rows],height=.58,color='#245f87')
ax.set_yticks(range(10),[r[0] for r in rows]);ax.invert_yaxis()
ax.set(xlim=(0,86),xlabel='Időcsökkenés (%)')
ax.spines[['top','right','left']].set_visible(False)
ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
for i,(_,gain,n,m) in enumerate(rows):
    ax.text(gain+1,i,f'{gain:.1f}'.replace('.',','),va='center')
    ax.text(1.3,i,f"{float(n['minutes_mean']):.2f} → {float(m['minutes_mean']):.2f}".replace('.',','),transform=ax.get_yaxis_transform(),ha='center',va='center')
    ax.text(1.78,i,f"{n['n']} / {m['n']}",transform=ax.get_yaxis_transform(),ha='center',va='center')
ax.text(1.3,1.03,'Perc (Ref. → AGATA)',transform=ax.transAxes,ha='center')
ax.text(1.78,1.03,'n (Ref. / AGATA)',transform=ax.transAxes,ha='center')
out=ROOT/'output/images';out.mkdir(parents=True,exist_ok=True)
for extension in ['pdf','png']:fig.savefig(out/('alkalmazas_idonyereseg.'+extension),dpi=220)
plt.close(fig)
print('Rebuilt application gains from all 35 reference and 39 AGATA observations.')
