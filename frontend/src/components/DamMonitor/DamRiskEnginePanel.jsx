import DataSourceBadge from "../DataSourceBadge.jsx";

const RISK_CLASS = { LOW: "live", MODERATE: "warn", HIGH: "sim", VERY_HIGH: "warn", CRITICAL: "crit" };

/** Advanced dam risk engine — combines calculated status + trend + ML into one structured result. */
export default function DamRiskEnginePanel({ risk }) {
  if (!risk) return null;
  return (
    <div className="panel glass-panel">
      <div className="panel-head">
        <h2>ADVANCED RISK ENGINE</h2>
        <DataSourceBadge kind="HYBRID" title={risk.formula} />
      </div>
      <div className="status-row">
        <span className={`badge ${RISK_CLASS[risk.risk] || ""}`}>{risk.risk}</span>
        <span className="hint">Composite score {risk.composite_score}</span>
      </div>
      <div className="dam-status-grid">
        <div className="metric"><span>Fill level</span><b>{risk.fill_percentage}%</b></div>
        <div className="metric"><span>Trend</span><b>{risk.trend}</b></div>
        <div className="metric"><span>Projected peak (m MSL)</span><b>{risk.predicted_peak_level_m != null ? `${risk.predicted_peak_level_m} m` : "—"}</b></div>
        <div className="metric"><span>Final level (m MSL)</span><b>{risk.predicted_level_m != null ? `${risk.predicted_level_m} m` : "—"}</b></div>
        <div className="metric">
          <span>ML confidence</span>
          <b>{risk.ml_confidence != null ? `${(risk.ml_confidence * 100).toFixed(1)}%` : "—"}</b>
        </div>
        <div className="metric"><span>Recommended response</span><b>{risk.recommended_response_level}</b></div>
      </div>
      <p className="hint"><b>Main drivers:</b> {(risk.main_drivers || []).join(" + ")}</p>
      <p className="hint formula">{risk.formula}</p>
    </div>
  );
}
