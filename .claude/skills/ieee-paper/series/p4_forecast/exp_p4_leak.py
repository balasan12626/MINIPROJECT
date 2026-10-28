"""How much does the evaluation protocol inflate skill? -> <work>/p4_leak.json.

Same task, features, flood thresholds (train-period p95) and XGBoost configuration as exp_p4.py; only the
split changes. For each protocol the model is fitted on a 500k-row sample of its training part, the decision
threshold is chosen on its validation part, and it is scored once on its test part:
  random   - all gauges and years, rows shuffled: 70 % train, 10 % validation, 20 % test (seed 42)
  time     - seen gauges: train 1980-2008, validation 2009-2014, test 2015-2020
  space    - unseen gauges in the training years 1980-2008 (validation = seen gauges 2009-2014)
  space+time (the paper's protocol) - unseen gauges 2015-2020
Bootstrap over test gauges (500 resamples) gives intervals for balanced accuracy.
usage: .venv\\Scripts\\python.exe exp_p4_leak.py <work>
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, balanced_accuracy_score
from sklearn.model_selection import GroupShuffleSplit
from xgboost import XGBClassifier

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from backend.ml.features_v4 import DATA, TRAIN_END, VAL_END, gauge_frame, load_static  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
SEED = 42
t00 = time.time()


def log(*a):
    print(f"[{time.time() - t00:6.0f}s]", *a, flush=True)


qdf = pd.read_csv(DATA / "streamflow_timeseries" / "streamflow_observed.csv")
dates = pd.DatetimeIndex(pd.to_datetime(qdf[["year", "month", "day"]]))
static = load_static()
meta = json.loads((ROOT / "models" / "flood_model_metadata_v4.json").read_text(encoding="utf-8"))
feats = meta["features"]
frames = []
for col in qdf.columns[3:]:
    g = gauge_frame(int(col), qdf[col].astype(float), dates)
    if g is not None:
        frames.append(g)
df = pd.concat(frames, ignore_index=True).join(static.astype("float32"), on="gauge_id")
del frames
df = df[["gauge_id", "year", "y"] + feats]
gauges = df["gauge_id"].unique()
_, ui = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(gauges, groups=gauges))
unseen = set(gauges[ui].tolist())
assert sorted(int(g) for g in unseen) == meta["unseen_gauges"], "same unseen gauges as the paper"
is_un = df["gauge_id"].isin(unseen).to_numpy()
yr = df["year"].to_numpy()
log(f"rows={len(df):,}")

rng = np.random.default_rng(SEED)
perm = rng.permutation(len(df))
n = len(df)
rand_tr, rand_va, rand_te = perm[:int(0.7 * n)], perm[int(0.7 * n):int(0.8 * n)], perm[int(0.8 * n):]
seen_tr = np.flatnonzero(~is_un & (yr <= TRAIN_END))
seen_va = np.flatnonzero(~is_un & (yr > TRAIN_END) & (yr <= VAL_END))
PROT = {
    "random": (rand_tr, rand_va, rand_te),
    "time": (seen_tr, seen_va, np.flatnonzero(~is_un & (yr > VAL_END))),
    "space": (seen_tr, seen_va, np.flatnonzero(is_un & (yr <= TRAIN_END))),
    "space_time": (seen_tr, seen_va, np.flatnonzero(is_un & (yr > VAL_END))),
}


def pick(y, s):
    grid = np.quantile(s, np.linspace(0.5, 0.995, 120))
    return float(max(grid, key=lambda t: balanced_accuracy_score(y, (s >= t).astype(int))))


out = {"n_rows": int(n), "protocols": {}}
fitted = {}
for name, (itr, iva, ite) in PROT.items():
    key = "seen" if name != "random" else "random"
    if key not in fitted:
        sub = itr if len(itr) <= 500_000 else np.random.default_rng(SEED).choice(itr, 500_000, replace=False)
        Xs, ys = df.iloc[sub][feats], df.iloc[sub]["y"].to_numpy().astype(int)
        Xv, yv = df.iloc[iva][feats], df.iloc[iva]["y"].to_numpy().astype(int)
        m = XGBClassifier(n_estimators=3000, max_depth=6, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                          min_child_weight=20, reg_lambda=5.0, scale_pos_weight=float((ys == 0).sum() / max(ys.sum(), 1)),
                          tree_method="hist", eval_metric="aucpr", early_stopping_rounds=100, n_jobs=4,
                          random_state=SEED)
        m.fit(Xs, ys, eval_set=[(Xv, yv)], verbose=False)
        fitted[key] = (m, pick(yv, m.predict_proba(Xv)[:, 1]))
        log("fitted", key, "trees", m.best_iteration + 1)
    m, thr = fitted[key]
    te = df.iloc[ite]
    y = te["y"].to_numpy().astype(int)
    p = m.predict_proba(te[feats])[:, 1]
    yp = (p >= thr).astype(int)
    tp, fp, fn = int(((yp == 1) & (y == 1)).sum()), int(((yp == 1) & (y == 0)).sum()), int(((yp == 0) & (y == 1)).sum())
    gid = te["gauge_id"].to_numpy()
    ug = np.unique(gid)
    idx = {g: np.flatnonzero(gid == g) for g in ug}
    br = np.random.default_rng(SEED)
    bs = []
    for _ in range(500):
        ix = np.concatenate([idx[g] for g in br.choice(ug, len(ug), replace=True)])
        if y[ix].min() != y[ix].max():
            bs.append(balanced_accuracy_score(y[ix], yp[ix]))
    out["protocols"][name] = {"n_test": int(len(y)), "n_gauges": int(len(ug)), "pos_rate": float(y.mean()),
                              "thr": thr, "ba": float(balanced_accuracy_score(y, yp)),
                              "ba_ci": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
                              "pr_auc": float(average_precision_score(y, p)),
                              "recall": tp / max(tp + fn, 1), "precision": tp / max(tp + fp, 1)}
    log(name, {k: round(v, 3) for k, v in out["protocols"][name].items() if isinstance(v, float)})
(WORK / "p4_leak.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
log("done")
