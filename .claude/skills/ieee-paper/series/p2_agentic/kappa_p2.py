"""Cohen's kappa between the second annotator's blind labels and the reference labels of P2.

usage: python kappa_p2.py <filled replies_to_label.csv> [work dir]
Writes <work>/p2_kappa.json (kappa, disagreements, guard recall / false rejection under the second labels).
"""
import csv
import json
import os
import sys
from pathlib import Path

src = Path(sys.argv[1])
work = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(os.environ["TEMP"]) / "aquasentinel-series"
key = json.loads((work / "p2_annotation_key.json").read_text(encoding="utf-8"))
ref = {(x["model"], x["i"]): x for x in json.loads((work / "p2_labels.json").read_text(encoding="utf-8"))["rows"]}
v2 = {(x["model"], x["i"]): x["v2_ok"] for x in json.loads((work / "p2_guard_v2.json").read_text(encoding="utf-8"))["rows"]}
pairs = []
with open(src, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        lab = (row.get("LABEL (supported / unsupported)") or "").strip().lower()
        if lab not in ("supported", "unsupported"):
            continue
        m, i = key[row["item"]]
        pairs.append(((m, i), lab == "supported"))
n = len(pairs)
a = [ref[k]["label_ok"] for k, _ in pairs]
b = [s for _, s in pairs]
po = sum(x == y for x, y in zip(a, b)) / n
pa, pb = sum(a) / n, sum(b) / n
pe = pa * pb + (1 - pa) * (1 - pb)
kappa = (po - pe) / (1 - pe)
res = {"n": n, "agreement": po, "kappa": kappa,
       "disagreements": [{"model": k[0], "i": k[1], "ref": ref[k]["label_ok"], "second": s} for k, s in pairs
                         if ref[k]["label_ok"] != s], "guards": {}}
for grp, f in (("dev", lambda k: "gpt-oss" in k[0]), ("heldout", lambda k: "allam" in k[0])):
    rows = [(k, s) for k, s in pairs if f(k)]
    for name in ("deployed_ok", "typed_ok", "v2_ok"):
        ok = lambda k: (v2[k] if name == "v2_ok" else ref[k][name]) is True  # noqa: E731
        u = [k for k, s in rows if not s]
        sp = [k for k, s in rows if s]
        res["guards"][f"{grp}:{name}"] = {"recall": 100 * sum(not ok(k) for k in u) / max(len(u), 1),
                                          "false_rej": 100 * sum(not ok(k) for k in sp) / max(len(sp), 1),
                                          "n_unsup": len(u), "n_sup": len(sp)}
(work / "p2_kappa.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
print(f"labelled {n}, agreement {100 * po:.1f}%, Cohen's kappa {kappa:.3f}, disagreements {len(res['disagreements'])}")
for k, v in res["guards"].items():
    print(k, {a_: round(b_, 1) for a_, b_ in v.items()})
