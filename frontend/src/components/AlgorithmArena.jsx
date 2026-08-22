import { useCallback, useEffect, useState } from "react";
import { fetchAlgorithmArena } from "../services/api.js";

function pct(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return `${(Number(v) * 100).toFixed(1)}%`;
}

export default function AlgorithmArena({ enabled = true, onMapPaths }) {
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
    if (!enabled) return undefined;
    run();
    const id = setInterval(run, 8000);
    return () => clearInterval(id);
  }, [enabled, run]);

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
        <button type="button" className="primary" disabled={busy} onClick={run}>
          {busy ? "Running…" : "Re-run algorithms"}
        </button>
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
                <td colSpan={5}>Run a scenario, then re-run arena.</td>
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
            {board.map((row, i) => (
              <tr key={row.method} className={i === 0 ? "arena-winner" : ""}>
                <td>
                  {i === 0 ? "★ " : ""}
                  {row.label}
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
    </div>
  );
}
