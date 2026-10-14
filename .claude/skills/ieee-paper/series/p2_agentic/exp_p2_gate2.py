"""P2 revision: what the disagreement gate buys, on the deployed classifiers' 910 held-out rows -> <work>/p2_gate2.json.

Same split and stored models as exp_p2_calib.py. The policy model (XGBoost) recommends dispatch when p >= tau_a;
a held row goes to an officer instead of being acted on automatically. For each rule we count
  errors caught     = policy-model errors that the rule holds (recall of errors), and errors that reach action,
  false dispatches  = released rows with p >= tau_a and no severe flood,
  missed dispatches = released rows with p <  tau_a and a severe flood,
with 2,000-row bootstrap CIs, and an expected cost c_FD*FD + c_MD*MD + c_R*holds for assumed cost ratios.
Baselines: no gate; one isotonic-calibrated XGBoost with no gate and its threshold tuned on out-of-fold
training predictions (no test information). Also describes the classifiers and the training data, and how far
the prototype's rainfall sweep lies from that data. Offline; no network call.
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedKFold, StratifiedShuffleSplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import train_flood_model as T  # noqa: E402
from backend.thresholds import MODEL_GAP_MAX, auto_threshold  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
TAU = auto_threshold()
C2 = json.loads((WORK / "p2_calib.json").read_text(encoding="utf-8"))

raw = T.add_engineered(T.load_joined())
y = raw["y"].to_numpy()
tr_idx, te_idx = next(StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42).split(raw, y))
tr_df, te_df, _ = T.apply_train_encodings(raw.iloc[tr_idx], raw.iloc[te_idx])
Xtr, num_cols, cat_cols = T.feature_frame(tr_df)
Xte, _, _ = T.feature_frame(te_df)
ytr, yte = tr_df["y"].to_numpy(), te_df["y"].to_numpy()
pipes = {n: joblib.load(ROOT / "models" / f"{n}_flood.pkl") for n in ("random_forest", "xgboost")}
prf, pxg = (pipes[n].predict_proba(Xte)[:, 1] for n in ("random_forest", "xgboost"))
assert abs(np.mean((pxg - yte) ** 2) - C2["reliability"]["xgboost"]["brier"]) < 1e-6, "same split as exp_p2_calib"

# isotonic XGBoost on the training split, and its out-of-fold predictions for threshold tuning
cal = CalibratedClassifierCV(clone(pipes["xgboost"]), method="isotonic", cv=5).fit(Xtr, ytr)
pcal = cal.predict_proba(Xte)[:, 1]
oof = np.zeros(len(ytr))
for f_tr, f_va in StratifiedKFold(5, shuffle=True, random_state=42).split(Xtr, ytr):
    c = CalibratedClassifierCV(clone(pipes["xgboost"]), method="isotonic", cv=5).fit(Xtr.iloc[f_tr], ytr[f_tr])
    oof[f_va] = c.predict_proba(Xtr.iloc[f_va])[:, 1]


def hold_of(rule):
    straddle = (np.minimum(prf, pxg) < TAU) & (TAU <= np.maximum(prf, pxg))
    if rule == "none":
        return np.zeros(len(yte), bool)
    if rule == "straddle":
        return straddle
    return (np.abs(prf - pxg) >= rule) | straddle


def counts(pred, hold, yv):
    wrong = pred != yv
    rel = ~hold
    return {"n": len(yv), "holds": int(hold.sum()), "errors": int(wrong.sum()), "caught": int((wrong & hold).sum()),
            "fd": int((pred & ~yv & rel).sum()), "md": int((~pred & yv & rel).sum())}


COSTS = [(1, 1, 0.2), (1, 5, 0.2), (1, 5, 0.5)]  # (c_FD, c_MD, c_R): assumed, labelled as such in the text


def summarise(cs):
    s = {"hold_pct": 100 * cs["holds"] / cs["n"], "err_recall_pct": 100 * cs["caught"] / max(cs["errors"], 1),
         "errors_reaching": cs["errors"] - cs["caught"], "fd": cs["fd"], "md": cs["md"], "holds": cs["holds"],
         "caught": cs["caught"], "errors": cs["errors"]}
    for cf, cm, cr in COSTS:
        s[f"cost_{cf}_{cm}_{cr}"] = 100 * (cf * cs["fd"] + cm * cs["md"] + cr * cs["holds"]) / cs["n"]
    return s


yb = yte.astype(bool)
rules = {"none": ("none", pxg >= TAU), "deployed": (MODEL_GAP_MAX, pxg >= TAU),
         "delta95": (C2["delta95_cv"], pxg >= TAU), "straddle": ("straddle", pxg >= TAU)}
for cf, cm, _ in COSTS[:2]:  # calibrated single model, threshold minimising training OOF cost (no gate)
    grid = np.linspace(0.05, 0.95, 91)
    tcost = [cf * np.sum((oof >= t) & (ytr == 0)) + cm * np.sum((oof < t) & (ytr == 1)) for t in grid]
    t_star = float(grid[int(np.argmin(tcost))])
    rules[f"calibrated_{cf}_{cm}"] = ("none", pcal >= t_star)
    rules[f"calibrated_{cf}_{cm}"] += (t_star,)

out = {"n_test": len(yte), "tau": TAU, "costs": COSTS, "rules": {}}
rng = np.random.default_rng(7)
B = 2000
boot_idx = [rng.integers(0, len(yte), len(yte)) for _ in range(B)]
for name, spec in rules.items():
    rule, pred = spec[0], spec[1]
    hold = hold_of(rule)
    s = summarise(counts(pred, hold, yb))
    bs = [summarise(counts(pred[ix], hold[ix], yb[ix])) for ix in boot_idx]
    s["ci"] = {k: [float(np.percentile([b[k] for b in bs], 2.5)), float(np.percentile([b[k] for b in bs], 97.5))]
               for k in ("hold_pct", "err_recall_pct", "errors_reaching")}
    if len(spec) > 2:
        s["threshold"] = spec[2]
    out["rules"][name] = s
# paired difference: errors reaching action, straddle minus deployed
hd, hs = hold_of(MODEL_GAP_MAX), hold_of("straddle")
pred = pxg >= TAU
wrong = pred != yb
diff = [int((wrong[ix] & ~hs[ix]).sum() - (wrong[ix] & ~hd[ix]).sum()) for ix in boot_idx]
out["straddle_minus_deployed_errors_reaching"] = {"value": int((wrong & ~hs).sum() - (wrong & ~hd).sum()),
                                                 "ci": [float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5))]}

# the classifiers and the data they were trained on
ev = json.loads((ROOT / "models" / "evaluation.json").read_text(encoding="utf-8"))
out["data"] = {"dataset": "INDOFLOODS", "target": "Flood Type == 'Severe Flood' (an event-level label)",
               "n_events": int(len(y)), "n_train": int(len(ytr)), "n_test": int(len(yte)),
               "pos_rate_train": float(ytr.mean()), "pos_rate_test": float(yte.mean()),
               "n_gauges": int(raw["GaugeID"].nunique()),
               "n_numeric": len(num_cols), "n_categorical": len(cat_cols),
               "n_precip": len(T.PRECIP_COLS), "n_catch_num": len([c for c in T.CATCHMENT_NUMERIC if c in num_cols]),
               "auc": {n: ev[n]["roc_auc"] for n in pipes}, "brier": {n: ev[n]["brier"] for n in pipes},
               "acc_at_tau": {n: float(np.mean(((pipes[n].predict_proba(Xte)[:, 1]) >= TAU) == yb)) for n in pipes},
               "t1d_train_pct": {q: float(np.nanpercentile(tr_df["T1d"], q)) for q in (50, 90, 99)},
               "t1d_train_max": float(np.nanmax(tr_df["T1d"])),
               "rf": "650 trees, depth 20, balanced class weights", "xgb": "650 trees, depth 7, lr 0.035, scale_pos_weight"}
# how far the sweep (one synthetic gauge, 24-h rain 0-300 mm, other inputs at defaults) is from the training rows
p2 = json.loads((WORK / "p2.json").read_text(encoding="utf-8"))
rains = [r["rain"] for r in p2["dual"]["rows"]]
out["sweep"] = {"n": len(rains), "rain_max": max(rains),
                "share_rain_above_train_p99": float(np.mean(np.array(rains) > out["data"]["t1d_train_pct"][99]))}
(WORK / "p2_gate2.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
for k, v in out["rules"].items():
    print(k, {a: (round(b, 1) if isinstance(b, float) else b) for a, b in v.items() if a != "ci"}, v["ci"])
print(out["straddle_minus_deployed_errors_reaching"])
print(json.dumps(out["data"], indent=0)[:1500], out["sweep"])
