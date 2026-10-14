---
name: ieee-paper
description: Use when writing, revising, rebuilding, checking or resubmitting the AquaSentinel IEEE conference paper (INDICON or any IEEE conference) — PDF and Word versions, blind-review vs camera-ready copies, tables, figures, references, reviewer/rejection responses, the issues-and-fixes report, or files for the guide.
---

# IEEE Paper Workflow

The paper is generated, never hand-edited. One LaTeX master (`scripts/paper.tex`) produces four papers
(blind + camera-ready, each as PDF and Word) and every number in it is checked against real data.

Paper: *"Fail-Closed Flood Evacuation Decision Support: Gauge-Held-Out Forecasting and a Constraint Shield
for Learned Route Proposals"*. It replaced INDICON 2026 submission 4244 ("Hybrid Quantum RL with XAI…"),
which was rejected for (1) limited novelty, (2) IEEE guideline non-compliance, (3) presentation/clarity.

## Files

| File | Role |
| --- | --- |
| `scripts/paper.tex` | **Edit here.** IEEEtran master with authors between `%<AUTHORS>` and `%</AUTHORS>`. |
| `scripts/build_paper_docx.js` | Word version (IEEE Word layout). **Tables I–V are duplicated here — change both.** Table/equation numbers for the Word text live in `tex2json.py` (`labels`) and `EQS` here. |
| `scripts/build_report_docx.js` | `INDICON_rejection_issues_and_fixes.docx` (issue / why / fix / YES-NO). |
| `scripts/exp.py` | Seeded runs of `backend/simulation/hqrl_demo.py` → `exp.json` (bench, ablation, sweep, gating). Needs `.venv`. |
| `scripts/figs.py` | Fig. 2 from `exp.json`. Fig. 1 is TikZ inside `paper.tex`. |
| `scripts/split_versions.py` | `paper.tex` → `camera.tex` + `blind.tex` (anonymous). |
| `scripts/render_imgs.py`, `tex2json.py` | PNGs of Fig. 1/equations and JSON of the text for the Word build. |
| `scripts/verify.py` | Fails the build if a number drifts from its source, pages > 6, Type 3 / unembedded fonts, or the blind PDF names the authors. |
| `scripts/style.py` | Writing-style stats (AI-marker words, sentence-length variety). Not an AI-detector score. |
| `scripts/make_paper.ps1` | Runs everything (8 steps). |

Work dir `%TEMP%\aquasentinel-ieee` (override `PAPER_WORK_DIR`). Output: `iee papper fineal/revised/`
and the deliverables copy `iee papper fineal/revised/FINEL/` (both PDFs, both .docx, the report and
`For_Guide_Nandhakumar_T.zip`). The original rejected PDF in `iee papper fineal/` is never touched.

## Commands

```powershell
.\.claude\skills\ieee-paper\scripts\make_paper.ps1            # full rebuild, re-runs experiments (~3 min)
.\.claude\skills\ieee-paper\scripts\make_paper.ps1 -SkipExp   # text-only edits, reuse exp.json
python .claude\skills\ieee-paper\scripts\style.py <pdf>       # style stats for any PDF
```

Needs: MiKTeX (`pdflatex`, IEEEtran), Poppler (`pdftoppm`, `pdffonts`), repo `.venv`, system Python with
matplotlib, Node 22+ (`docx` is npm-installed into the work dir on first run), Microsoft Word (page check).

## IEEE / INDICON rules (from the official guidelines — keep them)

- IEEE conference template, two columns, 10 pt Times, 8.5×11 in; **4–6 pages including references**.
- **Double-blind review: the submitted file has no names, affiliations, emails or self-identifying text.**
  Upload `SUBMIT_blind_review.pdf`; `camera_ready_with_authors.*` is only for after acceptance.
- No Type 3 fonts, all fonts embedded (then run IEEE PDF eXpress with the conference ID).
- References complete IEEE style (authors, title, venue, vol., no., pp., year). Verify new ones online.
- IEEE AI policy: AI-generated content is disclosed in the Acknowledgment (tool + sections). Keep it.
- Check the target conference's own page limit, paper size and blind-review rule before submitting.

## Content rules (why the first version was rejected — do not repeat)

