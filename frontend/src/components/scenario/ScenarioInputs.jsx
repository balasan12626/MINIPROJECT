import { useState } from "react";
import FeatureToggles from "../FeatureToggles.jsx";
import { useScenario } from "../../state/ScenarioContext.jsx";

const DAM_LABELS = {
  rainfall_mm: "Rainfall, 24 h (mm)",
  rainfall_intensity_mm_hr: "Rain intensity (mm/hr)",
  inflow_cumec: "Inflow (cumec)",
  outflow_cumec: "Outflow / release (cumec)",
  forecast_hours: "Forecast horizon (h)",
};

const SIM_LABELS = {
  rainfall_intensity: "Rainfall intensity",
  dam_level: "Yamuna barrage stage (m)",
  river_level: "Yamuna river level (m)",
  road_blockage: "Road blockage (0–1)",
  population: "Affected population",
  shelter_capacity_factor: "Shelter capacity factor",
  traffic: "Traffic congestion (0–1)",
  sos_count: "SOS count",
  ticks: "Simulation ticks",
  tick_seconds: "Seconds per tick",
};

const STEP = {
  road_blockage: 0.05,
  traffic: 0.05,
  shelter_capacity_factor: 0.05,
  dam_level: 0.1,
  river_level: 0.1,
  tick_seconds: 0.5,
};

function NumberField({ name, label, value, onChange, disabled, changed }) {
  return (
    <label className={changed ? "field-changed" : ""}>
      <span>
        {label}
        {changed ? <em className="field-changed-dot" title="Changed from the scenario preset" /> : null}
      </span>
      <input
        type="number"
        step={STEP[name] ?? "any"}
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(name, e.target.value === "" ? "" : Number(e.target.value))}
      />
    </label>
  );
}

/** Middle section: every input a run consumes, pre-filled from the scenario
 * and fully editable. Editing marks the page Custom; it never starts a run. */
export default function ScenarioInputs() {
  const ctx = useScenario();
  const [showPeople, setShowPeople] = useState(false);
  if (!ctx) return null;

  const {
    scenario,
    inputs,
    patchInputs,
    changedFields,
    isCustom,
    resetToScenario,
    dams,
    damId,
    setDamId,
    damLevel,
    damsError,
    evacuationRegion,
    regionDam,
    citizens,
    setCitizens,
    features,
    setFeatures,
    running,
  } = ctx;

  const damKeys = Object.keys(scenario?.dam?.controls || {});
  const simKeys = Object.keys(scenario?.sim?.params || {});
  const set = (name, value) => patchInputs({ [name]: value });

  const editCitizen = (index, key, value) => {
    setCitizens((prev) => prev.map((c, i) => (i === index ? { ...c, [key]: value } : c)));
  };

  return (
    <section className="scenario-inputs" aria-label="Scenario inputs">
      <div className="status-row section-head">
        <h3 className="section-title">Inputs</h3>
        {isCustom ? (
          <>
            <span className="badge crit" title={changedFields.join(", ")}>
              CUSTOM (MODIFIED · {changedFields.length})
            </span>
            <button type="button" className="link-btn" onClick={resetToScenario} disabled={running}>
              Reset to scenario
            </button>
          </>
        ) : (
          <span className="badge live">MATCHES “{scenario?.label}”</span>
        )}
      </div>

      <div className="grid-2 scenario-input-grid">
        {/* ---------------- reservoir ---------------- */}
        <div className="panel">
          <div className="panel-head">
            <h3>Reservoir / dam</h3>
            <span className="badge sim">POST /api/simulation/run</span>
          </div>

          <div className="form-grid">
            <label>
              <span>Dam</span>
              <select value={damId} disabled={running} onChange={(e) => setDamId(e.target.value)}>
                {dams.length === 0 ? <option value="">Loading dams…</option> : null}
                {dams.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} — {d.state}
                  </option>
                ))}
              </select>
            </label>

            <NumberField
              name="current_level_m"
              label="Reservoir level (m MSL)"
              value={damLevel}
              onChange={set}
              disabled={running}
              changed={changedFields.includes("current_level_m")}
            />

            {damKeys.map((k) => (
              <NumberField
                key={k}
                name={k}
                label={DAM_LABELS[k] || k}
                value={inputs[k]}
                onChange={set}
                disabled={running}
                changed={changedFields.includes(k)}
              />
            ))}
          </div>
          {regionDam ? (
            <p className="hint">
              Flood region: <b>{evacuationRegion?.name || "—"}</b>. Nearest registry reservoir: <b>{regionDam.name}</b> (
              {regionDam.distance_km} km). {regionDam.same_river ? "" : `It is on the ${regionDam.river}, so its level is not the barrage stage.`}
            </p>
          ) : null}
          {damsError ? <p className="error-text">{damsError}</p> : null}
        </div>

        {/* ---------------- evacuation ---------------- */}
        <div className="panel">
          <div className="panel-head">
            <h3>Flood &amp; evacuation</h3>
            <span className="badge sim">POST /api/simulation/start</span>
          </div>
          <div className="form-grid">
            {simKeys.map((k) => (
              <NumberField
                key={k}
                name={k}
                label={SIM_LABELS[k] || k}
                value={inputs[k]}
                onChange={set}
                disabled={running}
                changed={changedFields.includes(k)}
              />
            ))}
          </div>
          <p className="hint">
            Engine scenario <b>{scenario?.sim?.scenario}</b>. Barrage stage is the Yamuna gauge — a different
            quantity from the reservoir level on the left.
          </p>
        </div>
      </div>

      {/* ---------------- people ---------------- */}
      <div className="panel">
        <div className="panel-head">
          <h3>Residents / SOS roster ({citizens.length})</h3>
          <button type="button" className="link-btn" onClick={() => setShowPeople((v) => !v)}>
            {showPeople ? "Hide table" : "Edit table"}
          </button>
        </div>
        <p className="hint">
          Sized by <b>SOS count</b>. These exact rows are sent with the run, so edits here reach the engine.
        </p>
        {showPeople ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Age</th>
                  <th>People</th>
                  <th>Lat</th>
                  <th>Lon</th>
                  <th>Water level</th>
                </tr>
              </thead>
              <tbody>
                {citizens.map((c, i) => (
                  <tr key={`${c.citizen_name}-${i}`}>
                    <td>
                      <input
                        value={c.citizen_name}
                        disabled={running}
                        onChange={(e) => editCitizen(i, "citizen_name", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        value={c.age}
                        disabled={running}
                        onChange={(e) => editCitizen(i, "age", Number(e.target.value))}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        value={c.people}
                        disabled={running}
                        onChange={(e) => editCitizen(i, "people", Number(e.target.value))}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.0001"
                        value={c.lat}
                        disabled={running}
                        onChange={(e) => editCitizen(i, "lat", Number(e.target.value))}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.0001"
                        value={c.lon}
                        disabled={running}
                        onChange={(e) => editCitizen(i, "lon", Number(e.target.value))}
                      />
                    </td>
                    <td>
                      <input
                        value={c.water_level_note}
                        disabled={running}
                        onChange={(e) => editCitizen(i, "water_level_note", e.target.value)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      <FeatureToggles features={features} onChange={setFeatures} title="Run features" />
    </section>
  );
}
