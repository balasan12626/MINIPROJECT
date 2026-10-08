# IEEE paper series: audit report

Four 6-page IEEE conference papers built from the AquaSentinel prototype. Upload `SUBMIT_blind_review.pdf`
from each folder; `camera_ready_with_authors.*` is for after acceptance.
Sources: `.claude/skills/ieee-paper/series/` (P1–P3) and `.claude/skills/ieee-paper/scripts/` (P4).
Rebuild: `.venv\Scripts\python.exe .claude\skills\ieee-paper\series\build_series.py`
(P4: `.claude\skills\ieee-paper\scripts\make_paper.ps1 -SkipExp`).
The original rejected INDICON PDF in `iee papper fineal/` is untouched.

| Paper | Folder | Pages |
|---|---|---|
| P1 Constraint-preserving QAOA for flood shelter assignment | Paper1_Quantum_QAOA | 6 |
| P2 Rules decide, language models narrate (agentic AI) | Paper2_Agentic_AI | 6 |
| P3 Verifier-gated tool use: agentic re-planning with QAOA | Paper3_Agentic_Quantum | 6 |
| P4 Fail-closed flood evacuation decision support (revised INDICON 4244) | Paper4_FullScenario_FailClosed | 6 |

## Automated checks (every build)
- Every number in P1–P3 is generated from the experiment JSON into `nums.tex`; qualitative claims are
  asserted in `post_p*.py`, so the build fails if text and data disagree. P4 numbers are checked by `verify.py`.
- Pages ≤ 6, no Type 3 fonts, all fonts embedded, no author identity in the blind PDF, no undefined
  references or citations, no "??".
- References: none uncited, none missing, no duplicates, IEEE first-citation order (`audit_refs.py`).
  Every figure, table and algorithm is referenced in the text.

## Problems found and fixed
1. Software bug (safety): dispatch read the flood probability, not the policy action, so rescue teams were
   auto-dispatched even when a health check failed. Fixed in `backend/services/dispatch.py`
   (`dispatch_permitted`) and `backend/services/pipeline.py`; the disagreement hold now also applies in
   live mode. Exhaustive end-to-end check: 2,807 unsafe cases of 32,032 before, 0 after.
   Regression tests: `backend/tests/test_dispatch_gate.py`; backend suite 79 passed.
2. P1: noiseless-only results → added a global depolarising noise analysis; the XY advantage holds at
   every error rate tried.
3. P3: escalation branch was never exercised → added event E5 (double shelter failure): 27/27
   infeasible cases escalated, 0 wrong, 0 missed.
4. P3: references were not in first-citation order → reordered.
5. P2/P3 drafts claimed things the data did not support (escalation, a guessed cause) → rewritten and
   asserted.
6. P4 was 5 pages → added validation table, closure-sweep table, metric equations, threats to validity.

## Second audit (full read of all four PDFs)
Versions: `series_versions/1_before_audit/` (sources + PDFs before this audit) and
`series_versions/2_final_after_audit/`. The rejected INDICON original is untouched.

| # | Paper | Issue found | Fix |
|---|---|---|---|
| 1 | P4 | PDF printed "extitReproducibility." (a `\t` escape collapsed `\textit`) | Restored; build now fails on broken command names or tabs in the source |
| 2 | P3 | Raw-policy optimality 36.4% in Table I (valid plans only) vs 28.7% mean in Table III (all re-plans) | Table I now uses all re-plans for every policy (28.7%); note added; asserted |
| 3 | P3 | Comma splice "…6.7% with µ = 6, We did not…" | Period |
| 4 | P1 | Conclusion said simulated annealing solved the instances; results show 10% optimal | Conclusion now cites exhaustive search only |
| 5 | P1 | Abstract called the problem "hard" although exhaustive search takes 0.9 ms | "small constrained combinatorial problem" |
| 6 | P1 | G used before definition; sentence starting with a digit ("1 of the ten") | Defined G; "One of the ten" (asserted against data) |
| 7 | P2 | Dangling "This follows…" after a reordered sentence | "Our position follows…" |
| 8 | P2 | Unprovable claim "none would have shown up in a unit test" | Rephrased to what the audit showed |
| 9 | P2 | Inline set {AUTO, OVERRIDE} caused a badly spaced line; abstract slightly long | Rewritten in words; abstract shortened |

References checked online this round: Abbas 2024, Fuchs 2022, Min 2023, Manakul 2023, Leucker 2009,
Underhill 2026 (publisher page), Raei 2026, Liu 2025, Cadeliña 2024 (vol./no. confirmed; pages not
confirmed), Kitano 1999, Fox 2006, Galda 2021. No fabricated or mismatched entries found.

## Third round: toward 9/10
| Area | Change |
|---|---|
| App bug (agents) | The LLM radio never worked: the configured Llama models are retired on Groq (HTTP 404) and gpt-oss spent its 700-token budget on hidden reasoning before writing JSON (HTTP 400). Fixed in `backend/agents/dialogue.py` (`groq_body`: low reasoning effort, larger budget; current model list; `_primary_model`). Backend tests 79 passed. The template fallback had kept the radio working, so the failure was silent. |
| P2 experiments | A live Groq study was started and then dropped at the author's request (rate limits); P2 keeps its offline evaluation. The script `exp_p2_live.py` remains for later use. |
| P1 experiments | Gate-level Pauli-noise trajectories (10 instances, 200 runs per circuit); corrected the earlier claim that the global model is optimistic (it is pessimistic here). |
| P4 experiments | Minimum-based reliability gate measured on the same failure cases: blocks all 9 degraded-source cases, allows the healthy case at zero margin (checked by `verify.py`, 48 numbers). |
| P1, P3 | Explicit research-gap paragraphs. |
| References | Toolformer pages and Kitano volume/pages removed (could not be confirmed); 18 references checked online in total. |

## Results that do not favour the methods (kept on purpose)
- P1/P3: exhaustive search and a greedy rule solve these instances faster than simulated QAOA, and greedy
  is optimal more often than verified QAOA (P3).
- P2: the disagreement gate holds 73.7% of cases where both models already recommend action.
- P4: the shield matches but does not beat flood-aware A*; forecast precision is 0.328.

## Style
Humanizer pass applied (staged contrasts and closers rewritten); no em-dash connectors. Remaining
flagged words are technical or in cited titles ("energy landscape", "robustness", "comprehensive").
The IEEE AI-use disclosure is in every Acknowledgment and must stay.

## Remaining warnings
- Not done: P4 routing on the real Delhi road graph; P2 live LLM replies (needs GROQ key and approval).
- Word copies exist only for P4; P1–P3 are PDF + LaTeX.
- IEEE PDF eXpress check needs the target conference ID.

## Author verification required
- Name spellings (Abhishek/ABISHAK, Gowthaman/GOWTHMAN) and the students' department in the author blocks.
- Do not submit overlapping papers to the same venue at the same time (duplicate-submission policy).
- References were written from memory and spot-checked online; check DOIs/pages against IEEE Xplore or
  the publisher before camera-ready. In particular the page range "pp. 24–33" of Cadeliña et al. (2024).
- Third-party skills (ieee-acm-paper-writing, paper-audit, academic-research) were not installed: the
  install was blocked by Claude Code's safety check. Install them yourself with `! <command>` if wanted.
