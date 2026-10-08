"""V4 flood-forecast benchmark (CAMELS-IND, 3-day horizon).

`live_benchmark()` re-scores the saved v4 model on the untouched unseen-gauge
test set every time it is called, so the numbers shown in the UI are computed
now, from the artifact on disk -- not copied from a JSON file. The training-time
20-model comparison and the model's own train/validation scores are read from
the evaluation artifacts written by scripts/train_flood_model_v4.py and
scripts/benchmark_20_models.py.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score,
    precision_score, recall_score, roc_auc_score,
)

from backend.ml.inference import models_dir

_lock = threading.Lock()
_cache: dict[str, Any] = {}


def _read_json(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _load() -> tuple[Any, dict, dict] | None:
    directory = models_dir()
    paths = [directory / n for n in ("flood_forecast_v4.pkl", "flood_test_unseen_v4.npz", "flood_evaluation_v4.json")]
    if not all(p.exists() for p in paths):
        return None
    key = tuple(p.stat().st_mtime for p in paths)
    with _lock:
        if _cache.get("key") != key:
            data = np.load(paths[1], allow_pickle=False)
            _cache.update(
                key=key,
                model=joblib.load(paths[0]),
                test={k: data[k] for k in data.files},
                evaluation=_read_json(paths[2]) or {},
            )
        return _cache["model"], _cache["test"], _cache["evaluation"]


def _scores(y: np.ndarray, pred: np.ndarray, prob: np.ndarray | None = None) -> dict:
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    out = {
        "accuracy": float(accuracy_score(y, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp), "n": int(len(y)),
    }
    if prob is not None:
        out["roc_auc"] = float(roc_auc_score(y, prob))
    return out


def _fit_verdict(train_bal: float, test_bal: float) -> str:
    if train_bal < 0.80:
        return "UNDERFIT"
    if train_bal - test_bal > 0.05:
        return "OVERFIT"
    return "BALANCED"


def _zoo_summary() -> dict | None:
    bench = _read_json(models_dir() / "benchmark_20_models.json")
    if not bench:
        return None
    out = {"rules": bench.get("rules")}
    for key, label in (("NEW_CAMELS_IND", "new"), ("OLD_INDOFLOODS", "old")):
        block = bench.get(key)
        if not block:
            continue
        rows = []
        for r in block.get("results", []):
            if "error" in r:
                rows.append({"model": r["model"], "error": r["error"]})
                continue
            rows.append({
                "model": r["model"],
                "train_bal": r["train"]["bal"], "val_bal": r["val"]["bal"],
                "test_acc": r["test"]["acc"], "test_bal": r["test"]["bal"], "test_auc": r["test"]["auc"],
                "gap": r["gap_train_test_bal"], "verdict": r["verdict"],
                "passed": r["passed"], "tests": r["tests"], "note": r.get("note") or "",
            })
        out[label] = {"info": block.get("info"), "rows": rows}
    return out


def live_benchmark() -> dict:
    loaded = _load()
    if loaded is None:
        names = ("flood_forecast_v4.pkl", "flood_test_unseen_v4.npz", "flood_evaluation_v4.json")
        missing = [n for n in names if not (models_dir() / n).exists()]
        return {"available": False, "missing": missing,
                "message": "V4 MODEL NOT TRAINED YET -- missing models/" + ", models/".join(missing)
                           + ". Run scripts/train_flood_model_v4.py, then retry."}
    model, test, evaluation = loaded
    thr = float(evaluation["decision_threshold"])
    X, y = test["X"], test["y"].astype(int)

    t0 = time.perf_counter()
    prob = model.predict_proba(X)[:, 1]
    elapsed_ms = (time.perf_counter() - t0) * 1000
    live = _scores(y, (prob >= thr).astype(int), prob)

    ft = test["flood_today"]
    m = ~np.isnan(ft)
    persistence = _scores(y[m], ft[m].astype(int))

    selected = evaluation.get("selected_model")
    cand = (evaluation.get("candidates") or {}).get(selected, {})
    train_bal = (cand.get("train") or {}).get("balanced_accuracy")
    val_bal = (cand.get("validation") or {}).get("balanced_accuracy")

    return {
        "available": True,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "task": evaluation.get("task"),
        "dataset": "CAMELS-IND (228 gauged catchments, Peninsular India, 1980-2020)",
        "selected_model": selected,
        "decision_threshold": thr,
        "test_set": {"rows": int(len(y)), "gauges": int(len(np.unique(test["gauge_id"]))),
                     "years": "2015-2020", "unseen_gauges": True, "flood_rate": float(y.mean())},
        "live_test": live,
        "baseline_persistence": persistence,
        "baseline_always_no_flood_accuracy": float(1 - y.mean()),
        "inference": {"rows": int(len(y)), "total_ms": round(elapsed_ms, 1),
                      "per_1000_rows_ms": round(elapsed_ms / max(len(y), 1) * 1000, 2)},
        "fit_check": {
            "train_balanced_accuracy": train_bal,
            "validation_balanced_accuracy": val_bal,
            "test_balanced_accuracy": live["balanced_accuracy"],
            "verdict": _fit_verdict(train_bal, live["balanced_accuracy"]) if train_bal is not None else None,
        },
        "candidates": {
            name: {"train_bal": c["train"]["balanced_accuracy"], "val_bal": c["validation"]["balanced_accuracy"],
                   "val_auc": c["validation"]["roc_auc"]}
            for name, c in (evaluation.get("candidates") or {}).items()
        },
        "zoo": _zoo_summary(),
    }