- Every number comes from `models/flood_evaluation_v4.json` or `exp.json`; `verify.py` enforces it.
  Never put "example" or "representative" values in a table.
- Describe what the code actually does: the route proposer is an adaptive scoring policy (**not trained
  PPO**), the "QAOA" is a **classical QAOA-inspired sampler**, route explanations are attribution +
  constraint traces (TreeSHAP only for the flood model). No quantum speed-up claims.
- Report results that do not favour the method (flood-aware A* matches the shield; forecast precision
  0.328; mean-reliability gate misses single failures). Honest limits are part of the contribution.
- Novelty = fail-closed chain + proposer-agnostic constraint shield + gauge/time-held-out evaluation,
  positioned against safe-RL shielding [Alshiekh 2018; García & Fernández 2015].
- Re-plan latencies are wall-clock and machine-dependent; refresh them only from a new `exp.json`.
- Write plain academic English yourself. Never use "AI humanizer"/detector-evasion tools — ethics
  violations are desk-rejected and reported to the authors' institution.

## Paper series (P1–P3) and P4

Four 6-page papers share the system: P1 quantum (`series/p1_quantum`), P2 agentic AI (`series/p2_agentic`),
P3 agentic + quantum (`series/p3_qagentic`), P4 = the master paper above. Output and audit report:
`iee papper fineal/series/` (`AUDIT_REPORT.md`); version snapshots in `iee papper fineal/series_versions/`.

| Step | Command (repo root) |
| --- | --- |
| Experiments | `.venv\Scripts\python.exe .claude\skills\ieee-paper\series\p1_quantum\exp_p1.py %TEMP%\aquasentinel-series` (also `exp_p1_noise.py`), `p2_agentic\exp_p2.py` (+ `exp_p2_live.py`, calls Groq — needs author approval), `p3_qagentic\exp_p3.py` + `exp_p3_esc.py` |
| Build P1–P3 | `.venv\Scripts\python.exe .claude\skills\ieee-paper\series\build_series.py [p1 p2 p3]` |
| Build P4 | `.claude\skills\ieee-paper\scripts\make_paper.ps1 -SkipExp` (runs `exp_min.py` every time) |

- Every number in P1–P3 comes from `nums.tex`, written by `post_p*.py` from the experiment JSON; the post
  scripts also `assert` each qualitative claim in the text. Table rows are generated `tab_*.tex` files that
  the build inlines (an `\input` inside a booktabs tabular breaks `\bottomrule`).
- `audit_refs.py` fails the build on uncited/missing/duplicate references, references out of first-citation
  order, or figures/tables/algorithms never referenced. `reorder_refs.py <tex>` fixes the order.
- Both builds fail if the PDF text contains a broken command name (`extit`, …) or the source contains a tab:
  a collapsed `\t` in a Python string once printed "extitReproducibility" into P4.
- Do not submit overlapping papers to the same venue at the same time.
- Now five papers: `p4_forecast` (CAMELS-IND benchmark) and `p5_merged` (merged system paper built from P1–P4 numbers,
  macro prefixes Fc/Qa/Ra/Ag, bibliography via `p5_merged/fill_bib.py`). Build all with `PAPER_MAX_PAGES=6`.
  P5 duplicates P1–P4 results: submit P5 or the separate papers, never both. Details in `CLAUDE.md` ("IEEE paper series").

## Verify after every rebuild

1. Step 5 prints `ALL CHECKS PASSED`; step 7 shows both .docx at ≤ 6 pages.
2. `pdftoppm -png -r 70 blind.pdf p` in the work dir and look at every page (tables inside columns,
   figure legends readable, last-page columns balanced).
3. If a table changed, the Word copy matches (same rows in `build_paper_docx.js`).

## Known pitfalls

- Bash heredocs in this environment collapse `\\` → `\`; write LaTeX-touching Python with the Write tool.
- PowerShell treats MiKTeX's stderr update warning as an error — run pdflatex through `cmd /c`.
- Open questions only the authors can answer: name spellings (Abhishek/ABISHAK, Gowthaman/GOWTHMAN)
  and the students' department (IT vs AI & DS) in the author block of `paper.tex`.
