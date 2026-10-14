"""Citation audit for the four papers: uncited, missing, duplicate references and
first-citation order (IEEE numbers references in order of first citation)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {"P1": ROOT / "series/p1_quantum/paper.tex", "P2": ROOT / "series/p2_agentic/paper.tex",
         "P3": ROOT / "series/p3_qagentic/paper.tex", "P4": ROOT / "scripts/paper.tex",
         "P4F": ROOT / "series/p4_forecast/paper.tex",
         "P5": ROOT / "series/p5_merged/paper.tex"}
ok = True
for name, f in FILES.items():
    t = f.read_text(encoding="utf-8")
    body = t.split(r"\begin{thebibliography}")[0]
    bib = re.findall(r"\\bibitem\{([^}]+)\}", t)
    order = []
    for c in re.findall(r"\\cite\{([^}]+)\}", body):
        for k in (x.strip() for x in c.split(",")):
            if k not in order:
                order.append(k)
    uncited = [b for b in bib if b not in order]
    missing = [c for c in order if c not in bib]
    dups = sorted({b for b in bib if bib.count(b) > 1})
    out_of_order = [k for i, k in enumerate(order) if i < len(bib) and bib[i] != k]
    print(f"{name}: {len(bib)} refs, {len(order)} cited | uncited {uncited} | missing {missing} | dups {dups}")
    print(f"     first-citation order matches bibliography: {not out_of_order}"
          + ("" if not out_of_order else f" (first mismatch at {order.index(out_of_order[0]) + 1}: cited {out_of_order[0]}, listed {bib[order.index(out_of_order[0])]})"))
    ok &= not (uncited or missing or dups or out_of_order)
    labels = re.findall(r"\\label\{((?:fig|tab|eq|alg):[^}]+)\}", t)
    refs = set(re.findall(r"\\ref\{([^}]+)\}", t))
    unref = [lab for lab in labels if lab not in refs]
    print(f"     floats/equations never referenced in text: {unref or 'none'}")
    ok &= not [lab for lab in unref if not lab.startswith("eq:")]  # an unreferenced equation is allowed
print("REFERENCES OK" if ok else "REFERENCE ISSUES FOUND")
