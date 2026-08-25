import { useEffect, useMemo, useRef, useState } from "react";
import { fetchScenarios, resetSimulation, startSimulation } from "../../services/api.js";
import FeatureToggles, { DEFAULT_FEATURES } from "../../components/FeatureToggles.jsx";

const FALLBACK_NUMERIC = {
  rainfall_intensity: 55,
  dam_level: 199,
  river_level: 204.2,
  road_blockage: 0.15,
  population: 12000,
  shelter_capacity_factor: 1,
  traffic: 0.45,
  ticks: 24,
  tick_seconds: 2,
};

/** Built-in catalog so RUN never stays blocked if API catalog fails. */
const BUILTIN_SCENARIOS = [
  {
    id: "multiple_sos",
    title: "Multiple SOS",
    story: "Citizen emergency requests spike as water enters residential pockets.",
    defaults: { ...FALLBACK_NUMERIC, sos_count: 10 },
  },
  {
    id: "heavy_rainfall",
    title: "Heavy Rainfall",
    story: "Extreme rainfall increases runoff across the Yamuna floodplain.",
    defaults: {
      rainfall_intensity: 72,
      dam_level: 199.2,
      river_level: 204.6,
      road_blockage: 0.22,
      population: 14000,
      shelter_capacity_factor: 1,
      traffic: 0.55,
      sos_count: 10,
      ticks: 24,
      tick_seconds: 2,
    },
  },
  {
    id: "dam_overflow",
    title: "Dam Overflow",
    story: "Upstream barrage storage approaches danger; releases raise river stage.",
    defaults: {
      rainfall_intensity: 38,
      dam_level: 206.5,
      river_level: 205.2,
      road_blockage: 0.18,
      population: 15000,
      shelter_capacity_factor: 0.95,
      traffic: 0.5,
      sos_count: 10,
      ticks: 24,
      tick_seconds: 2,
    },
  },
  {
    id: "river_rise",
    title: "River Rise",
    story: "Yamuna stage climbs toward the danger mark.",
    defaults: {
      rainfall_intensity: 48,
      dam_level: 201,
      river_level: 205.6,
      road_blockage: 0.2,
      population: 13000,
      shelter_capacity_factor: 1,
      traffic: 0.52,
      sos_count: 10,
      ticks: 24,
      tick_seconds: 2,
    },
  },
  {
    id: "road_blockage",
    title: "Road Blockage",
    story: "Key floodplain corridors lose accessibility.",
    defaults: {
      rainfall_intensity: 50,
      dam_level: 199.5,
      river_level: 204.8,
      road_blockage: 0.55,
      population: 12000,
      shelter_capacity_factor: 1,
      traffic: 0.72,
      sos_count: 8,
      ticks: 24,
      tick_seconds: 2,
    },
  },
  {
    id: "shelter_congestion",
    title: "Shelter Congestion",
    story: "East-bank shelters fill; inland capacity absorbs demand.",
    defaults: {
      rainfall_intensity: 52,
      dam_level: 200,
      river_level: 204.9,
      road_blockage: 0.25,
      population: 18000,
      shelter_capacity_factor: 0.55,
      traffic: 0.6,
      sos_count: 12,
      ticks: 24,
      tick_seconds: 2,
    },
  },
  {
    id: "mass_evacuation",
    title: "Mass Evacuation",
    story: "Multiple zones require concurrent shelter assignment.",
    defaults: {
      rainfall_intensity: 65,
      dam_level: 202,
      river_level: 205.4,
      road_blockage: 0.35,
      population: 22000,
      shelter_capacity_factor: 0.8,
      traffic: 0.68,
      sos_count: 14,
      ticks: 28,
      tick_seconds: 2,
    },
  },
];

const PARAM_LABELS = {
  rainfall_intensity: "Rainfall intensity (mm)",
  dam_level: "Dam / barrage water level (m)",
  river_level: "River water level (m)",
  road_blockage: "Road blockage (0–1)",
  population: "Affected population",
  shelter_capacity_factor: "Shelter capacity factor",
  traffic: "Traffic congestion (0–1)",
  ticks: "Simulation ticks",
  tick_seconds: "Seconds per tick",
};

