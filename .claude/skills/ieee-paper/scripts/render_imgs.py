"""Render Fig. 1 (TikZ), equations (1)-(3) and Fig. 2 as PNG for the Word version -> <work>/img/."""
import re
import subprocess
import sys
from pathlib import Path

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
IMG = WORK / "img"
IMG.mkdir(exist_ok=True)
s = (WORK / "camera.tex").read_text(encoding="utf-8")
pre = ("\\documentclass[border=2pt]{standalone}\n\\usepackage{amsmath,amssymb,amsfonts,mathptmx}\n"
       "\\usepackage{tikz}\\usetikzlibrary{positioning,arrows.meta,fit}\n\\begin{document}\n")
tik = s[s.index("\\begin{tikzpicture}"):s.index("\\end{tikzpicture}") + len("\\end{tikzpicture}")]
jobs = {"arch": pre + tik + "\n\\end{document}\n"}
for n, m in enumerate(re.finditer(r"\\begin\{equation\}(.*?)\\end\{equation\}", s, re.S), 1):
    body = "\n".join(l for l in m.group(1).split("\n") if "\\label" not in l).strip().rstrip(",. ")
    jobs[f"eq{n}"] = pre + "$\\displaystyle " + body + "$\n\\end{document}\n"
for name, tex in jobs.items():
    (IMG / f"{name}.tex").write_text(tex, encoding="utf-8")
    subprocess.run(["pdflatex", "-interaction=nonstopmode", f"{name}.tex"], cwd=IMG, capture_output=True, check=True)
    subprocess.run(["pdftoppm", "-png", "-r", "600", "-singlefile", f"{name}.pdf", name], cwd=IMG, check=True)
subprocess.run(["pdftoppm", "-png", "-r", "300", "-singlefile", str(WORK / "fig_safety.pdf"), str(IMG / "safety")], check=True)
for _n in ("curves", "gauges"):
    subprocess.run(["pdftoppm", "-png", "-r", "300", "-singlefile", str(WORK / f"fig_{_n}.pdf"), str(IMG / _n)], check=True)
print("rendered", ", ".join(list(jobs) + ["safety"]))
