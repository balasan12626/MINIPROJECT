# P2: "Rules Decide, Language Models Narrate: A Fail-Closed Multi-Agent Architecture for Flood Response with Numeric Grounding"
7 pages · 19 references · 4 figures · 5 tables · 1 algorithm · overall **6.7 / 10**

## 1. CMT-style reviews (baseline)

**R1 (domain: LLM safety / agents)**: *Borderline, confidence 4*
- Summary: deterministic agents decide and the LLM only narrates. The paper has three fail-closed mechanisms (a health-gated policy, a disagreement gate between two models, and a numeric grounding guard) and evaluates them offline. It also reports, candidly, a dispatch bug and an LLM path that was failing silently.
- Strengths: an unusually honest paper; the miss analysis is traced to its causes (39 of 48 misses collide with real facts); the typed guard improves on the deployed one; the "check the whole path to action" lesson is useful.
- Weaknesses:
  1. **No real LLM output is evaluated.** All 1,400 replies are hand-constructed and injected through a stub. Only one real reply is shown. The detection rates therefore measure a regex against the authors' own error model, not against hallucinations.
  2. The guard is regex-based number matching. No baseline is compared, such as an NLI or entailment checker, SelfCheckGPT [13], a FActScore-style decomposition [12], or a "constrained decoding / fill a template with slots" approach. Without a comparison, 96% has nothing to be judged against.
  3. "Multi-agent" and "agentic" are mostly labels: 11 deterministic functions share one state. Reviewers from agent venues will push back on this.
  4. Missing recent work: RvLLM (NeurIPS 2025, runtime verification of LLM outputs), AgentSpec (2025, runtime enforcement for LLM agents), NeMo Guardrails (EMNLP 2023 demo), and disaster-specific LLM guardrail work from 2025–26.

**R2 (methods / verification)**: *Weak Reject, confidence 4*
1. The exhaustive check of a five-line pure function (16,032 cases) is trivial, as the paper itself says. It should not be listed as a contribution. The end-to-end dispatch audit (2,807 violations → 0) is the stronger result. Make it central and model the composed path more formally, for example as a small model-checking or property-based-testing setup.
2. The dual-model gate result (holds 69.7% of cases) shows that the two models are **miscalibrated**, yet there is no calibration analysis (reliability diagram, ECE) and no recalibration (isotonic or Platt) before the gap is compared. δ should be derived, not swept.
3. Eq. (5) is an approximation with no check. Compare the predicted P_miss with the observed 4.0%.
4. 32,032 = 1,001 × 8 × 2 × 2, so the undefined-p case is excluded from the end-to-end grid. State this.
5. Single-run numbers with no CIs. Add Wilson CIs for the detection rates (n = 200 per type).

**R3 (format / presentation)**: *Weak Accept on presentation only*
1. **Fig. 3 is cited before Fig. 2** (§V-B: "Fig. 3 plots …" comes before the first mention of Fig. 2). IEEE requires figures to be numbered in order of first citation. Swap them.
2. 7 pages; no DOIs; 8 of 19 references (42%) are from 2021 or later.
3. The 5-item contribution list is too long. Item 5 ("findings") is not a contribution in the IEEE sense; merge it.
4. AutoGen [4] is cited as arXiv. Cite the published COLM 2024 version (verify first).

**Meta-review**: An interesting and honest systems paper with a good practical lesson, but the central "LLM" claim is untested on a real LLM. **Weak Reject → Accept is reachable** with a real-LLM study and one guard baseline.

## 2. Ten scores
| Dim | Score | Justification |
|---|---|---|
| Novelty | 6.0 | "LLM narrates, rules decide" is an established safety pattern. The typed numeric guard and the composed-path audit are modest additions. |
| Gap clarity | 7.0 | The point that the facts are a small known set, so a deterministic check is possible, is well argued. |
| Soundness | 6.5 | Correct, but the guard evaluation uses synthetic errors only and the gate has no calibration analysis. |
| Math | 7.0 | Eqs (1)–(6) are formal and clear. Eq. (5) is unchecked. |
| Experimental design | 6.0 | No real-LLM study, no baseline guard, no CIs. |
| Results / justification | 7.5 | Excellent miss tracing; the δ sweep clearly explains the over-holding. |
| Related work | 6.0 | Missing 2024–26 guardrail and runtime-verification work for LLMs. |
| Presentation | 7.5 | Clean. Figure order error. |
| English | 8.0 | Natural and specific. The title is memorable. |
| Format / references | 6.5 | 7 pages, figure order, no DOIs. |

