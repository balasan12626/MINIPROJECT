# P4: Reviewer Comments and Responses (revision of 15 October 2026)

Paper: *Three-Day High-Flow Exceedance at Held-Out Gauges: A Leakage-Controlled Benchmark on CAMELS-IND*

| File | Use |
|---|---|
| `P4_SUBMIT_blind_review.pdf` | Upload for double-blind review (no author names, checked) |
| `P4_camera_ready_with_authors.pdf` | After acceptance only |

Build: 6 pages, `ALL CHECKS PASSED`, references cited in order (19), no overfull lines, no Type 3 fonts. Every number comes from `post_p4.py` / `post_p4_r2.py`, which assert each claim. No new experiments were run in this round: the basin folds and five extra splits were already in `p4_r2.json` (13 Oct). Old files are in `P4_Forecasting_CAMELS_IND/_before_revision3_2026-10-15/`.

Status key: ✅ done · ⚠️ partly done (reason given) · ❌ not done (reason given)

## Major comments

| # | Reviewer comment | Status | What changed |
|---|---|---|---|
| M1 | "Unseen in space" may leak through gauges on the same river; need basin-aware split | ✅ | Leave-basin-out: 15 river basins in 5 folds, each held out once and tested on 2015–2020. BA 0.866–0.906, below-level BA 0.785–0.864 (Table V). |
| M2 | Only one random split | ✅ | Five more gauge splits: BA 0.877–0.898. The text now says the primary split lies at the upper end of that range (asserted). |
| M3 | Random-split inflation compares different test sets; 1.7 points is small | ✅ (wording) | Abstract, results, discussion and conclusion now call the 1.7-point gap "indicative": the test sets differ in gauges, years and flood rate. Prevalence difference stated. ⚠️ A same-rows re-score was not run. |
| M4 | LSTM comparison unfair; "indistinguishable" wording | ✅ | LSTM described as "an optimistic reference, not a held-out competitor" (sees future rain, likely trained on test gauges and 2015). Paired interval of the difference given instead of "indistinguishable". Matched-alarm-rate comparison added. ⚠️ No self-trained deep baseline (stated as a limitation). |
| M5 | Low novelty | ⚠️ | Contributions cut from 5 to 3 and reframed: "The classifier is a standard gradient-boosted model; what is new is the task, the split and what they show." Novelty is still modest. |
| M6 | Not an ungauged method | ✅ | New sentence in §III and in the abstract: each test gauge needs its 1980–2008 record and a flow reading on day t. |
| M7 | Low precision; no POD/FAR/CSI | ✅ | CSI column in Tables II and VI; POD = recall and FAR = 1 − precision defined. Honest result: persistence has the highest CSI (0.448; LSTM 0.349, model 0.317); only threshold 0.75 lifts the model above it (0.461). |
| M8 | q95 is not an official danger level | ✅ | Stated in §III, Limitations; title says "High-Flow Exceedance"; 99th-percentile run reported. |
| M9 | Pooled lead days; onset skill belongs in the abstract | ✅ | Below-level BA (0.857) and the LSTM's lead on those rows are in the abstract. |
| M10 | No rainfall-forecast inputs | ⚠️ | Stated as an upper bound and as a limitation; needs new data. |

## Findings of the second review (strict reviewer + plain-English checker)

| # | Finding | Status | What changed |
|---|---|---|---|
| W1 | "Onsets need flow and meteorology together" is contradicted by the ablation (removing flow: 0.852 → 0.846; flow + season alone: 0.810) | ✅ | Contribution, ablation, discussion and conclusion now say skill on rivers below their level "comes mainly from meteorology". |
| W5 | Test is effectively 2015–2018 | ✅ | Limitation added (few CAMELS-IND flow records for 2019–2020). |
| — | Rendering bug "one of these 1 gauges" | ✅ | Now "of the 49 unseen gauges, 1 has no flow record in 2015–2020, which leaves 48 test gauges". |
| — | Abstract read as if persistence had PR-AUC 0.750 | ✅ | Sentence reordered; PR-AUC defined. |
| — | Text said single groups change below-level BA by "less than 0.005"; the true maximum is 0.0051 | ✅ | Now a macro (`\AblOnTol` = 0.006) with an assert. |
| — | "Onset rows" (river below level) confused with the 266 "flood onsets" | ✅ | Renamed "below-level rows" in text and tables. |
| — | Unweighted refit (BA 0.902, ECE 0.008) never discussed | ✅ | Text says it matched the selected model and is the better deployment choice; the weighted model is reported because it was selected on validation before testing. |
| — | Model selection unequal (only the selected model refit on all rows) | ✅ | Stated. |
| — | "beat", "stable", "neither easy nor hard" too strong | ✅ | Replaced with "scored above", the measured ranges, "upper end of the range". |
| — | Dam correlation tested without multiplicity correction | ✅ | Labelled exploratory. |
| — | Mosavi review cited for "often with random splits" | ✅ | Clause removed. ECE now cites Naeini et al. (AAAI 2015). |
| — | IMD, IMDAA, GLEAM, LSTM, PR-AUC, ECE not expanded | ✅ | Expanded at first use. |
| — | INDOFLOODS thanked but not used | ✅ | Removed from the Acknowledgment. |
| — | Long sentences, comma splice, dangling modifiers, missing articles | ✅ | Fixed (Methods model sentence, robustness sentence, CSI sentence, LSTM sentence, episodes sentence). |
| — | Trend rule CI "–" unexplained | ✅ | Footnote: "not resampled". ⚠️ Bootstrap for it not run. |
| — | Fig. 2 omits the trend rule | ❌ | Not changed (figure regeneration; low priority). |
| — | Same-rows re-score of the random split (reviewer Q1) | ❌ | Needs a re-run; the text calls the gap indicative instead. |

