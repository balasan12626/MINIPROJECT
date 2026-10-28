"""P4 second revision -> <work>/p4_r2.json. Offline; same data, task and features as exp_p4.py.

Answers the reviewer's requests that need new computation:
  onset     - onset-row BA and PR-AUC for every reference (persistence, climatology, LSTM, trend rule)
  trend     - a recession/trend rule with no learning: score = q_t/q95 + max(0, q_t - q_{t-3})/q95
  lstm      - paired gauge-bootstrap CI of BA(XGBoost) - BA(LSTM); both at a matched alarm rate
  splits    - five more random 20 % gauge splits (seeds 1..5) and a leave-basin-out evaluation
              (gauges grouped by CAMELS-IND river basin), each refit on a 500k-row sample like the ablation
  q99       - the same task with the 99th percentile as flood level (refit + test)
  ablation  - meteorology-only (rain, weather, soil moisture, season) on onset rows; a model without the
              positive-class weight (tests the over-confidence explanation)
  data      - rows dropped for missing flow and whether they cluster in the monsoon or after high flow;
              the dataset's 228-gauge (>30 % flow availability) subset; skill per test year; skill against
              reservoir regulation; flood-day rate in the test years (non-stationarity)
  calib     - Brier score, ECE with a gauge-bootstrap CI, ECE and Brier by season
  episodes  - alarms grouped into episodes; false episodes; a random-alarm reference for onset warnings
usage: .venv\\Scripts\\python.exe exp_p4_r2.py <work>
"""
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.isotonic import IsotonicRegression
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
OUT = {}
OUT_F = WORK / "p4_r2.json"


def log(*a):
    print(f"[{time.time() - t00:6.0f}s]", *a, flush=True)


def save():
    OUT_F.write_text(json.dumps(OUT, default=float), encoding="utf-8")


# ----------------------------------------------------------------------------- rebuild (as exp_p4.py) + q99 target
qdf = pd.read_csv(DATA / "streamflow_timeseries" / "streamflow_observed.csv")
dates = pd.DatetimeIndex(pd.to_datetime(qdf[["year", "month", "day"]]))
lstm = pd.read_csv(DATA / "streamflow_timeseries" / "lstm_pred_streamflow.csv")
lstm.index = pd.DatetimeIndex(pd.to_datetime(lstm[["year", "month", "day"]]))
static = load_static()
names = pd.read_csv(DATA / "attributes_csv" / "camels_ind_name.csv").set_index("gauge_id")
anth = pd.read_csv(DATA / "attributes_csv" / "camels_ind_anth.csv").set_index("gauge_id")
frames, thr, dropped = [], {}, []
for col in qdf.columns[3:]:
    q = qdf[col].astype(float)
    g = gauge_frame(int(col), q, dates)
    if g is None:
        continue
    gid = int(col)
    thr[gid] = g.attrs["flood_threshold"]
    qs = q.set_axis(dates)
    t99 = float(qs[qs.index.year <= TRAIN_END].dropna().quantile(0.99))
    fut = pd.concat([qs.shift(-k) for k in (1, 2, 3)], axis=1)
    y99 = pd.Series(np.where(fut.notna().any(axis=1), (fut.max(axis=1) >= t99).astype(float), np.nan), index=dates)
    g["y99"] = y99.reindex(g.index).astype("float32")
    # days inside the gauge's observed span whose target is undefined (no flow observed on t+1..t+3)
    obs = qs.notna().to_numpy()
    span = np.zeros(len(dates), bool)
    span[np.argmax(obs):len(obs) - np.argmax(obs[::-1])] = True
    und = span & ~fut.notna().any(axis=1).to_numpy()
    kept = span & ~und
    prev_q = (qs / thr[gid]).ffill().shift(1).to_numpy()
    monsoon = dates.month.isin([6, 7, 8, 9])
    dropped.append({"gauge": gid, "n_days": int(span.sum()), "n_dropped": int(und.sum()),
                    "dropped_monsoon": int((und & monsoon).sum()),
                    "dropped_after_high": int((und & (prev_q >= 1.0)).sum()),
                    "kept": int(kept.sum()), "kept_monsoon": int((kept & monsoon).sum()),
                    "kept_after_high": int((kept & (prev_q >= 1.0)).sum())})
    if col in lstm.columns:
        sim = lstm[col].astype(float).reindex(dates)
        fl = pd.concat([sim.shift(-k) for k in (1, 2, 3)], axis=1).max(axis=1)
        g["lstm_score"] = (fl / thr[gid]).reindex(g.index).astype("float32").to_numpy()
    else:
        g["lstm_score"] = np.nan
    g["date"] = g.index
    frames.append(g)
