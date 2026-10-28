# IEEE Reviewer Comments and Responses: Papers 1 and 2

Revision of 13–14 October 2026. Files in this folder:

| Paper | Upload for review (blind) | After acceptance |
|---|---|---|
| P1: One-Hot-Preserving QAOA with Transferable Angles for Flood Shelter Assignment | `P1_SUBMIT_blind_review.pdf` | `P1_camera_ready_with_authors.pdf` |
| P2: Rules Decide, Language Models Narrate: Fail-Closed Numeric Grounding of LLM Narration in a Flood-Response Pipeline | `P2_SUBMIT_blind_review.pdf` | `P2_camera_ready_with_authors.pdf` |

Both are 6 pages, pass every build check (numbers checked against the experiment data, references, fonts, page count), and the blind copies have no author names.

Status key: ✅ done · ⚠️ partly done (reason given) · ❌ not done (reason given)

---

## Paper 2: response to the reviewer

Original recommendation: Weak Accept, 3.4 / 5.

### Major comments

| # | Reviewer comment | Status | What we changed |
|---|---|---|---|
| 1 | Strongest baseline missing: let the LLM write placeholders and let the program fill every number. Also run "forbid arrival times in the prompt". | ✅ | Both designs were run live on gpt-oss-20b and gpt-oss-120b (first 120 states; the run was stopped there to limit API use). Unsupported replies: production prompt 28.0%; with the no-arrival-time rule 3.4%; placeholders only 1.7%, with 2.1% template fallbacks. Token use and words per reply are reported (new Table II). |
| 2 | Qualitative over-claims ("flood confirmed", "has breached") are the real residual risk; report miss rate per guard or narrow the claim. | ✅ | New section "Qualitative Over-Claims": 43 replies (14.3%) over-claim, and the deployed guard passes 27 of 43. The claim is narrowed to *numeric* grounding (new title). A frozen check on assertion words is added. We also report that our own prompt rule ("flood occurred") and our fallback template ("Flood has occurred") cause part of the problem. |
| 3 | Reference labels are not independent of the checkers; use a second blind annotator and Cohen's kappa. | ⚠️ | Every result is now also reported under the script-only labels, which were made before any manual reading. The second-annotator package is ready (`../../P2_Agentic_AI/second_annotator/`: blind sheet, facts, protocol, kappa script) but needs a co-author to fill in. The paper states this as the main open item. |
| 4 | Held-out result does not show v2 is better; use McNemar; report the 18 failed ALLaM-2 calls. | ✅ | McNemar p = 0.62 (recall) and p = 0.25 (false rejections), so the paper now says neither guard is shown to be better. All 18 failed calls were in the automated band (18 of 123 calls there, 0 of 27 elsewhere), and this is reported. |
| 5 | Judge comparison unfair: 23 failed judge calls counted as rejections; report with and without. | ✅ | Judge false rejections are 14.1% with the failures counted and 6.8% without them (277 answered replies). Both rows are in Table I. "Caught all it checked" is removed. |
| 6 | 2,807 is a grid count, not exposure; give a proof; discuss what the pure-function check misses. | ✅ | 2,807 = 401 probabilities × 7 failed-health combinations, i.e. one equivalence class. Because the probability is only compared with 0.40/0.50/0.60, which all lie on the grid, the grid check is a proof for the extracted functions. Exposure: 119 of 604 sweep settings were in the unsafe state. Asynchronous limits are discussed (stale flags, an override racing a tick, a real task-cancellation bug that only running the system found). |
| 7 | Gate: report recall of errors, a cost comparison, a no-gate baseline and a calibrated single model, with CIs. | ✅ | New Table V. The deployed gate catches 40.3% of errors (CI 34–47); the straddle rule only 15.9%, and it would let 55 more errors through (CI 42–69). We withdrew the earlier "replace with straddle" recommendation. When a missed dispatch costs 5×, a calibrated single model with no gate is cheapest. |
| 8 | Classifiers not described. | ✅ | INDOFLOODS, 4,548 events at 155 gauges, target = severe flood (35.8%), 55 numeric + 4 categorical inputs, stratified 80/20 split, ROC-AUC 0.818 / 0.806. The sweep extrapolates: 37% of its settings exceed the 99th percentile of training rainfall. |
| 9 | Narrow model coverage; say the rates are specific to the setup. | ⚠️ | The abstract and limits now say the rates are specific to our prompt, models and states. No new model family was tested, because API calls were stopped. |
| 10 | "Multi-agent" and "formal" overstated; compare with CAP and NeMo Guardrails. | ✅ | New title; the system is described as "a rule-based pipeline with an LLM narrator". Common Alerting Protocol is cited; NeMo's fact-checking rail is matched to our LLM-judge baseline. |

