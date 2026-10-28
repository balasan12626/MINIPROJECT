# P4: "Fail-Closed Flood Evacuation Decision Support: Gauge-Held-Out Forecasting and a Constraint Shield for Learned Route Proposals"
7 pages · 21 references · 4 figures · 7 tables · overall **6.4 / 10**
**Highest priority:** this is the closest descendant of the rejected INDICON paper (HQRL + XAI evacuation). It still has the same "three systems stitched together" shape that drew "limited novelty / random application of known concepts".

## 1. CMT-style reviews (baseline)

**R1 (hydrology / flood forecasting)**: *Borderline, confidence 4*
- Strengths: the evaluation design is genuinely good. Gauges are held out in space and in time, the threshold is chosen on validation, the test set is used once, there is a persistence baseline, results are reported per gauge, and the operating points are described. Saying that "persistence lies on the model's PR curve" is admirably honest.
- Weaknesses:
  1. **"242 CAMELS-IND gauges" vs ref [8], titled "228 catchments".** The Zenodo v2.2 release lists 242 gauges with streamflow, while the ESSD paper says 228. Cite the dataset version (Zenodo DOI 10.5281/zenodo.14005378, v2.2) and explain the number.
  2. **The abstract says "Trained on 242 gauges and tested on 49 held out".** §IV shows that training used the other ~193, and only 48 test gauges have 2015–2020 data. Fix the abstract.
  3. The model uses **today's observed streamflow** (qr_l0 carries 37% of the gain). The comparison with Nearing et al. [1] (truly ungauged basins) is therefore not like-for-like. "Unseen gauges" here means "gauges not in training, but whose live flow is observed". State this clearly.
  4. Missing baselines: LSTM, which CAMELS-IND itself ships as a regional LSTM baseline, and a climatology baseline.
- Questions: What is the precision at the onset-only evaluation per gauge? Are the 48 test gauges spatially independent of the training basins, i.e. not nested in the same river?

**R2 (methods / routing / safe RL)**: *Reject, confidence 4*
1. **The QUBO shield is decorative.** §III-C says that "candidates with v_k > 0 are removed before solving", so the QUBO only selects the minimum-cost item from a feasible list. That is an argmin, and an SA or "QAOA-inspired" solver adds nothing (as the paper itself observes). The title and contribution 2 overstate it.
2. **There is no learned proposer.** The title says "Learned Route Proposals" and the index terms include "safe reinforcement learning", but the proposer is a hand-written online weight update (§III-C admits "not a trained deep PPO agent"). This is the overclaim the INDICON reviewers punished.
3. Flood-aware A* matches the shield and is 15× faster, so the routing contribution has no positive result.
4. The severity sweep had no effect because of a generator bug (depths never cross 0.75). Fix the generator and re-run rather than report it.
5. The risk score (Eq. 2) uses hand-set coefficients and **does not use the forecaster evaluated in the paper** (§VI). The three stages are therefore not one pipeline in the evaluation.
6. The reliability values are hand-set constants, and the conflict score is scripted.

**R3 (format / presentation)**: *Borderline*
1. Three different studies in 7 pages leave little depth for any of them.
2. The ± s.d. in Table IV are over binary per-scenario outcomes. Wilson CIs would be clearer.
3. 7 pages; no DOIs; [9] INDOFLOODS has no volume, pages or DOI; [20] Underhill year (vol. 13 = 2025).
4. 7 index terms; "safe reinforcement learning" is not supported.

**Meta-review**: The forecasting half is publishable work with a careful, leakage-controlled evaluation. The routing and gating half repeats the INDICON weaknesses. **Weak Reject as is. Split the paper.**

## 2. Ten scores
| Dim | Score | Justification |
|---|---|---|
| Novelty | 5.0 | Each part is a known technique (XGBoost exceedance, shield/filter, threshold gate), and they are not deeply integrated. |
| Gap clarity | 6.5 | "How to join the stages so failures fail closed" is reasonable but spread across three gaps. |
| Soundness | 6.0 | Forecasting is sound. The routing QUBO is trivial after filtering, the proposer is not learned, the forecaster is not wired into the risk score, and the abstract's gauge counts are wrong. |
| Math | 6.5 | Eqs (1), (4) and (5) are fine. Eq. (2) is ad hoc. Eq. (3) is redundant after filtering. |
| Experimental design | 7.0 | Excellent forecasting split. Routing is a 15-node synthetic network with a generator bug. |
| Results / justification | 7.5 | Honest negatives, per-gauge spread, operating-point table, a worked shield trace. |
| Related work | 6.0 | Missing 2023–26 flood RL routing (e.g. ReinforceRouting, IJGIS) and LSTM CAMELS baselines. |
| Presentation | 7.0 | Dense; three stories compete. |
| English | 8.0 | Clear and natural. |
| Format / references | 6.5 | 7 pages, incomplete references, no DOIs. |

