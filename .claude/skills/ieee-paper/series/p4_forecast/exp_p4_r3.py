"""P4 third revision -> <work>/p4_r3.json and <work>/p4_r3_preds.npz. Offline; same data, task and features as exp_p4.py.

Answers the third review round. Every refit uses the primary split (seed 42) and the same 500k-row training sample,
configuration and validation-chosen threshold as the ablation, so the variants are compared with each other:
  clim       - the four CAMELS-IND climate indices (p_mean, pet_mean, aridity_p_pet, high_prec_freq) best match the full
               1980-2020 record, so they hold test-year rainfall. Refits: without them, and with them recomputed from
               1980-2008 forcing only (temporally valid).
  realtime   - without the reanalysis inputs that arrive late (humidity, GLEAM PET/AET, soil moisture).
  ablation   - all inputs, no flow, flow + season, meteorology + season, with per-row test predictions, so below-level
               differences get paired gauge-bootstrap intervals; onset warnings at each model's own threshold and at
               the all-input model's alarm rate (fair comparison of warning counts).
  logreg     - logistic regression on the same sample, scored once on the test set.
  samerows   - a random 70/10/20 row split model and the held-out model scored on the SAME rows (random-split test rows
               that are also held-out gauges in 2015-2020), with a paired gauge bootstrap of the difference.
  main       - stored selected model: gauge x year block bootstrap of BA (year-to-year variance); trend rule BA interval
               and PR curve.
usage: .venv\\Scripts\\python.exe exp_p4_r3.py <work>      (resumes: steps already in p4_r3.json are skipped)
"""
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, balanced_accuracy_score, precision_recall_curve
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from backend.ml.features_v4 import DATA, TRAIN_END, VAL_END, gauge_frame, load_static  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
SEED = 42
NB = 1000
t00 = time.time()
OUT_F = WORK / "p4_r3.json"
PRED_F = WORK / "p4_r3_preds.npz"
OUT = json.loads(OUT_F.read_text(encoding="utf-8")) if OUT_F.exists() else {}
PRED = dict(np.load(PRED_F)) if PRED_F.exists() else {}


def log(*a):
    print(f"[{time.time() - t00:6.0f}s]", *a, flush=True)


def save():
    OUT_F.write_text(json.dumps(OUT, default=float, indent=1), encoding="utf-8")
    np.savez_compressed(PRED_F, **PRED)


# ----------------------------------------------------------------------------- data (as exp_p4.py)
qdf = pd.read_csv(DATA / "streamflow_timeseries" / "streamflow_observed.csv")
dates = pd.DatetimeIndex(pd.to_datetime(qdf[["year", "month", "day"]]))
static = load_static()
CLIM = ["p_mean", "pet_mean", "aridity_p_pet", "high_prec_freq"]
clim_tr = {}
frames = []
for col in qdf.columns[3:]:
    g = gauge_frame(int(col), qdf[col].astype(float), dates)
    if g is None:
        continue
    gid = int(col)
    f = pd.read_csv(DATA / "catchment_mean_forcings" / f"{gid:05d}.csv")
    f = f[f["year"] <= TRAIN_END]
    p, pet = f["prcp(mm/day)"], f["pet(mm/day)"]
    clim_tr[gid] = {"p_mean": p.mean(), "pet_mean": pet.mean(), "aridity_p_pet": p.mean() / pet.mean(),
                    "high_prec_freq": float((p >= 5 * p.mean()).mean() * 365.25)}
    g["date"] = g.index
    frames.append(g)
df = pd.concat(frames, ignore_index=True).join(static.astype("float32"), on="gauge_id")
del frames
for c_ in df.columns:
    if df[c_].dtype == np.float64:
        df[c_] = df[c_].astype(np.float32)
ct = pd.DataFrame(clim_tr).T.astype("float32")
for c in CLIM:
    df[c + "_tr"] = df["gauge_id"].map(ct[c])
meta = json.loads((ROOT / "models" / "flood_model_metadata_v4.json").read_text(encoding="utf-8"))
feats = meta["features"]
assert all(c in feats for c in CLIM), "the four climate indices are model inputs"
gauges = np.array(sorted(df["gauge_id"].unique()))
log("rows", len(df), "gauges", len(gauges))
OUT["clim_audit"] = {c: {"corr_full_vs_train": float(np.corrcoef(static.loc[ct.index, c], ct[c])[0, 1]),
                         "mean_abs_diff": float((static.loc[ct.index, c] - ct[c]).abs().mean())} for c in CLIM}

