# P1: "Constraint-Preserving QAOA for Flood Shelter Assignment: A Statevector Study on Digital-Twin Instances"
7 pages · 18 references · 5 figures · 7 tables · 1 algorithm · overall **6.8 / 10**

## 1. CMT-style reviews (baseline)

**R1 (domain: quantum optimisation)**: *Weak Reject, confidence 4*
- Summary: compares the X and ring-XY mixers and mean vs CVaR training on 30 shelter-assignment QUBOs with 12 qubits, adds a noise study and a scaling run up to 18 qubits.
- Strengths: careful and honest ("we claim no quantum advantage"); exact feasibility re-check; worked instance; two noise models; equal two-qubit gate budget (Table V) makes the mixer comparison fair.
- Weaknesses:
  1. The main finding, that XY beats X on one-hot problems, is already established [7], [8] and in recent applied work (XY + warm start for VRP, arXiv 2504.19934, 2025; constraint-preserving QAOA for rostering, arXiv 2607.09145, 2026, which has an almost identical title). The paper must state what is new beyond "a new application".
  2. There is no Grover-mixer (GM-QAOA) or warm-start (Egger [14]) baseline, which are the obvious alternatives for a feasible subspace of size 81.
  3. The X mixer is run with a single penalty P. A reviewer will ask whether a tuned penalty or a slack encoding changes the ranking.
  4. Twelve qubits and one synthetic network make it hard to say anything general.
- Questions: How sensitive is P_opt to P for the X mixer? Why the ring XY and not the complete-graph XY?

**R2 (methods / statistics)**: *Borderline, confidence 4*
1. Results are means over 30 instances with no confidence interval or paired test. Add a paired Wilcoxon test of XY vs X on P_opt per instance and bootstrap 95% CIs (cheap, since the data exists).
2. Training variance is missing: there are only two random starts and one INTERP start. Report several optimiser seeds per instance.
3. At depth 4 the evaluations hit the 750 cap (Table I), so the depth trend is budget-limited, as the paper admits. Run one experiment with a larger budget.
4. Simulated annealing with 60 sweeps and one restart is a straw man. Use a tuned SA, or drop it and keep exhaustive search + greedy.
5. The Table I footnote says "Evals = objective evaluations at depth p", but §VI-A says "750 … including the restarts at lower depths". Make these consistent.
6. Lemma 1 is correct, but it is a one-line bound. Call it an observation, or extend it, for example with a condition under which the pairwise encoding is exact.

**R3 (format / presentation)**: *Weak Accept on presentation only*
1. The paper is 7 pages, over the usual 6-page limit.
2. There are no DOIs. Only 6 of 18 references (33%) are from 2021 or later.
3. Spelling mixes British and American forms ("penalises", "optimise", "Trotterised" next to "optimization"). IEEE prefers American spelling.
4. Index Terms should be 4–6 items. There are 8, and "QAOA" and "quantum alternating operator ansatz" repeat each other.
5. Table I (16 rows) could become a compact figure plus a smaller table to recover space.

**Meta-review**: The work is solid and honest but incremental. To pass, it needs a novelty claim that survives the 2020–2026 constraint-preserving QAOA literature, statistical tests, and at least one stronger quantum baseline. **Weak Reject** in its current form.

## 2. Ten scores
| Dim | Score | Justification |
|---|---|---|
| Novelty | 5.5 | XY > X on one-hot problems is known. The new parts are evacuation-shaped instances, the capacity "binding vs non-binding" split, and the gate-level vs global noise comparison. These are modest. |
| Gap clarity | 7.5 | The gap is stated explicitly (§II, "Research gap"), but it is narrow ("not evaluated on capacity-constrained evacuation instances"). |
| Soundness | 7.0 | The method is correct, feasibility is re-checked and the gate budget is fair. The weak SA baseline, single penalty, budget cap and missing seed variance hold the score down. |
| Math | 7.5 | Eqs (1)–(7) are clean, Lemma 1 is correct and the CVaR definition is right. There is no notation table and the Lemma is trivial. |
| Experimental design | 6.5 | 30 instances on one network; no statistics; missing GM-QAOA and warm-start baselines. |
| Results / justification | 7.5 | Good explanation of why CVaR lowers mean P_opt but raises success@32, a per-instance spread, and a worked instance. |
| Related work | 5.5 | 18 references, few from 2023–26, and no recent applied constrained-QAOA papers. |
| Presentation | 7.5 | Clear pipeline figure and good tables. Slightly over-long. |
| English | 8.0 | Natural, specific, no AI tells. Spelling is inconsistent. |
| Format / references | 6.5 | 7 pages, no DOIs, 8 index terms. |

