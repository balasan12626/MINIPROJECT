"""Paper 5 (merged system paper): numbers come from the four series papers.

  python post_p5.py <work_dir> <out_dir>
Re-runs post_p1..post_p4 (so their own asserts hold), then copies every macro of
p<k>/nums.tex into out_dir/nums.tex with a prefix per layer, copies the figures used
here, and asserts each qualitative claim that Paper 5 makes across the layers.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERIES = HERE.parent
WORK, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

# paper key -> (source folder, macro prefix)
SRC = {"p1": ("p1_quantum", "Qa"), "p2": ("p2_agentic", "Ag"),
       "p3": ("p3_qagentic", "Ra"), "p4": ("p4_forecast", "Fc")}
FIGS = {"p4": ["fig_pr.pdf", "fig_rel.pdf"], "p1": ["fig_popt.pdf"], "p3": ["fig_city.pdf"],
        "p2": ["fig_errtypes.pdf"]}

lines, raw = [], {}
for key, (folder, pre) in SRC.items():
    pdir = WORK / key
    r = subprocess.run([sys.executable, str(SERIES / folder / f"post_{key}.py"), str(WORK), str(pdir)],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"post_{key}.py failed:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    text = (pdir / "nums.tex").read_text(encoding="utf-8")
    for name, val in re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}", text):
        lines.append(f"\\newcommand{{\\{pre}{name}}}{{{val}}}")
        raw[pre + name] = val
    for f in FIGS.get(key, []):
        shutil.copy(pdir / f, OUT / f"fig_{pre.lower()}_{f[4:]}")
(OUT / "nums.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def v(name):
    s = raw[name].replace(",", "")
    m = re.fullmatch(r"([0-9.]+)\\times10\^\{(-?\d+)\}", s)
    return float(m.group(1)) * 10 ** int(m.group(2)) if m else float(s)


# forecast layer (Sec. IV)
assert v("FcXgbBA") > v("FcLstmBA") > v("FcClimBA") > v("FcPersBA"), "forecast ranking"
assert v("FcXgbPR") > v("FcLstmPR") > v("FcPersPR") > v("FcClimPR"), "PR-AUC ranking"
assert v("FcXgbPrec") < 0.5, "precision below one half -> review, not order"
assert v("FcLeakRandBA") > v("FcLeakSpTiBA") and v("FcLeakRandPR") > v("FcLeakSpTiPR"), "random split inflates"
assert v("FcLeadOne") > v("FcLeadTwo") > v("FcLeadThree"), "recall falls with lead day"
assert v("FcImpFlow") > 50, "streamflow carries most of the gain"
assert v("FcEvNoFlowWarn") > v("FcEvXgbWarn") and v("FcNoFlowBA") < v("FcXgbBA"), "no-flow: more onsets, lower BA"
assert v("FcPArea") < 0.05 and v("FcRhoArea") > 0, "skill rises with area"
assert v("FcEceIso") < v("FcEceRaw") and v("FcRelHiConf") > v("FcRelHiFreq"), "over-confident, fixed"
# QAOA layer (Sec. V)
assert v("QaSeedXYMin") > v("QaSeedXMax"), "XY above X for every seed"
assert v("QaStXYvXMaxP") < 0.05 and v("QaStXYvGMMinP") > 0.05, "XY>X significant, XY~Grover not"
assert v("QaHoFixedFour") > v("QaHoTrainedFour"), "fixed angles beat per-instance training on held-out"
assert v("QaCityP") > 0.05 and v("QaCitySuccFixed") > v("QaCitySuccTrained") and v("QaCitySuccP") < 0.05, "city"
assert v("QaExactMs") < 5, "exhaustive search takes about a millisecond"
assert v("QaScaleXYsix") > v("QaScaleUnisix") and v("QaGreedyOpt") > v("QaSATunedOpt"), "scaling, baselines"
assert v("QaGreedyFeas") == 100, "greedy always feasible"
# runtime assurance (Sec. VI)
assert v("RaTwinRawQ") > v("RaTwinRawSA") > 0, "unchecked dispatch unsafe"
assert v("RaViolBlindQ") > 90 and v("RaViolBlindSA") > 90, "nearly all unsafe twin samples invisible to penalty"
assert v("RaCitySAFoundThirtyTwo") < v("RaCitySAFoundEight"), "sampler fails at scale"
assert v("RaTimeoutFeasible") == v("RaCityTimeout") == v("RaTimeoutSettled"), "every time-out hid a plan"
assert v("RaCitySettled") + v("RaCityTimeout") == v("RaCityN"), "settled + time-outs = all"
assert v("RaAdaptOptQ") < v("RaFixedOptQ") and v("RaAdaptSame") == 100, "adaptive budget cost"
assert v("RaMilpMedThirtyTwo") > v("RaMilpMedEight") and v("RaMilpMaxS") < 60, "MILP cost"
# agents and narration (Sec. VII)
assert v("AgEtoEViolAfter") == 0 < v("AgEtoEViolBefore"), "bypass found and fixed"
assert v("AgPolViol") == 0, "policy verified exhaustively"
assert v("AgLiveTypRec") > v("AgLiveDepRec") and v("AgLiveTypFpr") > v("AgLiveDepFpr"), "typed: more recall, more FR"
assert v("AgLiveJJudRec") > v("AgLiveTypRec") and v("AgLiveJJudFpr") > v("AgLiveTypFpr"), "judge"
assert v("AgHoVtwoFpr") > v("AgDevVtwoFpr"), "revised guard FR rose on held-out family"
assert v("AgLiveEta") / v("AgLiveUnsup") > 0.9, "almost all unsupported numbers are arrival times"
assert v("AgGateStErrHeld") > v("AgGateDepErrHeld") and v("AgGateStHold") < v("AgGateDepHold") / 3, "straddle"
assert v("AgGateDepErrHeld") > v("AgGateDepErrRel"), "disagreement signals error"
assert v("AgErrOssEtaMin") > v("AgErrAllamEta") and v("AgErrAllamQty") > v("AgErrAllamEta"), "error kinds shift"
assert v("AgEceXgb") > v("AgEceRf") > v("AgEceCalRf") and v("AgEceCalXgb") < v("AgEceXgb"), "classifier calibration"
assert v("AgGateCalHold") < v("AgGateDepHold"), "calibration lowers hold rate"

(WORK / "p5.json").write_text(json.dumps({"source": "nums.tex of p1-p4", "macros": raw}, indent=1),
                              encoding="utf-8")
print(f"p5: {len(raw)} macros, all cross-layer claims hold")