GROUPS = {
    "flow": [f for f in feats if f.startswith("qr_") or f in ("log_q", "q_obs_today")],
    "rain": [f for f in feats if f.startswith("prcp_")],
    "weather": [f for f in feats if f in ("tmax", "tmin", "rh", "pet", "aet")],
    "soil": [f for f in feats if f.startswith("sm")],
    "season": [f for f in feats if f.startswith("doy_")],
}
MET = GROUPS["rain"] + GROUPS["weather"] + GROUPS["soil"] + GROUPS["season"]
LATE = [f for f in feats if f in ("rh", "pet", "aet") or f.startswith("sm")]
VARIANTS = {
    "all": feats,
    "no_flow": [f for f in feats if f not in GROUPS["flow"]],
    "flow_season": GROUPS["flow"] + GROUPS["season"],
    "met_season": MET,
    "no_clim": [f for f in feats if f not in CLIM],
    "clim_train": [f + "_tr" if f in CLIM else f for f in feats],
    "realtime": [f for f in feats if f not in LATE],
}

_, ui = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(gauges, groups=gauges))
unseen = set(gauges[ui].tolist())
assert sorted(int(g) for g in unseen) == meta["unseen_gauges"], "same unseen gauges as the stored split"
is_un = df["gauge_id"].isin(unseen).to_numpy()
yr = df["year"].to_numpy()
i_tr = np.flatnonzero(~is_un & (yr <= TRAIN_END))
i_va = np.flatnonzero(~is_un & (yr > TRAIN_END) & (yr <= VAL_END))
i_te = np.flatnonzero(is_un & (yr > VAL_END))
te = df.iloc[i_te].reset_index(drop=True)
y = te["y"].to_numpy().astype(int)
below = (te["flood_today"] == 0).to_numpy()
gids = te["gauge_id"].to_numpy()
ug = np.unique(gids)
gidx = {g: np.flatnonzero(gids == g) for g in ug}
rng = np.random.default_rng(SEED)
BOOTG = rng.choice(ug, (NB, len(ug)), replace=True)


def boots():
    for row in BOOTG:
        yield np.concatenate([gidx[g] for g in row])

log("test rows", len(te))


def pick(yv, s):
    grid = np.quantile(s[np.isfinite(s)], np.linspace(0.5, 0.995, 120))
    return float(max(grid, key=lambda t: balanced_accuracy_score(yv, (s >= t).astype(int))))


def ba(yy, a):
    return float(balanced_accuracy_score(yy, a)) if yy.min() != yy.max() else float("nan")


def summary(s, t, rows=None):
    rows = np.arange(len(y)) if rows is None else rows
    yy, ss = y[rows], s[rows]
    a = ss >= t
    tp = int((a & (yy == 1)).sum())
    r = {"ba": ba(yy, a), "pr_auc": float(average_precision_score(yy, ss)), "alarms_per_1000": float(1000 * a.mean()),
         "precision": tp / max(int(a.sum()), 1), "recall": tp / max(int((yy == 1).sum()), 1)}
    b = below[rows]
    r["below_ba"] = ba(yy[b], a[b])
    r["below_pr_auc"] = float(average_precision_score(yy[b], ss[b]))
    return r


def ci(v):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]


# onsets: river reaches q95 after >= 7 observed days below it (as exp_p4.py)
ONS = []
for g, gi in gidx.items():
    order = gi[np.argsort(te["date"].to_numpy()[gi])]
    ft = te["flood_today"].to_numpy()[order]
    d = te["date"].to_numpy()[order]
    pos = {pd.Timestamp(x): k for k, x in enumerate(d)}
    for k in range(7, len(order)):
        if ft[k] == 1 and np.all(ft[k - 7:k] == 0) and (pd.Timestamp(d[k]) - pd.Timestamp(d[k - 7])).days == 7:
            ONS.append([order[pos[pd.Timestamp(d[k]) - pd.Timedelta(days=L)]] if (pd.Timestamp(d[k]) - pd.Timedelta(days=L)) in pos
                        else -1 for L in (1, 2, 3)])
ONS = np.array(ONS)
log("onsets", len(ONS))


def warned(s, t):
    a = np.zeros(len(ONS), bool)
    for c in range(3):
        ok = ONS[:, c] >= 0
        a[ok] |= s[ONS[ok, c]] >= t
    return float(100 * a.mean())


def fit_xgb(fs):
    sub = i_tr[np.random.default_rng(SEED).choice(len(i_tr), min(500_000, len(i_tr)), replace=False)]
    ys = df["y"].to_numpy()[sub].astype(int)
    yv = df["y"].to_numpy()[i_va].astype(int)
    m = XGBClassifier(n_estimators=3000, max_depth=6, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                      min_child_weight=20, reg_lambda=5.0, scale_pos_weight=float((ys == 0).sum() / (ys == 1).sum()),
                      tree_method="hist", eval_metric="aucpr", early_stopping_rounds=100, n_jobs=4, random_state=SEED)
    Xs = df.iloc[sub][fs]
    Xv = df.iloc[i_va][fs]
    m.fit(Xs, ys, eval_set=[(Xv, yv)], verbose=False)
    return m, pick(yv, m.predict_proba(Xv)[:, 1])


