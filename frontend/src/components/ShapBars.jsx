export default function ShapBars({ explain, showCounterfactual = true }) {
  if (!explain?.available) {
    return <div className="muted">{explain?.message || "SHAP explanation loads with rainfall."}</div>;
  }
  const maxAbs = Math.max(...(explain.bars || []).map((b) => Math.abs(b.shap_value)), 0.001);
  const method = explain.method || "SHAP-style feature attribution";
  const methodBadge = String(method).toLowerCase().includes("treeshap")
    ? "TreeSHAP"
    : "SHAP-style feature attribution";
  return (
    <div>
      <p className="muted">
        <span className="data-source-badge src-hist">{methodBadge}</span> on {explain.model_id} · Raw ML P=
        {explain.flood_probability != null ? `${(explain.flood_probability * 100).toFixed(1)}%` : "n/a"} ·{" "}
        {explain.risk_category}
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
      </div>
    </div>
  );
}
