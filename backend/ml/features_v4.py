"""V4 feature builder (CAMELS-IND, 3-day flood horizon).

Single source for the v4 features: scripts/train_flood_model_v4.py trains on
exactly these columns and backend/ml/forecast_v4.py serves predictions from
them, so training and serving cannot drift apart.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "dataset" / "camels_ind"
TRAIN_END, VAL_END = 2008, 2014
HORIZON = 3
FLOOD_PCTL = 0.95
MIN_TRAIN_OBS = 3 * 365

FORCING_COLS = {
    "prcp(mm/day)": "prcp", "tmax(C)": "tmax", "tmin(C)": "tmin", "rel_hum(%)": "rh",
    "pet_gleam(mm/day)": "pet", "aet_gleam(mm/day)": "aet",
    "sm_lvl1(kg/m2)": "sm1", "sm_lvl2(kg/m2)": "sm2", "sm_lvl3(kg/m2)": "sm3", "sm_lvl4(kg/m2)": "sm4",
}
STATIC = {
    "topo": ["elev_mean", "slope_mean", "cwc_area", "dpsbar"],
    "clim": ["p_mean", "aridity_p_pet", "high_prec_freq", "pet_mean"],
    "land": ["trees_frac", "crops_frac", "built_area_frac", "water_frac"],
    "soil": ["soil_depth", "soil_conductivity_top", "sand_frac_top", "clay_frac_top"],
}


def load_static() -> pd.DataFrame:
    parts = []
    for name, cols in STATIC.items():
        df = pd.read_csv(DATA / "attributes_csv" / f"camels_ind_{name}.csv")
        parts.append(df.set_index("gauge_id")[cols])
    out = pd.concat(parts, axis=1)
    out["log_area"] = np.log1p(out.pop("cwc_area"))
    return out


def gauge_frame(gid: int, q: pd.Series, dates: pd.DatetimeIndex) -> pd.DataFrame | None:
    path = DATA / "catchment_mean_forcings" / f"{gid:05d}.csv"
    if not path.exists():
        return None
    f = pd.read_csv(path)
    f.index = pd.to_datetime(f[["year", "month", "day"]])
    f = f[list(FORCING_COLS)].rename(columns=FORCING_COLS).reindex(dates)

    q = q.set_axis(dates)
    train_q = q[q.index.year <= TRAIN_END].dropna()
    if len(train_q) < MIN_TRAIN_OBS:
        return None
    thr = float(train_q.quantile(FLOOD_PCTL))
    if thr <= 0:
        return None

    d = pd.DataFrame(index=dates)
    p = f["prcp"]
    for lag in range(0, 4):
        d[f"prcp_l{lag}"] = p.shift(lag)
    for w in (3, 7, 14, 30, 90):
        d[f"prcp_s{w}"] = p.rolling(w, min_periods=1).sum()
    d["prcp_max7"] = p.rolling(7, min_periods=1).max()
    for c in ("tmax", "tmin", "rh", "pet", "aet", "sm1", "sm2", "sm3", "sm4"):
        d[c] = f[c]
    d["sm1_d3"] = f["sm1"] - f["sm1"].shift(3)
    d["sm2_d7"] = f["sm2"] - f["sm2"].shift(7)

    r = q / thr  # observed flow relative to this gauge's train-period flood threshold
    for lag in range(0, 4):
        d[f"qr_l{lag}"] = r.shift(lag)
    d["qr_d1"] = r - r.shift(1)
    d["qr_d3"] = r - r.shift(3)
    d["qr_m7"] = r.rolling(7, min_periods=3).mean()
    d["qr_max7"] = r.rolling(7, min_periods=3).max()
    d["qr_m30"] = r.rolling(30, min_periods=10).mean()
    d["log_q"] = np.log1p(q.clip(lower=0))
    d["q_obs_today"] = q.notna().astype("float32")

    doy = dates.dayofyear.to_numpy()
    d["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    d["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)

    fut = pd.concat([q.shift(-k) for k in range(1, HORIZON + 1)], axis=1)
    fut_max = fut.max(axis=1, skipna=True)
    d["y"] = np.where(fut.notna().any(axis=1), (fut_max >= thr).astype(float), np.nan)
    d["flood_today"] = (q >= thr).astype(float).where(q.notna())
    d["gauge_id"] = gid
    d["year"] = dates.year
    d = d[d["y"].notna()]
    d = d.astype({c: "float32" for c in d.columns if c not in ("gauge_id", "year")})
    d.attrs["flood_threshold"] = thr
    return d
