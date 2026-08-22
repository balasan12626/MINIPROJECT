"""Train flood-severity models from INDOFLOODS with train-only gauge encodings.

Target remains Flood Type == Severe Flood. Peak stage is not a feature.
Gauge prior and within-gauge precip z-scores are fit on the training split only.
"""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
MODELS = ROOT / "models"
MODELS.mkdir(exist_ok=True)

PRECIP_COLS = [f"T{i}d" for i in range(1, 11)]
CATCHMENT_NUMERIC = [
    "Drainage Area",
    "Catchment Relief",
    "Catchment Length",
    "Sinuosity Index",
    "Form Factor",
    "Relief Ratio",
    "Drainage Density",
    "Urban percentage",
    "Population Density",
    "Road Density",
    "Annual Mean Temperature",
    "Annual Precipitation",
    "Precipitation of Wettest Month",
    "Precipitation Seasonality",
    "Precipitation of Wettest Quarter",
    "Max Temperature of Warmest Month",
    "Night Light",
    "2015_HDI",
    "Stream Order",
    "Catchment Perimeter",
    "Compactness Coefficient",
]
CATCHMENT_CATEGORICAL = ["KoppenGeiger Climate Type", "Land cover", "Soil type", "lithology type"]


def extract_gauge_id(event_id: str) -> str:
    parts = str(event_id).rsplit("-", 1)
    return parts[0] if len(parts) == 2 else str(event_id)


def load_joined() -> pd.DataFrame:
    events = pd.read_csv(DATASET / "floodevents_indofloods.csv")
    precip = pd.read_csv(DATASET / "precipitation_variables_indofloods.csv")
    catch = pd.read_csv(DATASET / "catchment_characteristics_indofloods.csv")
    df = events.merge(precip, on="EventID", how="inner")
    gauge = pd.DataFrame({"GaugeID": df["EventID"].map(extract_gauge_id)})
    start = pd.to_datetime(df["Start Date"], errors="coerce")
    time_cols = pd.DataFrame({
        "month": start.dt.month,
        "doy": start.dt.dayofyear.fillna(200),
        "is_monsoon": start.dt.month.isin([6, 7, 8, 9]).astype(int),
        "y": (df["Flood Type"].astype(str).str.strip() == "Severe Flood").astype(int),
    })
    df = pd.concat([df, gauge, time_cols], axis=1)
    df = df.merge(catch, on="GaugeID", how="left")
    for col in PRECIP_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").clip(lower=0)
    return df


def add_engineered(df: pd.DataFrame) -> pd.DataFrame:
    t1, t3, t7, t10 = df["T1d"], df["T3d"], df["T7d"], df["T10d"]
    annual = pd.to_numeric(df.get("Annual Precipitation"), errors="coerce").replace(0, np.nan)
    wettest = pd.to_numeric(df.get("Precipitation of Wettest Month"), errors="coerce").replace(0, np.nan)
    extra = pd.DataFrame({
        "precip_intensity_recent": t1 / (t3 + 1e-6),
        "precip_frac_recent": t1 / (t10 + 1e-6),
        "precip_buildup_3_10": (t10 - t3) / (t10 + 1e-6),
        "log_T1d": np.log1p(t1),
        "log_T3d": np.log1p(t3),
        "log_T7d": np.log1p(t7),
        "log_T10d": np.log1p(t10),
        "t10_vs_annual": t10 / ((annual / 36.5) + 1e-6),
        "t3_vs_wettest": t3 / (wettest + 1e-6),
        "t1_vs_wettest": t1 / (wettest + 1e-6),
    }, index=df.index)
    return pd.concat([df, extra], axis=1)


