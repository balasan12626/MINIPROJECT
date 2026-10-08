"""paper.tex (master, with authors) -> <work>/camera.tex and <work>/blind.tex (double-blind, no authors).

The author block in paper.tex must sit between the lines '%<AUTHORS>' and '%</AUTHORS>'.
"""
import shutil
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
s = (SCRIPTS / "paper.tex").read_text(encoding="utf-8")
a, b = s.index("%<AUTHORS>"), s.index("%</AUTHORS>") + len("%</AUTHORS>")
blind_auth = ("\\author{\\IEEEauthorblockN{Anonymous Author(s)}\n"
              "\\IEEEauthorblockA{\\textit{Affiliation withheld for double-blind review}}}")
(WORK / "camera.tex").write_text(s, encoding="utf-8")
(WORK / "blind.tex").write_text(s[:a] + blind_auth + s[b:], encoding="utf-8")
print("wrote camera.tex, blind.tex")
