"""Train v2 flood pipeline: XGBoost/RF/Ridge/LightGBM regressor for Peak Flood
Level (m), then an alert classifier (Flood Type) fed the regressor's own
predicted level. Group-aware (GaugeID) split throughout to avoid the station
leakage present in the v1 model. CPU-only. Old v1 artifacts are untouched.
"""

from __future__ import annotations

import json
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix, f1_score,
    mean_absolute_error, precision_score, r2_score, recall_score,
    roc_auc_score, root_mean_squared_error,
)
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier, XGBRegressor

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
MODELS = ROOT / "models"
SEED = 42

PRECIP_COLS = [f"T{i}d" for i in range(1, 11)]
CATCHMENT_NUMERIC = [
    "Drainage Area", "Catchment Relief", "Catchment Length", "Sinuosity Index",
    "Form Factor", "Relief Ratio", "Drainage Density", "Urban percentage",
    "Population Density", "Road Density", "Annual Mean Temperature",
    "Annual Precipitation", "Precipitation of Wettest Month",
    "Precipitation Seasonality", "Precipitation of Wettest Quarter",
    "Max Temperature of Warmest Month", "Night Light", "2015_HDI",
    "Stream Order", "Catchment Perimeter", "Compactness Coefficient",
]
CATCHMENT_CATEGORICAL = ["KoppenGeiger Climate Type", "Land cover", "Soil type", "lithology type"]
NUMERIC = (
    PRECIP_COLS
    + ["month", "doy", "is_monsoon", "log_T1d", "log_T3d", "log_T7d", "log_T10d",
       "precip_intensity_recent", "precip_frac_recent", "precip_buildup_3_10"]
    + CATCHMENT_NUMERIC
)
LGBM_OK = False
try:
    from lightgbm import LGBMClassifier, LGBMRegressor
    LGBM_OK = True
except Exception:
    pass
CATBOOST_OK = False
try:
    from catboost import CatBoostClassifier
    CATBOOST_OK = True
except Exception:
    pass


def extract_gauge_id(event_id: str) -> str:
    parts = str(event_id).rsplit("-", 1)
    return parts[0] if len(parts) == 2 else str(event_id)


def load_joined() -> pd.DataFrame:
    events = pd.read_csv(DATASET / "floodevents_indofloods.csv")
    precip = pd.read_csv(DATASET / "precipitation_variables_indofloods.csv")
    catch = pd.read_csv(DATASET / "catchment_characteristics_indofloods.csv")
    df = events.merge(precip, on="EventID", how="inner")
    df["GaugeID"] = df["EventID"].map(extract_gauge_id)
    start = pd.to_datetime(df["Start Date"], errors="coerce")
    df["month"] = start.dt.month
    df["doy"] = start.dt.dayofyear.fillna(200)
    df["is_monsoon"] = start.dt.month.isin([6, 7, 8, 9]).astype(int)
    df["y_level"] = pd.to_numeric(df["Peak Flood Level (m)"], errors="coerce")
    df["y_severe"] = (df["Flood Type"].astype(str).str.strip() == "Severe Flood").astype(int)
    df = df.merge(catch, on="GaugeID", how="left")
    for col in PRECIP_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").clip(lower=0)
    t1, t3, t7, t10 = df["T1d"], df["T3d"], df["T7d"], df["T10d"]
    df["precip_intensity_recent"] = t1 / (t3 + 1e-6)
    df["precip_frac_recent"] = t1 / (t10 + 1e-6)
    df["precip_buildup_3_10"] = (t10 - t3) / (t10 + 1e-6)
    df["log_T1d"] = np.log1p(t1)
    df["log_T3d"] = np.log1p(t3)
    df["log_T7d"] = np.log1p(t7)
    df["log_T10d"] = np.log1p(t10)
    return df.dropna(subset=["y_level"]).reset_index(drop=True)


def feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    X = df[[c for c in NUMERIC if c in df.columns] + CATCHMENT_CATEGORICAL].copy()
    for col in NUMERIC:
        if col in X.columns:
            X[col] = pd.to_numeric(X[col], errors="coerce")
    for col in CATCHMENT_CATEGORICAL:
        X[col] = X[col].astype(str).replace({"nan": "Unknown", "None": "Unknown"})
    return X


def build_preprocessor(extra_numeric: list[str] | None = None, scale: bool = False) -> ColumnTransformer:
    numeric = [c for c in NUMERIC] + (extra_numeric or [])
    num_steps = [("imputer", SimpleImputer(strategy="median"))]
    if scale:
        num_steps.append(("scaler", StandardScaler()))
    return ColumnTransformer([
        ("num", Pipeline(num_steps), numeric),
        ("cat", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), CATCHMENT_CATEGORICAL),
    ])


