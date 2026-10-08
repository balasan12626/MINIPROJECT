"""Train v4 flood forecaster on CAMELS-IND (Mangukiya et al. 2025, CC-BY-4.0,
doi:10.5281/zenodo.14999580).

Task: on day t, predict whether a gauge's observed streamflow exceeds its flood
threshold on any of days t+1..t+3. Only information known at the end of day t is
used (past/present rainfall, weather, soil moisture, observed flow, static
catchment attributes). No future rainfall is fed in.

Leakage controls:
  * Flood threshold = per-gauge p95 of flow in the TRAIN years only.
  * Flow-derived features are scaled by that same train-period threshold.
  * Time split: train 1980-2008, validation 2009-2014, test 2015-2020.
  * Gauge split: 20% of gauges are never seen in training or validation; the
    primary test is those unseen gauges in the test years.
  * Model family, hyperparameters and the decision threshold are chosen on the
    validation set only. The test set is scored exactly once.
  * CAMELS hydrological signatures (camels_ind_hydro) are excluded: they are
    computed from the full 1980-2020 flow record, which includes test years.

Earlier artifacts (v1, v2, v3) are left untouched.
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, brier_score_loss, confusion_matrix,
    f1_score, precision_score, recall_score, roc_auc_score, average_precision_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Feature definition is shared with the API (backend/ml/forecast_v4.py).
from backend.ml.features_v4 import (  # noqa: E402
    DATA, FLOOD_PCTL, HORIZON, MIN_TRAIN_OBS, TRAIN_END, VAL_END, gauge_frame, load_static,
)

MODELS = ROOT / "models"
SEED = 42
TRAIN_ROWS = 500_000


def build() -> tuple[pd.DataFrame, dict]:
    qdf = pd.read_csv(DATA / "streamflow_timeseries" / "streamflow_observed.csv")
    dates = pd.to_datetime(qdf[["year", "month", "day"]])
    dates = pd.DatetimeIndex(dates)
    static = load_static()
    frames, skipped = [], []
    for col in qdf.columns[3:]:
        g = gauge_frame(int(col), qdf[col].astype(float), dates)
        if g is None:
            skipped.append(int(col))
            continue
        frames.append(g)
    df = pd.concat(frames, ignore_index=True)
    df = df.join(static.astype("float32"), on="gauge_id")
    return df, {"gauges_used": int(df["gauge_id"].nunique()), "gauges_skipped": skipped}


def scores(y, prob, thr) -> dict:
    yp = (prob >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, yp, labels=[0, 1]).ravel()
    return {
        "threshold": float(thr),
        "accuracy": float(accuracy_score(y, yp)),
        "balanced_accuracy": float(balanced_accuracy_score(y, yp)),
        "precision": float(precision_score(y, yp, zero_division=0)),
        "recall": float(recall_score(y, yp, zero_division=0)),
        "specificity": float(tn / max(tn + fp, 1)),
        "f1": float(f1_score(y, yp, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, prob)),
        "pr_auc": float(average_precision_score(y, prob)),
        "brier": float(brier_score_loss(y, prob)),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "n": int(len(y)), "positive_rate": float(np.mean(y)),
    }


def pick_threshold(y, prob) -> float:
    """Decision threshold that maximises balanced accuracy -- VALIDATION ONLY."""
    grid = np.linspace(0.02, 0.98, 97)
    best = max(grid, key=lambda t: balanced_accuracy_score(y, (prob >= t).astype(int)))
    return float(best)


def main() -> None:
    t0 = time.time()
    df, info = build()
    feats = [c for c in df.columns if c not in ("y", "gauge_id", "year", "flood_today")]
    print(f"rows={len(df):,} gauges={info['gauges_used']} features={len(feats)} build={time.time()-t0:.0f}s")

    gauges = df["gauge_id"].unique()
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    seen_idx, unseen_idx = next(gss.split(gauges, groups=gauges))
    unseen = set(gauges[unseen_idx].tolist())
    is_unseen = df["gauge_id"].isin(unseen)

    tr = df[~is_unseen & (df["year"] <= TRAIN_END)]
    va = df[~is_unseen & (df["year"] > TRAIN_END) & (df["year"] <= VAL_END)]
    te_unseen = df[is_unseen & (df["year"] > VAL_END)]
    te_seen = df[~is_unseen & (df["year"] > VAL_END)]
    del df
    n_train_available = len(tr)
    # Fixed random sample of the training years: the full 1.6M rows do not fit in
    # RAM on the dev machine. Every candidate is fit on this same sample.
    tr = tr.iloc[np.random.default_rng(SEED).choice(len(tr), min(TRAIN_ROWS, len(tr)), replace=False)]
    Xtr, ytr = tr[feats], tr["y"].to_numpy().astype(int)
    Xva, yva = va[feats], va["y"].to_numpy().astype(int)
    print(f"train={len(tr):,} (pos {ytr.mean():.3f})  val={len(va):,}  test_unseen={len(te_unseen):,}  test_seen={len(te_seen):,}")

    rng = np.random.default_rng(SEED)
    sub = np.arange(len(Xtr))
    pos_w = float((ytr == 0).sum() / max((ytr == 1).sum(), 1))

    candidates = {
        "logistic_regression": (make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                                              LogisticRegression(max_iter=2000, class_weight="balanced")), "sub"),
        "random_forest": (make_pipeline(SimpleImputer(strategy="median"),
                                        RandomForestClassifier(n_estimators=300, max_depth=16, min_samples_leaf=50,
                                                               max_features="sqrt", class_weight="balanced_subsample",
                                                               n_jobs=-1, random_state=SEED)), "sub"),
        "hist_gradient_boosting": (HistGradientBoostingClassifier(
            max_iter=1500, learning_rate=0.05, max_leaf_nodes=63, min_samples_leaf=500, l2_regularization=5.0,
            class_weight="balanced", early_stopping=True, validation_fraction=0.1, n_iter_no_change=50,
            random_state=SEED), "full"),
    }
    for depth, mcw in ((4, 50), (6, 20), (8, 100)):
        candidates[f"xgboost_d{depth}"] = (XGBClassifier(
            n_estimators=3000, max_depth=depth, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
            min_child_weight=mcw, reg_lambda=5.0, scale_pos_weight=pos_w, tree_method="hist",
            eval_metric="aucpr", early_stopping_rounds=100, n_jobs=-1, random_state=SEED), "full")

    results, fitted = {}, {}
    for name, (model, rows) in candidates.items():
        t1 = time.time()
        X_fit, y_fit = (Xtr.iloc[sub], ytr[sub]) if rows == "sub" else (Xtr, ytr)
        if name.startswith("xgboost"):
            model.fit(X_fit, y_fit, eval_set=[(Xva, yva)], verbose=False)
        else:
            model.fit(X_fit, y_fit)
        p_va = model.predict_proba(Xva)[:, 1]
        thr = pick_threshold(yva, p_va)
        p_tr = model.predict_proba(Xtr.iloc[sub])[:, 1]
        results[name] = {
            "fit_rows": rows, "fit_seconds": round(time.time() - t1, 1),
            "train": scores(ytr[sub], p_tr, thr),
            "validation": scores(yva, p_va, thr),
        }
        fitted[name] = model
        v = results[name]["validation"]
        print(f"{name:22s} val bal_acc={v['balanced_accuracy']:.4f} auc={v['roc_auc']:.4f} "
              f"pr_auc={v['pr_auc']:.4f} train bal_acc={results[name]['train']['balanced_accuracy']:.4f} "
              f"({results[name]['fit_seconds']}s)")

    best = max(results, key=lambda n: (results[n]["validation"]["balanced_accuracy"], results[n]["validation"]["pr_auc"]))
    model, thr = fitted[best], results[best]["validation"]["threshold"]
    print("SELECTED on validation:", best, "threshold", thr)

    # --- Baselines, scored on the same test rows ---
    def persistence(frame):  # "flood in next 3 days iff flooded today"
        m = frame["flood_today"].notna()
        return scores(frame.loc[m, "y"].to_numpy().astype(int), frame.loc[m, "flood_today"].to_numpy(), 0.5)

    test = {}
    for label, frame in (("unseen_gauges_2015_2020", te_unseen), ("seen_gauges_2015_2020", te_seen)):
        y = frame["y"].to_numpy().astype(int)
        prob = model.predict_proba(frame[feats])[:, 1]
        onset = (frame["flood_today"] == 0).to_numpy()
        test[label] = {
            "model": scores(y, prob, thr),
            "model_flood_onset_only": scores(y[onset], prob[onset], thr),
            "baseline_persistence": persistence(frame),
            "baseline_always_no_flood_accuracy": float(1 - y.mean()),
        }
        m = test[label]["model"]
        print(f"TEST {label}: acc={m['accuracy']:.4f} bal_acc={m['balanced_accuracy']:.4f} "
              f"recall={m['recall']:.4f} prec={m['precision']:.4f} auc={m['roc_auc']:.4f} | "
              f"persistence bal_acc={test[label]['baseline_persistence']['balanced_accuracy']:.4f}")

    export_test_set(te_unseen, feats)
    out_model = MODELS / "flood_forecast_v4.pkl"
    joblib.dump(model, out_model)
    evaluation = {
        "task": f"P(observed streamflow >= gauge train-period p{int(FLOOD_PCTL*100)} on any of days t+1..t+{HORIZON})",
        "selected_model": best,
        "decision_threshold": thr,
        "selection_rule": "max validation balanced accuracy (tie-break PR-AUC); threshold picked on validation",
        "candidates": results,
        "test": test,
    }
    metadata = {
        "version": "4.0.0",
        "dataset": "CAMELS-IND (Mangukiya et al., 2025) doi:10.5281/zenodo.14999580, CC-BY-4.0",
        "model": best, "features": feats, "decision_threshold": thr,
        "horizon_days": HORIZON, "flood_threshold": f"per-gauge p{int(FLOOD_PCTL*100)} of 1980-{TRAIN_END} flow",
        "split": {
            "train": f"seen gauges, 1980-{TRAIN_END}", "validation": f"seen gauges, {TRAIN_END+1}-{VAL_END}",
            "test_primary": f"unseen gauges (20%, GroupShuffleSplit seed {SEED}), {VAL_END+1}-2020",
            "test_secondary": f"seen gauges, {VAL_END+1}-2020",
        },
        "unseen_gauges": sorted(int(g) for g in unseen),
        "n_train": int(len(tr)), "n_train_available": int(n_train_available), "n_val": int(len(va)),
        "n_test_unseen": int(len(te_unseen)), "n_test_seen": int(len(te_seen)),
        **info,
        "excluded": "camels_ind_hydro signatures (computed over the full record incl. test years); future rainfall",
    }
    (MODELS / "flood_evaluation_v4.json").write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
    (MODELS / "flood_model_metadata_v4.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Saved {out_model.name}, flood_evaluation_v4.json, flood_model_metadata_v4.json  total={time.time()-t0:.0f}s")


def export_test_set(te_unseen: pd.DataFrame, feats: list[str]) -> None:
    """Save the unseen-gauge test rows (features + label) for live re-scoring by
    GET /api/ml/benchmark-v4. Never used for training or model selection."""
    np.savez_compressed(
        MODELS / "flood_test_unseen_v4.npz",
        X=te_unseen[feats].to_numpy(dtype=np.float32),
        y=te_unseen["y"].to_numpy().astype(np.int8),
        flood_today=te_unseen["flood_today"].to_numpy(dtype=np.float32),
        gauge_id=te_unseen["gauge_id"].to_numpy().astype(np.int32),
        features=np.array(feats),
    )


def export_only() -> None:
    """Rebuild the identical unseen-gauge test split and export it (no training)."""
    df, _ = build()
    feats = [c for c in df.columns if c not in ("y", "gauge_id", "year", "flood_today")]
    gauges = df["gauge_id"].unique()
    _, unseen_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(gauges, groups=gauges))
    te = df[df["gauge_id"].isin(set(gauges[unseen_idx].tolist())) & (df["year"] > VAL_END)]
    export_test_set(te, feats)
    print(f"Exported {len(te):,} unseen-gauge test rows")


if __name__ == "__main__":
    export_only() if "--export-test" in sys.argv else main()
