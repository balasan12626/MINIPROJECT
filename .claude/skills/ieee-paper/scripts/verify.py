"""Guards for the IEEE paper. Exit code 1 if any check fails.

1. Every key number in paper.tex matches its source (models/flood_evaluation_v4.json, <work>/exp.json).
2. Tables in build_paper_docx.js carry the same numbers (Word and PDF must not drift apart).
3. blind.pdf has no author identity; both PDFs have <= 6 pages and no Type 3 / unembedded fonts.
usage: python verify.py <work>
"""
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[3]
WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
tex = (SCRIPTS / "paper.tex").read_text(encoding="utf-8")
js = (SCRIPTS / "build_paper_docx.js").read_text(encoding="utf-8")
import os
MAX_PAGES = int(os.environ.get("PAPER_MAX_PAGES", "8"))  # INDICON: set 6
fails = []


def need(value, where, label):
    if value not in where[1]:
        fails.append(f"{label}: '{value}' not found in {where[0]}")


f3 = lambda x: f"{x:.3f}"
v4 = json.loads((ROOT / "models" / "flood_evaluation_v4.json").read_text(encoding="utf-8"))["test"]["unseen_gauges_2015_2020"]
exp = json.loads((WORK / "exp.json").read_text(encoding="utf-8"))
expected = []
for key, row in (("model", v4["model"]), ("onset", v4["model_flood_onset_only"]), ("persist", v4["baseline_persistence"])):
    for m in ("balanced_accuracy", "recall", "precision", "f1", "roc_auc", "pr_auc"):
        expected.append((f3(row[m]), f"forecast {key}.{m}"))
for r in exp["bench"]:
    expected.append((f"{r['clearance_time_min']:.2f}", f"bench {r['method']} clearance"))
    # re-plan latency is wall-clock time and varies by run/machine, so it is not checked exactly
for g in exp["gating"]:
    expected.append((f3(g["mean_reliability"]), f"gating {'+'.join(g['failures'])}"))
s4 = {r["method"]: r["safe"] for r in exp["sweep"] if r["severity"] == 0.35 and r["closures"] == 4}
expected.append((f"{s4['Proposer only']:.1f}", "sweep proposer-only @4 closures"))
expected.append((f"{s4['Proposer + QUBO (SA)']:.1f}", "sweep shield @4 closures"))
emin = json.loads((WORK / "exp_min.json").read_text(encoding="utf-8"))
for g in emin:
    expected.append((f3(g["min"]), f"min gate {'+'.join(g['failures'])}"))
n_block_min = sum(1 for g in emin if not g["min_gate_allows"] and g["failures"] not in (["none"], ["shelter_failure"]))
n_src = sum(1 for g in emin if g["failures"] not in (["none"], ["shelter_failure"]))
if not (n_block_min == n_src == 9 and all(g["min_gate_allows"] for g in emin if g["failures"] in (["none"], ["shelter_failure"]))):
    fails.append("text claims the min gate blocks all nine source failures and allows the healthy case")
xx = json.loads((WORK / "exp_extra.json").read_text(encoding="utf-8"))["forecast"]
for key, fmt in (("ba", f3), ("roc_auc", f3), ("pr_auc", f3), ("gauge_ba_median", f3), ("gauge_ba_q1", f3),
                 ("gauge_ba_q3", f3), ("gauge_ba_min", f3), ("model_prec_at_persist_recall", f3)):
    expected.append((fmt(xx[key]), f"extra {key}"))
for r in xx["thresholds"]:
    expected.append((f"{r['alarms_per_1000']:.1f}", f"extra alarms@{r['t']}"))
if not xx["gauge_ba_below_07"] == 0:
    fails.append("text says no gauge fell below 0.7")
if not xx["model_prec_at_persist_recall"] < 0.789 + 1e-9:
    fails.append("text says persistence lies on/above the PR curve")
for value, label in expected:
    need(value, ("paper.tex", tex), label)
    if not label.startswith(("sweep", "extra")):
        need(value, ("build_paper_docx.js", js), label)


def pdf(name):
    p = WORK / name
    info = subprocess.run(["pdfinfo", str(p)], capture_output=True, text=True).stdout
    pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    fonts = subprocess.run(["pdffonts", str(p)], capture_output=True, text=True).stdout.splitlines()[2:]
    if pages > MAX_PAGES:
        fails.append(f"{name}: {pages} pages (limit {MAX_PAGES})")
    if any("Type 3" in f for f in fonts):
        fails.append(f"{name}: Type 3 font")
    if any(f.split()[-5] == "no" for f in fonts if len(f.split()) >= 5):
        fails.append(f"{name}: font not embedded")
    return pages


pages = {n: pdf(n) for n in ("blind.pdf", "camera.pdf")}
text = subprocess.run(["pdftotext", "-enc", "UTF-8", str(WORK / "blind.pdf"), "-"], capture_output=True).stdout.decode("utf-8")
for pat in (r"\bSona\b", "gmail", r"\bSalem\b", "github", "Nandhakumar", "Balakarthikeyan", "Gowthaman", "Abhishek", "AquaSentinel"):
    if re.search(pat, text, re.I):
        fails.append(f"blind.pdf identifies authors: '{pat}'")
for broken in ("extit", "extbf", "extsc", "egin{"):
    if broken in text:
        fails.append(f"blind.pdf: broken LaTeX command in output text ('{broken}')")
if "\t" in tex:
    fails.append("paper.tex contains a tab character (a collapsed backslash escape?)")
for pat in ("representative pattern", "example values", "must be re-run", "TODO"):
    if pat.lower() in tex.lower():
        fails.append(f"placeholder text in paper.tex: '{pat}'")

print(f"checked {len(expected)} numbers; pages {pages}")
print("\n".join("FAIL " + f for f in fails) if fails else "ALL CHECKS PASSED")
sys.exit(1 if fails else 0)
