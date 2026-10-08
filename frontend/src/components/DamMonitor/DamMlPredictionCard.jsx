import DataSourceBadge from "../DataSourceBadge.jsx";

/** BOX 2 — ML risk prediction, independently computed from the trained model.
 * Deliberately kept visually + structurally separate from the calculated
 * status (DamStatusCard) — this is the model's own output, not a threshold. */
export default function DamMlPredictionCard({ prediction, loading }) {
  if (loading) return <div className="risk-split-col"><p className="hint">Running ML prediction…</p></div>;
  if (!prediction) return <div className="risk-split-col"><p className="hint">Click LOAD SCENARIO above to run the ML prediction.</p></div>;
  if (!prediction.available) {
    return (
      <div className="risk-split-col">
        <DataSourceBadge kind="UNAVAILABLE" />
        <h3>ML risk prediction</h3>
        <p className="error-text">{prediction.message || "MODEL UNAVAILABLE"}</p>
      </div>
    );
  }
  const prob = prediction.probability_severe;
  return (
    <div className="risk-split-col">
      <DataSourceBadge kind="REAL ML" title={`${prediction.stage1_model} + ${prediction.stage2_model} v${prediction.model_version}`} />
      <h3>ML risk prediction</h3>
      <b>{prediction.risk_category || "—"}</b>
      <p className="hint">Trained model output — independent of the calculated status above</p>
      <div className="dam-status-grid">
        <div className="metric"><span>Severe-flood probability</span><b>{prob != null ? `${(prob * 100).toFixed(1)}%` : "—"}</b></div>
        <div className="metric"><span title="INDOFLOODS peak flood level from the catchment model — not the reservoir elevation">ML peak flood level (catchment model)</span><b>{prediction.predicted_peak_level_m != null ? `${prediction.predicted_peak_level_m} m` : "—"}</b></div>
        <div className="metric"><span>Recommended response</span><b>{prediction.recommended_response_level || "—"}</b></div>
        <div className="metric"><span>Model</span><b>{prediction.stage1_model || "—"}</b></div>
      </div>
      {prediction.model_evaluation?.available ? (
        <p className="hint">
          Model holdout: R² {prediction.model_evaluation.regression_holdout?.r2 ?? "—"} · classifier accuracy{" "}
          {prediction.model_evaluation.classifier_holdout?.accuracy != null
            ? `${(prediction.model_evaluation.classifier_holdout.accuracy * 100).toFixed(1)}%`
            : "—"}{" "}
          (real, stored evaluation — not recomputed here)
        </p>
      ) : null}
      <p className="hint formula">{prediction.catchment_note}</p>
    </div>
  );
}