## 3. Novelty audit
| Work | Method | Limitation vs P4 |
|---|---|---|
| Nearing et al., Nature 2024 [1] | global LSTM, ungauged | Truly ungauged. P4 uses observed flow. |
| Kirschstein & Sun, ICML 2024 [7] | river-topology GNN | Better lead times. Not a baseline in P4. |
| Mangukiya et al., ESSD 2025 [8] | CAMELS-IND plus a regional LSTM baseline | Its LSTM predictions are an obvious missing baseline. |
| Liu et al., NHESS 2025 [2] | DQN storm-surge evacuation | Real RL. P4 has none. |
| Raei et al., ISPRS Archives 2026 [3] | MARL wildfire evacuation | Real RL on a real network (Lytton, BC). |
| ReinforceRouting (IJGIS, 2023/24) | RL flood evacuation routing | Missing; closest competitor (verify reference). |
| Alshiekh et al. 2018 [4] | shielding | P4's shield is a filter, not a formal shield. |

**Verdict: the routing part adds nothing to the state of the art. The forecasting part is a solid incremental study.** Recommended re-scope:
1. **Paper 4a (submit):** "Three-day flood-exceedance forecasting on gauges held out in space and time: CAMELS-IND". Add the CAMELS-IND LSTM baseline, climatology, onset-only per-gauge analysis, and calibration. This is a clean, honest and publishable paper.
2. **Paper 4b (later):** a real shield (with a trained PPO or DQN proposer) on the Delhi OSM graph, with congestion dynamics where A* is actually weak. Only then is "shield for learned proposals" a true title.
3. Drop the QUBO from the routing story, or use it where filtering is impossible, i.e. joint assignment of many groups under shared capacity (which is P1's problem).

## 4. Reference audit (21 references)
Checked online: Liu et al. NHESS 25, 4767–4786 (2025) OK, DOI 10.5194/nhess-25-4767-2025. Raei et al. ISPRS Arch. XLIX-M-1-2026, 41–50 OK, DOI 10.5194/isprs-archives-XLIX-M-1-2026-41-2026. Mangukiya et al. ESSD 17, 461–491 (2025) OK, DOI 10.5194/essd-17-461-2025. INDOFLOODS (Kuntla & Saharia, BAMS 2025) exists, but **the volume, pages and DOI are missing**. Underhill et al. exists, but **the year should probably be 2025**. Cadeliña 2024 OK. The rest are standard and correct.
7 of 21 (33%) are from 2021–26. No DOIs.

## 5. Format audit
- 7 pages.
- Index terms include an unsupported term ("safe reinforcement learning").
- Incomplete reference [9].
- Fig. 1–4 are cited in order (OK).
- Table V has dense, run-together columns in the PDF (check for an overfull hbox).
- Fonts and figures OK.

## 6. Overclaims (fix even if nothing else changes)
- Title: "Learned Route Proposals". The proposer is not learned.
- Abstract: "Trained on 242 … tested on 49". Should be ~193 for training and 48 for test.
- Contribution 2: "QUBO penalties" for the shield. The QUBO has no role after filtering.
- Index term "safe reinforcement learning".
- "Gauge-held-out" is accurate. Do not call it "ungauged".

## 7. Venues (verify)
Paper 4a: IEEE IGARSS 2027 (geoscience; 4-page format), IEEE TENCON 2027, IEEE India Council INDICON 2027 (a resubmission must be substantially new). Paper 4b: none yet.

## 8. TODO for authors
- Decide whether to split (recommended).
- [TODO-EXPERIMENT] CAMELS-IND regional LSTM baseline and climatology on the same 48 gauges and years.
- [TODO-EXPERIMENT] Reliability diagram / Brier score for XGBoost.
- [TODO-EXPERIMENT] Fix the scenario generator (depths that cross 0.75) and re-run the severity sweep.
- [TODO] State the dataset version (Zenodo v2.2), fix the abstract gauge counts, and complete reference [9].
