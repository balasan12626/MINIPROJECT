"""Final v4 fit on ALL training rows (1980-2008, seen gauges) -- no subsample.

Same split, features, flood definition and selection rules as
train_flood_model_v4.py. Memory-lean for an 8 GB machine: features go straight
to float32 numpy and XGBoost trains from a QuantileDMatrix.

The winning family/depth from the v4 candidate comparison (XGBoost depth 6) is
refit here. Early stopping and the decision threshold use VALIDATION only. The
full-data model replaces models/flood_forecast_v4.pkl only if its validation
balanced accuracy beats the current v4 model's; the previous model is kept as
models/flood_forecast_v4_500k.pkl. The unseen-gauge test set is then scored once.
"""

from __future__ import annotations

import gc
import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
spec = importlib.util.spec_from_file_location("v4", str(ROOT / "scripts" / "train_flood_model_v4.py"))
v4 = importlib.util.module_from_spec(spec)
sys.modules["v4"] = v4
spec.loader.exec_module(v4)


def main() -> None:
    t0 = time.time()
    df, info = v4.build()
    feats = [c for c in df.columns if c not in ("y", "gauge_id", "year", "flood_today")]
    gauges = df["gauge_id"].unique()
    _, unseen_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=v4.SEED).split(gauges, groups=gauges))
    unseen = set(gauges[unseen_idx].tolist())
    is_unseen = df["gauge_id"].isin(unseen).to_numpy()
    year = df["year"].to_numpy()
    m_tr = ~is_unseen & (year <= v4.TRAIN_END)
    m_va = ~is_unseen & (year > v4.TRAIN_END) & (year <= v4.VAL_END)
    m_te = is_unseen & (year > v4.VAL_END)

    X = df[feats].to_numpy(dtype=np.float32)
    y = df["y"].to_numpy().astype(np.int8)
    flood_today = df["flood_today"].to_numpy(dtype=np.float32)
    del df
    gc.collect()
    Xtr, ytr = X[m_tr], y[m_tr]
    Xva, yva = X[m_va], y[m_va]
    Xte, yte, ft_te = X[m_te], y[m_te], flood_today[m_te]
    del X, y, flood_today
    gc.collect()
    print(f"FULL train={len(ytr):,} (pos {ytr.mean():.3f}) val={len(yva):,} test_unseen={len(yte):,} "
          f"build={time.time()-t0:.0f}s", flush=True)

    pos_w = float((ytr == 0).sum() / max((ytr == 1).sum(), 1))
    model = xgb.XGBClassifier(
        n_estimators=3000, max_depth=6, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
        min_child_weight=20, reg_lambda=5.0, scale_pos_weight=pos_w, tree_method="hist", max_bin=256,
        eval_metric="aucpr", early_stopping_rounds=100, n_jobs=-1, random_state=v4.SEED,
    )
    t1 = time.time()
    model.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)
    print(f"fit {time.time()-t1:.0f}s best_iteration={model.best_iteration}", flush=True)

    p_va = model.predict_proba(Xva)[:, 1]
    thr = v4.pick_threshold(yva, p_va)
    val = v4.scores(yva, p_va, thr)
    rng = np.random.default_rng(v4.SEED)
    tr_idx = rng.choice(len(ytr), min(500_000, len(ytr)), replace=False)  # train score on a sample (RAM)
    train = v4.scores(ytr[tr_idx], model.predict_proba(Xtr[tr_idx])[:, 1], thr)
    del Xtr
    gc.collect()

    ev_path = MODELS / "flood_evaluation_v4.json"
    evaluation = json.loads(ev_path.read_text(encoding="utf-8"))
    old_name = evaluation["selected_model"]
    old_val = evaluation["candidates"][old_name]["validation"]["balanced_accuracy"]
    print(f"VALIDATION full-data bal_acc={val['balanced_accuracy']:.4f} vs current {old_name} {old_val:.4f} "
          f"(train bal_acc={train['balanced_accuracy']:.4f})", flush=True)

    name = "xgboost_d6_full"
    evaluation["candidates"][name] = {"fit_rows": "full", "fit_seconds": round(time.time() - t1, 1),
                                      "best_iteration": int(model.best_iteration),
                                      "train": train, "validation": val}
    if val["balanced_accuracy"] <= old_val:
        evaluation["full_data_refit"] = {"kept": old_name, "reason": "full-data refit did not improve validation"}
        ev_path.write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
        print("KEPT existing model (full-data refit not better on validation)")
        return

    # Winner on validation -> score the untouched test ONCE, then promote.
    prob = model.predict_proba(Xte)[:, 1]
    m = ~np.isnan(ft_te)
    onset = ft_te == 0
    yte = yte.astype(int)
    test_unseen = {
        "model": v4.scores(yte, prob, thr),
        "model_flood_onset_only": v4.scores(yte[onset], prob[onset], thr),
        "baseline_persistence": v4.scores(yte[m], ft_te[m].astype(int), 0.5),
        "baseline_always_no_flood_accuracy": float(1 - yte.mean()),
    }
    t = test_unseen["model"]
    print(f"TEST unseen_gauges_2015_2020: acc={t['accuracy']:.4f} bal_acc={t['balanced_accuracy']:.4f} "
          f"recall={t['recall']:.4f} prec={t['precision']:.4f} auc={t['roc_auc']:.4f}", flush=True)

    backup = MODELS / "flood_forecast_v4_500k.pkl"
    if not backup.exists():
        shutil.copy2(MODELS / "flood_forecast_v4.pkl", backup)
    joblib.dump(model, MODELS / "flood_forecast_v4.pkl")
    evaluation["previous_selected_model"] = old_name
    evaluation["selected_model"] = name
    evaluation["decision_threshold"] = thr
    evaluation["test"]["unseen_gauges_2015_2020"] = test_unseen
    evaluation["test"].pop("seen_gauges_2015_2020", None)  # belonged to the 500k model; not rescored
    evaluation["full_data_refit"] = {"kept": name, "previous_model_backup": backup.name}
    ev_path.write_text(json.dumps(evaluation, indent=2), encoding="utf-8")

    meta_path = MODELS / "flood_model_metadata_v4.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update(model=name, decision_threshold=thr, n_train=int(len(ytr)), version="4.1.0",
                note="refit on all training rows; selected over the 500k-sample model on validation")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"PROMOTED {name} -> models/flood_forecast_v4.pkl (backup {backup.name}) total={time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
