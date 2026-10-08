"""Shared locations for the project-report pipeline."""
import os
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[4]  # scripts -> project-report -> skills -> .claude -> repo
REPORT_DIR = ROOT / "MINI PROIOJECTT  REPOT FINEL"
SAMPLE = REPORT_DIR / "SAMPLE PROJECT REPORT FORMAT & INSTRUCTIONS.docx"
OUTPUT_NAME = "AquaSentinel_Project_Report"
WORK = Path(os.environ.get("REPORT_WORK_DIR", Path(tempfile.gettempdir()) / "aquasentinel-report"))
FIG = WORK / "fig"
WORK.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    for k in ("SKILL_DIR", "ROOT", "REPORT_DIR", "SAMPLE", "WORK"):
        print(f"{k}={globals()[k]}")
