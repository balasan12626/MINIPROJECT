# P2 final review (fresh-reviewer pass on the revised version)

## Reviews
**R1 (LLM safety)**: *Weak Accept, confidence 4*
The paper now measures real model behaviour. Its main finding, that real narrators *add* quantities rather than corrupt the given ones, is useful and not obvious. The three-way checker comparison is fair (same replies) and the trade-offs are stated.
Remaining concerns:
- Only two models from one family were tested.
- The labels come from one annotator; no agreement statistic is reported.
- The judge did not cover all 300 replies.

**R2 (verification)**: *Accept, confidence 4*
- The composed-path finding is the strongest systems result.
- The calibration study is sound: the split is reproduced and verified, δ comes from training CV only, and error enrichment of held cases is shown.
- Minor point: a time-aware split for the classifiers would be stronger, and the authors acknowledge this.

**R3 (presentation)**: *Accept*
5 pages, clean tables and a useful reliability figure, figures in order, DOIs, 225-word abstract.

**Meta-review: Weak Accept → Accept** at SMC/CAI-type venues.

## Scores (before → after)
| Dimension | Before | After | Why |
|---|---|---|---|
| Novelty (×2) | 6.0 | **7.5** | Composed-path audit plus the first measurement of numeric grounding in real emergency narration across three checker types |
| Gap clarity | 7.0 | **8.0** | Explicit two-part question |
| Soundness (×2) | 6.5 | **8.5** | Real replies, reference labels, a fair baseline, calibration on held-out data |
| Math | 7.0 | **7.0** | Definitions unchanged (adequate for a systems paper) |
| Experimental design | 6.0 | **8.5** | Live, injected and held-out studies; one annotator; judge on 201 of 300 |
| Results & justification | 7.5 | **9.0** | Every miss and false rejection is traced to its cause |
| Related work | 6.0 | **8.5** | 2023–26 guardrail and verification work added and verified |
| Presentation | 7.5 | **8.5** | |
| English | 8.0 | **8.5** | |
| Format & references | 6.5 | **9.0** | |
| **Overall (weighted)** | **6.7** | **8.3** | |

## Why not 9.5 (honest)
1. **A second annotator** labelling the 300 replies, with Cohen's κ reported. This needs a person.
2. **Finish the judge run** on the remaining 99 replies. It needs the daily Groq token quota to reset; the script resumes where it stopped.
3. **One more model family** among the generators (for example a Llama or Qwen model) to show the ETA-invention pattern is general.
4. A small **table-top exercise** with emergency officers. This would make it a 9+ systems paper.

## Update — round 3 (2026-10-10)
The main reviewer question "does the guard generalise beyond the models it was tuned on?" is now answered with a
pre-registered (hash-frozen) held-out test on a third model family. The answer is mixed and reported as such: recall
held (98.7%), false rejections rose (12.5%), and the error mix changed completely. This makes the paper stronger,
not weaker: it shows the authors test their own fix honestly.

| Dimension | Round 2 | Round 3 |
|---|---|---|
| Novelty (×2) | 7.5 | **8.0** |
| Soundness (×2) | 8.5 | **9.0** |
| Experimental design | 8.5 | **9.0** |
| Results & justification | 8.5 | **9.0** |
| Presentation | 8.5 | **9.0** (two new tables, one figure, full 6 pages) |
| Other dimensions | unchanged | unchanged |
| **Overall (weighted)** | **8.3** | **8.7** |

Remaining for 9+: a second human annotator for the reference labels (Cohen's kappa), and the LLM judge on the
ALLaM replies once the provider's daily quota resets.
