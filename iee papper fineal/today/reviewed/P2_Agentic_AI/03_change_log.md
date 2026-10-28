# P2 change log (2026-10-10)

The title is unchanged. Source backup: `p2_agentic/paper_v1_before_revision.tex`.

| # | Change | Reviewer point it fixes | Evidence |
|---|---|---|---|
| 1 | **Real-LLM study.** 300 replies from gpt-oss-20b and gpt-oss-120b (Groq, T = 0.85) generated through the production prompt code. Previously there was 1 real reply. | R1-1: "no real LLM output is evaluated" (the main reason for Weak Reject) | `exp_p2_live.py` (now checkpoints and resumes), `data/p2_live_*.json` |
| 2 | **Reference labels** with a written protocol (supported / unsupported / procedural). Every reply flagged by any method or disputed between methods was read in full; 4 manual overrides are recorded in code with reasons; a random sample of accepted replies was checked. | Ground truth for real replies | `label_p2_live.py`, `data/p2_labels*.{json,txt}` |
| 3 | Finding: **36.3%** of real replies contain an unsupported number, and **97%** of those are invented ETAs. On real traffic the deployed guard has 89.0% recall and 5.8% false rejections; the typed guard has 93.6% and 10.5%. | Results quality and novelty | `post_p2_v2.py` |
| 4 | **LLM-as-judge baseline** (Qwen3 27B, a different model family): it caught 100% of the unsupported live replies it checked, but missed 15% of one-digit probability errors on injected data and costs one model call per message. No checker dominates, and the paper says so. | R1-2: no baseline checker | `exp_p2_judge.py`, `exp_p2_judge_match.py` |
| 5 | The judge covered 201 of 300 live replies before the provider's **daily token limit** (200k tokens/day). This is stated in the paper, and the live table compares all three checkers on the same 201 replies. | Honesty, fairness | Table II |
| 6 | **Calibration study on the classifiers' own held-out rows** (split rebuilt and verified against `models/evaluation.json`): XGBoost ECE 0.108 vs RF 0.044; held cases are wrong 1.8× as often as released ones; the straddle-only rule holds 7.6% of cases (a quarter of the deployed rule) and 52% of them are errors; a training-CV δ₉₅ = 0.28 matches the sweep's 0.31; isotonic calibration lowers the hold rate | R2-2: "gate shows miscalibration, no calibration analysis"; "δ should be derived" | `exp_p2_calib.py`, new Fig. 2 and Table IV |
| 7 | The exhaustive test of a 5-line function is **no longer a contribution**. The composed dispatch-path check (2,807 → 0) is now the headline. | R2-1 | Contributions list |
| 8 | Contributions 5 → 4; index terms 7 → 5 | R3-3 | — |
| 9 | Qualitative over-claims measured: 14% of replies say "flood confirmed" or "breached" when only a probability exists. Listed as a limitation numeric guards cannot see. | Honesty, limitations | `post_p2_v2.py` |
| 10 | Related work: + NeMo Guardrails (EMNLP'23), Chain-of-Verification (ACL Findings'24), RvLLM (NeurIPS'25), AgentSpec (ICSE'26), LLM-as-a-judge (NeurIPS'23); AutoGen now cites the COLM 2024 version; Kitano now has pages | R1-4, R3-4 | 22 references, DOIs where they exist, checked against Crossref |
| 11 | Figure order fixed (the old Fig. 3-before-Fig. 2 problem is gone); Table II overflow fixed | R3-1 | `audit_refs.py` |
| 12 | **7 → 5 pages** (blind), 6 pages camera-ready; abstract 225 words | Format | — |
| 13 | The deployment note about the silently failing LLM path was shortened into the discussion, because the live study supersedes it | Presentation | — |
| 14 | 20 new `assert`s tie every new claim in the text to the data | Integrity | `post_p2_v2.py` |

## Round 3 (2026-10-10) — held-out model family, full 6 pages
- Third model family: ALLaM-2 7B, 150 states, same prompt (132 replies parsed, 18 failed). Labelled with the unchanged
  protocol; 8 manual decisions recorded in `label_p2_live.py` OVERRIDES (team/mission/alert-level labels, reporting
  intervals, one correct clock time).
- Revised guard `guard_v2.py`, frozen by SHA-256 before any ALLaM reply was read; held-out test in `exp_p2_guard_v2.py`.
- Results (honest): v2 recall 100% / FR 0% on the development replies it was built on; on ALLaM, recall 98.7%
  (1 miss) but false rejection 12.5% (7 replies, all procedural labels the dev models never used). Deployed guard on
  ALLaM: 96.1 / 7.1; first typed guard: 100 / 17.9.
- ALLaM's errors differ from gpt-oss: invented quantities 39% of replies, wrong probabilities 16%, ETAs only 4.5%
  (gpt-oss: ETAs in 32–39%, never a wrong probability).
- New: Section V-D "A Held-Out Model Family", Table IV (dev vs held-out), Table V (real excerpts with each check's
  verdict, generated from stored replies), Fig. 2 (error types per model), deployment rules in the Discussion.
- The existing gpt-oss analysis is unchanged (post script now restricts it to the development models).
- Build: 6 full pages (blind and camera), abstract 250 words, no overfull boxes, ALL CHECKS PASSED.
