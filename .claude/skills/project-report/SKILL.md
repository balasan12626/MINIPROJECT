---
name: project-report
description: Use when creating, updating, regenerating or checking the AquaSentinel final-year project report (.docx/.pdf) in the Sona College sample format — cover page, bonafide certificate, declaration, chapters, figures, screenshots, references, student/supervisor/HOD details.
---

# Project Report Workflow

The report is generated, never hand-edited. Formatting comes only from the college sample
`MINI PROIOJECTT  REPOT FINEL/SAMPLE PROJECT REPORT FORMAT & INSTRUCTIONS.docx`; content comes
from `scripts/content.py` and from real repository data.

## Files

| File | Role |
| --- | --- |
| `scripts/content.py` | **Edit here.** Top block = title, course, department, students + register numbers, supervisor, HOD, designations. Below = every chapter, table, abstract, SDG page and the 37 references. |
| `scripts/build.py` | Unzips the sample, keeps its cover/certificate/declaration layout, inserts the content, removes the template instructions and sample chapters. |
| `scripts/figs.py` | Draws architecture, workflow, stage machine, HQRL, deployment diagrams and charts from `models/*.json`. |
| `scripts/hqrl_bench.py` | Runs the real HQRL benchmark (30 scenarios, seed 42). Needs `.venv` (networkx). |
| `scripts/screenshots.mjs` | Headless Chrome via DevTools protocol (no npm installs): Command Center, Simulation (Heavy Rainfall run), Rescue Route (Pull from Simulation). |
| `scripts/finalize.ps1` | Microsoft Word COM: updates TOC, List of Figures/Tables page numbers, saves .docx + .pdf. |
| `scripts/make_report.ps1` | Runs all steps in order. |
| `scripts/paths.py` | Locations. Work dir = `%TEMP%\aquasentinel-report` (override with `REPORT_WORK_DIR`). |

Output: `MINI PROIOJECTT  REPOT FINEL/AquaSentinel_Project_Report.docx` and `.pdf`.

## Commands

```powershell
# rebuild after editing content.py (reuses saved screenshots)
.\.claude\skills\project-report\scripts\make_report.ps1

# also start backend + frontend and recapture the three UI screenshots (MongoDB must be running)
.\.claude\skills\project-report\scripts\make_report.ps1 -Screenshots
```

Requirements: system Python with `lxml`, `Pillow`, `matplotlib`; repo `.venv`; Node 22+; Google Chrome; Microsoft Word (for TOC page numbers and PDF).

## Format rules (from the sample — keep them)

- A4, sample margins, Times New Roman; code in Courier New.
- Body 14 pt, justified, 1.5 line spacing (`line=360`), 6 pt after.
- Chapter heading 14 pt bold, new page, outline level 0; sections level 1; sub-sections level 2.
- Captions 12 pt bold centred: tables **above** (`TableCaption`), figures **below** (`FigureCaption`), code (`CodeCaption`, not listed in List of Tables).
- Tables 11 pt, single borders, shaded repeating header row; small tables kept on one page.
- Bonafide certificate double spacing; references 12 pt single spacing, Harvard style, alphabetical, numbered `[n]`.
- Chapters follow the sample TOC: 1 Introduction, 2 Literature Review, 3 Need for Proposed Technique, 4 Design & Implementation (4.1–4.15), 5 Results & Discussion, 6 Conclusion & Future Scope, then SDG Goals, Publications, References.
- Template guidance text, red text, yellow highlights and the sample's example chapters/names must not survive. Yellow is allowed only for details still missing.

## Content rules

- Every metric must come from `models/*.json`, a seeded run, or a real test run — never estimate. Report test failures honestly.
- Cite with `[@Key]` in `content.py`; `build.py` turns keys into `[n]` and prints `uncited:` — it must be empty. Add references only after verifying them (no invented papers); keep ≥ 15 from 2024–2026.
- In-text "Figure X.Y" references must match caption numbers; check after adding or moving a figure.
- Do not claim quantum speed-up, real deployment, live CWC gauges, hospitals, boats or phone numbers (see CLAUDE.md "Does not exist").

## Verify after every rebuild

1. `build.py` output shows `uncited: []`.
2. `pdftoppm -jpeg -r 45 <pdf> p` and look at every page: cover fits one page, no blank pages, TOC has no cover lines, abstract is one page.
3. No leftover `<Designation>`, `STUDENT NAME`, `Insert`, sample names, red text or highlights in `word/document.xml`.
4. The run leaves the rescue desk with 10 pulled cases if `-Screenshots` was used — use **Reset desk** on /rescue to clear.