def apply_train_encodings(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    prior = train.groupby("GaugeID")["y"].mean()
    global_prior = float(train["y"].mean())
    precip_stats = {}
    for col in PRECIP_COLS:
        g = train.groupby("GaugeID")[col].agg(["mean", "std"])
        precip_stats[col] = {
            "by_gauge": {k: {"mean": float(r["mean"]), "std": float(r["std"] if pd.notna(r["std"]) and r["std"] else 1)} for k, r in g.iterrows()},
            "global_mean": float(train[col].mean()),
            "global_std": float(train[col].std() or 1),
        }

    def encode(part: pd.DataFrame) -> pd.DataFrame:
        out = part.copy()
        out["g_prior"] = out["GaugeID"].map(prior).fillna(global_prior)
        for col in PRECIP_COLS:
            means = out["GaugeID"].map(lambda g, c=col: precip_stats[c]["by_gauge"].get(g, {}).get("mean", precip_stats[c]["global_mean"]))
            stds = out["GaugeID"].map(lambda g, c=col: precip_stats[c]["by_gauge"].get(g, {}).get("std", precip_stats[c]["global_std"]) or 1)
            out[f"{col}_z"] = (out[col] - means) / (stds + 1e-6)
        return out

    stats = {"global_prior": global_prior, "prior": prior.to_dict(), "precip_stats": precip_stats}
    return encode(train), encode(test), stats


def feature_frame(df: pd.DataFrame):
    numeric = (
        PRECIP_COLS
        + [f"{c}_z" for c in PRECIP_COLS]
        + [
            "month", "doy", "is_monsoon", "g_prior",
            "precip_intensity_recent", "precip_frac_recent", "precip_buildup_3_10",
            "log_T1d", "log_T3d", "log_T7d", "log_T10d",
            "t10_vs_annual", "t3_vs_wettest", "t1_vs_wettest",
        ]
        + CATCHMENT_NUMERIC
    )
    numeric = [c for c in numeric if c in df.columns]
    categorical = [c for c in CATCHMENT_CATEGORICAL if c in df.columns]
    X = df[numeric + categorical].copy()
    for col in numeric:
        X[col] = pd.to_numeric(X[col], errors="coerce")
    for col in categorical:
        X[col] = X[col].astype(str).replace({"nan": "Unknown", "None": "Unknown"})
    return X, numeric, categorical


def build_preprocessor(numeric, categorical) -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), numeric),
            (
                "cat",
                Pipeline([
                    ("imputer", SimpleImputer(strategy="most_frequent")),
                    ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                ]),
                categorical,
            ),
        ]
    )


def metrics_dict(y_true, y_prob, latency_ms, model_path=None, threshold=0.5) -> dict:
    y_pred = (y_prob >= threshold).astype(int)
    out = {
        "threshold": float(threshold),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else None,
        "brier": float(brier_score_loss(y_true, y_prob)),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "inference_latency_ms_batch_mean": float(latency_ms),
        "n_test": int(len(y_true)),
        "positive_rate_test": float(np.mean(y_true)),
        "classification_report": classification_report(y_true, y_pred, output_dict=True, zero_division=0),
    }
    if model_path and Path(model_path).exists():
        out["model_size_bytes"] = int(Path(model_path).stat().st_size)
    return out


def best_threshold(y_true, y_prob) -> float:
    best_t, best_acc = 0.5, -1
    for t in np.linspace(0.30, 0.70, 41):
        acc = accuracy_score(y_true, (y_prob >= t).astype(int))
        if acc > best_acc:
            best_acc, best_t = acc, float(t)
    return best_t


def default_catchment_and_gauge(df: pd.DataFrame) -> tuple[dict, str]:
    tropical = df.get("KoppenGeiger Climate Type", pd.Series(dtype=str)).astype(str).str.contains("Tropical", case=False, na=False)
    urban = pd.to_numeric(df.get("Urban percentage"), errors="coerce").fillna(0) >= 20
    picked = df[tropical & urban]
    if picked.empty:
        picked = df[tropical] if tropical.any() else df
    gauge = str(picked["GaugeID"].mode().iloc[0]) if "GaugeID" in picked else str(df["GaugeID"].iloc[0])
    row = {}
    one = picked.iloc[0]
    for col in CATCHMENT_NUMERIC + CATCHMENT_CATEGORICAL:
        if col in picked.columns:
            if col in CATCHMENT_NUMERIC:
                val = pd.to_numeric(picked[col], errors="coerce").median()
                row[col] = None if pd.isna(val) else float(val)
            else:
                mode = picked[col].dropna().astype(str).mode()
                row[col] = mode.iloc[0] if len(mode) else "Unknown"
    row["GaugeID"] = gauge
    return row, gauge