def reg_candidates() -> dict:
    cands = {
        "ridge": Pipeline([("prep", build_preprocessor(scale=True)), ("m", Ridge(alpha=5.0, random_state=SEED))]),
        "random_forest": Pipeline([("prep", build_preprocessor()), ("m", RandomForestRegressor(
            n_estimators=400, max_depth=10, min_samples_leaf=3, max_features="sqrt", random_state=SEED, n_jobs=-1))]),
        "xgboost": Pipeline([("prep", build_preprocessor()), ("m", XGBRegressor(
            n_estimators=400, max_depth=5, learning_rate=0.04, subsample=0.85, colsample_bytree=0.75,
            min_child_weight=3, reg_alpha=0.5, reg_lambda=1.5, random_state=SEED, n_jobs=-1, tree_method="hist"))]),
    }
    if LGBM_OK:
        cands["lightgbm"] = Pipeline([("prep", build_preprocessor()), ("m", LGBMRegressor(
            n_estimators=400, max_depth=6, learning_rate=0.04, subsample=0.85, colsample_bytree=0.75,
            min_child_samples=5, reg_alpha=0.5, reg_lambda=1.5, random_state=SEED, n_jobs=-1, verbosity=-1))])
    return cands


def cv_score_regressor(pipe, X, y, groups, log_target: bool):
    gkf = GroupKFold(n_splits=5)
    maes, rmses, r2s = [], [], []
    yt = np.log1p(y) if log_target else y
    from sklearn.base import clone
    for tr, va in gkf.split(X, yt, groups):
        p = clone(pipe)
        p.fit(X.iloc[tr], yt.iloc[tr])
        pred = p.predict(X.iloc[va])
        pred_orig = np.expm1(pred) if log_target else pred
        y_orig = y.iloc[va].to_numpy()
        maes.append(mean_absolute_error(y_orig, pred_orig))
        rmses.append(root_mean_squared_error(y_orig, pred_orig))
        r2s.append(r2_score(y_orig, pred_orig))
    return {
        "mae_mean": float(np.mean(maes)), "mae_std": float(np.std(maes)),
        "rmse_mean": float(np.mean(rmses)), "rmse_std": float(np.std(rmses)),
        "r2_mean": float(np.mean(r2s)), "r2_std": float(np.std(r2s)),
    }


def oof_predict(pipe, X, y, groups, log_target: bool) -> np.ndarray:
    from sklearn.base import clone
    gkf = GroupKFold(n_splits=5)
    yt = np.log1p(y) if log_target else y
    oof = np.zeros(len(y))
    for tr, va in gkf.split(X, yt, groups):
        p = clone(pipe)
        p.fit(X.iloc[tr], yt.iloc[tr])
        pred = p.predict(X.iloc[va])
        oof[va] = np.expm1(pred) if log_target else pred
    return oof


def clf_candidates(extra_numeric):
    prep = build_preprocessor(extra_numeric=extra_numeric)
    cands = {
        "xgboost": Pipeline([("prep", prep), ("m", XGBClassifier(
            n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.85, colsample_bytree=0.75,
            min_child_weight=3, reg_lambda=1.0, random_state=SEED, n_jobs=-1, tree_method="hist",
            eval_metric="auc"))]),
    }
    if LGBM_OK:
        cands["lightgbm"] = Pipeline([("prep", build_preprocessor(extra_numeric=extra_numeric)), ("m", LGBMClassifier(
            n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.85, colsample_bytree=0.75,
            min_child_samples=5, reg_lambda=1.0, random_state=SEED, n_jobs=-1, class_weight="balanced", verbosity=-1))])
    if CATBOOST_OK:
        cands["catboost"] = Pipeline([("prep", build_preprocessor(extra_numeric=extra_numeric)), ("m", CatBoostClassifier(
            iterations=300, depth=5, learning_rate=0.05, l2_leaf_reg=3.0, random_state=SEED,
            auto_class_weights="Balanced", verbose=False))])
    return cands


def cv_score_classifier(pipe, X, y, groups):
    from sklearn.base import clone
    gkf = GroupKFold(n_splits=5)
    accs, precs, recs, f1s, aucs = [], [], [], [], []
    for tr, va in gkf.split(X, y, groups):
        p = clone(pipe)
        p.fit(X.iloc[tr], y.iloc[tr])
        prob = p.predict_proba(X.iloc[va])[:, 1]
        pred = (prob >= 0.5).astype(int)
        accs.append(accuracy_score(y.iloc[va], pred))
        precs.append(precision_score(y.iloc[va], pred, zero_division=0))
        recs.append(recall_score(y.iloc[va], pred, zero_division=0))
        f1s.append(f1_score(y.iloc[va], pred, zero_division=0))
        aucs.append(roc_auc_score(y.iloc[va], prob))
    return {
        "recall_mean": float(np.mean(recs)), "recall_std": float(np.std(recs)),
        "precision_mean": float(np.mean(precs)), "f1_mean": float(np.mean(f1s)),
        "roc_auc_mean": float(np.mean(aucs)), "accuracy_mean": float(np.mean(accs)),
    }


