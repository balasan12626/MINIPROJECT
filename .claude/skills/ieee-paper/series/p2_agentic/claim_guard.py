"""Claim guard (prototype, P2 revision): rejects narration that asserts an observed flood when the state holds
only a forecast probability. Written on the development replies (gpt-oss) and frozen (SHA-256 recorded in
claim_guard_freeze.json) before any reply of the prompt-variant run (exp_p2_variants.py) was read.

The state never contains an observation of flooding, a breach, overtopping or water ingress, so any such
assertion is unsupported. A hedge just before the assertion ("chance of breach", "expecting water ingress",
"could overtop", "if flooding is confirmed") makes it a forecast and is allowed.
"""
import re

ASSERT = re.compile(
    r"\b(?:flood(?:ing)?\s+(?:(?:is|has\s+been|now)\s+)?confirmed|confirmed\s+flood(?:ing)?"
    r"|flood\s+risk[^.;]{0,20}\bconfirmed"
    r"|flood(?:ing)?\s+(?:has\s+)?(?:occurred|started|begun)|flood\s+occurred"
    r"|(?:has|have)\s+(?:breached|overtopped|burst)|(?:is|are)\s+breached|(?:is|are)\s+breaching"
    r"|water\s+(?:is\s+)?(?:overtopping|breaching)|overtopping\s+(?:is|has)"
    r"|water\s+(?:has\s+)?entered|water\s+ingress"
    r"|(?:is|are)\s+(?:now\s+)?(?:flooded|under\s+water|submerged|inundated)"
    r"|full-blown\s+flood|flood\s+is\s+(?:here|underway))",
    re.I)
HEDGE = re.compile(r"\b(?:could|may|might|possible|possibly|likely|expect\w*|chance\s+of|risk\s+of|if|unless|"
                   r"potential|forecast\w*|prepare\s+for|watch\s+for|not|no)\b[^.;]*$", re.I)


def claim_ok(turns) -> bool:
    """True when no assertion of an observed flood appears without a hedge in the 40 characters before it."""
    for t in turns or []:
        s = str(t.get("text") or "")
        for m in ASSERT.finditer(s):
            if not HEDGE.search(s[max(0, m.start() - 40):m.start()]):
                return False
    return True