### Minor comments

| Reviewer comment | Status | What we changed |
|---|---|---|
| Table II repeats columns | ✅ | Merged into one Table I |
| 97% vs "almost all" | ✅ | Both now say 106 of 109 (97%) |
| 64% vs Fig. 2 (68%) | ✅ | Same categories used throughout: 39% of all ALLaM-2 replies, 67% of its unsupported ones |
| Table III header and judge CIs | ✅ | Sample sizes in the header; judge Wilson CIs at most ±14 points |
| ×100 rule sensitivity | ✅ | Recall unchanged on the development replies (89.0%); false rejections 5.8% → 6.3% |
| Give the δ value | ✅ | δ95 = 0.28; the sweep stops holding agreeing cases at δ = 0.31 |
| Explain 16,032 vs 32,032 | ✅ | 1,002 × 8 × 2 = 16,032 and 1,001 × 8 × 2 × 2 = 32,032 (also added to the companion paper P5) |
| Template-fallback rate per model | ✅ | 38.7% (gpt-oss-20b), 33.3% (gpt-oss-120b), 63.3% (ALLaM-2) |
| How excerpts were chosen | ✅ | The excerpt table was removed for space; two examples are quoted in the text, with how they were chosen stated |
| Overlap with the companion paper | ✅ | Stated in the introduction (no citation, because the review is double-blind) |
| Check refs [16], [17] | ✅ | RvLLM: NeurIPS 38, pp. 89374–89394, doi 10.52202/085713-2693. AgentSpec: ICSE 2026, pp. 2938–2950 (checked with Crossref) |
| Blind copy without names | ✅ | Checked |

### Answers to the reviewer's questions

1. **Slots only?** The narrator left a digit or number word in 2.1% of replies, and those go to the template. One reply that passed still carried an unsupported number.
2. **Fallback share in practice?** The measured rates are 33–63% of calls per model with the deployed guard, but 2.1–2.6% with the improved prompts.
3. **Straddle instead of the gap rule?** 55 more errors would reach dispatch (CI 42–69). Cost per 100 events is in Table V.

---

## Paper 1: response to the reviewer

Original recommendation: Weak Accept. The pasted review was cut off after major comment 5, so the comments below are the ones that were visible.

| # | Reviewer comment | Status | What we changed |
|---|---|---|---|
| 1 | The mixer preserves one-hot, not capacity; title overstates; compare with a mixer on the feasible subspace. | ✅ | Title changed to "One-Hot-Preserving QAOA". A mixer confined to fully feasible plans reaches P_opt 0.444 against 0.215 for ring-XY (better on 26 of 30 instances, p = 4.4e-06). The paper states that preparing its start state needs the feasible set, so it is a bound, not a practical circuit. |
| 2 | The "shared energy scale" explanation is not tested. | ✅ | With the scaling switched off, the transferred angles collapse to 0.029. A different normalisation gives 0.282, close to our 0.306. So transfer needs a common scale, not our particular one. |
| 3 | "0 evaluations" hides the offline cost; give the break-even. | ✅ | One-time cost: 78,992 evaluations, which per-instance training would spend on about 32 disruptions. |
| 4 | The per-instance baseline is weak; add equal-budget, warm-start and stronger-optimizer baselines. | ✅ | Fixed angles 0.306 vs best of 5 COBYLA seeds 0.242 and L-BFGS-B 0.225. A warm start from the fixed angles with a full budget improves to 0.385 (p = 0.0019). |
| 5 | "Statistically indistinguishable from Grover" is not equivalence. | ✅ | Reworded. The data lean towards XY: ahead on 20 of 30 instances, mean difference 0.076 (CI 0.018–0.141), unadjusted p = 0.047, not significant after Holm. |
| 6+ | (rest of the review was cut off) | — | Please paste the remainder if it exists. |