const EXAMPLE_CITIZENS = [
  { citizen_name: "Priya Sharma", age: 29, lat: 28.651, lon: 77.262, people: 3, water_level_note: "knee-deep" },
  { citizen_name: "Aarav Mehta", age: 41, lat: 28.6284, lon: 77.2495, people: 2, water_level_note: "waist-deep" },
  { citizen_name: "Ananya Reddy", age: 17, lat: 28.6075, lon: 77.2898, people: 4, water_level_note: "ankle-deep" },
  { citizen_name: "Rohan Gupta", age: 54, lat: 28.715, lon: 77.2315, people: 1, water_level_note: "chest-deep" },
  { citizen_name: "Fatima Khan", age: 36, lat: 28.5518, lon: 77.2934, people: 5, water_level_note: "knee-deep" },
  { citizen_name: "Kabir Singh", age: 8, lat: 28.6558, lon: 77.2675, people: 2, water_level_note: "ankle-deep" },
  { citizen_name: "Isha Patel", age: 63, lat: 28.6406, lon: 77.2495, people: 2, water_level_note: "waist-deep" },
  { citizen_name: "Vivek Nair", age: 33, lat: 28.5889, lon: 77.2532, people: 3, water_level_note: "knee-deep" },
  { citizen_name: "Meera Joshi", age: 24, lat: 28.6127, lon: 77.2773, people: 1, water_level_note: "waist-deep" },
  { citizen_name: "Arjun Das", age: 47, lat: 28.5672, lon: 77.21, people: 4, water_level_note: "chest-deep" },
];

function roster(n) {
  const count = Math.max(0, Number(n) || 0);
  return Array.from({ length: count }, (_, i) => {
    const src = { ...EXAMPLE_CITIZENS[i % EXAMPLE_CITIZENS.length] };
    if (i >= EXAMPLE_CITIZENS.length) {
      src.citizen_name = `${EXAMPLE_CITIZENS[i % EXAMPLE_CITIZENS.length].citizen_name} ${i + 1}`;
      src.lat = Number((src.lat + 0.004 * Math.floor(i / 10)).toFixed(5));
      src.lon = Number((src.lon + 0.004 * (i % 5)).toFixed(5));
    }
    return src;
  });
}

function paramsFromDefaults(defaults = {}) {
  const next = { ...FALLBACK_NUMERIC };
  for (const key of Object.keys(FALLBACK_NUMERIC)) {
    if (defaults[key] != null) next[key] = Number(defaults[key]);
  }
  return next;
}