df = pd.concat(frames, ignore_index=True).join(static.astype("float32"), on="gauge_id")
del frames
meta = json.loads((ROOT / "models" / "flood_model_metadata_v4.json").read_text(encoding="utf-8"))
feats = meta["features"]
gauges = np.array(sorted(df["gauge_id"].unique()))
log("rows", len(df), "gauges", len(gauges))

GROUPS = {
    "flow": [f for f in feats if f.startswith("qr_") or f in ("log_q", "q_obs_today")],
    "rain": [f for f in feats if f.startswith("prcp_")],
    "weather": [f for f in feats if f in ("tmax", "tmin", "rh", "pet", "aet")],
    "soil": [f for f in feats if f.startswith("sm")],
    "season": [f for f in feats if f.startswith("doy_")],
}
MET = GROUPS["rain"] + GROUPS["weather"] + GROUPS["soil"] + GROUPS["season"]


def pick(y, s):
    grid = np.quantile(s[np.isfinite(s)], np.linspace(0.5, 0.995, 120))
    return float(max(grid, key=lambda t: balanced_accuracy_score(y, (s >= t).astype(int))))


def scores(y, s, t, onset):
    r = {"ba": float(balanced_accuracy_score(y, (s >= t).astype(int))), "pr_auc": float(average_precision_score(y, s)),
         "alarm_rate": float((s >= t).mean()), "prev": float(y.mean())}
    yp = s >= t
    r["precision"] = float((yp & (y == 1)).sum() / max(yp.sum(), 1))
    r["recall"] = float((yp & (y == 1)).sum() / max((y == 1).sum(), 1))
    if onset is not None and y[onset].min() != y[onset].max():
        r["onset_ba"] = float(balanced_accuracy_score(y[onset], (s[onset] >= t).astype(int)))
        r["onset_pr_auc"] = float(average_precision_score(y[onset], s[onset]))
    return r


def fit(tr, va, fs, target="y", weight=True):
    sub = tr.iloc[np.random.default_rng(SEED).choice(len(tr), min(500_000, len(tr)), replace=False)]
    ys = sub[target].to_numpy().astype(int)
    yv = va[target].to_numpy().astype(int)
    pw = float((ys == 0).sum() / max((ys == 1).sum(), 1)) if weight else 1.0
    m = XGBClassifier(n_estimators=3000, max_depth=6, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                      min_child_weight=20, reg_lambda=5.0, scale_pos_weight=pw, tree_method="hist",
                      eval_metric="aucpr", early_stopping_rounds=100, n_jobs=4, random_state=SEED)
    m.fit(sub[fs], ys, eval_set=[(va[fs], yv)], verbose=False)
    pv = m.predict_proba(va[fs])[:, 1]
    return m, pick(yv, pv), pv


def split_eval(unseen, tag, target="y", fs=None, weight=True):
    fs = fs or feats
    is_un = df["gauge_id"].isin(unseen)
    tr = df[~is_un & (df["year"] <= TRAIN_END) & df[target].notna()]
    va = df[~is_un & (df["year"] > TRAIN_END) & (df["year"] <= VAL_END) & df[target].notna()]
    te = df[is_un & (df["year"] > VAL_END) & df[target].notna()]
    m, t, _ = fit(tr, va, fs, target, weight)
    p = m.predict_proba(te[fs])[:, 1]
    y = te[target].to_numpy().astype(int)
    r = scores(y, p, t, (te["flood_today"] == 0).to_numpy())
    r.update({"n_test_gauges": int(te["gauge_id"].nunique()), "n_test": int(len(te)), "thr": t})
    # persistence on the same rows, for reference
    r["pers_ba"] = float(balanced_accuracy_score(y, np.nan_to_num(te["flood_today"].to_numpy(), nan=0.0) >= 0.5))
    log(tag, round(r["ba"], 4), round(r["pr_auc"], 4), r.get("onset_ba"))
    return r, m, t, te, p


