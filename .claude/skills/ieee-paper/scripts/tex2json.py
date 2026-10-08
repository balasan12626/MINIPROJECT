import re, json
s = open("camera.tex", encoding="utf-8").read()
MATH = {
 r"\operatorname{clip}((s-70)/30,0,1)": "clip((s − 70)/30, 0, 1)", r"\pm": "±",
 r"\sigma_R=1/(1+e^{-(R-38)/12})": "σ_R = 1/(1 + e^(−(R − 38)/12))",
 r"0.50\le p<0.60": "0.50 ≤ p < 0.60", r"42+17i": "42 + 17i", r"42+19i": "42 + 19i",
 r"c_k=T_k+5H_k": "c_k = T_k + 5H_k", r"i=0,\dots,29": "i = 0, …, 29",
 r"p\ge0.60": "p ≥ 0.60", r"p_{\mathrm{ML}}": "p_ML", r"P_2>\max_k c_k": "P_2 > max_k c_k",
 r"p<0.50": "p < 0.50", r"q^{95}_{g}": "q^(95)_g", r"v_k>0": "v_k > 0",
 r"w_T T + w_H H": "w_T·T + w_H·H", r"x_k\in\{0,1\}": "x_k ∈ {0, 1}",
}
bib = re.findall(r"\\bibitem\{([^}]+)\}", s)
num = {k: i + 1 for i, k in enumerate(bib)}
labels = {"fig:arch": "1", "fig:curves": "2", "fig:gauges": "3", "fig:stress": "4", "tab:fc": "I", "tab:val": "II", "tab:thr": "III", "tab:route": "IV", "tab:sweep": "V", "tab:shield": "VI", "tab:gate": "VII",
          "eq:target": "1", "eq:risk": "2", "eq:qubo": "3", "eq:ba": "4", "eq:safe": "5", "sec:gating": "V-C"}


def inline(t):
    t = re.sub(r"\\cite\{([^}]+)\}", lambda m: ", ".join(f"[{num[k.strip()]}]" for k in m.group(1).split(",")), t)
    t = re.sub(r"\\ref\{([^}]+)\}", lambda m: labels[m.group(1)], t)
    t = re.sub(r"\$([^$]+)\$", lambda m: "\x01" + MATH.get(m.group(1), m.group(1)) + "\x02", t)
    rep = [(r"\~{n}", "ñ"), ("~", " "), ("``", "“"), ("''", "”"), ("---", "—"), ("--", "–"), (r"\%", "%"), (r"\&", "&"),
           (r"vs.\ ", "vs. "), (r"\ ", " "),
           (r"\texttt{run\_pipeline(mode, observations)}", "run_pipeline(mode, observations)"),
           (r"\_", "_"), (r"\'{i}", "í"), (r"\'{a}", "á"), (r"\"{o}", "ö"), (r"\~{n}", "ñ"),
           (r"\textit{et al.}", "\x03et al.\x04")]
    for a, b in rep:
        t = t.replace(a, b)
    t = re.sub(r"\\textsc\{([^}]+)\}", lambda m: m.group(1).upper(), t)
    t = t.replace("'", "’").replace("`", "‘")
    t = re.sub(r"\\(?:textit|emph)\{([^}]*)\}", lambda m: "\x03" + m.group(1) + "\x04", t)
    runs = []
    for part in re.split(r"(\x03[^\x04]*\x04|\x01[^\x02]*\x02)", t):
        if not part:
            continue
        if part[0] in "\x01\x03":
            runs.append({"t": part[1:-1], "i": True})
        else:
            runs.append({"t": part})
    for r in runs:
        r["t"] = re.sub(r"\s+", " ", r["t"])
        if "\\" in r["t"]:
            print("LEFTOVER:", r["t"][:100])
    return runs


title = re.search(r"\\title\{(.*?)\}\s*\n", s, re.S).group(1)
title = re.sub(r"\\\\\s*", " ", title).strip()
out = {"title": title,
       "abstract": inline(re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", s, re.S).group(1).strip()),
       "keywords": re.search(r"\\begin\{IEEEkeywords\}(.*?)\\end\{IEEEkeywords\}", s, re.S).group(1).strip(),
       "blocks": [], "refs": []}
body = s[s.index(r"\section{Introduction}"):s.index(r"\begin{thebibliography}")]
body = body.replace(r"\balance", "")
body = re.sub(r"\\begin\{(figure|table)\}.*?\\end\{\1\}",
              lambda m: "\n\n@@FLOAT " + re.search(r"\\label\{([^}]+)\}", m.group(0)).group(1) + "@@\n\n", body, flags=re.S)
body = re.sub(r"\\begin\{equation\}.*?\\label\{([^}]+)\}.*?\\end\{equation\}",
              lambda m: "\n\n@@EQ " + m.group(1) + "@@\n\n", body, flags=re.S)
body = re.sub(r"\\label\{[^}]+\}", "", body)
body = re.sub(r"^%.*$", "", body, flags=re.M)
for chunk in re.split(r"\n\s*\n", body):
    c = chunk.strip()
    if not c:
        continue
    m = re.match(r"\\section\*?\{([^}]+)\}\s*(.*)", c, re.S)
    if m:
        out["blocks"].append({"type": "h1", "text": m.group(1)})
        c = m.group(2).strip()
        if not c:
            continue
    m = re.match(r"\\subsection\{([^}]+)\}\s*(.*)", c, re.S)
    if m:
        out["blocks"].append({"type": "h2", "text": m.group(1)})
        c = m.group(2).strip()
        if not c:
            continue
    m = re.match(r"@@(FLOAT|EQ) ([^@]+)@@", c)
    if m:
        out["blocks"].append({"type": m.group(1).lower(), "id": m.group(2)})
        continue
    if r"\begin{enumerate}" in c:
        before, c = c.split(r"\begin{enumerate}", 1)
        if before.strip():
            out["blocks"].append({"type": "p", "runs": inline(before.strip())})
        c = r"\begin{enumerate}" + c
        items = re.findall(r"\\item\s+(.*?)(?=\\item|\\end\{enumerate\})", c, re.S)
        for n, it in enumerate(items, 1):
            out["blocks"].append({"type": "li", "n": n, "runs": inline(it.strip())})
        rest = c.split(r"\end{enumerate}")[1].strip()
        if rest:
            out["blocks"].append({"type": "p", "noindent": True, "runs": inline(rest)})
        continue
    noind = bool(re.match(r"(where|with) ", c))
    out["blocks"].append({"type": "p", "noindent": noind, "runs": inline(c)})
for m in re.finditer(r"\\bibitem\{[^}]+\}\s*(.*?)(?=\\bibitem|\\end\{thebibliography\})", s, re.S):
    out["refs"].append(inline(m.group(1).strip()))
json.dump(out, open("paper.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out["blocks"]), "blocks", len(out["refs"]), "refs")
print(out["title"])
print([b["type"] + ":" + b.get("text", b.get("id", "")) for b in out["blocks"] if b["type"] not in ("p", "li")])
