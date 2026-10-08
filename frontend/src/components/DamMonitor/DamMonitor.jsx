import { useEffect, useRef, useState } from "react";
import { fetchDam, fetchDams, predictDamRisk, runDamSimulation } from "../../services/api.js";
import IndiaDamMap from "./IndiaDamMap.jsx";
import DamSelector from "./DamSelector.jsx";
import TopDamsSelector from "./TopDamsSelector.jsx";
import { indianDams } from "../../data/indianDams.js";
import { formatDateTimeIST } from "../../utils/time.js";
import { useScenario } from "../../state/ScenarioContext.jsx";
import DamStatusCard from "./DamStatusCard.jsx";
import DamMlPredictionCard from "./DamMlPredictionCard.jsx";
import DamSimulationControls from "./DamSimulationControls.jsx";
import DamTimeSeriesChart from "./DamTimeSeriesChart.jsx";
import DamRiskEnginePanel from "./DamRiskEnginePanel.jsx";
import DataSourceBadge from "../DataSourceBadge.jsx";
import KpiCard from "../KpiCard.jsx";

const DEFAULT_CONTROLS = {
  current_level_m: null,
  rainfall_mm: 20,
  rainfall_intensity_mm_hr: 5,
  inflow_cumec: 800,
  outflow_cumec: 600,
  capacity_override_m: null,
  forecast_hours: 72,
  temperature_c: null,
};

// idle -> selected -> loading -> ready <-> simulating -> completed
//                         \-> error (retry -> loading)
const STATUS_LABEL = {
  idle: "Select a dam to begin",
  selected: "Dam selected — click LOAD SCENARIO",
  loading: "Loading scenario…",
  ready: "Scenario ready",
  simulating: "Running simulation…",
  completed: "Simulation complete",
  error: "Scenario loading failed",
};

/** Dam Monitor tab — /simulation. AI dam monitoring & disaster simulation
 * control center: pick a real Indian dam scenario, explicitly LOAD it
 * (idle → selected → loading → ready → simulating → completed / error),
 * then compare calculated status vs. an independent ML prediction and run
 * rainfall/inflow/outflow what-ifs. */
