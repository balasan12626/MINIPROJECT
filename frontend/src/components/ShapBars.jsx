import { memo } from "react";

function ShapBars({ explain, loading = false, error = null, onRetry, showCounterfactual = true }) {
  if (loading) {
    return (
      <div className="kpi-loading">
        <span className="run-spinner" aria-hidden />
        CALCULATING SHAP EXPLANATION…
      </div>
    );
  }
  if (error) {
    return (
      <div className="unavailable" role="alert">
        SHAP explanation unavailable
        <div className="hint" style={{ marginTop: 4 }}>Reason: {error}</div>
        {onRetry ? (
          <button type="button" className="primary" style={{ marginTop: 8 }} onClick={onRetry}>
            Retry
          </button>
        ) : null}
      </div>
    );
  }
  if (!explain?.available) {
    return <div className="muted">{explain?.message || "Awaiting simulation data — explanation runs once rainfall is available."}</div>;
  }
  const maxAbs = Math.max(...(explain.bars || []).map((b) => Math.abs(b.shap_value)), 0.001);
  const method = explain.method || "SHAP-style feature attribution";
  const methodBadge = String(method).toLowerCase().includes("treeshap")
    ? "TreeSHAP"
    : "SHAP-style feature attribution";
  const hasProb = explain.flood_probability != null;
  const hasPeak = explain.predicted_peak_flood_level_m != null;
  return (
    <div>
      <p className="muted">
        <span className="data-source-badge src-hist">{methodBadge}</span> on {explain.model_id || "model"}
        {hasPeak ? ` · Predicted peak level = ${explain.predicted_peak_flood_level_m} m` : null}
        {hasProb ? ` · Raw ML P=${(explain.flood_probability * 100).toFixed(1)}%` : null}
        {explain.risk_category ? ` · ${explain.risk_category}` : null}
      </p>
      {showCounterfactual && explain.counterfactual?.message ? (
        <p className="counterfactual">{explain.counterfactual.message}</p>
      ) : null}
      <div className="shap-list">
        {(explain.bars || []).map((b) => (
          <div className="shap-row" key={b.feature}>
            <span className="shap-label">{String(b.feature).replaceAll("_", " ")}</span>
            <div className="shap-track">
              <div
                className={`shap-bar ${b.shap_value >= 0 ? "up" : "down"}`}
                style={{ width: `${(Math.abs(b.shap_value) / maxAbs) * 100}%` }}
              />
            </div>
            <b className={b.shap_value >= 0 ? "up" : "down"}>
              {b.shap_value >= 0 ? "+" : ""}
              {b.shap_value}
            </b>
          </div>
        ))}
        {!(explain.bars || []).length ? <div className="muted">No feature contributions returned.</div> : null}
      </div>
    </div>
  );
}

export default memo(ShapBars);
