"""Fill Paper 5's bibliography from the four series papers, in first-citation order.

  python fill_bib.py
Takes each \\bibitem from p1-p4 paper.tex by key and writes the cited ones between
\\begin{thebibliography} and \\end{thebibliography}. Re-run after changing citations.
"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRCS = ["p1_quantum", "p2_agentic", "p3_qagentic", "p4_forecast"]
items = {}
for s in SRCS:
    t = (HERE.parent / s / "paper.tex").read_text(encoding="utf-8")
    bib = t.split(r"\begin{thebibliography}{00}")[1].split(r"\end{thebibliography}")[0]
    for m in re.finditer(r"\\bibitem\{([^}]+)\}(.*?)(?=\\bibitem\{|\Z)", bib, re.S):
        items.setdefault(m.group(1), m.group(0).strip())
p = HERE / "paper.tex"
t = p.read_text(encoding="utf-8")
head, rest = t.split(r"\begin{thebibliography}{00}")
_, tail = rest.split(r"\end{thebibliography}")
order = []
for c in re.findall(r"\\cite\{([^}]+)\}", head):
    for k in (x.strip() for x in c.split(",")):
        if k not in order:
            order.append(k)
missing = [k for k in order if k not in items]
if missing:
    raise SystemExit(f"no bibitem for {missing}")
p.write_text(head + "\\begin{thebibliography}{00}\n" + "\n".join(items[k] for k in order)
             + "\n\\end{thebibliography}" + tail, encoding="utf-8")
print(f"{len(order)} references written")