# ----------------------------------------------------------------------------- 1. stored selected model, trend rule
if "main" not in OUT:
    model = joblib.load(ROOT / "models" / "flood_forecast_v4.pkl")
    THR = float(meta["decision_threshold"])
    p = model.predict_proba(te[feats])[:, 1]
    assert abs(balanced_accuracy_score(y, (p >= THR).astype(int)) - 0.8978479116831157) < 1e-9
    PRED["selected"] = p.astype("float32")
    # gauge x year block bootstrap: resample gauges, then years within the test period
    yrs = te["year"].to_numpy()
    uy = np.unique(yrs)
    gy = {(g, t): np.flatnonzero((gids == g) & (yrs == t)) for g in ug for t in uy}
    r2 = np.random.default_rng(SEED + 1)
    two = []
    for _ in range(NB):
        gs, ts = r2.choice(ug, len(ug)), r2.choice(uy, len(uy))
        ix = np.concatenate([gy[(g, t)] for g in gs for t in ts])
        two.append(ba(y[ix], p[ix] >= THR))
    q0 = np.nan_to_num(te["qr_l0"].to_numpy(), nan=0.0)
    d3 = np.nan_to_num(te["qr_d3"].to_numpy(), nan=0.0)
    tr_s = q0 + np.maximum(0.0, d3)
    va = df.iloc[i_va]
    tr_v = np.nan_to_num(va["qr_l0"].to_numpy(), nan=0.0) + np.maximum(0.0, np.nan_to_num(va["qr_d3"].to_numpy(), nan=0.0))
    t_tr = pick(va["y"].to_numpy().astype(int), tr_v)
    PRED["trend"] = tr_s.astype("float32")
    pr, rc, _ = precision_recall_curve(y, tr_s)
    keep = np.unique(np.linspace(0, len(pr) - 1, 400).astype(int))
    OUT["main"] = {"thr": THR, "ba": ba(y, p >= THR), "ba_ci_gauge": ci([ba(y[ix], p[ix] >= THR) for ix in boots()]),
                   "ba_ci_gauge_year": ci(two), "years": [int(t) for t in uy],
                   "trend": summary(tr_s, t_tr) | {"thr": t_tr, "ba_ci": ci([ba(y[ix], tr_s[ix] >= t_tr) for ix in boots()]),
                                                     "pr_curve": {"precision": pr[keep].tolist(), "recall": rc[keep].tolist()}},
                   "warned_pct": warned(p, THR), "n_onsets": int(len(ONS))}
    save()
    log("main", OUT["main"]["ba"], OUT["main"]["ba_ci_gauge"], OUT["main"]["ba_ci_gauge_year"], "trend", OUT["main"]["trend"]["ba_ci"])

# ----------------------------------------------------------------------------- 2. refits on the primary split
OUT.setdefault("variants", {})
for name, fs in VARIANTS.items():
    if name in OUT["variants"]:
        continue
    m, t = fit_xgb(fs)
    s = m.predict_proba(te[fs])[:, 1]
    PRED[name] = s.astype("float32")
    OUT["variants"][name] = summary(s, t) | {"thr": t, "n_inputs": len(fs), "warned_pct": warned(s, t),
                                             "best_iteration": int(m.best_iteration)}
    save()
    v = OUT["variants"][name]
    log(name, round(v["ba"], 4), round(v["pr_auc"], 4), round(v["below_ba"], 4), round(v["alarms_per_1000"], 1))

# paired gauge-bootstrap intervals of the differences, and onset warnings at a common alarm rate
if "paired" not in OUT:
    V = OUT["variants"]
    th = {k: V[k]["thr"] for k in V}
    pairs = {"all-no_flow": ("all", "no_flow"), "all-flow_season": ("all", "flow_season"),
             "all-met_season": ("all", "met_season"), "met_season-flow_season": ("met_season", "flow_season"),
             "all-no_clim": ("all", "no_clim"), "all-clim_train": ("all", "clim_train"), "all-realtime": ("all", "realtime")}
    OUT["paired"] = {}
    for nm, (a_, b_) in pairs.items():
        sa, sb = PRED[a_], PRED[b_]
        d_all = [ba(y[ix], sa[ix] >= th[a_]) - ba(y[ix], sb[ix] >= th[b_]) for ix in boots()]
        d_bel = []
        for ix in boots():
            bx = ix[below[ix]]
            d_bel.append(ba(y[bx], sa[bx] >= th[a_]) - ba(y[bx], sb[bx] >= th[b_]))
        OUT["paired"][nm] = {"ba_diff": V[a_]["ba"] - V[b_]["ba"], "ba_ci": ci(d_all),
                             "below_diff": V[a_]["below_ba"] - V[b_]["below_ba"], "below_ci": ci(d_bel)}
    rate = float((PRED["all"] >= th["all"]).mean())
    OUT["matched_warn"] = {"alarm_rate": rate}
    for k in ("all", "no_flow", "met_season", "flow_season"):
        t_m = float(np.quantile(PRED[k], 1 - rate))
        OUT["matched_warn"][k] = {"own_thr_pct": V[k]["warned_pct"], "matched_pct": warned(PRED[k], t_m)}
    save()
    log("paired", {k: (round(v["below_diff"], 4), [round(x, 4) for x in v["below_ci"]]) for k, v in OUT["paired"].items()})
    log("matched warnings", OUT["matched_warn"])

