"""F11 — measured uncertainty for the deployed peak-level / alert models.

    python scripts/conformal_v2.py            → models/conformal_v2.json

The live app predicts the peak flood level with models/flood_regressor_v3.pkl
(LightGBM, log1p target, mild tail weighting) and the severe-flood alert with
models/flood_alert_model_v2.pkl. This script attaches a 90 % interval to the
first and a 90 % prediction SET to the second, by CV-conformal calibration:

1. The same GroupShuffleSplit(80/20, seed 42) by GaugeID as training; the 20 %
   test gauges are NOT touched until step 4.
2. GroupKFold(5) over the TRAINING gauges only, refitting the exact v3 recipe
   per fold → out-of-fold predictions (each row predicted by a model that never
   saw its gauge).
3. Nonconformity scores on those OOF rows: |log1p(y) − log1p(ŷ)| for the level,
   1 − p(true class) for the alert → the finite-sample conformal quantile q.
4. ONE evaluation of the deployed models on the held-out test gauges: empirical
   coverage, interval width, set sizes. Reported as measured — never tuned.

The live "flood probability" is a hybrid operational blend, not one model's
output, so it gets NO interval (and the UI says so).
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
sys.path.insert(0, str(ROOT))


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / "scripts" / file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


t2 = _load("t2", "train_flood_model_v2.py")
t3 = _load("t3", "train_flood_model_v3.py")

ALPHA = 0.10


def conformal_quantile(scores: np.ndarray, alpha: float) -> float:
    """Finite-sample split-conformal quantile: the ⌈(n+1)(1−α)⌉-th smallest score."""
    s = np.sort(np.asarray(scores, dtype=float))
    n = len(s)
    k = min(n, math.ceil((n + 1) * (1 - alpha)))
    return float(s[k - 1])


def interval(pred_m: np.ndarray, q_log: float) -> tuple[np.ndarray, np.ndarray]:
    lp = np.log1p(np.maximum(pred_m, 0))
    return np.expm1(lp - q_log), np.expm1(lp + q_log)


def prediction_set(p_severe: float, q: float) -> list[str]:
    out = []
    if 1 - (1 - p_severe) <= q:  # score of "not severe" = 1 − p(not severe) = p_severe
        out.append("no_severe_flood")
    if 1 - p_severe <= q:
        out.append("severe_flood")
    return out


def main() -> int:
    from sklearn.model_selection import GroupKFold, GroupShuffleSplit

    raw = t2.load_joined()
    X_all = t2.feature_frame(raw)
    y_level = raw["y_level"]
    y_sev = raw["y_severe"]
    groups = raw["GaugeID"]
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=t2.SEED)
    tr_idx, te_idx = next(gss.split(X_all, y_level, groups))
    Xtr, Xte = X_all.iloc[tr_idx].reset_index(drop=True), X_all.iloc[te_idx].reset_index(drop=True)
    ytr, yte = y_level.iloc[tr_idx].reset_index(drop=True), y_level.iloc[te_idx].reset_index(drop=True)
    str_, ste = y_sev.iloc[tr_idx].reset_index(drop=True), y_sev.iloc[te_idx].reset_index(drop=True)
    gtr = groups.iloc[tr_idx].reset_index(drop=True)
    gte = groups.iloc[te_idx].reset_index(drop=True)

    # ---- 2. OOF on training gauges (v3 recipe for the level; deployed clf recipe for the alert) ----
    gkf = GroupKFold(n_splits=5)
    folds = list(gkf.split(Xtr, ytr, gtr))
    oof_level = np.full(len(ytr), np.nan)
    for tr_i, va_i in folds:
        pipe = t3.build_pipe()
        w = t3.tail_weight(ytr.iloc[tr_i], upper_mult=3.0)
        pipe.fit(Xtr.iloc[tr_i], np.log1p(ytr.iloc[tr_i]), m__sample_weight=w)
        oof_level[va_i] = np.expm1(pipe.predict(Xtr.iloc[va_i]))
    level_scores = np.abs(np.log1p(ytr.to_numpy()) - np.log1p(np.maximum(oof_level, 0)))
    q_log = conformal_quantile(level_scores, ALPHA)
    abs_scores = np.abs(ytr.to_numpy() - oof_level)  # metres — what the UI shows (± q m)
    q_abs = conformal_quantile(abs_scores, ALPHA)

    clf_deployed = joblib.load(MODELS / "flood_alert_model_v2.pkl")
    from sklearn.base import clone

    Xtr_c = Xtr.copy()
    Xtr_c["pred_peak_level"] = oof_level
    oof_p = np.full(len(ytr), np.nan)
    for tr_i, va_i in folds:
        c = clone(clf_deployed)
        c.fit(Xtr_c.iloc[tr_i], str_.iloc[tr_i])
        oof_p[va_i] = c.predict_proba(Xtr_c.iloc[va_i])[:, 1]
    true_p = np.where(str_.to_numpy() == 1, oof_p, 1 - oof_p)
    q_clf = conformal_quantile(1 - true_p, ALPHA)

    # ---- 4. one evaluation of the DEPLOYED models on the held-out gauges ----
    reg_deployed = joblib.load(MODELS / "flood_regressor_v3.pkl")
    pred_te = np.expm1(reg_deployed.predict(Xte))
    lo, hi = interval(pred_te, q_log)
    y = yte.to_numpy()
    inside = (y >= lo) & (y <= hi)
    per_gauge = {g: float(inside[gte.to_numpy() == g].mean()) for g in np.unique(gte)}
    inside_abs = np.abs(y - pred_te) <= q_abs
    per_gauge_abs = [float(inside_abs[gte.to_numpy() == g].mean()) for g in np.unique(gte)]

    Xte_c = Xte.copy()
    Xte_c["pred_peak_level"] = pred_te
    p_te = clf_deployed.predict_proba(Xte_c)[:, 1]
    sets = [prediction_set(float(p), q_clf) for p in p_te]
    truth = np.where(ste.to_numpy() == 1, "severe_flood", "no_severe_flood")
    covered = np.array([t in s for t, s in zip(truth, sets)])
    sizes = np.array([len(s) for s in sets])

    out = {
        "artifact": "conformal_v2",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "method": "CV-conformal: GroupKFold(5) out-of-fold scores on TRAINING gauges only; coverage measured once on held-out gauges",
        "alpha": ALPHA,
        "target_coverage": 1 - ALPHA,
        "split": "GroupShuffleSplit 80/20 by GaugeID, random_state=42 (same as training)",
        "no_test_tuning": True,
        "peak_level_abs": {
            "model": "flood_regressor_v3.pkl (LightGBM, log1p target)",
            "score": "|y - y_hat| (metres)",
            "q_m": round(q_abs, 3),
            "interval": "[y_hat - q_m, y_hat + q_m]",
            "test_coverage": round(float(inside_abs.mean()), 4),
            "test_coverage_median_gauge": round(float(np.median(per_gauge_abs)), 4),
            "test_coverage_min_gauge": round(float(min(per_gauge_abs)), 4),
            "test_width_m": round(2 * q_abs, 3),
            "oof_mae_m": round(float(np.mean(abs_scores)), 3),
            "note": "INDOFLOODS peak levels are gauge elevations (m) at very different datums; an unseen gauge's absolute level is hard to predict, so the interval is wide. Shown as-is.",
        },
        "peak_level": {
            "model": "flood_regressor_v3.pkl (LightGBM, log1p target)",
            "score": "|log1p(y) - log1p(y_hat)|",
            "q_log": round(q_log, 6),
            "interval": "[expm1(log1p(y_hat) - q), expm1(log1p(y_hat) + q)]  (multiplicative, metres)",
            "n_calibration": int(len(level_scores)),
            "n_calibration_gauges": int(gtr.nunique()),
            "test_rows": int(len(y)),
            "test_gauges": int(gte.nunique()),
            "test_coverage": round(float(inside.mean()), 4),
            "test_coverage_median_gauge": round(float(np.median(list(per_gauge.values()))), 4),
            "test_coverage_min_gauge": round(float(min(per_gauge.values())), 4),
            "test_mean_width_m": round(float(np.mean(hi - lo)), 3),
            "test_median_width_m": round(float(np.median(hi - lo)), 3),
        },
        "alert": {
            "model": "flood_alert_model_v2.pkl (fed the v3 predicted level, as at inference)",
            "score": "1 - p(true class)",
            "q": round(q_clf, 6),
            "n_calibration": int(len(oof_p)),
            "test_coverage": round(float(covered.mean()), 4),
            "test_singleton_rate": round(float((sizes == 1).mean()), 4),
            "test_both_classes_rate": round(float((sizes == 2).mean()), 4),
            "test_empty_rate": round(float((sizes == 0).mean()), 4),
        },
        "caveats": [
            "Coverage is marginal (on average over gauges like the held-out ones), not guaranteed per gauge or per event.",
            "Calibrated on INDOFLOODS events; a city far from any gauge is a transfer and the interval is not validated there.",
            "The operational flood probability is a hybrid blend (rain + stage + ML prior), not this model — it has no interval.",
        ],
    }
    path = MODELS / "conformal_v2.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("peak_level_abs", "peak_level", "alert")}, indent=2))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
