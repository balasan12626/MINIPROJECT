"""P2 third revision: break-even miss:false cost ratio of the disagreement gate -> <work>/p2_breakeven.json.

Same split, stored models and isotonic baseline as exp_p2_gate2.py (asserted against p2_gate2.json). Assumed
costs: false dispatch 1, missed dispatch r, officer review 0.2, held events decided correctly. For each r on a
grid, the calibrated single model (no gate) uses the threshold that minimises the out-of-fold training cost at
that r (no test information). r* is the smallest r at which that model costs no more than the deployed gate
on the test events. The 95% interval resamples test events (2,000 bootstrap replicates; thresholds fixed).
Offline; no network call.
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedKFold, StratifiedShuffleSplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import train_flood_model as T  # noqa: E402
from backend.thresholds import MODEL_GAP_MAX, auto_threshold  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
TAU = auto_threshold()
G2 = json.loads((WORK / "p2_gate2.json").read_text(encoding="utf-8"))
C_R = 0.2

raw = T.add_engineered(T.load_joined())
y = raw["y"].to_numpy()
tr_idx, te_idx = next(StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42).split(raw, y))
tr_df, te_df, _ = T.apply_train_encodings(raw.iloc[tr_idx], raw.iloc[te_idx])
Xtr, _, _ = T.feature_frame(tr_df)
Xte, _, _ = T.feature_frame(te_df)
ytr, yte = tr_df["y"].to_numpy(), te_df["y"].to_numpy()
pipes = {n: joblib.load(ROOT / "models" / f"{n}_flood.pkl") for n in ("random_forest", "xgboost")}
prf, pxg = (pipes[n].predict_proba(Xte)[:, 1] for n in ("random_forest", "xgboost"))
cal = CalibratedClassifierCV(clone(pipes["xgboost"]), method="isotonic", cv=5).fit(Xtr, ytr)
pcal = cal.predict_proba(Xte)[:, 1]
oof = np.zeros(len(ytr))
for f_tr, f_va in StratifiedKFold(5, shuffle=True, random_state=42).split(Xtr, ytr):
    c = CalibratedClassifierCV(clone(pipes["xgboost"]), method="isotonic", cv=5).fit(Xtr.iloc[f_tr], ytr[f_tr])
    oof[f_va] = c.predict_proba(Xtr.iloc[f_va])[:, 1]

yb = yte.astype(bool)
pred = pxg >= TAU
straddle = (np.minimum(prf, pxg) < TAU) & (TAU <= np.maximum(prf, pxg))
hold = (np.abs(prf - pxg) >= MODEL_GAP_MAX) | straddle
dep = {"fd": int((pred & ~yb & ~hold).sum()), "md": int((~pred & yb & ~hold).sum()), "holds": int(hold.sum())}
none = {"fd": int((pred & ~yb).sum()), "md": int((~pred & yb).sum())}
for k in ("fd", "md", "holds"):
    assert dep[k] == G2["rules"]["deployed"][k], "same deployed gate as exp_p2_gate2"
assert none["fd"] == G2["rules"]["none"]["fd"] and none["md"] == G2["rules"]["none"]["md"]

grid_t = np.linspace(0.05, 0.95, 91)
R = np.round(np.arange(1.0, 10.0001, 0.05), 2)
t_of_r = []
for r in R:
    tc = [np.sum((oof >= t) & (ytr == 0)) + r * np.sum((oof < t) & (ytr == 1)) for t in grid_t]
    t_of_r.append(float(grid_t[int(np.argmin(tc))]))
calpred = np.array([pcal >= t for t in t_of_r])  # (len(R), n_test)
assert abs(t_of_r[int(np.argmin(np.abs(R - 5)))] - G2["rules"]["calibrated_1_5"]["threshold"]) < 1e-9


def costs(ix):
    yv = yb[ix]
    g = (pred[ix] & ~yv & ~hold[ix]).sum() + R * (~pred[ix] & yv & ~hold[ix]).sum() + C_R * hold[ix].sum()
    n0 = (pred[ix] & ~yv).sum() + R * (~pred[ix] & yv).sum()
    cp = calpred[:, ix]
    cc = (cp & ~yv).sum(axis=1) + R * (~cp & yv).sum(axis=1)
    return g, n0, cc


def r_star(g, cc):
    w = np.where(cc <= g)[0]
    return float(R[w[0]]) if len(w) else float("inf")


ix0 = np.arange(len(yte))
g, n0, cc = costs(ix0)
rs = r_star(g, cc)
after = R >= rs
out = {"c_review": C_R, "r_grid": [float(R[0]), float(R[-1]), 0.05], "r_star": rs,
       "single_crossing": bool(np.all(cc[after] <= g[after]) and np.all(cc[~after] > g[~after])),
       "gate_beats_none_all_r": bool(np.all(g < n0)),
       "t_at_r_star": t_of_r[int(np.where(R == rs)[0][0])] if np.isfinite(rs) else None,
       "cost_per100_at_1": {"gate": float(100 * g[0] / len(yte)), "cal": float(100 * cc[0] / len(yte)),
                            "none": float(100 * n0[0] / len(yte))}}
rng = np.random.default_rng(7)
bs = []
for _ in range(2000):
    ix = rng.integers(0, len(yte), len(yte))
    gb, _, cb = costs(ix)
    bs.append(r_star(gb, cb))
bs = np.array(bs)
out["boot"] = {"B": 2000, "ci": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
               "share_no_crossing_in_grid": float(np.mean(~np.isfinite(bs)))}
(WORK / "p2_breakeven.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