## Space (7 → 6 pages)

Removed: Table I (position, now one sentence), Table III (candidate models, now one sentence), Fig. 3 (gain importance, numbers kept in text), Table X (lead day, numbers kept in text), Fig. 5 (catchment area, ρ and p kept in text). Merged the operating-point and season tables (with CSI). Title shortened from 4 lines to 2. Protocol list turned into one sentence. Repeated Results text trimmed.

## Our own score estimate (not a real review)

| | Before (11 Oct PDF) | Now |
|---|---|---|
| Strict reviewer, overall | 3.2 / 5 Borderline | about 3.4 / 5, between Borderline and Weak Accept |

What would still raise it: a deep baseline trained on the same split (no future rain); a same-rows re-score of the random split; rainfall-forecast inputs.

## Note on P5

P5 reuses P4's macros (prefix `Fc`). The P4 wording changed ("indicative gap", "below-level", "mainly from meteorology"), so P5 must be rebuilt and its P4 summary re-read before P5 is submitted.

---

# Round 4 (15 October 2026, afternoon): seven-agent check, new experiments, final fixes

New experiments (all offline, primary split, 500,000-row refits unless stated; scripts `exp_p4_r3.py`, `exp_p4_r4.py`; results `p4_r3.json`, `p4_r4.json`, also copied to `shared_code/results_snapshot_2026-10-14/`):

| Weakness | Experiment | Result | Paper change |
|---|---|---|---|
| Climate indices hold test-year rainfall (audit: shipped indices best match 1980-2020) | Recomputed from 1980-2008 forcing; and dropped | BA 0.897 and 0.896 vs 0.898; paired intervals include zero | Disclosed in III-B; rows in Table IV |
| Not real-time | Dropped late reanalysis inputs (humidity, GLEAM PET/AET, soil moisture) | BA 0.893, loss 0.005 (interval just above zero); below-level loss not detectable | Abstract, V-D, Table IV |
| Leakage gap compared different test sets | Random-split model and held-out model on the SAME 10,793 rows | BA 0.925 vs 0.906 (gap 1.2-2.5 points), PR-AUC 0.803 vs 0.771 | Now a tested measurement (abstract, V-B, conclusion) |
| "Onsets announced by weather" | Onset warnings at a common alarm rate | No-flow 88.7% vs 89.5%: its higher raw count came from more alarms | Claim removed and replaced |
| "Mainly from meteorology" (no intervals) | Paired gauge bootstrap of below-level BA | Removing flow: not detectable; removing others: significant; met vs flow alone: not resolved | Reworded everywhere |
| Logistic regression only on validation | Scored on test | BA 0.893, PR-AUC 0.682 (boosting adds about 5 PR-AUC points) | Table IV, V-D |
| Gauge-only CIs too narrow | Gauge x year block bootstrap | 0.870-0.916 (was 0.886-0.910) | Abstract, V-A |
| Trend rule had no CI / missing from Fig. 2 | Bootstrapped; PR curve stored | 0.811-0.845; added to Fig. 2 | Table I, Fig. 2 |
| Persistence wins CSI | Decision rules with thresholds chosen for validation CSI, test scored once | Model at CSI threshold 0.490, hybrid (persistence when high, model otherwise) 0.500 vs persistence 0.448 (both intervals exclude zero); onset warnings fall from 91% to 54%; seasonal thresholds no gain | New Section V-F and Table V |

Text fixes: 2019 and 2020 now reported (lower BA); earlier test scoring of the sample model disclosed; LSTM "led" changed to "within sampling noise"; primary split stated as the most favourable of six, with the six-split mean (0.889) leading the abstract; log flow is unscaled; partial horizons disclosed; persistence on missing readings stated; "in our system" removed; Fig. 4 (deployment sketch) removed; two references added (Jolliffe and Stephenson 2012; Zadrozny and Elkan 2002) plus Naeini et al. 2015. Not done (user decision): a deep baseline on the same split (PyTorch not installed).

Build: 6 pages (blind and camera), ALL CHECKS PASSED, 21 references in citation order, no overfull lines, no Type 3 fonts, blind copy anonymous. Previous files: `P4_Forecasting_CAMELS_IND/_before_revision4_2026-10-15/`.

# Round 5 (15 October 2026): neural baseline, trade-off figure, readability

| Change | Result |
|---|---|
| Neural baseline on the same split and sample (scikit-learn MLP 128-64, inputs plus a 14-day history; `exp_p4_r5.py`) | BA 0.862, PR-AUC 0.596, below-level BA 0.822; XGBoost higher on all three (intervals exclude zero). No LSTM: PyTorch not installed by the authors' choice. |
| Model-alone CSI rule vs persistence (paired interval added to `exp_p4_r4.py`) | Gain 0.019 to 0.065 |
| Trade-off curve, CSI vs onsets warned (new Fig. 3, replaces the rules table) | Every threshold warning of at least 80% of onsets has CSI at most 0.424 |
| Readability | Protocol, robustness, operational and warning paragraphs rewritten with one message each; numbers that the tables carry removed from the text |

Build: 6 pages, ALL CHECKS PASSED. Copy also in `10OCT/16/`.

# Round 6 (15 October 2026)

New title: *When Random Splits Flatter Flood Forecasts: Three-Day High-Flow Warnings at Held-Out Indian Gauges*. Seven reviewer points fixed (random-alarm baseline now compared with the matching measure; 228 vs 242 gauges explained; abstract comma; dropped-day and Brier figures given; unweighted refit threshold stated; bound written as 'less than 0.006'). Fresh reviewer score before these fixes: 4/5 overall, 4/5 humanised writing.

