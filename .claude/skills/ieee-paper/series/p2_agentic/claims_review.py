"""Reference labels for qualitative over-claims in the prompt-design replies -> <work>/p2_claims_review.txt.

Every reply whose text contains a word from a deliberately wide list (confirm, breach, occur, overtop, ingress,
submerg, inundat, flooded, under water, started, begun, hit) is written out with the frozen claim check's verdict,
to be read in full. A reply with none of these words is taken as free of over-claims. Decisions after reading go
into CLAIM_LABELS in post_p2_r2.py ({(model, variant, i): True if the reply over-claims}).
usage: python claims_review.py <work>
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from claim_guard import claim_ok  # noqa: E402

WORK = Path(sys.argv[1])
WIDE = re.compile(r"confirm|breach|occur|overtop|ingress|submerg|inundat|flooded|under water|started|begun|\bhit\b", re.I)
n = 0
with open(WORK / "p2_claims_review.txt", "w", encoding="utf-8") as fh:
    for tag in ("gpt-oss-20b", "gpt-oss-120b"):
        for r in json.loads((WORK / f"p2_var_{tag}.json").read_text(encoding="utf-8"))["rows"]:
            if not r["parsed"]:
                continue
            hits = [t["text"] for t in r["turns"] if WIDE.search(t["text"])]
            if not hits:
                continue
            n += 1
            fh.write(f"### {tag} {r['variant']} {r['i']} band={r['band']} claim_ok={claim_ok(r['turns'])}\n")
            for h in hits:
                fh.write("    | " + h.replace(" ", " ") + "\n")
print("candidates", n)
