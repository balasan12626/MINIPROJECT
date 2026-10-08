"""V4 flood forecast serving -- historical replay on real CAMELS-IND data.

The v4 model needs a gauge's observed river flow and weather history. The live
site has no observed-gauge feed (Open-Meteo/GloFAS discharge is modelled and on
a different scale), so v4 is served as a REPLAY: pick a real gauge and date,
the features are rebuilt from the dataset with the same builder training used
(backend/ml/features_v4.py), and the response carries the model's probability,
what actually happened in the next 3 days, and SHAP contributions from the
same XGBoost booster that produced the probability.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import numpy as np
import pandas as pd

from backend.ml.benchmark_v4 import _load as _load_model
from backend.ml.features_v4 import DATA, HORIZON, TRAIN_END, VAL_END, gauge_frame, load_static
from backend.ml.inference import models_dir

_lock = threading.Lock()
_data: dict[str, Any] = {}
_frames: dict[int, pd.DataFrame] = {}
_MAX_CACHED_GAUGES = 16

FEATURE_LABELS = {
    "qr_l0": "River flow today (÷ flood level)", "qr_l1": "River flow yesterday (÷ flood level)",
    "qr_l2": "River flow 2 days ago (÷ flood level)", "qr_l3": "River flow 3 days ago (÷ flood level)",
    "qr_d1": "1-day change in flow", "qr_d3": "3-day change in flow", "qr_m7": "7-day mean flow",
    "qr_max7": "7-day peak flow", "qr_m30": "30-day mean flow", "log_q": "River flow (log m³/s)",
    "prcp_l0": "Rain today", "prcp_l1": "Rain yesterday", "prcp_l2": "Rain 2 days ago", "prcp_l3": "Rain 3 days ago",
    "prcp_s3": "Rain, last 3 days", "prcp_s7": "Rain, last 7 days", "prcp_s14": "Rain, last 14 days",
    "prcp_s30": "Rain, last 30 days", "prcp_s90": "Rain, last 90 days", "prcp_max7": "Heaviest day, last 7 days",
    "sm1": "Topsoil moisture", "sm2": "Soil moisture (layer 2)", "sm3": "Soil moisture (layer 3)",
    "sm4": "Deep soil moisture", "sm1_d3": "Topsoil moisture change (3 d)", "sm2_d7": "Soil moisture change (7 d)",
    "doy_sin": "Season (sin)", "doy_cos": "Season (cos)",
}


def _reference() -> dict[str, Any]:
    with _lock:
        if not _data:
            q = pd.read_csv(DATA / "streamflow_timeseries" / "streamflow_observed.csv")
            _data["dates"] = pd.DatetimeIndex(pd.to_datetime(q[["year", "month", "day"]]))
            _data["q"] = q.drop(columns=["year", "month", "day"]).astype("float32")
            _data["static"] = load_static().astype("float32")
            names = pd.read_csv(DATA / "attributes_csv" / "camels_ind_name.csv").set_index("gauge_id")
            topo = pd.read_csv(DATA / "attributes_csv" / "camels_ind_topo.csv").set_index("gauge_id")
            _data["names"], _data["topo"] = names, topo
            meta_path = models_dir() / "flood_model_metadata_v4.json"
            _data["meta"] = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        return _data


def _frame(gid: int) -> pd.DataFrame | None:
    ref = _reference()
    with _lock:
        if gid in _frames:
            return _frames[gid]
    col = str(gid)
    if col not in ref["q"].columns:
        return None
    g = gauge_frame(gid, ref["q"][col].astype(float), ref["dates"])
    if g is None:
        return None
    thr = g.attrs.get("flood_threshold")
    g = g.join(ref["static"], on="gauge_id")
    g.attrs["flood_threshold"] = thr
    with _lock:
        if len(_frames) >= _MAX_CACHED_GAUGES:
            _frames.pop(next(iter(_frames)))
        _frames[gid] = g
    return g


def list_gauges() -> dict[str, Any]:
    if _load_model() is None:
        return {"available": False, "message": "V4 MODEL NOT TRAINED YET"}
    ref = _reference()
    unseen = set(ref["meta"].get("unseen_gauges") or [])
    rows = []
    for gid in sorted(unseen):
        name = ref["names"].loc[gid] if gid in ref["names"].index else None
        topo = ref["topo"].loc[gid] if gid in ref["topo"].index else None
        rows.append({
            "gauge_id": int(gid),
            "site": None if name is None else str(name["cwc_site_name"]),
            "river": None if name is None else str(name["cwc_river"]),
            "basin": None if name is None else str(name["river_basin"]),
            "lat": None if topo is None else float(topo["cwc_lat"]),
            "lon": None if topo is None else float(topo["cwc_lon"]),
        })
    return {"available": True, "gauges": rows, "test_years": [VAL_END + 1, 2020],
            "note": "Gauges held out of training and validation entirely."}


def _flood_days(g: pd.DataFrame, limit: int = 12) -> list[str]:
    """Test-period dates where a flood arrived within 3 days but the river was not yet flooded."""
    test = g[(g["year"] > VAL_END) & (g["y"] == 1) & (g["flood_today"] == 0)]
    return [d.strftime("%Y-%m-%d") for d in test.index[:limit]]


def predict_replay(gauge_id: int, date: str | None) -> dict[str, Any]:
    loaded = _load_model()
    if loaded is None:
        return {"available": False, "message": "V4 MODEL NOT TRAINED YET"}
    model, _, evaluation = loaded
    ref = _reference()
    feats = list(ref["meta"].get("features") or [])
    thr = float(evaluation["decision_threshold"])

    g = _frame(int(gauge_id))
    if g is None or not feats:
        return {"available": False, "message": f"Gauge {gauge_id} has no usable CAMELS-IND record"}
    test_rows = g[g["year"] > VAL_END]
    if test_rows.empty:
        return {"available": False, "message": f"Gauge {gauge_id} has no labelled days in {VAL_END + 1}-2020"}
    if date:
        ts = pd.Timestamp(date)
        if ts not in g.index:
            return {"available": False, "message": f"No labelled record for gauge {gauge_id} on {date}",
                    "suggested_dates": _flood_days(g)}
    else:
        ts = test_rows.index[-1]

    row = g.loc[[ts], feats]
    x = row.to_numpy(dtype=np.float32)
    prob = float(model.predict_proba(x)[0, 1])

    explanation = None
    if hasattr(model, "get_booster"):  # XGBoost: exact TreeSHAP of the booster that made `prob`
        import xgboost as xgb
        contrib = model.get_booster().predict(xgb.DMatrix(x, feature_names=feats), pred_contribs=True)[0]
        order = np.argsort(-np.abs(contrib[:-1]))[:8]
        explanation = {
            "method": "XGBoost TreeSHAP (pred_contribs), log-odds units",
            "base_value": float(contrib[-1]),
            "top": [{"feature": feats[i], "label": FEATURE_LABELS.get(feats[i], feats[i]),
                     "value": None if np.isnan(x[0, i]) else float(x[0, i]), "contribution": float(contrib[i])}
                    for i in order],
        }

    q_col = ref["q"][str(int(gauge_id))]
    pos = ref["dates"].get_loc(ts)
    window = slice(max(pos - 13, 0), min(pos + HORIZON + 1, len(ref["dates"])))
    flood_thr = g.attrs.get("flood_threshold")
    history = [{"date": d.strftime("%Y-%m-%d"),
                "flow": None if pd.isna(v) else float(v),
                "future": bool(d > ts)}
               for d, v in zip(ref["dates"][window], q_col.iloc[window])]

    name = ref["names"].loc[int(gauge_id)] if int(gauge_id) in ref["names"].index else None
    actual = int(g.at[ts, "y"])
    predicted = int(prob >= thr)
    return {
        "available": True,
        "mode": "HISTORICAL_REPLAY",
        "model": evaluation.get("selected_model"),
        "gauge_id": int(gauge_id),
        "site": None if name is None else str(name["cwc_site_name"]),
        "river": None if name is None else str(name["cwc_river"]),
        "date": ts.strftime("%Y-%m-%d"),
        "gauge_seen_in_training": int(gauge_id) not in set(ref["meta"].get("unseen_gauges") or []),
        "date_in_training_years": bool(ts.year <= TRAIN_END),
        "flood_probability": round(prob, 4),
        "decision_threshold": thr,
        "predicted_flood_within_3d": bool(predicted),
        "actual_flood_within_3d": bool(actual),
        "outcome": ("TRUE ALARM" if predicted and actual else "FALSE ALARM" if predicted
                    else "MISSED FLOOD" if actual else "CORRECT ALL-CLEAR"),
        "flooded_today": bool(g.at[ts, "flood_today"] == 1),
        "flood_threshold_m3s": None if flood_thr is None else round(float(flood_thr), 2),
        "history": history,
        "explanation": explanation,
        "suggested_dates": _flood_days(g),
    }
