const FIELD_LABELS = {
  current_level_m: "Current water level (m)",
  rainfall_mm: "Rainfall (mm, cumulative)",
  rainfall_intensity_mm_hr: "Rainfall intensity (mm/hr)",
  inflow_cumec: "Inflow (cumec)",
  outflow_cumec: "Outflow / release (cumec)",
  capacity_override_m: "Reservoir capacity override (m, optional)",
  forecast_hours: "Forecast duration (hours)",
  temperature_c: "Temperature (°C, optional)",
};

export default function DamSimulationControls({
  controls,
  onChange,
  scenarios = {},
  onApplyScenario,
  onRun,
  running,
  error,
  locked = false,
}) {
  function setField(key, value) {
    onChange({ ...controls, [key]: value === "" ? null : Number(value) });
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>SIMULATION CONTROLS</h2>
        <span className="badge sim">DAM SIMULATION</span>
      </div>
      <p className="hint">
        {locked
          ? "Load the scenario above first — controls unlock once the dam data and ML prediction finish loading."
          : "Pick a scenario preset to auto-fill rainfall/inflow/outflow, or edit values directly — results recalculate automatically."}
      </p>
      <div className="form-grid scenario-pick-grid">
        {Object.entries(scenarios).map(([id, s]) => (
          <button key={id} type="button" className="scenario-pick" onClick={() => onApplyScenario?.(id)} disabled={running || locked}>
            <strong>{s.title}</strong>
            <span>{s.story}</span>
          </button>
        ))}
      </div>
      <h3 style={{ marginTop: 16 }}>INPUTS</h3>
      <div className="form-grid">
        {Object.keys(FIELD_LABELS).map((key) => (
          <label key={key}>
            {FIELD_LABELS[key]}
            <input
              type="number"
              step="0.1"
              value={controls[key] ?? ""}
              onChange={(e) => setField(key, e.target.value)}
              disabled={running || locked}
            />
          </label>
        ))}
      </div>
      {error ? <div className="error-banner" role="alert"><p>{error}</p></div> : null}
      <div className="actions run-scenario-bar">
        <button className="primary run-scenario-btn" type="button" onClick={onRun} disabled={running || locked}>
          {running ? (
            <>
              <span className="pdf-btn-spinner" aria-hidden />
              RUNNING…
            </>
          ) : (
            "RUN SIMULATION"
          )}
        </button>
      </div>
    </div>
  );
}
