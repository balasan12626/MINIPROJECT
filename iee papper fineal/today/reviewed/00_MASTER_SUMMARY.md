# UPDATE: revision of P1 and P2 (2026-10-10, evening)

| Paper | Before | After | What changed | Ready? |
|---|---|---|---|---|
| **P1** QAOA → *"Constraint-Preserving QAOA with Transferable Angles for Flood Shelter Assignment"* | 6.8 | **8.3** | New contribution (angle transfer, held-out and real OSM city networks); 5 seeds; paired tests; Grover baseline; penalty sweep; tuned SA; 26 verified references with DOIs; 6 pages | **Yes**, after you read it through |
| **P2** Rules Decide, LLMs Narrate | 6.7 | **8.3** | 300 real LLM replies with reference labels; LLM-judge baseline; held-out calibration study with a reliability figure; 22 verified references with DOIs; 5 pages | **Yes**, after you check the labels (judge covered 201/300; finishing it is optional) |
| P3 | 6.3 | — | Not revised. Its angle-memory idea is now covered by P1's transfer result, so **do not submit it separately** | No |
| P4 | 6.4 | — | Not revised. Split it: the forecasting half is a separate paper | Needs rework |

Final files: `P1_Quantum_QAOA/final/` and `P2_Agentic_AI/final/` (blind and camera-ready PDF and .tex, figures, data, scripts). Per paper: `03_change_log.md`, `04_final_review.md` and `05_todo_for_authors.md`.
**Why 8.3 and not 9.5:** the remaining gaps need things only you can provide: a hardware run (P1), a second annotator (P2) and a bigger model or data set. Each `04_final_review.md` lists them.

---

# Full audit of the 4 papers in `today\` (2026-10-10)

**Source check.** The four PDFs in `today\` are the blind-review builds from `series_versions\4_extended_7pages\`. Paper 2 and Paper 4 are byte-identical to those builds. Paper 1 and Paper 3 are recompiles made 5 minutes later. The editable `.tex` for every paper is in `series_versions\4_extended_7pages\<paper>\camera_ready_with_authors.tex`.
**Backup.** The untouched originals are in `iee papper fineal\today_originals_backup_2026-10-10\`.
**Scope.** This is the baseline audit (Phase 0 + Phase 2). No paper text was changed.

## Scores out of 10

Overall = weighted mean. Novelty and soundness count double, so the weights total 12.

| # | Dimension | P1 QAOA | P2 Agentic AI | P3 Agentic+Quantum | P4 Full scenario |
|---|---|---|---|---|---|
| 1 | Novelty / originality (×2) | 5.5 | 6.0 | 5.0 | 5.0 |
| 2 | Problem & gap clarity | 7.5 | 7.0 | 7.0 | 6.5 |
| 3 | Technical soundness (×2) | 7.0 | 6.5 | 6.0 | 6.0 |
| 4 | Mathematical formulation | 7.5 | 7.0 | 7.0 | 6.5 |
| 5 | Experimental design | 6.5 | 6.0 | 6.0 | 7.0 |
| 6 | Results & justification | 7.5 | 7.5 | 7.0 | 7.5 |
| 7 | Related work (2022–26) | 5.5 | 6.0 | 6.0 | 6.0 |
| 8 | Presentation / figures / tables | 7.5 | 7.5 | 7.0 | 7.0 |
| 9 | English / natural voice | 8.0 | 8.0 | 7.5 | 8.0 |
| 10 | IEEE format & references | 6.5 | 6.5 | 6.5 | 6.5 |
| | **Overall** | **6.8** | **6.7** | **6.3** | **6.4** |
| | Likely CMT verdict today | Weak Reject / Borderline | Weak Reject / Borderline | Weak Reject | Weak Reject |

**Honest bottom line.** None of the four papers can reach 9+ by editing alone. The writing is already good, with clear English, honest limits and no hype. What keeps the scores down is research substance:
- each paper's main idea is already known in the literature
- the experiments are small: one synthetic 15-node network, 12 qubits, and LLM errors that the authors injected themselves
- strong recent baselines are missing

These are the same problems behind the INDICON rejection ("limited novelty") and the STCR rejection ("random application of well-known concepts", "weak justification"). With the experiments listed in each `05_todo_for_authors` section, P1 and P2 can realistically reach about 8–8.5. P3 and P4 need to be re-scoped.

## Problems that affect all four papers (fix these first)

1. **Four papers come from one prototype.**
   - P1 and P3 use the same twin, seeds (42+17i), R5 closure, Shelter A surge, QUBO and XY mixer.
   - P2 and P4 share the same gated policy (τ = 0.50 / 0.60) and the same health checks.
   - P4 is the closest descendant of the INDICON paper that was already rejected.

   Copied wording is low (1–2% shared 8-word phrases, mostly the acknowledgment), but the data and ideas overlap heavily. If two of these are under review at the same time without citing each other, they can be flagged as duplicate or "salami" submissions under IEEE policy. **Submit P1 and P2 first.** They are the most distinct papers. Fold P3 into P1, or hold it until P1 is accepted and cite it in the third person. Re-scope P4 as described below.
2. **Length is 7 pages.** Most IEEE conferences allow 6 pages, often with paid extra pages, and some allow 5 for review. Check the target venue's limit before submitting.
3. **No reference has a DOI.** Most target venues ask for DOIs where they exist, so add them.
4. **Recent references are too few.** Only 33–42% of references are from 2021–2026. Each related-work section misses work from 2024–26 that reviewers will know (listed per paper).
5. **The acknowledgment appears in the blind PDFs.** It names no people, but many CMT venues want acknowledgments removed for review. Keep the IEEE AI-use disclosure, but move it to the camera-ready version if the venue says so.
6. **Clean points.** All fonts are embedded, there are no Type 3 fonts, the page size is US Letter, the PDF author/title metadata is blank (good for blind review), all figures are vector, and no page numbers or headers were found.

## Master table

| Paper | Before | After (est.) | Biggest remaining risk | Ready to submit? | Best-fit venue (verify dates) |
|---|---|---|---|---|---|
| P1 Constraint-Preserving QAOA | 6.8 | ~8.0 with TODOs | "XY beats X on one-hot problems is already known" (Wang 2020, Fuchs 2022) | After TODOs | IEEE QCE 2027 (Quantum Week, applications track); IEEE ICRC |
| P2 Rules Decide, LLMs Narrate | 6.7 | ~8.3 with TODOs | No real LLM outputs evaluated (only 1 real reply) | After TODOs | IEEE CAI 2027 (Singapore; paper call not yet published); IEEE SMC 2027; IEEE R10 HTC |
| P3 Verifier-Gated Tool Use | 6.3 | ~7.0 | Result is close to tautological (exhaustive search is the last fallback); heavy overlap with P1 | Needs major rework, or merge into P1 | Merge into P1, or a workshop at QCE / AAMAS |
| P4 Fail-Closed Flood DSS | 6.4 | ~7.5 if split | Three loosely coupled systems; the QUBO does nothing after filtering; nearest to the rejected INDICON paper | Needs major rework (split the forecasting part into its own paper) | Forecasting part: IEEE IGARSS 2027 or IEEE TENCON; routing part: not yet |

Deadline status: the IEEE CAI 2027 paper call says "coming soon". QCE26 deadlines have passed and QCE27 has not been announced. GHTC 2026 is running now and its deadlines are closed. Check every venue's site before you plan around it.

Per-paper detail: `P1_.../review.md` … `P4_.../review.md`. Each file has the CMT reviews, the 10 scores, the novelty table, the reference audit, the format audit, overclaims, venues and the TODO list.