# ----------------------------------------------------------------------------- 3. logistic regression
if "logreg" not in OUT:
    sub = i_tr[np.random.default_rng(SEED).choice(len(i_tr), min(500_000, len(i_tr)), replace=False)]
    lr = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                       LogisticRegression(max_iter=2000, class_weight="balanced"))
    lr.fit(df.iloc[sub][feats], df["y"].to_numpy()[sub].astype(int))
    va = df.iloc[i_va]
    t_lr = pick(va["y"].to_numpy().astype(int), lr.predict_proba(va[feats])[:, 1])
    s = lr.predict_proba(te[feats])[:, 1]
    PRED["logreg"] = s.astype("float32")
    OUT["logreg"] = summary(s, t_lr) | {"thr": t_lr, "ba_ci": ci([ba(y[ix], s[ix] >= t_lr) for ix in boots()]),
                                         "diff_vs_all_ci": ci([ba(y[ix], PRED["all"][ix] >= OUT["variants"]["all"]["thr"])
                                                               - ba(y[ix], s[ix] >= t_lr) for ix in boots()])}
    save()
    log("logreg", OUT["logreg"]["ba"], OUT["logreg"]["pr_auc"])

# ----------------------------------------------------------------------------- 4. random split, scored on the same rows
if "samerows" not in OUT:
    n = len(df)
    perm = np.random.default_rng(SEED).permutation(n)
    r_tr, r_va, r_te = perm[:int(0.7 * n)], perm[int(0.7 * n):int(0.8 * n)], perm[int(0.8 * n):]
    sub = r_tr[np.random.default_rng(SEED).choice(len(r_tr), 500_000, replace=False)]
    ys = df["y"].to_numpy()[sub].astype(int)
    yv = df["y"].to_numpy()[r_va].astype(int)
    m = XGBClassifier(n_estimators=3000, max_depth=6, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                      min_child_weight=20, reg_lambda=5.0, scale_pos_weight=float((ys == 0).sum() / (ys == 1).sum()),
                      tree_method="hist", eval_metric="aucpr", early_stopping_rounds=100, n_jobs=4, random_state=SEED)
    m.fit(df.iloc[sub][feats], ys, eval_set=[(df.iloc[r_va][feats], yv)], verbose=False)
    t_r = pick(yv, m.predict_proba(df.iloc[r_va][feats])[:, 1])
    pos_te = {int(r): k for k, r in enumerate(i_te)}
    common = np.array(sorted(pos_te[int(r)] for r in np.intersect1d(r_te, i_te)))
    s_r = np.full(len(te), np.nan, "float32")
    s_r[common] = m.predict_proba(te.iloc[common][feats])[:, 1]
    PRED["random_on_common"] = s_r
    s_h, t_h = PRED["all"], OUT["variants"]["all"]["thr"]
    cg = gids[common]
    cidx = {g: common[cg == g] for g in np.unique(cg)}
    cu = np.array(sorted(cidx))
    r3 = np.random.default_rng(SEED + 2)
    dba, dpr = [], []
    for _ in range(NB):
        ix = np.concatenate([cidx[g] for g in r3.choice(cu, len(cu), replace=True)])
        dba.append(ba(y[ix], s_r[ix] >= t_r) - ba(y[ix], s_h[ix] >= t_h))
        dpr.append(float(average_precision_score(y[ix], s_r[ix]) - average_precision_score(y[ix], s_h[ix])))
    OUT["samerows"] = {"n_rows": int(len(common)), "n_gauges": int(len(cu)), "prev": float(y[common].mean()),
                       "random": summary(np.nan_to_num(s_r, nan=0.0), t_r, common) | {"thr": t_r},
                       "heldout": summary(s_h, t_h, common),
                       "ba_diff_ci": ci(dba), "pr_diff_ci": ci(dpr)}
    save()
    log("samerows", OUT["samerows"]["random"]["ba"], OUT["samerows"]["heldout"]["ba"], OUT["samerows"]["ba_diff_ci"])
log("done")
