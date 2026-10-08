import { useState } from "react";
import { fetchV4Gauges, predictV4Replay } from "../../services/api.js";

/** "Try the V4 model" — historical replay on a real CAMELS-IND gauge-day.
 *
 * Nothing loads until the user clicks. Every value shown is the response of
 * POST /api/ml/predict-v4 for the chosen gauge and date: the model's
 * probability, what the river actually did in the next 3 days, and TreeSHAP
 * contributions from the same XGBoost booster. */

const OUTCOME_TONE = {
  "TRUE ALARM": "live",
  "CORRECT ALL-CLEAR": "live",
  "FALSE ALARM": "warn",
  "MISSED FLOOD": "crit",
};

function FlowStrip({ history, threshold }) {
  const flows = history.map((h) => h.flow).filter((v) => typeof v === "number");
  if (!flows.length) return null;
  const max = Math.max(...flows, threshold || 0) || 1;
  return (
    <div className="v4-flow" role="img" aria-label="Observed river flow, 14 days before and 3 days after the forecast date">
      {history.map((h) => (
        <span
          key={h.date}
          className={`v4-flow-bar ${h.future ? "future" : ""} ${typeof h.flow === "number" && threshold && h.flow >= threshold ? "over" : ""}`}
          style={{ height: `${typeof h.flow === "number" ? Math.max(2, (h.flow / max) * 100) : 0}%` }}
          title={`${h.date}: ${typeof h.flow === "number" ? `${h.flow.toFixed(1)} m³/s` : "no reading"}${h.future ? " (after forecast)" : ""}`}
        />
      ))}
      {threshold ? <span className="v4-flow-thr" style={{ bottom: `${(threshold / max) * 100}%` }} /> : null}
    </div>
  );
}

export default function V4ReplayPanel() {
  const [gauges, setGauges] = useState(null);
  const [gaugeId, setGaugeId] = useState("");
  const [date, setDate] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function loadGauges() {
    setBusy(true);
    setError(null);
    try {
      const out = await fetchV4Gauges();
      if (!out?.available || !Array.isArray(out.gauges)) {
        setError(out?.message || "Gauge list unavailable");
        return;
      }
      setGauges(out.gauges);
      setGaugeId(String(out.gauges[0]?.gauge_id ?? ""));
    } catch (err) {
      console.error("[AquaSentinel] Loading V4 gauges failed:", err);
      setError(err?.message || "Gauge list request failed");
    } finally {
      setBusy(false);
    }
  }

  async function run(nextDate = date) {
    if (!gaugeId) return;
    setBusy(true);
    setError(null);
    try {
      const out = await predictV4Replay(Number(gaugeId), nextDate || undefined);
      if (!out?.available) {
        setError(out?.message || "Prediction unavailable");
        setResult(out?.suggested_dates ? { suggested_dates: out.suggested_dates } : null);
      } else {
        setResult(out);
        setDate(out.date);
      }
    } catch (err) {
      console.error("[AquaSentinel] V4 replay prediction failed:", err);
      setError(err?.response?.data?.detail?.[0]?.msg || err?.message || "Request failed");
    } finally {
      setBusy(false);
    }
  }

  if (!gauges) {
    return (
      <div className="panel v4-replay">
        <h3>Try the V4 model on a real river</h3>
        <p className="hint">
          Replays the model on a real day at a gauge it never saw in training, then shows what the river actually did.
        </p>
        <button type="button" className="primary" onClick={loadGauges} disabled={busy}>
          {busy ? "Loading gauges…" : "Load test gauges"}
        </button>
        {error ? <p className="unavailable">{error}</p> : null}
      </div>
    );
  }

  const top = result?.explanation?.top || [];
  const maxAbs = Math.max(...top.map((t) => Math.abs(t.contribution)), 1e-9);

  return (
    <div className="panel v4-replay">
      <div className="panel-head">
        <h3>Try the V4 model on a real river</h3>
        <span className="badge sim">historical replay · unseen gauges</span>
      </div>
      <div className="v4-controls">
        <label>
          Gauge
          <select value={gaugeId} onChange={(e) => { setGaugeId(e.target.value); setResult(null); setDate(""); }}>
            {gauges.map((g) => (
              <option key={g.gauge_id} value={g.gauge_id}>
                {g.site || g.gauge_id} — {g.basin || "?"} ({g.gauge_id})
              </option>
            ))}
          </select>
        </label>
        <label>
          Date (2015–2020, blank = latest)
          <input type="date" min="2015-01-01" max="2020-12-31" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <button type="button" className="primary" onClick={() => run()} disabled={busy || !gaugeId}>
          {busy ? "Predicting…" : "Predict"}
        </button>
      </div>

      {result?.suggested_dates?.length ? (
        <p className="hint">
          Days when a flood was coming (river not yet flooded):{" "}
          {result.suggested_dates.slice(0, 6).map((d) => (
            <button key={d} type="button" className="linklike" onClick={() => run(d)} disabled={busy}>
              {d}
            </button>
          ))}
        </p>
      ) : null}
      {error ? <p className="unavailable">{error}</p> : null}

      {result?.available ? (
        <>
          <div className="grid-4">
            <div className="panel kpi">
              <div className="label">Flood probability (next 3 days)</div>
              <div className="value">{(result.flood_probability * 100).toFixed(1)}%</div>
              <div className="sub">alarm at ≥ {(result.decision_threshold * 100).toFixed(0)}%</div>
            </div>
            <div className="panel kpi">
              <div className="label">Model says</div>
              <div className="value">{result.predicted_flood_within_3d ? "FLOOD" : "NO FLOOD"}</div>
              <div className="sub">{result.site} · {result.date}</div>
            </div>
            <div className="panel kpi">
              <div className="label">What actually happened</div>
              <div className="value">{result.actual_flood_within_3d ? "FLOOD" : "NO FLOOD"}</div>
              <div className="sub">flood level {result.flood_threshold_m3s} m³/s{result.flooded_today ? " · already flooded that day" : ""}</div>
            </div>
            <div className="panel kpi">
              <div className="label">Result</div>
              <div className="value">
                <span className={`badge ${OUTCOME_TONE[result.outcome] || ""}`}>{result.outcome}</span>
              </div>
              <div className="sub">{result.model}</div>
            </div>
          </div>

          <div className="grid-2">
            <div className="panel">
              <h3>River flow — 14 days before, 3 days after</h3>
              <FlowStrip history={result.history} threshold={result.flood_threshold_m3s} />
              <p className="hint">Dashed line = flood level. Faded bars = the 3 days the model was predicting (not seen by it).</p>
            </div>
            <div className="panel">
              <h3>Why (SHAP)</h3>
              {top.length ? (
                top.map((t) => (
                  <div className="metric v4-shap" key={t.feature}>
                    <span>{t.label}</span>
                    <span className="v4-shap-bar" aria-hidden="true">
                      <span
                        className={t.contribution >= 0 ? "up" : "down"}
                        style={{ width: `${(Math.abs(t.contribution) / maxAbs) * 50}%` }}
                      />
                    </span>
                    <b>{t.contribution >= 0 ? "+" : ""}{t.contribution.toFixed(2)}</b>
                  </div>
                ))
              ) : (
                <p className="muted">No explanation available for this model type.</p>
              )}
              <p className="hint">{result.explanation?.method} · red pushes toward flood, green toward no flood.</p>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