def run_basins():
    """Leave-basin-out: CAMELS-IND river basins grouped into 5 folds (GroupKFold), each basin held out once.
    Train = gauges of the other basins, 1980-2008; validation = same gauges 2009-2014; test = held-out basins
    2015-2020."""
    from sklearn.model_selection import GroupKFold
    basin = {int(g): str(names.loc[g, "river_basin"]) for g in gauges if g in names.index}
    gl = np.array(sorted(basin))
    OUT["basins"] = {}
    for f, (_, te_i) in enumerate(GroupKFold(n_splits=5).split(gl, groups=[basin[g] for g in gl])):
        held = set(gl[te_i].tolist())
        r_, *_ = split_eval(held, f"basin_fold{f}")
        r_["basins"] = sorted({basin[g] for g in held})
        r_["n_gauges_in_basin"] = len(held)
        OUT["basins"][f"fold{f}"] = r_
        save()
    OUT["basin_sizes"] = pd.Series(basin).value_counts().to_dict()
    save()


if len(sys.argv) > 2 and sys.argv[2] == "basins":  # resume: only the leave-basin-out refits
    OUT.update(json.loads(OUT_F.read_text(encoding="utf-8")))
    run_basins()
    log("done (basins)")
    sys.exit(0)

# ----------------------------------------------------------------------------- primary split, stored model
_, ui = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(gauges, groups=gauges))
unseen = set(gauges[ui].tolist())
assert sorted(int(g) for g in unseen) == meta["unseen_gauges"], "same unseen gauges as the stored split"
is_un = df["gauge_id"].isin(unseen)
te = df[is_un & (df["year"] > VAL_END)].reset_index(drop=True)
va = df[~is_un & (df["year"] > TRAIN_END) & (df["year"] <= VAL_END)]
assert len(te) == meta["n_test_unseen"], "test rows match the stored split"
OUT["gauges"] = {"listed": int(len(qdf.columns) - 3), "used": int(len(gauges)), "unseen": len(unseen),
                 "unseen_with_test_rows": int(te["gauge_id"].nunique()),
                 "unseen_without_test_rows": sorted(int(g) for g in unseen - set(te["gauge_id"].unique())),
                 "seen_with_test_rows": int(df[~is_un & (df["year"] > VAL_END)]["gauge_id"].nunique())}
model = joblib.load(ROOT / "models" / "flood_forecast_v4.pkl")
THR = float(meta["decision_threshold"])
p_te = model.predict_proba(te[feats])[:, 1]
p_va = model.predict_proba(va[feats])[:, 1]
y = te["y"].to_numpy().astype(int)
yva = va["y"].to_numpy().astype(int)
onset = (te["flood_today"] == 0).to_numpy()
assert abs(balanced_accuracy_score(y, (p_te >= THR).astype(int)) - 0.8978479116831157) < 1e-9

# references
hist = df[is_un & (df["year"] <= TRAIN_END)][["gauge_id", "date", "y"]]


def clim_table(frame):
    frame = frame.assign(doy=frame["date"].dt.dayofyear)
    tab = {}
    for gid, gdf in frame.groupby("gauge_id"):
        rate = np.zeros(367)
        doy, yy = gdf["doy"].to_numpy(), gdf["y"].to_numpy()
        for d in range(1, 367):
            dist = np.minimum(np.abs(doy - d), 366 - np.abs(doy - d))
            mm = dist <= 15
            rate[d] = yy[mm].mean() if mm.any() else 0.0
        tab[gid] = rate
    return tab


ct = clim_table(hist)
clim = np.array([ct[g][d] for g, d in zip(te["gauge_id"], te["date"].dt.dayofyear)])
trs = df[~is_un & (df["year"] <= TRAIN_END)]
ctv = clim_table(trs[["gauge_id", "date", "y"]])
clim_va = np.array([ctv[g][d] for g, d in zip(va["gauge_id"], va["date"].dt.dayofyear)])
del trs


def trend(frame):
    q0 = np.nan_to_num(frame["qr_l0"].to_numpy(), nan=0.0)
    d3 = np.nan_to_num(frame["qr_d3"].to_numpy(), nan=0.0)
    return q0 + np.maximum(0.0, d3)


S = {"xgboost": (p_te, THR), "persistence": (np.nan_to_num(te["flood_today"].to_numpy(), nan=0.0), 0.5),
     "climatology": (clim, pick(yva, clim_va)), "trend": (trend(te), pick(yva, trend(va)))}