export default function DamMonitor() {
  const [dams, setDams] = useState([]);
  const [scenarios, setScenarios] = useState({});
  const [listError, setListError] = useState("");
  const [listLoading, setListLoading] = useState(true);

  const [selectedId, setSelectedId] = useState("");
  const [selectedTopDamId, setSelectedTopDamId] = useState(null);
  const [status, setStatus] = useState("idle");
  const [loadingStep, setLoadingStep] = useState("");
  const [scenarioError, setScenarioError] = useState("");

  const [damDetail, setDamDetail] = useState(null);
  const [mlPrediction, setMlPrediction] = useState(null);
  const [controls, setControls] = useState(DEFAULT_CONTROLS);
  const [scenarioId, setScenarioId] = useState(null);
  const [runResult, setRunResult] = useState(null);
  const [runError, setRunError] = useState("");

  const runningRef = useRef(false);
  const [regionDamId, setRegionDamId] = useState(null);
  const unified = useScenario();
  const appliedRef = useRef(null);

  useEffect(() => {
    let alive = true;
    fetchDams()
      .then((d) => {
        if (!alive) return;
        const list = Array.isArray(d?.dams) ? d.dams : [];
        setDams(list);
        setScenarios(d?.scenarios || {});
        setRegionDamId(d?.region_dam?.dam_id || null);
        if (!list.length) setListError(d?.message || "No dams available.");
      })
      .catch((err) => alive && setListError(err.message || "Failed to load dams"))
      .finally(() => alive && setListLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  // SELECT — highlights the dam and clears all previously loaded/run state.
  // No stale data from a previous dam survives a new selection.
  function selectDam(id) {
    setSelectedId(id);
    setStatus("selected");
    setLoadingStep("");
    setScenarioError("");
    setRunError("");
    setDamDetail(null);
    setMlPrediction(null);
    setRunResult(null);
    setScenarioId(null);
    setControls(DEFAULT_CONTROLS);
  }

  // LOAD SCENARIO — explicit step. Each staged message corresponds to a real
  // async call completing (no arbitrary delays). Populates dam data, the
  // independent ML prediction, simulation defaults, and an initial baseline
  // run, then flips status to "ready" so Run Simulation unlocks.
  async function loadScenario(damIdArg, presetControls, presetId) {
    const damId = typeof damIdArg === "string" && damIdArg ? damIdArg : selectedId;
    if (!damId || status === "loading") return;
    setStatus("loading");
    setScenarioError("");
    try {
      setLoadingStep("Preparing reservoir data…");
      const detail = await fetchDam(damId);
      if (!detail || detail.available === false) {
        throw new Error(detail?.message || "Dam data unavailable");
      }
      setDamDetail(detail);

      const base = { ...DEFAULT_CONTROLS, ...(presetControls || {}) };
      setLoadingStep("Loading weather & ML risk prediction…");
      const ml = await predictDamRisk({ dam_id: damId, rainfall_24h_mm: base.rainfall_mm });
      setMlPrediction(ml);

      setLoadingStep("Preparing simulation parameters…");
      const initialControls = { ...base, current_level_m: detail.current_level_m };
      setControls(initialControls);
      setScenarioId(presetId || null);

      setLoadingStep("Initializing prediction model…");
      const result = await runDamSimulation({ dam_id: damId, scenario: presetId || undefined, ...initialControls });
      if (result?.available === false) throw new Error(result?.message || "Simulation unavailable");
      setRunResult(result);
      if (result?.ml_prediction_box) setMlPrediction(result.ml_prediction_box);

      setLoadingStep("Scenario ready.");
      setStatus("ready");
    } catch (err) {
      setScenarioError(err.message || "Scenario loading failed.");
      setStatus("error");
    }
  }

  // Unified scenario -> reservoir run. Picks the page's dam (first one if the
  // user has not chosen yet) and loads straight through, so selecting a
  // scenario reloads this whole section without a manual LOAD click.
  useEffect(() => {
    if (!unified?.scenario || !dams.length) return;
    const key = `${unified.activeId}:${unified.revision}`;
    if (appliedRef.current === key) return;
    appliedRef.current = key;
    // The evacuation region's dam (backend region_dam), never just row 0.
    const damId = selectedId || unified?.damId || regionDamId || dams[0]?.id;
    if (!damId) return;
    setSelectedId(damId);
    loadScenario(damId, unified.scenario.dam?.controls, unified.scenario.dam?.preset);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unified?.activeId, unified?.revision, dams.length]);

  function applyScenario(id) {
    const preset = scenarios[id];
    if (!preset || (status !== "ready" && status !== "completed")) return;
    setScenarioId(id);
    setControls((c) => ({ ...c, ...preset.defaults }));
  }

  function editControls(next) {
    if (status !== "ready" && status !== "completed") return;
    setScenarioId(null);
    setControls(next);
    // Surface manual edits to the page-level "Custom (modified)" badge.
    if (unified) {
      const changed = {};
      for (const [k, v] of Object.entries(next || {})) {
        if (v !== null && v !== undefined && Number(controls?.[k]) !== Number(v)) changed[k] = v;
      }
      if (Object.keys(changed).length) unified.patchInputs(changed);
    }
  }

  function commitCurrentLevel(n) {
    if (status !== "ready" && status !== "completed") return;
    editControls({ ...controls, current_level_m: n });
  }

  // RUN SIMULATION — only reachable once the scenario is ready (or already
  // completed, for a re-run with edited inputs). Guarded against overlap.
  async function runSimulation() {
    if (!selectedId || runningRef.current) return;
    if (status !== "ready" && status !== "completed") return;
    runningRef.current = true;
    setStatus("simulating");
    setRunError("");
    try {
      const body = { dam_id: selectedId, scenario: scenarioId || undefined, ...controls };
      const result = await runDamSimulation(body);
      if (result?.available === false) throw new Error(result?.message || "Simulation unavailable");
      setRunResult(result);
      setMlPrediction(result.ml_prediction_box);
      setStatus("completed");
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setRunError(typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : err.message || String(err));
      setStatus("ready");
    } finally {
      runningRef.current = false;
    }
  }

  // Dynamic recalculation once the scenario is loaded: any control/scenario
  // change auto-reruns after a short debounce. Never fires before "ready".
  useEffect(() => {
    if (status !== "ready" && status !== "completed") return undefined;
    if (!selectedId) return undefined;
    const t = window.setTimeout(() => {
      runSimulation();
    }, 600);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [controls, scenarioId]);

  const statusData = runResult?.status_box || damDetail?.status_box;
  const risk = runResult?.risk_engine;
  const projection = runResult?.projection;
  const selectedDam = dams.find((d) => d.id === selectedId);
  const workspaceReady = status === "ready" || status === "simulating" || status === "completed";
  const running = status === "simulating";

  if (listLoading) return <div className="panel glass-panel"><p className="hint">Loading dam registry…</p></div>;
  if (listError && !dams.length) {
    return (
      <div className="panel glass-panel">
        <p className="error-text">{listError}</p>
      </div>
    );
  }

  return (
    <div className="page dam-monitor">
      <div className="status-row builder-head">
        <div>
          <p className="eyebrow">AI dam monitoring & disaster simulation</p>
          <h2 className="section-title">Dam Monitor — {selectedDam?.name || "select a dam"}</h2>
        </div>
        <span className={`badge ${status === "error" ? "crit" : status === "ready" || status === "completed" ? "live" : "sim"}`}>
          {STATUS_LABEL[status]}
        </span>
      </div>
      <p className="hint">
        Select one of 5 major Indian dam scenarios, click the Load Scenario button, then adjust the controls —
        everything recalculates automatically once loaded.
      </p>

      <DamSelector dams={dams} selectedId={selectedId} onSelect={selectDam} />

      <div className="status-row builder-head">
        <h2 className="section-title">Top 10 Dams in India</h2>
      </div>
      <p className="hint">
        Select any of India&apos;s 10 major dams to fly the map to it — a navigation reference, independent of the
        loaded simulation scenario above.
      </p>
      <TopDamsSelector dams={indianDams} selectedId={selectedTopDamId} onSelect={setSelectedTopDamId} />

      <div className="grid-2 dam-map-row">
        <IndiaDamMap
          dams={dams}
          selectedId={selectedId}
          onSelect={selectDam}
          topDams={indianDams}
          selectedTopDamId={selectedTopDamId}
          onSelectTopDam={setSelectedTopDamId}
        />
        <div className="panel">
          <h2>DOWNSTREAM & REFERENCE INFO</h2>
          {selectedDam ? (
            <>
              <div className="metric"><span>River</span><b>{selectedDam.river}</b></div>
              <div className="metric"><span>Downstream region</span><b>{selectedDam.downstream_region}</b></div>
              <div className="metric"><span>Historical / normal level</span><b>{selectedDam.historical_normal_level_m} m</b></div>
              <div className="metric"><span>Risk threshold</span><b>{selectedDam.risk_threshold_pct}%</b></div>
              <div className="metric"><span>Capacity</span><b>{selectedDam.capacity_note}</b></div>
              <div className="metric"><span>Last updated</span><b>{formatDateTimeIST(selectedDam.last_updated)}</b></div>
              <p className="hint">
                <DataSourceBadge kind="HISTORICAL" /> Full-reservoir-level and capacity figures are public reference
                values (approximate), not a live official feed.
              </p>
            </>
          ) : (
            <p className="hint">Select a dam above or on the map.</p>
          )}

          {status === "selected" || status === "loading" || status === "error" ? (
            <div className="load-scenario-box">
              <button
                type="button"
                className="primary run-scenario-btn"
                onClick={loadScenario}
                disabled={status === "loading"}
              >
                {status === "loading" ? (
                  <>
                    <span className="pdf-btn-spinner" aria-hidden />
                    LOADING…
                  </>
                ) : status === "error" ? (
                  "RETRY LOAD SCENARIO"
                ) : (
                  "LOAD SCENARIO"
                )}
              </button>
              {status === "loading" ? <p className="hint dam-live-pulse">{loadingStep}</p> : null}
              {status === "error" ? (
                <div className="error-banner" role="alert">
                  <p>Scenario loading failed.</p>
                  <p>Reason: {scenarioError}</p>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      <div className="grid-2 dam-kpi-row">
        <KpiCard
          label="Current Dam Level"
          value={statusData ? statusData.current_level_m : null}
          suffix=" m"
          sub={selectedDam ? `${selectedDam.name} · editable once loaded` : ""}
          editable={workspaceReady}
          numericValue={statusData?.current_level_m}
          onCommit={commitCurrentLevel}
          loading={!statusData && status === "loading"}
        />
        <KpiCard
          label="Total / Full Dam Capacity"
          value={statusData ? statusData.full_reservoir_level_m : null}
          suffix=" m"
          sub="Full reservoir level (FRL) — static reference"
          loading={!statusData && status === "loading"}
        />
      </div>

      <div className="risk-split glass-panel">
        <DamStatusCard status={statusData} />
        <div className="risk-split-arrow" aria-hidden>vs</div>
        <DamMlPredictionCard prediction={mlPrediction} loading={status === "loading"} />
      </div>

      <DamSimulationControls
        controls={controls}
        onChange={editControls}
        // The page-level scenario pills own preset selection now; the dam's
        // own preset row would be a second, competing selector.
        scenarios={unified ? {} : scenarios}
        onApplyScenario={applyScenario}
        onRun={runSimulation}
        running={running}
        error={runError}
        locked={!workspaceReady}
      />

      {risk ? <DamRiskEnginePanel risk={risk} /> : null}

      <div className="panel">
        <div className="panel-head">
          <h2>PREDICTED WATER LEVEL OVER TIME</h2>
          {running ? <span className="badge live dam-live-pulse">RECALCULATING…</span> : null}
        </div>
        <DamTimeSeriesChart projection={projection} />
      </div>
    </div>
  );
}
