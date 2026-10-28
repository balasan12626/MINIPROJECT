# P3: "Verifier-Gated Tool Use: An Agentic Re-Planning Loop with a QAOA Solver for Flood Shelter Assignment"
7 pages · 20 references · 6 figures · 6 tables · 1 algorithm · overall **6.3 / 10**

## 1. CMT-style reviews (baseline)

**R1 (agents / planning)**: *Weak Reject, confidence 4*
- Summary: a monitor→planner→solver→verifier loop with fallbacks (greedy → exhaustive → human), a stability term and angle memory, tested on 30 five-event episodes.
- Strengths: clear loop design; honest that classical methods win; the stability and angle-memory results are practical.
- Weaknesses:
  1. **The headline results hold by construction.** The verifier removes invalid dispatches (0%) by definition. The "27/27 correct escalations, 0 wrong" result follows from exhaustive search being the last fallback: exhaustive search cannot miss a feasible plan. Neither is an empirical finding.
  2. The "raw" baseline (dispatch the most frequent sample) is a straw man. No one would deploy it.
  3. Verify-then-fallback is the Simplex architecture [8] and shielding [9]. Angle reuse is known [17], [18]. Plan stability is known [12]. The paper combines known parts.
  4. **Overlap with P1.** It uses the same instances, QUBO, mixer and seeds. If P1 is also submitted, it must be cited and the difference must be clear.

**R2 (methods / statistics)**: *Weak Reject, confidence 4*
1. Only one QAOA draw per event, so there is no variance. This is admitted twice, and the limitations paragraph repeats the same sentence.
2. **Inconsistency:** §V-F says the verified policy "reassigned 0.82 groups per re-plan" without the stability term, but Table VI (with memory, µ = 0) shows 0.72. Either the sentence refers to the cold-start configuration and must say so, or one of the numbers is wrong.
3. Eq. (5) predicts that fallbacks are rare unless P_feas is tiny. Report the observed P_feas at the 4 fallback events to support this.
4. Comparing optimality across µ is subtle, because "optimal" changes with µ. Report travel-time regret against the µ = 0 optimum as well.

**R3 (format / presentation)**: *Borderline on presentation*
1. **Fig. 6 is cited before Fig. 5** (§V-F: "Table VI and Fig. 6 …").
2. The Table IV footnote defines "fb." but the abbreviation is never used.
3. "The unverified top sample was invalid at E3 closure, E4 A failed" is an awkward fragment.
4. One limitations sentence is duplicated ("raw, verified and portfolio policies shared one QAOA draw…").
5. 7 pages, no DOIs.
6. The [14] Underhill reference is listed as "vol. 13, 2026". Vol. 13 of Front. Environ. Sci. is the 2025 volume (DOI 10.3389/fenvs.2025.1724250). Check the year.

**Meta-review**: Well written, but the contributions are either guaranteed by design or already known, and the paper overlaps heavily with P1. **Reject as a separate paper.** Merge its strongest parts (angle memory across events, stability term) into P1 as a "re-planning" section, or re-scope it as described below.

## 2. Ten scores
| Dim | Score | Justification |
|---|---|---|
| Novelty | 5.0 | The parts are Simplex, shielding, parameter transfer and plan repair. The main metrics are true by construction. |
| Gap clarity | 7.0 | The gap ("how an agent should verify and reuse a probabilistic optimiser over changing problems") is clearly stated. |
| Soundness | 6.0 | Straw-man baseline, single draw, table/text mismatch. |
| Math | 7.0 | Eqs (1)–(5) are fine. The tool-cost complexity paragraph is good. |
| Experimental design | 6.0 | 30 episodes on one fixed event script; no variance; one kind of infeasibility. |
| Results / justification | 7.0 | Good per-event breakdown; the stability result is well explained. |
| Related work | 6.0 | Good classical anchors; missing 2025 agent runtime-enforcement work (AgentSpec, RvLLM). |
| Presentation | 7.0 | Figure order, duplicated sentence, stray footnote. |
| English | 7.5 | Mostly natural, with a few broken fragments. |
| Format / references | 6.5 | 7 pages, no DOIs, a year to check. |

## 3. Novelty audit
| Work | Overlap with P3 |
|---|---|
| Sha, IEEE Software 2001 (Simplex) [8] | Same verify-and-switch architecture. |
| Alshiekh et al., AAAI 2018 (shielding) [9] | Same idea for learned policies. |
| Fox et al., ICAPS 2006 (plan stability) [12] | Same stability objective. |
| Galda et al., QCE 2021; Brandão 2018 [17], [18] | Angle transfer and concentration. |
| AgentSpec 2025; RvLLM NeurIPS 2025 | Runtime checks on agent actions and outputs. Not cited. |
| P1 (same authors) | Same instances, QUBO and mixer. |

**Verdict: largely already published as concepts.** Ways to make it new:
1. **Remove the exhaustive oracle from the fallback chain** and test at sizes where enumeration is impossible (G = 6–8; use MPS or a sampler instead of a statevector). Escalation correctness then becomes an empirical question.
2. **Make the verifier probabilistic-aware.** Choose the number of shots N online from Eq. (5) and a latency budget, and prove or measure the miss-rate bound. That is a real contribution.
3. **Fold it into P1** as "QAOA under re-planning: angle reuse across disruption events" (67% fewer evaluations). That is the one genuinely useful new number here.

## 4. Reference audit (20 references)
All exist. Checked: Underhill et al. (Frontiers, DOI 10.3389/fenvs.2025.1724250; **year probably 2025, not 2026**); Cadeliña 2024 OK; Galda QCE 2021 OK; Leucker & Schallhart 2009 OK; Fox ICAPS 2006 OK. Problems: no DOIs; 7 of 20 (35%) are from 2021–26.

## 5. Format audit
Figure order (Fig. 6 cited before Fig. 5); stray footnote; duplicated sentence; 7 pages; 9 index terms (cut to 5–6); "8143.2" vs "8143.3" ms (fine, but report 8.1 s); fonts and figures OK.

## 6. Overclaim check
- "never escalated a solvable case" is presented as a finding but is guaranteed by the exhaustive fallback. Say so.
- The title says "Verifier-Gated Tool Use" in general terms, but only deterministic Python agents are tested, with no LLM. Say "agent loop", not "tool-using agents" in the LLM sense, or add an LLM planner.

## 7. Venues
Best option: merge into P1 (IEEE QCE 2027). As a stand-alone paper: an AAMAS 2027 workshop or an IEEE SMC 2027 special session (verify).

## 8. TODO for authors
- Decide: merge into P1, or re-scope as above (your decision).
- [TODO-EXPERIMENT] 10 QAOA draws per event, giving mean ± std for all policies.
- [TODO-EXPERIMENT] A run without the exhaustive fallback at G ≥ 6.
- Fix: the 0.82 vs 0.72 inconsistency, figure order, duplicated sentence, the "fb." footnote, and the Underhill year.