export default function ScenarioBuilder({ onStarted }) {
  const [scenarios, setScenarios] = useState([]);
  const [selected, setSelected] = useState("");
  const [params, setParams] = useState(FALLBACK_NUMERIC);
  const [citizens, setCitizens] = useState(() => roster(10));
  const [features, setFeatures] = useState({ ...DEFAULT_FEATURES });
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [launching, setLaunching] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const [ready, setReady] = useState(false);
  const launchLock = useRef(false);
  const current = useMemo(() => scenarios.find((s) => s.id === selected), [scenarios, selected]);

  function applyScenarioList(list, note = "") {
    setScenarios(list);
    const first = list.find((s) => s.id === "multiple_sos") || list[0];
    selectScenario(first);
    setReady(true);
    setLoadError(note);
  }

  function loadScenarios() {
    let alive = true;
    setPageLoading(true);
    setLoadError("");
    setReady(false);
    fetchScenarios()
      .then((d) => {
        if (!alive) return;
        const list = Array.isArray(d?.scenarios) ? d.scenarios : [];
        if (!list.length) {
          applyScenarioList(BUILTIN_SCENARIOS, d?.message || "API catalog empty — using built-in scenarios.");
          return;
        }
        applyScenarioList(list);
      })
      .catch((err) => {
        if (!alive) return;
        applyScenarioList(
          BUILTIN_SCENARIOS,
          `${err?.message || "Failed to load scenarios"} — using built-in catalog.`
        );
      })
      .finally(() => {
        if (alive) setPageLoading(false);
      });
    return () => {
      alive = false;
    };
  }

  useEffect(() => loadScenarios(), []);

  function selectScenario(scenario) {
    if (!scenario) return;
    const defaults = scenario.defaults || {};
    const nextParams = paramsFromDefaults(defaults);
    const nextCitizens = roster(defaults.sos_count ?? nextParams.sos_count ?? 10);
    setSelected(scenario.id);
    setParams(nextParams);
    setCitizens(nextCitizens);
    setError("");
  }

  function addCitizen() {
    setCitizens((rows) => {
      const i = rows.length;
      const base = EXAMPLE_CITIZENS[i % EXAMPLE_CITIZENS.length];
      const src = {
        ...base,
        citizen_name: i < EXAMPLE_CITIZENS.length ? base.citizen_name : `${base.citizen_name} ${i + 1}`,
        lat: Number((base.lat + 0.004 * Math.floor(i / 10)).toFixed(5)),
        lon: Number((base.lon + 0.004 * (i % 5)).toFixed(5)),
      };
      return [...rows, src];
    });
  }

  function removeCitizen() {
    setCitizens((rows) => (rows.length <= 0 ? rows : rows.slice(0, -1)));
  }

  function removeCitizenAt(i) {
    setCitizens((rows) => rows.filter((_, idx) => idx !== i));
  }

  function clearCitizens() {
    setCitizens([]);
  }

  function resetDefaultTen() {
    setCitizens(roster(10));
  }

  function setCountExact(n) {
    const count = Math.max(0, Number(n) || 0);
    setCitizens(roster(count));
  }

  function editCitizen(i, field, value) {
    setCitizens((rows) => rows.map((row, idx) => (idx === i ? { ...row, [field]: value } : row)));
  }

  async function run() {
    if (launchLock.current || !selected) return;
    launchLock.current = true;
    let finished = false;
    const finishLaunch = () => {
      if (finished) return;
      finished = true;
      window.clearTimeout(launchTimer);
      setLaunching(false);
      launchLock.current = false;
    };
    const launchTimer = window.setTimeout(() => {
      finishLaunch();
      setError("Launch timed out (~20s). Check API on :8000, hard-refresh, then retry RUN.");
    }, 20000);
    try {
      setLaunching(true);
      setError("");
      sessionStorage.removeItem("flood_run_theater");
      await resetSimulation().catch(() => {});
      const state = await startSimulation({
        scenario: selected,
        ...params,
        sos_count: citizens.length,
        citizens,
        features,
      });
      onStarted?.({
        runId: state?.run_id || `run-${Date.now()}`,
        scenario: selected,
        title: current?.title,
        features,
      });
      window.setTimeout(() => {
        document.getElementById("sim-execution")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 60);
      window.setTimeout(() => {
        document.getElementById("ieee-hqrl-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 850);
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (status === 401) {
        setError("API rejected the request. Restart the backend, then retry RUN.");
      } else if (status === 403) {
        setError("Forbidden — restart backend with auth disabled.");
      } else if (err?.code === "ECONNABORTED" || String(err?.message || "").toLowerCase().includes("timeout")) {
        setError("Backend timeout — restart API: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000");
      } else {
        setError(typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : err.message || String(err));
      }
    } finally {
      finishLaunch();
    }
  }

  return (
    <div className="page sim-builder">
      <div className="status-row">
        <h2 style={{ margin: 0 }}>1 · CHOOSE SCENARIO & FILL DETAILS</h2>
        <span className="badge sim">SIMULATION MODE</span>
      </div>
      <p className="hint">
        Step 1: click a scenario to fill rainfall, river/dam water, roads, SOS. Step 2: set feature radios ON/OFF.
        Step 3: click <b>RUN SCENARIO</b> — fresh output appears below (old run is cleared). Below the map you also get
        the <b>IEEE HQRL</b> live research panel (dynamic replan + paper benchmark).
      </p>
      <div className="grid-2">
        <div className="panel">
          <h2>SCENARIO</h2>
          <div className="form-grid">
            {scenarios.map((s) => (
              <button
                key={s.id}
                type="button"
                className={selected === s.id ? "primary" : ""}
                disabled={launching}
                onClick={() => selectScenario(s)}
              >
                {s.title}
              </button>
            ))}
          </div>
          <h3 style={{ marginTop: 16 }}>ENVIRONMENT DETAILS</h3>
          <div className="form-grid">
            {Object.entries(params).map(([k, v]) => (
              <label key={k}>
                {PARAM_LABELS[k] || k.replaceAll("_", " ")}
                <input
                  type="number"
                  step="0.01"
                  value={v}
                  onChange={(e) => setParams({ ...params, [k]: Number(e.target.value) })}
                />
              </label>
            ))}
            <label>
              SOS count (default 10 · min 0 · no max)
              <div className="sos-count-row">
                <button type="button" onClick={removeCitizen}>Reduce −</button>
                <b>{citizens.length}</b>
                <button type="button" onClick={addCitizen}>Add +</button>
                <button type="button" onClick={resetDefaultTen}>Reset to 10</button>
                <button type="button" className="danger" onClick={clearCitizens}>Clear all (0)</button>
                <input
                  type="number"
                  min={0}
                  style={{ width: 90 }}
                  value={citizens.length}
                  onChange={(e) => setCountExact(e.target.value)}
                  title="Type exact count"
                />
              </div>
            </label>
          </div>
          {error ? <div className="unavailable">{error}</div> : null}
        </div>
        <div className="panel">
          <h2>LOADED FOR: {current?.title || "—"}</h2>
          <p>{current?.story || "Select a scenario above."}</p>
          <div className="scenario-preview">
            <div className="metric"><span>Rainfall</span><b>{params.rainfall_intensity} mm</b></div>
            <div className="metric"><span>River water</span><b>{params.river_level} m</b></div>
            <div className="metric"><span>Dam water</span><b>{params.dam_level} m</b></div>
            <div className="metric"><span>Road blockage</span><b>{(params.road_blockage * 100).toFixed(0)}%</b></div>
            <div className="metric"><span>Population</span><b>{params.population}</b></div>
            <div className="metric"><span>SOS citizens</span><b>{citizens.length}</b></div>
          </div>
          <div className="process-steps">
            {["Select", "Fill details", "Features ON/OFF", "Run", "Output below"].map((s, i) => (
              <span key={s} className="stage">{i + 1}. {s}</span>
            ))}
          </div>
        </div>
      </div>
      <FeatureToggles features={features} onChange={setFeatures} />
      <div className="panel">
        <h2>SOS QUEUE — EDIT BEFORE RUN (CRUD)</h2>
        <p className="hint">{citizens.length} citizens (default 10). Add / edit / delete rows. Min 0, no upper limit. Then Run.</p>
        <div className="actions" style={{ marginBottom: 10 }}>
          <button type="button" className="primary" onClick={addCitizen}>Add person</button>
          <button type="button" onClick={resetDefaultTen}>Load default 10</button>
          <button type="button" className="danger" onClick={clearCitizens}>Delete all</button>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Name</th>
                <th>Age</th>
                <th>Latitude</th>
                <th>Longitude</th>
                <th>People</th>
                <th>Water depth</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {citizens.map((c, i) => (
                <tr key={i}>
                  <td>{i + 1}</td>
                  <td><input value={c.citizen_name} onChange={(e) => editCitizen(i, "citizen_name", e.target.value)} /></td>
                  <td><input type="number" value={c.age} onChange={(e) => editCitizen(i, "age", Number(e.target.value))} /></td>
                  <td><input type="number" step="0.0001" value={c.lat} onChange={(e) => editCitizen(i, "lat", Number(e.target.value))} /></td>
                  <td><input type="number" step="0.0001" value={c.lon} onChange={(e) => editCitizen(i, "lon", Number(e.target.value))} /></td>
                  <td><input type="number" value={c.people} onChange={(e) => editCitizen(i, "people", Number(e.target.value))} /></td>
                  <td><input value={c.water_level_note} onChange={(e) => editCitizen(i, "water_level_note", e.target.value)} /></td>
                  <td><button type="button" className="danger" onClick={() => removeCitizenAt(i)}>Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!citizens.length ? <p className="hint">Queue empty (0). Add people or Reset to 10.</p> : null}
        </div>
        <div className="actions run-scenario-bar">
          <button
            className="primary run-scenario-btn"
            type="button"
            onClick={run}
            disabled={launching || pageLoading || !ready || !selected}
          >
            <span className="pdf-btn-glow" aria-hidden />
            {launching ? (
              <>
                <span className="pdf-btn-spinner" aria-hidden />
                STARTING…
              </>
            ) : pageLoading ? (
              "Loading scenarios…"
            ) : !ready ? (
              "Scenarios not ready"
            ) : (
              "RUN SCENARIO"
            )}
          </button>
          <p className="hint run-scenario-hint">
            {ready ? "Scenarios ready ✓ — live output appears below after run." : "Wait until scenarios finish loading."}
          </p>
        </div>
        {loadError ? (
          <div className="error-banner" role="alert">
            <p>{loadError}</p>
            <button type="button" className="primary" onClick={() => loadScenarios()}>
              Retry load
            </button>
          </div>
        ) : null}
        {error ? (
          <div className="error-banner" role="alert">
            <p>{error}</p>
          </div>
        ) : null}
      </div>
      {pageLoading ? (
        <div className="page-loader" role="status" aria-live="polite">
          <div className="page-loader-card glass-elevated">
            <span className="run-spinner" />
            <h2>Loading simulation lab</h2>
            <p className="hint">Fetch scenarios → validate → populate controls → enable RUN</p>
            <div className="pdf-progress"><i /></div>
          </div>
        </div>
      ) : null}
      {launching ? (
        <div className="run-launch" role="status" aria-live="polite">
          <div className="run-launch-card">
            <span className="run-spinner" />
            <h2>Launching {current?.title || "scenario"}</h2>
            <p className="run-now">Clearing previous run · rainfall / river / dam · ML prediction</p>
            <div className="pdf-progress"><i /></div>
            <ul className="pdf-overlay-steps">
              <li className="on">Reset prior run</li>
              <li className="on">Load environment + SOS queue</li>
              <li className="on">Start Random Forest / XGBoost</li>
              <li>Scroll to live output below</li>
            </ul>
            <p className="hint" style={{ marginTop: 12 }}>
              If this lasts more than ~30s, the API is down or you are not signed in.
            </p>
            <button
              type="button"
              className="danger"
              style={{ marginTop: 8 }}
              onClick={() => {
                setLaunching(false);
                launchLock.current = false;
                setError("Launch cancelled. Sign in as OPERATOR/ADMIN, confirm API on :8000, then retry RUN.");
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