## 3. Novelty audit (closest work, checked by search)
| Work | Method | Instances | Limitation vs P1 |
|---|---|---|---|
| Wang et al., PRA 2020 [7] | ring/complete XY mixers | graph colouring | Already shows XY > X. P1 adds no new theory. |
| Fuchs et al., Algorithms 2022 [8] | general constraint-preserving mixers | generic | Already covers P1's mixer class. |
| Bärtschi & Eidenbenz, IEEE QCE 2020 (Grover mixers) | GM-QAOA | constrained problems | Missing from P1. It is the natural competitor. |
| arXiv 2504.19934 (2025) | warm-start + XY mixer | VRP sub-problems | Missing. It combines two things P1 treats separately. |
| arXiv 2607.09145 (2026) | coverage-preserving / guarded-XY mixers | personnel rostering | Missing. Its title is nearly the same as P1's, so P1 must differentiate. |
| arXiv 2312.06922 (2023) | QAOA+ for uncapacitated facility location, slack variables | facility location | Relevant to P1's capacity encoding. |
| Cadeliña et al., ECTI-CIT 2024 [3] | D-Wave QUBO, disaster vehicle routing | Marikina City | Annealer only; no mixer comparison. |
| Yin et al., Front. Public Health 2023 | quantum *genetic* algorithm, shelter allocation | city scale | Quantum-inspired only, not QAOA. |
| Harrigan et al., Nat. Phys. 2021 [15] | hardware QAOA | MaxCut / SK | Shows that hardware performance degrades. |

**Verdict: incremental.** Three feasible ways to make it new:
1. **Capacity-aware mixer.** Design a mixer that also preserves (or softly guards) the capacity constraint. A Dicke-state/XY hybrid would do it, since a capacity limit is a Hamming-weight limit per shelter column. Compare it with pairwise penalties. This would be a genuinely new construction.
2. **Theory for the pairwise encoding.** Give a condition on the n_g and R_s under which the pairwise encoding is exact, and measure the 93.3% exactness against it. This turns Lemma 1 into a real result.
3. **Angle transfer across disruption states.** Train once and transfer to all 30 instances (concentration). Report P_opt with zero per-instance training. This is new for evacuation and useful in practice.

## 4. Reference audit (18 references)
All 18 exist and their bibliographic details are correct as far as checked. Cadeliña 2024 was confirmed on the ECTI-CIT site, vol. 18 no. 1 pp. 24–33. The others are standard, well-known papers.
Problems: no DOIs; 6 of 18 (33%) are from 2021–26, below the 50% target; [5] Farhi is arXiv-only (standard and acceptable, but pair it with the published version of [6]); [11] Sherali 1991 is fine as a classic.
References to add: Bärtschi & Eidenbenz QCE 2020 (Grover mixers); Blekos et al. 2024 QAOA review (Physics Reports); arXiv 2504.19934; arXiv 2607.09145; a slack-encoding paper. **Verify each with Crossref before citing.**

## 5. Format audit
- 7 pages, over the usual 6 → cut, or check the venue's extra-page rule.
- 8 index terms → reduce to 5–6.
- Mixed UK/US spelling → convert to US.
- No DOIs → add them.
- Fonts embedded, no Type 3 fonts, vector figures, captions placed correctly (tables above, figures below), equations numbered → OK.
- Figures are cited in order (Figs 1→5) → OK.

## 6. Overclaim check
The title, abstract and conclusion match the results, and the "no quantum advantage" claim is stated clearly. One small issue: the abstract says the XY mixer "kept most of its probability on feasible plans at every depth". That is true (0.66–0.80), but "most" at 0.66 should be stated as a number.

## 7. Venues (verify dates)
IEEE QCE 2027 (Quantum Week; QCE26 abstracts were due April 2026, so expect roughly the same month in 2027). IEEE ICRC (Rebooting Computing). IEEE CAI 2027 (quantum-AI track, if one exists).

## 8. TODO for authors (needed to reach ~8+)
- [TODO-EXPERIMENT] Paired Wilcoxon test plus bootstrap CIs, XY vs X, per depth. The per-instance data already exists, so this is a script only.
- [TODO-EXPERIMENT] 5 optimiser seeds per instance at p = 4. Report mean ± std.
- [TODO-EXPERIMENT] GM-QAOA (Grover mixer over the 81 one-hot plans) as a third mixer.
- [TODO-EXPERIMENT] X-mixer penalty sweep (P × {0.5, 1, 2, 4}).
- [TODO-EXPERIMENT] Tuned SA (many restarts), or remove SA.
- Pick one of the novelty options in §3 and make it the headline contribution.
- Cut to 6 pages, add DOIs, add 5–8 verified references from 2023–26.