## 3. Novelty audit
| Work | Method | Limitation vs P2 |
|---|---|---|
| Ji et al., ACM CSUR 2023 [1] | hallucination survey | Background only. |
| FActScore [12], SelfCheckGPT [13] (EMNLP 2023) | atomic-claim / sampling checks | Open-domain and probabilistic. P2 should compare against one of them. |
| RvLLM (NeurIPS 2025, arXiv 2505.18585) | runtime verification of LLM output against domain specs (incl. numeric) | **Closest competitor. Not cited.** |
| AgentSpec (arXiv 2503.18666, 2025) | runtime enforcement rules for LLM agents | Close to "rules decide". Not cited. |
| NeMo Guardrails (EMNLP 2023 demo) | programmable rails | Standard tool. Not cited (verify reference). |
| "Generative AI-driven reliability layer for disaster resilience" (arXiv 2601.18308, 2026) | guardrails for disaster LLM use | Same domain. Not cited. |
| Parasuraman 2000 [5], Simplex/shielding [14] | levels of automation, run-time shields | Conceptual basis, cited. |

**Verdict: incremental to moderately new.** The combination (state-grounded numeric guard + composed-path fail-closed audit in a deployed emergency system) is a credible contribution if the evaluation uses a real LLM. Ways to make it stronger:
1. **Real-LLM study.** Run 3 open models × 200 states at temperature > 0. Measure natural hallucination rates and guard precision/recall against hand labels. This is the single most important fix.
2. **Formalise the composed-path check** as a model-checking problem (for example in a small TLA+ or Python property-based-testing harness) and present the bug as the case study.
3. **Calibrate before gating.** Isotonic-calibrate RF and XGB on validation data, then re-run the gate. Show that the disagreement rate drops for principled reasons.

## 4. Reference audit (19 references)
All exist (well-known works; details checked against memory and the venues). Problems: [4] AutoGen should cite the published COLM 2024 version (verify); [8] Kitano SMC 1999 needs vol./pages (vol. 6, pp. 739–743, verify); no DOIs; 8 of 19 (42%) are from 2021–26. Add RvLLM, AgentSpec, NeMo Guardrails, one disaster-LLM paper and Chain-of-Verification (ACL Findings 2024, verify).

## 5. Format audit
- Figure citation order is wrong (Fig. 3 before Fig. 2) → renumber.
- 7 pages → cut.
- Index terms: 7 → 5–6.
- Five contributions → 3–4.
- No DOIs.
- Table II has a column-width overflow in the PDF ("admin (0.50–0.60) Administrator" runs together) → check for an overfull hbox.
- Fonts and figures OK.

## 6. Overclaim check
- The abstract says the guard was "driven through the real generation code". It was, but with a stubbed client. Say "real prompt-building and parsing code with a stubbed LLM" in the abstract itself.
- "Eleven role-specific agents" is accurate, but "multi-agent architecture" implies interacting autonomous agents. Consider "multi-role" or define "agent" early.

## 7. Venues (verify dates)
IEEE CAI 2027 (Singapore; the paper call is "coming soon"). IEEE SMC 2027 (human-machine systems track). IEEE R10 HTC or GHTC 2027 (humanitarian). DSN workshops (dependable AI).

## 8. TODO for authors
- [TODO-EXPERIMENT] A real-LLM study (≥ 2 models, 200 states, logged and hand-labelled) giving guard precision/recall. This is the decision that determines acceptance.
- [TODO-EXPERIMENT] One baseline guard (NLI entailment, or SelfCheckGPT) on the same replies.
- [TODO-EXPERIMENT] Reliability diagrams and ECE for RF and XGB, with the gate re-run after calibration.
- [TODO] Wilson 95% CIs on Table V (a script, no new data).
- Fix the figure order, cut to 6 pages, add DOIs and 5+ verified references from 2024–26.
