"""Reorder \\bibitem entries into first-citation order (IEEE numbering). usage: reorder_refs.py <paper.tex>"""
import re
import sys
from pathlib import Path

f = Path(sys.argv[1])
t = f.read_text(encoding="utf-8")
head, rest = t.split(r"\begin{thebibliography}{00}")
bibblock, tail = rest.split(r"\end{thebibliography}")
items = re.findall(r"(\\bibitem\{([^}]+)\}.*?)(?=\\bibitem\{|\Z)", bibblock, re.S)
entries = {k: txt.strip() for txt, k in items}
order = []
for c in re.findall(r"\\cite\{([^}]+)\}", head):
    for k in (x.strip() for x in c.split(",")):
        if k not in order:
            order.append(k)
assert set(order) == set(entries), (set(order) ^ set(entries))
new = "\n" + "\n".join(entries[k] for k in order) + "\n"
f.write_text(head + r"\begin{thebibliography}{00}" + new + r"\end{thebibliography}" + tail, encoding="utf-8")
print("reordered", len(order), "references")
