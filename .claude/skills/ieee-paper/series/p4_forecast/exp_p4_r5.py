"""P4 neural baseline -> <work>/p4_r5.json. Offline; same data, primary split and 500k-row training sample as the ablation.

A multilayer perceptron (scikit-learn MLPClassifier) trained on the same split, without future rain: the inputs are the
model's 50 features plus the last 14 days of q/q95 and rainfall (a short history window, so the network sees the recent
sequence directly). Hidden layers 128-64, ReLU, Adam, early stopping on a held-out 10 % of the training sample; the
decision threshold is chosen on validation balanced accuracy like every other model. Positive class weighted by
oversampling positives in the training sample to the same ratio as XGBoost's scale_pos_weight. Scored once on test,
with a paired gauge bootstrap of the difference to the all-input XGBoost refit (p4_r3_preds.npz 'all').
usage: .venv\\Scripts\\python.exe exp_p4_r5.py <work>
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, balanced_accuracy_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from backend.ml.features_v4 import DATA, TRAIN_END, VAL_END, gauge_frame, load_static  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
SEED = 42
NB = 1000
WIN = 14
t00 = time.time()


def log(*a):
    print(f"[{time.time() - t00:6.0f}s]", *a, flush=True)


qdf = pd.read_csv(DATA / "streamflow_timeseries" / "streamflow_observed.csv")
dates = pd.DatetimeIndex(pd.to_datetime(qdf[["year", "month", "day"]]))
static = load_static()
frames = []
for col in qdf.columns[3:]:
    g = gauge_frame(int(col), qdf[col].astype(float), dates)
    if g is None:
        continue
    # 14-day history of q/q95 and rainfall, known at the end of day t (lags 4..13; lags 0..3 are already inputs)
    for k in range(4, WIN):
        g[f"qr_h{k}"] = g["qr_l0"].shift(k).astype("float32")
        g[f"pr_h{k}"] = g["prcp_l0"].shift(k).astype("float32")
    frames.append(g)
df = pd.concat(frames, ignore_index=True).join(static.astype("float32"), on="gauge_id")
del frames
for c_ in df.columns:
    if df[c_].dtype == np.float64:
        df[c_] = df[c_].astype(np.float32)
meta = json.loads((ROOT / "models" / "flood_model_metadata_v4.json").read_text(encoding="utf-8"))
feats = meta["features"]
fs = feats + [f"qr_h{k}" for k in range(4, WIN)] + [f"pr_h{k}" for k in range(4, WIN)]
gauges = np.array(sorted(df["gauge_id"].unique()))
_, ui = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(gauges, groups=gauges))
unseen = set(gauges[ui].tolist())
assert sorted(int(g) for g in unseen) == meta["unseen_gauges"]
is_un = df["gauge_id"].isin(unseen).to_numpy()
yr = df["year"].to_numpy()
i_tr = np.flatnonzero(~is_un & (yr <= TRAIN_END))
i_va = np.flatnonzero(~is_un & (yr > TRAIN_END) & (yr <= VAL_END))
i_te = np.flatnonzero(is_un & (yr > VAL_END))
te = df.iloc[i_te].reset_index(drop=True)
y = te["y"].to_numpy().astype(int)
below = (te["flood_today"] == 0).to_numpy()
log("rows", len(df), "test", len(te), "inputs", len(fs))

# same 500k training sample as the ablation, then oversample positives to the XGBoost class weight
sub = i_tr[np.random.default_rng(SEED).choice(len(i_tr), min(500_000, len(i_tr)), replace=False)]
ys = df["y"].to_numpy()[sub].astype(int)
pos, neg = np.flatnonzero(ys == 1), np.flatnonzero(ys == 0)
rng = np.random.default_rng(SEED)
rep = rng.choice(pos, len(neg) - len(pos), replace=True)
idx = rng.permutation(np.concatenate([np.arange(len(ys)), rep]))
Xs = df.iloc[sub][fs].to_numpy()
va = df.iloc[i_va]
Xva, yv = va[fs].to_numpy(), va["y"].to_numpy().astype(int)
del df, va
X = Xs[idx]
del Xs
Y = ys[idx]
net = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                    MLPClassifier(hidden_layer_sizes=(128, 64), activation="relu", alpha=1e-4, batch_size=1024,
                                  learning_rate_init=1e-3, max_iter=40, early_stopping=True, validation_fraction=0.1,
                                  n_iter_no_change=4, random_state=SEED))
net.fit(X, Y)
del X, Y
mlp = net[-1]
log("trained epochs", mlp.n_iter_, "best val score", mlp.best_validation_score_)
pv = net.predict_proba(Xva)[:, 1]
grid = np.quantile(pv, np.linspace(0.5, 0.995, 120))
thr = float(max(grid, key=lambda t: balanced_accuracy_score(yv, (pv >= t).astype(int))))
s = net.predict_proba(te[fs].to_numpy())[:, 1]


def summ(sc, t):
    a = sc >= t
    tp = int((a & (y == 1)).sum())
    return {"ba": float(balanced_accuracy_score(y, a)), "pr_auc": float(average_precision_score(y, sc)),
            "precision": tp / max(int(a.sum()), 1), "recall": tp / max(int((y == 1).sum()), 1),
            "alarms_per_1000": float(1000 * a.mean()), "below_ba": float(balanced_accuracy_score(y[below], a[below])),
            "below_pr_auc": float(average_precision_score(y[below], sc[below]))}


OUT = {"inputs": len(fs), "window_days": WIN, "epochs": int(mlp.n_iter_), "thr": thr, "mlp": summ(s, thr)}
r3 = json.loads((WORK / "p4_r3.json").read_text(encoding="utf-8"))
pr3 = np.load(WORK / "p4_r3_preds.npz")
sx, tx = pr3["all"], r3["variants"]["all"]["thr"]
assert len(sx) == len(s), "same test rows as the XGBoost refit"
gids = te["gauge_id"].to_numpy()
ug = np.unique(gids)
gidx = {g: np.flatnonzero(gids == g) for g in ug}
r = np.random.default_rng(SEED)
d_ba, d_pr, d_bel = [], [], []
for _ in range(NB):
    ix = np.concatenate([gidx[g] for g in r.choice(ug, len(ug), replace=True)])
    d_ba.append(balanced_accuracy_score(y[ix], sx[ix] >= tx) - balanced_accuracy_score(y[ix], s[ix] >= thr))
    d_pr.append(average_precision_score(y[ix], sx[ix]) - average_precision_score(y[ix], s[ix]))
    bx = ix[below[ix]]
    d_bel.append(balanced_accuracy_score(y[bx], sx[bx] >= tx) - balanced_accuracy_score(y[bx], s[bx] >= thr))
ci = lambda v: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]  # noqa: E731
OUT["xgb_minus_mlp"] = {"ba_ci": ci(d_ba), "pr_ci": ci(d_pr), "below_ci": ci(d_bel)}
(WORK / "p4_r5.json").write_text(json.dumps(OUT, indent=1), encoding="utf-8")
log("mlp", {k: round(v, 4) for k, v in OUT["mlp"].items()})
log("xgb-mlp", OUT["xgb_minus_mlp"])
log("done")