Other fixes:
- The city map files had been rebuilt after the first run, so the city test was re-run on a frozen copy of the data. Delhi, Chennai, Mumbai and Kolkata reproduce exactly; Guwahati and Patna changed slightly. Updated result: success within 32 shots rises from 74.9% to 89.9% (p ≈ 0.01).
- The position table, the scaling table and Algorithm 1 were folded into the text to stay at 6 pages.

### Round 3 (14 Oct 2026)

New title: "One-Hot-Preserving QAOA for Flood Shelter Assignment: Pairwise Capacity Encoding and Angle Transfer". All new numbers come from stored results (`p1_r3.json`, `p1_r3_cities.json`, `p1_r3_cand.json`, written by `exp_p1_r3.py`) through `post_p1_r3.py`, which asserts every comparison in the text. On the user's instruction (slow machine) no new training runs were made for M2, M3 and M7; those items are handled in the text and listed below as not done.

| # | Comment | Status | What changed (measured numbers) |
|---|---|---|---|
| M1 | theta* chosen with oracle P_opt; best-of-5 also chosen by P_opt | ✅ done, claim weakened | Text now says Eq. (7) uses the exact optima of the development set. Two oracle-free rules added (min. mean energy, min. mean CVaR) over the same 30 trained sets. Held-out P_opt (XY, mean, p=4): P_opt rule 0.306, energy rule 0.264, CVaR rule 0.234, per-instance training 0.163 (Holm p 8.5e-4, 3.8e-3, 0.039). Leave-one-out on the development set: P_opt rule 0.292, energy rule 0.082, CVaR rule 0.164, per-instance training 0.215. So the oracle-free rules are not reliable, and the abstract, contributions, discussion and conclusion say so. Best of 5 now chosen by lowest training energy: 0.203 (was 0.242 by P_opt). Per-instance training reaches lower energy than the fixed set (0.300 vs 0.530, lower on 24 of 30), and energy ranks P_opt poorly across candidate sets (Spearman 0.33). |
| M2 | "new disruption instances" overstates | ⚠️ renamed only | Now "held-out seeds of one disruption pattern" everywhere; varied disruptions listed as a limitation. A generator for three other patterns is in `exp_p1_r3.py` (phase `dis`) but was not run. |
| M3 | scaling evidence thin | ⚠️ text only | Rewrite 8 applied ("fixed angles remain usable at 15 and 18 qubits; it does not establish a gain"); minimum fixed P_opt is 36x and 34x uniform one-hot. A one-hot subspace simulator was added to `qaoa_sim.py` (agrees with the full statevector to 1.8e-16 at G=4, 5) and `exp_p1_sub.py` is ready, but the run (G=5..10, 30 instances) was stopped and is listed as future work. |
| M4 | "tuned" SA weak; uniform-over-feasible baseline | ✅ | "tuned" dropped. SA with one-hot moves ends at the optimum in 93.3% (the encoding's limit) vs 80.0% for bit-flip SA; both visit the optimum every time, so with a verifier both reach 100%. Uniform sampling over feasible plans gives P_opt 0.049; the feasible-subspace mixer's 0.444 is 9.0x that. |
| M5 | statistics: unadjusted p, city clustering, unnamed test, seeds ignored | ✅ | Holm per family (4 depths; 7 transfer rows; 4 city tests). Median paired differences in Table II (+0.195, +0.131, +0.102 for XY mean). Per-city table: fixed set ahead in P_opt in only 3 of 6 cities (sign test p = 1.00); success@32 higher in all 6 (sign test p = 0.03; Holm Wilcoxon p = 0.042). Wilcoxon signed-rank named for success@N. Two-level bootstrap (instances, then seeds): XY mean 0.188, CI 0.127-0.257. |
| M6 | success@N vs verifier; best-of-N gap | ✅ | New Table III: expected gap of the cheapest verified plan among N = 8/32/128 samples. N=8: fixed 0.09%, per-instance 1.49%, uniform one-hot 6.7%; N=128: per-instance 0.10%. Text states the sampler is optimal whenever the optimum is drawn. |
| M7 | hardware cost not quantified | ✅ partly | CNOT counts per layer (Table I): X 28, ring-XY 28, Grover 150 (two W-state layers of 12 CNOTs + 122-CNOT multi-controlled phase with 10 ancillas, Nielsen & Chuang construction); one-time W-state preparation 12 CNOTs (3 per group, checked numerically). XY gate = 2 CNOTs (Vatan & Williams 2004). eps = 0.01 per gate ~ 0.5% per CNOT, compared with Sycamore's 0.36% / 0.62% two-qubit Pauli errors (Arute et al. 2019, checked in the supplement). Noise was not re-run per CNOT (limitation). |
| M8 | novelty and contributions | ✅ | Contributions rewritten around the pairwise encoding and its exactness, the mixer comparison with CNOT counts, transfer with three selection rules and the energy-scale ablation, and the verifier. "Matches or outperforms ... at no per-instance cost" removed. Positioning paragraph added (ring-XY is from [7]; differences from [18]-[20]). Angle concentration: a set's development P_opt predicts its held-out P_opt (Spearman 0.98); only 7 of 30 trained sets beat per-instance training (median set 0.062). Binding vs non-binding: per-instance training 0.106 vs 0.228, fixed set 0.312 vs 0.298, so the gain comes mostly from capacity-binding instances. |
| Minor | macros, p format, tables, notation, refs | ✅ | Macro spacing checked in the PDF text; one p-value format ($8.5\times10^{-4}$, three decimals between 0.01 and 0.1). Table I: "seeds" column removed, Evals and CNOT explained. Penalty renamed mu; group size m_g; optimal set X*. Lemma -> Remark, noting that lambda < 1 breaks the bound. Fig. 1 caption notes different y-axes. Noise table dropped for space (numbers kept in text). Punctuation after equations fixed; "Training never uses the optimal plan" and per-variant training stated. Refs checked: [13], [14] on arXiv (no journal version), Farhi 2014 and Brandao 2018 have no journal version (arXiv pages checked); added Vatan & Williams, Nielsen & Chuang, Arute et al. (Crossref checked). "Mean cost 47 minutes per pair" dropped. 93.3% vs "every instance has an infeasible zero-penalty plan" explained (such plans usually cost more than the optimum). |
| Rewrites 1-10 | | ✅ | All ten applied or rephrased to the same effect (9: "Threats to validity" merged into Limitations; 10: ratio given, 36x and 34x uniform; 6 rephrased as "Stronger optimizers stayed below"). |

Build: `build_series.py p1` -> 6 pages (blind and camera), REFERENCES OK, ALL CHECKS PASSED, no Type 3 fonts. Style: 4,618 words, burstiness 0.58, no em dashes in prose, tell words: "significant" (statistical use only). Old P1 PDFs are in `_before_revision3/`.

---

## Our own score estimate (not a real review)

| Criterion (out of 5) | P1 | P2 |
|---|---|---|
| Originality | 3 | 3.3 |
| Technical soundness | 4 | 4 |
| Clarity | 4 | 4 |
| Significance | 3.3 | 3.5 |
| Reproducibility | 4.3 | 4 |
| **Overall** | **about 3.8** | **about 3.8** (was 3.4) |

Only the conference reviewers give the real score.

## What would still raise the score

1. **P2:** a co-author fills in the second-annotator sheet; we then report Cohen's kappa (highest value, no API calls).
2. **P2:** one more model family (Llama or Qwen); needs approval for API calls.
3. **P1:** run the fixed-angle circuit on real hardware or a hardware noise model.

## Submission checklist

- Upload only the `*_SUBMIT_blind_review.pdf` files.
- Run each through IEEE PDF eXpress with the conference ID.
- Check the venue's page limit and blind-review rule.
- Do not submit P5 to the same venue as P1 or P2, because it reuses their results.
- The AI-use disclosure stays in the Acknowledgment, as the IEEE policy requires.