ls = te["lstm_score"].to_numpy()
lv = va["lstm_score"].to_numpy()
S["lstm_sim"] = (np.nan_to_num(ls, nan=0.0), pick(yva[np.isfinite(lv)], lv[np.isfinite(lv)]))
OUT["lstm_coverage_test"] = float(np.isfinite(ls).mean())
OUT["methods"] = {k: scores(y, s, t, onset) for k, (s, t) in S.items()}
log("methods", {k: (round(v["ba"], 3), round(v.get("onset_ba", 0), 3)) for k, v in OUT["methods"].items()})

# LSTM: paired gauge bootstrap of the BA difference, and matched alarm rate
rng = np.random.default_rng(SEED)
gids = te["gauge_id"].to_numpy()
ug = np.unique(gids)
idx = {g: np.flatnonzero(gids == g) for g in ug}
diff, diff_on = [], []
for _ in range(1000):
    ix = np.concatenate([idx[g] for g in rng.choice(ug, len(ug), replace=True)])
    yb = y[ix]
    a = balanced_accuracy_score(yb, p_te[ix] >= THR) - balanced_accuracy_score(yb, S["lstm_sim"][0][ix] >= S["lstm_sim"][1])
    diff.append(a)
    ob = onset[ix]
    diff_on.append(balanced_accuracy_score(yb[ob], p_te[ix][ob] >= THR)
                   - balanced_accuracy_score(yb[ob], S["lstm_sim"][0][ix][ob] >= S["lstm_sim"][1]))
rate_l = float((S["lstm_sim"][0] >= S["lstm_sim"][1]).mean())
t_match = float(np.quantile(p_te, 1 - rate_l))
OUT["lstm"] = {"diff_ba": float(np.mean(diff)), "diff_ci": [float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5))],
               "diff_onset_ci": [float(np.percentile(diff_on, 2.5)), float(np.percentile(diff_on, 97.5))],
               "lstm_alarm_rate": rate_l, "xgb_matched": scores(y, p_te, t_match, onset), "t_match": t_match}

# calibration: Brier, ECE with gauge-bootstrap CI, by season
iso = IsotonicRegression(out_of_bounds="clip").fit(p_va, yva)
p_cal = iso.predict(p_te)


def ece(yy, p, bins=10):
    e = np.linspace(0, 1, bins + 1)
    b = np.clip(np.digitize(p, e[1:-1]), 0, bins - 1)
    return float(sum((b == k).sum() / len(p) * abs(p[b == k].mean() - yy[b == k].mean()) for k in range(bins) if (b == k).any()))


mon = te["date"].dt.month.isin([6, 7, 8, 9]).to_numpy()
cal = {"brier_raw": float(np.mean((p_te - y) ** 2)), "brier_iso": float(np.mean((p_cal - y) ** 2)),
       "brier_clim": float(np.mean((clim - y) ** 2)), "ece_raw": ece(y, p_te), "ece_iso": ece(y, p_cal)}
eb = {"raw": [], "iso": []}
for _ in range(500):
    ix = np.concatenate([idx[g] for g in rng.choice(ug, len(ug), replace=True)])
    eb["raw"].append(ece(y[ix], p_te[ix]))
    eb["iso"].append(ece(y[ix], p_cal[ix]))
cal["ece_ci"] = {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in eb.items()}
for nm, m_ in (("monsoon", mon), ("other", ~mon)):
    cal[nm] = {"ece_raw": ece(y[m_], p_te[m_]), "ece_iso": ece(y[m_], p_cal[m_]),
               "brier_raw": float(np.mean((p_te[m_] - y[m_]) ** 2)), "brier_iso": float(np.mean((p_cal[m_] - y[m_]) ** 2))}
OUT["calibration"] = cal

# per test year, 228-gauge subset, regulation, non-stationarity
alarm = p_te >= THR
OUT["per_year"] = {int(yr): scores(y[m_], p_te[m_], THR, onset[m_]) | {"n": int(m_.sum())}
                   for yr in sorted(te["year"].unique()) for m_ in [(te["year"] == yr).to_numpy()]}
avail = names["flow_availability"]
g228 = set(int(g) for g in avail[avail > 30].index)
m228 = te["gauge_id"].isin(g228).to_numpy()
OUT["g228"] = {"n_gauges_total": int(len(g228 & set(gauges.tolist()))), "n_test_gauges": int(te[m228]["gauge_id"].nunique()),
               **scores(y[m228], p_te[m228], THR, onset[m228])}
pg = []
for g in ug:
    ix = idx[g]
    if y[ix].min() != y[ix].max():
        pg.append((g, balanced_accuracy_score(y[ix], alarm[ix])))
