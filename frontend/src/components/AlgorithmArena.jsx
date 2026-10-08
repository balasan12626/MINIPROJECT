import { useCallback, useEffect, useState } from "react";
import { fetchAlgorithmArena } from "../services/api.js";

function pct(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return `${(Number(v) * 100).toFixed(1)}%`;
}

/** Path contest + policy engine.
 *
 * Computed ONCE per run input, not on a timer: the single RUN SCENARIO flow
 * drives it. `runKey` changes when the run id changes, when the first model
 * tick lands, or when the set of blocked roads changes — only then is the
 * arena re-run. The manual re-run lives in a collapsed Advanced panel. */
export default function AlgorithmArena({ enabled = true, onMapPaths, runKey = "" }) {
  const [arena, setArena] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const data = await fetchAlgorithmArena();
      if (data?.available === false) {
        setError(data.message || "Arena unavailable");
        return;
      }
      setArena(data);
      onMapPaths?.(data?.map_paths || null);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [onMapPaths]);

  useEffect(() => {
    if (!enabled) return;
    run();
    // Deliberately keyed on runKey only — no interval polling.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, runKey]);

  if (!enabled) return null;

  const policy = arena?.policy || {};
  const rules = policy.rules || [];
  const board = arena?.scoreboard || [];
  const verdict = arena?.agent_verdict || {};
  const primary = arena?.path_runs?.[0];

  return (
    <div className="panel arena-panel">
      <div className="status-row">
        <h2 style={{ margin: 0 }}>ALGORITHM ARENA</h2>
        {busy ? <span className="badge sim">Computing…</span> : null}
      </div>
      <p className="hint">
        {arena?.pitch ||
          "Flood-aware Dijkstra / A* vs greedy · RF/XGB + physics twin · policy engine gates agent autonomy."}
      </p>
      {error ? <div className="unavailable">{error}</div> : null}

      <div className="grid-3 arena-twin">
        <div className="metric">
          <span>ML (RF/XGB)</span>
          <b>{pct(arena?.ml?.flood_probability)}</b>
          <small className="hint">{arena?.ml?.model_id || "—"} · gap {pct(arena?.ml?.dual?.gap)}</small>
        </div>
        <div className="metric">
          <span>Physics twin</span>
          <b>{pct(arena?.physics?.flood_probability)}</b>
          <small className="hint">inundation {arena?.physics?.inundation_radius_km ?? "—"} km</small>
        </div>
        <div className={`metric autonomy-${(policy.autonomy_level || "").toLowerCase()}`}>
          <span>Autonomy gate</span>
          <b>{policy.autonomy_level || "—"}</b>
          <small className="hint">{policy.autonomy_note}</small>
        </div>
      </div>

      {arena?.twin_diverge ? (
        <div className="transfer-banner panel" style={{ marginTop: 10 }}>
          Physics and ML diverge ≥ 20% — transfer / HOLD warning active.
        </div>
      ) : null}

      <h3 style={{ marginTop: 14 }}>Policy engine — which rules fired</h3>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Rule</th>
              <th>When</th>
              <th>Then</th>
              <th>Fired</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.id} className={r.fired ? "rule-fired" : ""}>
                <td>{r.id}</td>
                <td>{r.when}</td>
                <td>{r.then}</td>
                <td>{r.fired ? "YES" : "no"}</td>
                <td>{r.detail}</td>
              </tr>
            ))}
            {!rules.length ? (
              <tr>
                <td colSpan={5}>Run a scenario — the arena computes once per run.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <h3 style={{ marginTop: 14 }}>Path contest (same SOS → shelter)</h3>
      <p className="hint">
        Map: <span style={{ color: "#5ce1ff" }}>blue = before (shortest km)</span>
        {" · "}
        <span style={{ color: "#ff5d6c" }}>red = after flood (A* / Dijkstra)</span>
        {primary ? (
          <>
            {" "}
            · focus {primary.citizen_name} → {primary.shelter_name || primary.shelter_id}
          </>
        ) : null}
      </p>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Algorithm</th>
              <th>Avg ETA (min)</th>
              <th>Lives / min</th>
              <th>Blocked roads used</th>
              <th>Assignments</th>
            </tr>
          </thead>
          <tbody>
            {board.map((row) => (
              <tr key={row.method} className={row.winner ? "arena-winner" : ""}>
                <td>
                  {row.winner ? "★ " : ""}
                  {row.label}
                  {row.eligible === false ? <small className="hint"> (reference only)</small> : null}
                </td>
                <td>{row.avg_eta_min}</td>
                <td>{row.avg_lives_per_min}</td>
                <td>{row.blocked_roads_used}</td>
                <td>{row.assignments}</td>
              </tr>
            ))}
            {!board.length ? (
              <tr>
                <td colSpan={5}>No path scores yet.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <h3 style={{ marginTop: 14 }}>Agent referee (policy is boss)</h3>
      <ul className="summary-list">
        <li>
          <b>Flood Risk:</b> {verdict.flood_risk_agent || "—"}
        </li>
        <li>
          <b>Physics:</b> {verdict.physics_agent || "—"}
        </li>
        <li>
          <b>Rescue:</b> {verdict.rescue_agent || "—"}
        </li>
        <li>
          <b>Shelter:</b> {verdict.shelter_agent || "—"}
        </li>
        <li>
          <b>Administrator:</b> {verdict.administrator_agent || "—"}
        </li>
      </ul>
      <p className="hint">
        ★ = the Referee&apos;s pick ({arena?.winner_label || "—"}): best lives/min among drivable, flood-aware routes
        that use no blocked road. ETAs are road travel time at 25 km/h free-flow, slowed by traffic and flood exposure.
      </p>
      <details className="arena-advanced">
        <summary>Advanced</summary>
        <button type="button" disabled={busy} onClick={run}>
          {busy ? "Running…" : "Re-run algorithms now"}
        </button>
      </details>
    </div>
  );
}
