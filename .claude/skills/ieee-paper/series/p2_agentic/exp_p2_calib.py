"""P2 calibration / disagreement-gate study on the deployed models' own held-out rows -> <work>/p2_calib.json.

Rebuilds the INDOFLOODS split used to train models/random_forest_flood.pkl and xgboost_flood.pkl
(StratifiedShuffleSplit 80/20, random_state=42, encodings fit on train only), checks that the stored
models reproduce models/evaluation.json on it, then on the 910 test rows:
  - reliability (10 equal-width bins), ECE and Brier for both deployed models
  - the gate (2) with the deployed delta, straddle-only, and a delta set as the 95th percentile of the
    model gap in 5-fold cross-validated predictions on the TRAINING split (no test information)
  - whether a hold flags rows on which the deployed model is wrong (error rate held vs released)
  - isotonic-calibrated copies of both models (CalibratedClassifierCV, 5-fold, training split only)
Offline; no network call.
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

raw = T.add_engineered(T.load_joined())
y = raw["y"].to_numpy()
tr_idx, te_idx = next(StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42).split(raw, y))
tr_df, te_df, _ = T.apply_train_encodings(raw.iloc[tr_idx], raw.iloc[te_idx])
Xtr, _, _ = T.feature_frame(tr_df)
Xte, _, _ = T.feature_frame(te_df)
ytr, yte = tr_df["y"].to_numpy(), te_df["y"].to_numpy()
ev = json.loads((ROOT / "models" / "evaluation.json").read_text(encoding="utf-8"))
pipes = {n: joblib.load(ROOT / "models" / f"{n}_flood.pkl") for n in ("random_forest", "xgboost")}
pte = {n: p.predict_proba(Xte)[:, 1] for n, p in pipes.items()}
for n in pipes:  # the rebuilt split must be the one the deployed models were evaluated on
    brier = float(np.mean((pte[n] - yte) ** 2))
    assert abs(brier - ev[n]["brier"]) < 1e-6  # xgboost scores in float32, f"{n}: split does not reproduce evaluation.json"


def reliability(p, yv, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    rows, ece = [], 0.0
    for b in range(bins):
        m = (p >= edges[b]) & ((p < edges[b + 1]) if b < bins - 1 else (p <= 1))
        if m.sum():
            rows.append({"lo": float(edges[b]), "n": int(m.sum()), "conf": float(p[m].mean()),
                         "freq": float(yv[m].mean())})
            ece += m.sum() / len(p) * abs(p[m].mean() - yv[m].mean())
    return rows, float(ece)


def gate(prf, pxg, delta):
    gap = np.abs(prf - pxg) >= delta if delta is not None else np.zeros(len(prf), bool)
    straddle = (np.minimum(prf, pxg) < TAU) & (TAU <= np.maximum(prf, pxg))
    return gap | straddle


def gate_stats(prf, pxg, yv, delta, model="xgboost"):
    hold = gate(prf, pxg, delta)
    p_dep = pxg if model == "xgboost" else prf
    pred = p_dep >= TAU
    wrong = pred != yv.astype(bool)
    both = (prf >= TAU) & (pxg >= TAU)
    released_auto = both & ~hold
    return {"hold_pct": 100 * hold.mean(), "both_auto": int(both.sum()),
            "both_auto_held_pct": 100 * (hold & both).sum() / max(both.sum(), 1),
            "err_held_pct": 100 * wrong[hold].mean() if hold.any() else None,
            "err_released_pct": 100 * wrong[~hold].mean() if (~hold).any() else None,
            "n_held": int(hold.sum()),
            "auto_released": int(released_auto.sum()),
            "auto_released_precision": float(yv[released_auto].mean()) if released_auto.any() else None}


# delta from the training split only: 95th percentile of the cross-validated model gap
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
oof = {n: np.zeros(len(ytr)) for n in pipes}
for f_tr, f_va in skf.split(Xtr, ytr):
    for n, p in pipes.items():
        m = clone(p).fit(Xtr.iloc[f_tr], ytr[f_tr])
        oof[n][f_va] = m.predict_proba(Xtr.iloc[f_va])[:, 1]
gap_oof = np.abs(oof["random_forest"] - oof["xgboost"])
delta95 = float(np.percentile(gap_oof, 95))

out = {"n_train": int(len(ytr)), "n_test": int(len(yte)), "pos_rate_test": float(yte.mean()), "tau": TAU,
       "delta_deployed": MODEL_GAP_MAX, "delta95_cv": delta95,
       "gap_test_mean": float(np.abs(pte["random_forest"] - pte["xgboost"]).mean()),
       "gap_test_p95": float(np.percentile(np.abs(pte["random_forest"] - pte["xgboost"]), 95)),
       "reliability": {}, "gate": {}, "calibrated": {}}
for n in pipes:
    rows, ece = reliability(pte[n], yte)
    out["reliability"][n] = {"bins": rows, "ece": ece, "brier": float(np.mean((pte[n] - yte) ** 2)),
                             "mean_p": float(pte[n].mean())}
for name, d in (("deployed", MODEL_GAP_MAX), ("delta95_cv", delta95), ("straddle_only", None)):
    out["gate"][name] = gate_stats(pte["random_forest"], pte["xgboost"], yte, d)

# isotonic calibration fitted on the training split only
pcal = {}
for n, p in pipes.items():
    c = CalibratedClassifierCV(clone(p), method="isotonic", cv=5).fit(Xtr, ytr)
    pcal[n] = c.predict_proba(Xte)[:, 1]
    rows, ece = reliability(pcal[n], yte)
    out["calibrated"][n] = {"bins": rows, "ece": ece, "brier": float(np.mean((pcal[n] - yte) ** 2))}
out["calibrated"]["gate_deployed_delta"] = gate_stats(pcal["random_forest"], pcal["xgboost"], yte, MODEL_GAP_MAX)
out["calibrated"]["gap_test_mean"] = float(np.abs(pcal["random_forest"] - pcal["xgboost"]).mean())
(WORK / "p2_calib.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in out.items() if k not in ("reliability", "calibrated")}, indent=1))
print({n: round(out["reliability"][n]["ece"], 3) for n in pipes}, {n: round(out["calibrated"][n]["ece"], 3) for n in pipes})
