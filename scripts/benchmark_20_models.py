"""Benchmark 20 classifier families on OLD data (INDOFLOODS severe-flood events)
and NEW data (CAMELS-IND 3-day flood forecast), with fixed pass/fail tests.

Report only: writes models/benchmark_20_models.json. No model artifact is saved
or replaced.

Both datasets use a gauge-aware split so the test set is gauges the model never
saw. Each model's decision threshold is picked on validation; test is scored once.

Pass/fail rules (fixed before running):
  T1 test accuracy >= 0.85
  T2 test balanced accuracy >= 0.85
  T3 not overfit:   train_bal - test_bal <= 0.05
  T4 not underfit:  train_bal >= 0.80
  T5 beats baseline: test_bal > baseline test_bal
  T6 stable on unseen gauges: |val_bal - test_bal| <= 0.05
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis, QuadraticDiscriminantAnalysis
from sklearn.ensemble import (
    AdaBoostClassifier, BaggingClassifier, ExtraTreesClassifier, GradientBoostingClassifier,
    HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, RidgeClassifier, SGDClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC, LinearSVC
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
SEED = 42
NEW_TRAIN_ROWS = 100_000
NEW_VAL_ROWS = 100_000
SVM_ROWS = 15_000


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / "scripts" / file))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def model_zoo(pos_w: float) -> dict:
    rf = RandomForestClassifier(n_estimators=300, max_depth=16, min_samples_leaf=20, max_features="sqrt",
                                class_weight="balanced_subsample", n_jobs=-1, random_state=SEED)
    xgb = XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                        min_child_weight=10, reg_lambda=5.0, scale_pos_weight=pos_w, tree_method="hist",
                        n_jobs=-1, random_state=SEED)
    return {
        "01 Logistic Regression": LogisticRegression(max_iter=3000, class_weight="balanced"),
        "02 Ridge Classifier": RidgeClassifier(class_weight="balanced"),
        "03 SGD (log-loss)": SGDClassifier(loss="log_loss", class_weight="balanced", random_state=SEED),
        "04 Linear SVM": LinearSVC(class_weight="balanced", dual=False),
        "05 RBF SVM": SVC(kernel="rbf", C=1.0, class_weight="balanced", random_state=SEED),
        "06 K-Nearest Neighbors": KNeighborsClassifier(n_neighbors=25, n_jobs=-1),
        "07 Gaussian Naive Bayes": GaussianNB(),
        "08 LDA": LinearDiscriminantAnalysis(),
        "09 QDA": QuadraticDiscriminantAnalysis(reg_param=0.1),
        "10 Decision Tree": DecisionTreeClassifier(max_depth=10, min_samples_leaf=20, class_weight="balanced",
                                                   random_state=SEED),
        "11 Random Forest": rf,
        "12 Extra Trees": ExtraTreesClassifier(n_estimators=300, max_depth=16, min_samples_leaf=20,
                                               class_weight="balanced_subsample", n_jobs=-1, random_state=SEED),
        "13 AdaBoost": AdaBoostClassifier(n_estimators=200, random_state=SEED),
        "14 Gradient Boosting": GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.1,
                                                           subsample=0.8, random_state=SEED),
        "15 Hist Gradient Boosting": HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
                                                                    max_leaf_nodes=31, min_samples_leaf=50,
                                                                    l2_regularization=5.0, class_weight="balanced",
                                                                    random_state=SEED),
        "16 XGBoost": xgb,
        "17 CatBoost": CatBoostClassifier(iterations=500, depth=6, learning_rate=0.05, auto_class_weights="Balanced",
                                          verbose=0, random_seed=SEED, allow_writing_files=False, thread_count=-1),
        "18 MLP Neural Net": MLPClassifier(hidden_layer_sizes=(64, 32), alpha=1e-3, early_stopping=True,
                                           max_iter=200, random_state=SEED),
        "19 Bagged Trees": BaggingClassifier(DecisionTreeClassifier(max_depth=12, min_samples_leaf=20),
                                             n_estimators=100, n_jobs=-1, random_state=SEED),
        "20 Ensemble RF+XGBoost": VotingClassifier([("rf", rf), ("xgb", xgb)], voting="soft"),
    }


def score_fn(model, X):
    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1]
    return model.decision_function(X)


def pick_threshold(y, s) -> float:
    grid = np.unique(np.quantile(s, np.linspace(0.01, 0.99, 197)))
    return float(max(grid, key=lambda t: balanced_accuracy_score(y, (s >= t).astype(int))))


def m(y, s, thr) -> dict:
    yp = (s >= thr).astype(int)
    return {"acc": float(accuracy_score(y, yp)), "bal": float(balanced_accuracy_score(y, yp)),
            "auc": float(roc_auc_score(y, s))}


def run_suite(label, prep_factory, Xtr, ytr, Xva, yva, Xte, yte, baseline_bal, svm_rows) -> list[dict]:
    pos_w = float((ytr == 0).sum() / max((ytr == 1).sum(), 1))
    rows = []
    for name, clf in model_zoo(pos_w).items():
        t0 = time.time()
        Xf, yf = Xtr, ytr
        note = ""
        if name.startswith("05") and len(Xtr) > svm_rows:
            idx = np.random.default_rng(SEED).choice(len(Xtr), svm_rows, replace=False)
            Xf, yf = Xtr.iloc[idx], ytr[idx]
            note = f"fit on {svm_rows:,}-row subsample (kernel SVM is O(n^2))"
        pipe = Pipeline([("prep", prep_factory()), ("clf", clf)])
        try:
            pipe.fit(Xf, yf)
            s_va = score_fn(pipe, Xva)
            thr = pick_threshold(yva, s_va)
            tr, va, te = m(yf, score_fn(pipe, Xf), thr), m(yva, s_va, thr), m(yte, score_fn(pipe, Xte), thr)
        except Exception as exc:  # report, don't hide
            rows.append({"model": name, "error": str(exc)[:200]})
            print(f"[{label}] {name}: ERROR {exc}")
            continue
        gap = tr["bal"] - te["bal"]
        tests = {
            "T1_acc>=85": te["acc"] >= 0.85,
            "T2_bal>=85": te["bal"] >= 0.85,
            "T3_not_overfit": gap <= 0.05,
            "T4_not_underfit": tr["bal"] >= 0.80,
            "T5_beats_baseline": te["bal"] > baseline_bal,
            "T6_stable_unseen": abs(va["bal"] - te["bal"]) <= 0.05,
        }
        if tr["bal"] < 0.80:
            verdict = "UNDERFIT"
        elif gap > 0.05:
            verdict = "OVERFIT"
        else:
            verdict = "BALANCED"
        row = {"model": name, "train": tr, "val": va, "test": te, "gap_train_test_bal": float(gap),
               "tests": {k: bool(v) for k, v in tests.items()}, "passed": int(sum(tests.values())),
               "verdict": verdict, "fit_seconds": round(time.time() - t0, 1), "note": note}
        rows.append(row)
        print(f"[{label}] {name:28s} train_bal={tr['bal']:.3f} val_bal={va['bal']:.3f} test_acc={te['acc']:.3f} "
              f"test_bal={te['bal']:.3f} auc={te['auc']:.3f} gap={gap:+.3f} {verdict} pass={row['passed']}/6 "
              f"({row['fit_seconds']}s)", flush=True)
    return rows


def old_data():
    t1 = _load("t1_bench", "train_flood_model.py")
    raw = t1.add_engineered(t1.load_joined()).reset_index(drop=True)
    groups = raw["GaugeID"].to_numpy()
    rest_idx, te_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(raw, groups=groups))
    rest = raw.iloc[rest_idx].reset_index(drop=True)
    tr_idx, va_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=SEED)
                          .split(rest, groups=rest["GaugeID"]))
    tr_raw, va_raw, te_raw = rest.iloc[tr_idx], rest.iloc[va_idx], raw.iloc[te_idx]
    tr_enc, va_enc, _ = t1.apply_train_encodings(tr_raw, va_raw)   # encodings fit on train gauges only
    _, te_enc, _ = t1.apply_train_encodings(tr_raw, te_raw)
    Xtr, num, cat = t1.feature_frame(tr_enc)
    Xva, _, _ = t1.feature_frame(va_enc)
    Xte, _, _ = t1.feature_frame(te_enc)
    ytr, yva, yte = (d["y"].to_numpy().astype(int) for d in (tr_enc, va_enc, te_enc))
    info = {"rows": len(raw), "train": len(Xtr), "val": len(Xva), "test": len(Xte),
            "test_gauges": int(te_raw["GaugeID"].nunique()), "test_positive_rate": float(yte.mean()),
            "baseline": "always predict majority class (balanced accuracy 0.5)",
            "baseline_test_acc": float(max(yte.mean(), 1 - yte.mean())), "baseline_test_bal": 0.5}
    return (lambda: t1.build_preprocessor(num, cat)), Xtr, ytr, Xva, yva, Xte, yte, info


def new_data():
    v4 = _load("v4_bench", "train_flood_model_v4.py")
    df, _ = v4.build()
    feats = [c for c in df.columns if c not in ("y", "gauge_id", "year", "flood_today")]
    gauges = df["gauge_id"].unique()
    _, unseen_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(gauges, groups=gauges))
    is_unseen = df["gauge_id"].isin(set(gauges[unseen_idx].tolist()))
    tr = df[~is_unseen & (df["year"] <= v4.TRAIN_END)]
    va = df[~is_unseen & (df["year"] > v4.TRAIN_END) & (df["year"] <= v4.VAL_END)]
    te = df[is_unseen & (df["year"] > v4.VAL_END)]
    del df
    # Same unseen-gauge test split as train_flood_model_v4.py; saved for the
    # live re-scoring endpoint (GET /api/ml/benchmark-v4).
    v4.export_test_set(te, feats)
    rng = np.random.default_rng(SEED)
    tr = tr.iloc[rng.choice(len(tr), min(NEW_TRAIN_ROWS, len(tr)), replace=False)]
    va = va.iloc[rng.choice(len(va), min(NEW_VAL_ROWS, len(va)), replace=False)]
    ft = te["flood_today"].notna()
    ypers, fpers = te.loc[ft, "y"].to_numpy().astype(int), te.loc[ft, "flood_today"].to_numpy().astype(int)
    info = {"train": len(tr), "val": len(va), "test": len(te), "test_gauges": int(te["gauge_id"].nunique()),
            "test_positive_rate": float(te["y"].mean()),
            "baseline": "persistence: flood in next 3 days iff flooded today",
            "baseline_test_acc": float(accuracy_score(ypers, fpers)),
            "baseline_test_bal": float(balanced_accuracy_score(ypers, fpers)),
            "note": f"all 20 models fit on the same {NEW_TRAIN_ROWS:,}-row train sample for a fair comparison"}
    prep = lambda: Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())])
    return (prep, tr[feats], tr["y"].to_numpy().astype(int), va[feats], va["y"].to_numpy().astype(int),
            te[feats], te["y"].to_numpy().astype(int), info)


def main() -> None:
    out = {"rules": __doc__.split("Pass/fail rules (fixed before running):")[1].strip()}
    for label, loader in (("OLD_INDOFLOODS", old_data), ("NEW_CAMELS_IND", new_data)):
        prep, Xtr, ytr, Xva, yva, Xte, yte, info = loader()
        print(f"[{label}] {info}", flush=True)
        out[label] = {"info": info, "results": run_suite(label, prep, Xtr, ytr, Xva, yva, Xte, yte,
                                                         info["baseline_test_bal"], SVM_ROWS)}
        (MODELS / "benchmark_20_models.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("Saved models/benchmark_20_models.json")


if __name__ == "__main__":
    main()
