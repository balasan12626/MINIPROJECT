import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"font.family":"serif","font.serif":["Times New Roman"],"font.size":8,"pdf.fonttype":42,"ps.fonttype":42})
d=json.load(open("exp.json"))
rows=[r for r in d["sweep"] if r["severity"]==0.35]
meths=["Static shortest path","Flood-aware A*","Proposer only","Proposer + QUBO (SA)"]
labels=["Static shortest path","Flood-aware A*","Policy proposer (no shield)","Proposer + shield"]
cl=[0,2,4]; w=0.2
fig,ax=plt.subplots(figsize=(3.45,2.15))
hatch=["","//","..","xx"]; col=["0.85","0.55","1.0","0.25"]
for i,(m,l) in enumerate(zip(meths,labels)):
    v=[next(r["safe"] for r in rows if r["method"]==m and r["closures"]==c) for c in cl]
    b=ax.bar([x+(i-1.5)*w for x in range(3)],v,w,label=l,color=col[i],edgecolor="black",linewidth=0.5,hatch=hatch[i])
ax.set_xticks(range(3)); ax.set_xticklabels([f"{c} initial closures" for c in cl])
ax.set_ylim(60,102); ax.set_ylabel("Safe routes (%)")
ax.legend(fontsize=6.3,ncol=2,loc="lower center",bbox_to_anchor=(0.5,1.0),frameon=False)
ax.grid(axis="y",linewidth=0.3)
fig.tight_layout(pad=0.3); fig.savefig("fig_safety.pdf")
print("ok")