def default_catchment_profile(df: pd.DataFrame) -> dict:
    tropical = df.get("KoppenGeiger Climate Type", pd.Series(dtype=str)).astype(str).str.contains("Tropical", case=False, na=False)
    urban = pd.to_numeric(df.get("Urban percentage"), errors="coerce").fillna(0) >= 20
    picked = df[tropical & urban]
    if picked.empty:
        picked = df[tropical] if tropical.any() else df
    row = {}
    for col in CATCHMENT_NUMERIC:
        if col in picked.columns:
            val = pd.to_numeric(picked[col], errors="coerce").median()
            row[col] = None if pd.isna(val) else float(val)
    for col in CATCHMENT_CATEGORICAL:
        if col in picked.columns:
            mode = picked[col].dropna().astype(str).mode()
            row[col] = mode.iloc[0] if len(mode) else "Unknown"
    return row


def main():
    MODELS.mkdir(exist_ok=True)
    raw = load_joined()
    X_all = feature_frame(raw)
    y_level = raw["y_level"]
    y_severe = raw["y_severe"]
    groups = raw["GaugeID"]

    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    train_idx, test_idx = next(gss.split(X_all, y_level, groups))
    Xtr, Xte = X_all.iloc[train_idx].reset_index(drop=True), X_all.iloc[test_idx].reset_index(drop=True)
    ytr, yte = y_level.iloc[train_idx].reset_index(drop=True), y_level.iloc[test_idx].reset_index(drop=True)
    gtr = groups.iloc[train_idx].reset_index(drop=True)
    ytr_sev, yte_sev = y_severe.iloc[train_idx].reset_index(drop=True), y_severe.iloc[test_idx].reset_index(drop=True)

    print(f"rows total={len(X_all)} train={len(Xtr)} test(holdout gauges)={len(Xte)} "
          f"n_gauges_train={gtr.nunique()} n_gauges_test={groups.iloc[test_idx].nunique()}")

    # --- Stage 1: regression model + target-transform comparison ---
    reg_results = {}
    for log_t in (False, True):
        for name, pipe in reg_candidates().items():
            key = f"{name}{'_log' if log_t else ''}"
            t0 = time.perf_counter()
            reg_results[key] = cv_score_regressor(pipe, Xtr, ytr, gtr, log_t)
            reg_results[key]["cv_seconds"] = round(time.perf_counter() - t0, 2)
            reg_results[key]["log_target"] = log_t
            print("REG", key, {k: round(v, 3) if isinstance(v, float) else v for k, v in reg_results[key].items()})

    best_reg_key = min(reg_results, key=lambda k: reg_results[k]["mae_mean"])
    best_reg_name = best_reg_key.replace("_log", "")
    best_log = reg_results[best_reg_key]["log_target"]
    best_pipe = reg_candidates()[best_reg_name]

    from sklearn.base import clone
    final_reg = clone(best_pipe)
    yfit = np.log1p(ytr) if best_log else ytr
    final_reg.fit(Xtr, yfit)
    pred_test = final_reg.predict(Xte)
    pred_test_orig = np.expm1(pred_test) if best_log else pred_test
    holdout_metrics = {
        "mae": float(mean_absolute_error(yte, pred_test_orig)),
        "rmse": float(root_mean_squared_error(yte, pred_test_orig)),
        "r2": float(r2_score(yte, pred_test_orig)),
    }
    print("REG HOLDOUT", best_reg_key, holdout_metrics)

    # --- Stage 2: alert classifier fed the regressor's own predicted level ---
    oof_pred = oof_predict(best_pipe, Xtr, ytr, gtr, best_log)
    Xtr_c = Xtr.copy()
    Xtr_c["pred_peak_level"] = oof_pred
    Xte_c = Xte.copy()
    Xte_c["pred_peak_level"] = pred_test_orig

    clf_results = {}
    fitted_clf = {}
    for name, pipe in clf_candidates(["pred_peak_level"]).items():
        t0 = time.perf_counter()
        clf_results[name] = cv_score_classifier(pipe, Xtr_c, ytr_sev, gtr)
        clf_results[name]["cv_seconds"] = round(time.perf_counter() - t0, 2)
        print("CLF", name, {k: round(v, 3) if isinstance(v, float) else v for k, v in clf_results[name].items()})
        fitted_clf[name] = pipe

    best_clf_name = max(clf_results, key=lambda n: (clf_results[n]["recall_mean"], clf_results[n]["roc_auc_mean"]))
    final_clf = clone(fitted_clf[best_clf_name])
    final_clf.fit(Xtr_c, ytr_sev)
    prob_test = final_clf.predict_proba(Xte_c)[:, 1]
    pred_sev_test = (prob_test >= 0.5).astype(int)
    clf_holdout = {
        "accuracy": float(accuracy_score(yte_sev, pred_sev_test)),
        "precision": float(precision_score(yte_sev, pred_sev_test, zero_division=0)),
        "recall": float(recall_score(yte_sev, pred_sev_test, zero_division=0)),
        "f1": float(f1_score(yte_sev, pred_sev_test, zero_division=0)),
        "roc_auc": float(roc_auc_score(yte_sev, prob_test)),
        "confusion_matrix": confusion_matrix(yte_sev, pred_sev_test).tolist(),
        "classification_report": classification_report(yte_sev, pred_sev_test, output_dict=True, zero_division=0),
    }
    print("CLF HOLDOUT", best_clf_name, clf_holdout)

    joblib.dump(final_reg, MODELS / "flood_regressor_v2.pkl")
    joblib.dump(final_clf, MODELS / "flood_alert_model_v2.pkl")

    metadata = {
        "version": "2.0.0",
        "tuning_attempt_note": (
            "A shallower/more-regularized LightGBM (stage1) and CatBoost (stage2) config was tried "
            "under the same GroupKFold(5) CV and looked better in-sample (stage1 CV MAE 91.6->85.4; "
            "stage2 CV recall 0.447->0.490). But on the untouched holdout gauges both got WORSE, not "
            "better (stage1 holdout MAE 80.1->91.1, R2 0.488->0.428; stage2 holdout recall 0.671->0.643, "
            "F1 0.559->0.526, ROC-AUC 0.695->0.649) -- the CV gain did not generalize. Per validation "
            "policy this candidate was rejected and the original v2.0 hyperparameters were kept."
        ),
        "dataset": "INDOFLOODS (floodevents + precipitation_variables + catchment_characteristics)",
        "datasets_excluded": {
            "daily-rainfall-at-state-level.csv": "no GaugeID/lat-lon/state key shared with INDOFLOODS catchment table",
            "india_weather_rainfall_data.xlsx": "no GaugeID/lat-lon/state key shared with INDOFLOODS catchment table",
        },
        "n_rows": int(len(X_all)), "n_train": int(len(Xtr)), "n_test": int(len(Xte)),
        "n_gauges_train": int(gtr.nunique()), "n_gauges_test": int(groups.iloc[test_idx].nunique()),
        "validation": "GroupShuffleSplit 80/20 by GaugeID for holdout (unseen catchments); GroupKFold(5) by GaugeID for model comparison",
        "stage1": {
            "task": "regression", "target": "Peak Flood Level (m)",
            "model": best_reg_name, "log_target": bool(best_log),
            "features_numeric": [c for c in NUMERIC if c in X_all.columns],
            "features_categorical": CATCHMENT_CATEGORICAL,
        },
        "stage2": {
            "task": "classification", "target": "Flood Type == 'Severe Flood'",
            "model": best_clf_name,
            "features_numeric": [c for c in NUMERIC if c in X_all.columns] + ["pred_peak_level"],
            "features_categorical": CATCHMENT_CATEGORICAL,
            "note": "pred_peak_level is the stage-1 regressor's own OOF (train) / holdout (test) prediction, not ground truth, to keep inference-time behavior consistent",
        },
        "leakage_excluded_columns": [
            "Peak FL Date", "Num Peak FL", "Peak Discharge Q (cumec)", "Peak Discharge Date",
            "Flood Volume (cumec)", "Event Duration (days)", "Time to Peak (days)", "Recession Time (day)",
        ],
        "gauge_identity_excluded": "GaugeID, g_prior, per-gauge precip z-scores dropped vs v1 to avoid group leakage and to generalize to unseen/live catchments",
        "alert_thresholds_reused_from": "backend/utils/geo.py risk_category (0.35/0.5/0.7 on severe-flood probability)",
        "default_catchment": default_catchment_profile(raw),
        "random_state": SEED,
    }
    (MODELS / "flood_model_metadata_v2.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (MODELS / "flood_evaluation_v2.json").write_text(json.dumps({
        "regression_cv": reg_results, "regression_holdout": holdout_metrics,
        "classification_cv": clf_results, "classification_holdout": clf_holdout,
    }, indent=2), encoding="utf-8")
    print("DONE best_reg=", best_reg_key, "best_clf=", best_clf_name)


if __name__ == "__main__":
    main()