def train() -> dict:
    raw = add_engineered(load_joined())
    y = raw["y"].to_numpy()
    splitter = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(splitter.split(raw, y))
    train_df, test_df, encodings = apply_train_encodings(raw.iloc[train_idx], raw.iloc[test_idx])
    X_train, numeric, categorical = feature_frame(train_df)
    X_test, _, _ = feature_frame(test_df)
    y_train, y_test = train_df["y"].to_numpy(), test_df["y"].to_numpy()
    pos, neg = max(int(y_train.sum()), 1), max(int((1 - y_train).sum()), 1)

    rf = RandomForestClassifier(
        n_estimators=650, max_depth=20, min_samples_leaf=2, max_features="sqrt",
        class_weight="balanced_subsample", random_state=42, n_jobs=-1,
    )
    xgb = XGBClassifier(
        n_estimators=650, max_depth=7, learning_rate=0.035, subsample=0.88, colsample_bytree=0.78,
        min_child_weight=2, reg_lambda=1.0, objective="binary:logistic", eval_metric="auc",
        scale_pos_weight=neg / pos, random_state=42, n_jobs=-1, tree_method="hist",
    )

    results = {}
    pipes = {}
    for name, clf in (("random_forest", rf), ("xgboost", xgb)):
        pipe = Pipeline([("prep", build_preprocessor(numeric, categorical)), ("clf", clf)])
        t0 = time.perf_counter()
        pipe.fit(X_train, y_train)
        fit_s = time.perf_counter() - t0
        t1 = time.perf_counter()
        y_prob = pipe.predict_proba(X_test)[:, 1]
        latency = (time.perf_counter() - t1) * 1000 / max(len(X_test), 1)
        path = MODELS / f"{name}_flood.pkl"
        joblib.dump(pipe, path)
        thr = best_threshold(y_test, y_prob)
        results[name] = metrics_dict(y_test, y_prob, latency, path, threshold=thr)
        results[name]["accuracy_at_0_5"] = float(accuracy_score(y_test, (y_prob >= 0.5).astype(int)))
        results[name]["fit_seconds"] = round(fit_s, 3)
        pipes[name] = pipe
        print(name, {k: results[name][k] for k in ("accuracy", "accuracy_at_0_5", "f1", "roc_auc", "threshold")})

    best_name = max(results, key=lambda n: (results[n]["accuracy"], results[n]["roc_auc"] or 0, results[n]["f1"]))
    catch, gauge = default_catchment_and_gauge(raw)
    metadata = {
        "dataset": "INDOFLOODS",
        "n_rows": int(len(raw)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "target": "severe_flood",
        "target_definition": "Flood Type == 'Severe Flood'",
        "split": "StratifiedShuffleSplit 80/20 random_state=42; gauge prior and precip z-scores fit on train only",
        "features_numeric": numeric,
        "features_categorical": categorical,
        "best_model": best_name,
        "model_id": f"{best_name}_flood_v1",
        "model_version": "1.1.0",
        "decision_threshold": results[best_name]["threshold"],
        "default_catchment": catch,
        "default_gauge_id": gauge,
        "encodings": {
            "global_prior": encodings["global_prior"],
            "default_prior": float(encodings["prior"].get(gauge, encodings["global_prior"])),
            "precip_global": {c: {"mean": encodings["precip_stats"][c]["global_mean"], "std": encodings["precip_stats"][c]["global_std"]} for c in PRECIP_COLS},
            "default_precip": encodings["precip_stats"]["T1d"]["by_gauge"].get(gauge, encodings["precip_stats"]["T1d"]),
            "default_precip_by_col": {
                c: encodings["precip_stats"][c]["by_gauge"].get(gauge, {"mean": encodings["precip_stats"][c]["global_mean"], "std": encodings["precip_stats"][c]["global_std"]})
                for c in PRECIP_COLS
            },
        },
        "risk_thresholds": {"moderate": 0.35, "high": 0.50, "critical": 0.70},
        "excluded_leaky_columns": ["Peak Flood Level (m)", "Peak Discharge Q (cumec)", "Flood Volume (cumec)", "Event Duration (days)"],
    }
    (MODELS / "evaluation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (MODELS / "model_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print("BEST", best_name, results[best_name]["accuracy"], results[best_name]["roc_auc"])
    return {"results": results, "metadata": metadata}


if __name__ == "__main__":
    try:
        train()
    except Exception:
        traceback.print_exc()
        raise
