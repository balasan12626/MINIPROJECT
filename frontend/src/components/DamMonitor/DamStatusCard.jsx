import DataSourceBadge from "../DataSourceBadge.jsx";

/** BOX 1 — Calculated reservoir status. Pure arithmetic, no ML involved. */
export default function DamStatusCard({ status }) {
  if (!status) return <div className="panel glass-panel"><p className="hint">Click LOAD SCENARIO above to see reservoir status.</p></div>;
  return (
    <div className="risk-split-col">
      <DataSourceBadge kind="CALCULATED" title={status.calculation} />
      <h3>Calculated reservoir status</h3>
      <b>{status.fill_percentage}%</b>
      <p className="hint">{status.status.replace("_", " ")}</p>
      <div className="dam-status-grid">
        <div className="metric"><span>Current level (m MSL)</span><b>{status.current_level_m} m</b></div>
        <div className="metric"><span>Full reservoir level (m MSL)</span><b>{status.full_reservoir_level_m} m</b></div>
        <div className="metric"><span>Head below FRL</span><b>{status.remaining_level_m} m</b></div>
        <div className="metric"><span>Recommended response</span><b>{status.recommended_response_level}</b></div>
      </div>
      {status.overflow ? <p className="error-text">Current level exceeds full reservoir level — overflow condition.</p> : null}
      <p className="hint formula">{status.calculation}</p>
    </div>
  );
}
