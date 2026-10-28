# P1 final review (fresh-reviewer pass on the revised 6-page version)

## Reviews
**R1 (quantum optimisation)**: *Weak Accept, confidence 4*
The angle-transfer result is the paper's real contribution, and it is tested properly: a leave-one-out test, a held-out set, and then real road networks. It is also practically meaningful (training moves offline). The mixer comparison is now replicated and tested.
Remaining concerns:
- All results are classical simulation at 12 qubits.
- There is no hardware run, even though fixed angles would make one cheap.
- Exhaustive search solves everything in 0.9 ms, which the authors state.

**R2 (methods)**: *Accept, confidence 4*
Seeds, paired tests, Holm correction, bootstrap CIs, a held-out split, a fair penalty sweep and tuned SA are all present.
Minor points:
- The per-instance budget is capped, so "transfer beats training" partly reflects the optimiser budget. The authors say so, and show that transfer equals the best of 5 seeds.
- City demand is sampled, not recorded.

**R3 (presentation)**: *Accept*
6 pages, clean tables, DOIs throughout, 5 index terms, 248-word abstract, no overfull boxes, references ordered by first citation.

**Meta-review: Weak Accept → Accept** at QCE-type venues. The core risk is now relevance (classical methods dominate), not soundness.

## Scores (before → after)
| Dimension | Before | After | Why |
|---|---|---|---|
| Novelty (×2) | 5.5 | **7.5** | Transfer under inequality constraints, across disruptions and real networks, is new. The mixer finding alone was not. |
| Gap clarity | 7.5 | **8.5** | Positioning table plus explicit three-part gap |
| Soundness (×2) | 7.0 | **8.5** | Seeds, tests, held-out, penalty sweep, tuned SA |
| Math | 7.5 | **7.5** | Formulation fine; transfer rule formalised; no deeper theory |
| Experimental design | 6.5 | **9.0** | Dev/held-out/real-network splits, statistics, strong baselines |
| Results & justification | 7.5 | **8.5** | Explains why transfer works (energy scaling) and where it doesn't (X mixer) |
| Related work | 5.5 | **8.5** | 26 verified references, 2023–26 work included |
| Presentation | 7.5 | **8.5** | 6 pages, clean figures |
| English | 8.0 | **8.5** | |
| Format & references | 6.5 | **9.0** | DOIs, order, page limit |
| **Overall (weighted)** | **6.8** | **8.3** | |

## Why not 9.5 (honest)
To go higher, the paper needs things editing cannot add:
1. **A hardware run.** The fixed angles make a 12-qubit XY circuit runnable on IBM Quantum's free tier without any on-device training. Even one instance on hardware would lift novelty and relevance.
2. **Larger instances** (20–30 qubits with a tensor-network simulator), to show that transfer survives where enumeration starts to hurt.
3. **Recorded demand** (real evacuation group sizes and shelter capacities) for the city instances.

## Update — round 3 (2026-10-10)
Added transfer to 15 and 18 qubits and transfer under gate noise (Section V-D, Table V). This answers the reviewer
question "do the angles survive a larger problem?" up to 18 qubits. The mean gain is **not** significant with ten
instances per size, and the paper says so; the robust finding is that fixed angles never collapse, while per-instance
training does (success@32: 63→100% at 15 q, 39→92% at 18 q), and the gain holds under 1% two-qubit noise.

| Dimension | Round 2 | Round 3 |
|---|---|---|
| Novelty (×2) | 7.5 | **7.8** |
| Soundness (×2) | 8.5 | **8.8** |
| Results & justification | 8.5 | **9.0** |
| Other dimensions | unchanged | unchanged |
| **Overall (weighted)** | **8.3** | **8.5** |

Remaining for 9+: one hardware run of the fixed-angle 12-qubit XY circuit (IBM free tier), or 20–30 qubits with a
tensor-network simulator. Neither can be produced by editing.
