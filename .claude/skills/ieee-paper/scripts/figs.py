"""Fig. 2 (safe-route rate vs closures) from <work>/exp.json -> <work>/fig_safety.pdf."""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                     "pdf.fonttype": 42, "ps.fonttype": 42})  # Type 42 = no Type 3 fonts (IEEE)
d = json.loads((WORK / "exp.json").read_text(encoding="utf-8"))
rows = [r for r in d["sweep"] if r["severity"] == 0.35]
meths = ["Static shortest path", "Flood-aware A*", "Proposer only", "Proposer + QUBO (SA)"]
labels = ["Static shortest path", "Flood-aware A*", "Policy proposer (no shield)", "Proposer + shield"]
closures, w = [0, 2, 4], 0.2
fig, ax = plt.subplots(figsize=(3.45, 2.15))
hatch, col = ["", "//", "..", "xx"], ["0.85", "0.55", "1.0", "0.25"]
for i, (m, label) in enumerate(zip(meths, labels)):
    v = [next(r["safe"] for r in rows if r["method"] == m and r["closures"] == c) for c in closures]
    ax.bar([x + (i - 1.5) * w for x in range(3)], v, w, label=label, color=col[i], edgecolor="black",
           linewidth=0.5, hatch=hatch[i])
ax.set_xticks(range(3))
ax.set_xticklabels([f"{c} initial closures" for c in closures])
ax.set_ylim(60, 102)
ax.set_ylabel("Safe routes (%)")
ax.legend(fontsize=6.3, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 1.0), frameon=False)
ax.grid(axis="y", linewidth=0.3)
fig.tight_layout(pad=0.3)
fig.savefig(WORK / "fig_safety.pdf")
print("saved", WORK / "fig_safety.pdf")