ri = [float(anth.loc[g, "reservoir_index"]) if g in anth.index else np.nan for g, _ in pg]
nd = [float(anth.loc[g, "num_dams"]) if g in anth.index else np.nan for g, _ in pg]
bav = [b for _, b in pg]
ok = np.isfinite(ri)
OUT["regulation"] = {"rho_reservoir_index": float(spearmanr(np.array(ri)[ok], np.array(bav)[ok])[0]),
                     "p_reservoir_index": float(spearmanr(np.array(ri)[ok], np.array(bav)[ok])[1]),
                     "rho_num_dams": float(spearmanr(np.array(nd)[ok], np.array(bav)[ok])[0]),
                     "p_num_dams": float(spearmanr(np.array(nd)[ok], np.array(bav)[ok])[1]),
                     "ba_with_dams": float(np.median([b for b, n in zip(bav, nd) if n > 0])) if any(n > 0 for n in nd) else None,
                     "ba_no_dams": float(np.median([b for b, n in zip(bav, nd) if n == 0])) if any(n == 0 for n in nd) else None,
                     "n_with_dams": int(sum(n > 0 for n in nd)), "n_no_dams": int(sum(n == 0 for n in nd))}
fl = df[df["year"] > VAL_END]
OUT["nonstationarity"] = {"flood_today_rate_test_years": float(np.nanmean(fl["flood_today"])),
                          "flood_today_rate_train_years": float(np.nanmean(df[df["year"] <= TRAIN_END]["flood_today"])),
                          "per_year": {int(yr): float(np.nanmean(fl[fl["year"] == yr]["flood_today"])) for yr in sorted(fl["year"].unique())}}
dr = pd.DataFrame(dropped)
OUT["dropped"] = {"n_dropped": int(dr["n_dropped"].sum()), "n_days": int(dr["n_days"].sum()), "n_kept": int(dr["kept"].sum()),
                  "monsoon_share_dropped": float(dr["dropped_monsoon"].sum() / max(dr["n_dropped"].sum(), 1)),
                  "monsoon_share_kept": float(dr["kept_monsoon"].sum() / dr["kept"].sum()),
                  "after_high_share_dropped": float(dr["dropped_after_high"].sum() / max(dr["n_dropped"].sum(), 1)),
                  "after_high_share_kept": float(dr["kept_after_high"].sum() / dr["kept"].sum()),
                  "flood_today_rate_kept": float(np.nanmean(df["flood_today"]))}

# alarm episodes and a random-alarm reference for onset warnings
eps = {"n": 0, "false": 0}
for g in ug:
    ix = idx[g]
    order = np.argsort(te["date"].to_numpy()[ix])
    a_, y_ = alarm[ix][order], y[ix][order]
    k = 0
    while k < len(a_):
        if a_[k]:
            j = k
            while j + 1 < len(a_) and a_[j + 1]:
                j += 1
            eps["n"] += 1
            eps["false"] += int(not y_[k:j + 1].any())
            k = j + 1
        else:
            k += 1
r_all = float(alarm.mean())
r_mon = float(alarm[mon].mean())
eps.update({"alarm_rate": r_all, "alarm_rate_monsoon": r_mon,
            "random_warn_3d_pct": 100 * (1 - (1 - r_all) ** 3), "random_warn_3d_monsoon_pct": 100 * (1 - (1 - r_mon) ** 3)})
OUT["episodes"] = eps
save()
log("descriptive parts saved")

# ----------------------------------------------------------------------------- refits (about 3-4 min each)
OUT["refits"] = {}
r, *_ = split_eval(unseen, "met_only", fs=MET)
OUT["refits"]["met_only"] = r
r, m_nw, t_nw, te_nw, p_nw = split_eval(unseen, "no_class_weight", weight=False)
r["ece_raw"] = ece(te_nw["y"].to_numpy().astype(int), p_nw)
OUT["refits"]["no_class_weight"] = r
r, *_ = split_eval(unseen, "q99", target="y99")
OUT["refits"]["q99"] = r
save()
OUT["splits"] = {}
for s in (1, 2, 3, 4, 5):
    _, u = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=s).split(gauges, groups=gauges))
    r, *_ = split_eval(set(gauges[u].tolist()), f"split_seed{s}")
    OUT["splits"][str(s)] = r
    save()
run_basins()
log("done")
