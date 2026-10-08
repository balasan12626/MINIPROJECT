import { lazy, memo, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { pauseSimulation, resumeSimulation, resetSimulation, overrideSimulation, sendSimulationSos, fetchMlExplainV2, downloadSimReport, forceDispatch } from "../../services/api.js";
import FloodMap from "../../maps/FloodMap.jsx";
import AgentList from "../../components/AgentList.jsx";
import ScenarioRunTheater from "../../components/ScenarioRunTheater.jsx";
import ShapBars from "../../components/ShapBars.jsx";
import { DEFAULT_FEATURES } from "../../components/FeatureToggles.jsx";
import KpiCard from "../../components/KpiCard.jsx";
import HistoryChart from "../../charts/HistoryChart.jsx";
import LazyMount from "../../components/LazyMount.jsx";
import RescueOpsPanel from "../../components/rescue/RescueOpsPanel.jsx";
import AlgorithmArena from "../../components/AlgorithmArena.jsx";
import VoiceSosAgent from "../../components/VoiceSosAgent.jsx";
import NearestDamPanel from "../../components/NearestDamPanel.jsx";
import { collapseFeed } from "../../utils/feed.js";
import { createSimStore, SimStoreProvider, useSim, useSimFeed, useSimStore } from "./simStore.js";

// Heavy, below-the-fold modules: split out and mounted only when scrolled near.
const IeeeHqrlEmbed = lazy(() => import("../../components/IeeeHqrlEmbed.jsx"));
const AgentTalk = lazy(() => import("../../components/AgentTalk.jsx"));
const DemoRunPanels = lazy(() => import("../../components/DemoRunPanels.jsx"));
const ModelBenchmarkPanel = lazy(() => import("../../components/ModelBenchmarkPanel.jsx"));

const EMPTY = [];
const EXPLAIN_DEBOUNCE_MS = 800;

/** /simulation run view (flood / evacuation part).
 *
 * State lives in a tiny external store (simStore.js) fed by ONE poller +
 * websocket. Every section below subscribes to the slice it renders, so a
 * poll re-renders only the sections whose data changed — not the whole page. */
export default function SimulationExecution({ runMeta = null }) {
  const storeRef = useRef(null);
  if (!storeRef.current) storeRef.current = createSimStore();
  const store = storeRef.current;
  useSimFeed(store);

  useEffect(() => {
    if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
    return () => {
      if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
    };
  }, []);

  return (
    <SimStoreProvider value={store}>
      <RunView runMeta={runMeta} store={store} />
    </SimStoreProvider>
  );
}

function useFeats(runMeta) {
  const features = useSim(({ sim }) => sim?.features);
  const metaFeatures = runMeta?.features;
  return useMemo(() => ({ ...DEFAULT_FEATURES, ...(features || metaFeatures || {}) }), [features, metaFeatures]);
}

function RunView({ runMeta, store }) {
  const setSim = store.setSim;
  const { status, awaitingData, runId } = useSim(({ sim }) => ({
    status: runStatusOf(sim),
    awaitingData: runStatusOf(sim) === "running" && !(sim?.history || []).length,
    runId: sim?.run_id,
  }));
  const feats = useFeats(runMeta);

  const [sos, setSos] = useState({ citizen_name: "Priya Sharma", age: 34, people: 2, lat: 28.651, lon: 77.262, water_level_note: "knee-deep rainwater" });
  const [sosError, setSosError] = useState("");
  const [sosBusy, setSosBusy] = useState(false);
  const [showMap, setShowMap] = useState(true);
  const [replayTick, setReplayTick] = useState(null);
  const [selectedName, setSelectedName] = useState(null);
  const [arenaPaths, setArenaPaths] = useState(null);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [sosRegionWarning, setSosRegionWarning] = useState("");

  useEffect(() => {
    if (status === "completed") setShowMap(true);
  }, [status]);

  // Definition-of-done: a real timeout/error state instead of an infinite
  // "AWAITING ML..." spinner if the backend stalls before its first tick.
  const [stallError, setStallError] = useState("");
  useEffect(() => {
    setStallError("");
    if (!awaitingData) return undefined;
    const t = window.setTimeout(() => {
      setStallError("The simulation hasn't produced its first result after 30s — the backend may be overloaded or stalled.");
    }, 30000);
    return () => window.clearTimeout(t);
  }, [awaitingData, runId]);

  const editCard = useCallback(async (body) => {
    const next = await overrideSimulation(body);
    setSim(next);
  }, [setSim]);

  const onPause = useCallback(() => pauseSimulation().then(setSim), [setSim]);
  const onResume = useCallback(() => {
    sessionStorage.removeItem("flood_run_theater");
    setShowMap(true);
    resumeSimulation().then(setSim);
  }, [setSim]);
  const onReset = useCallback(() => {
    sessionStorage.removeItem("flood_run_theater");
    setShowMap(true);
    resetSimulation().then(setSim);
  }, [setSim]);
  const onForceDispatch = useCallback(() => forceDispatch().then(setSim), [setSim]);
  const onFullscreen = useCallback(() => {
    sessionStorage.setItem("flood_run_theater", "1");
    setShowMap(false);
  }, []);
  const onSelectPerson = useCallback((e) => setSelectedName(e?.citizen_name || null), []);
  const clearStall = useCallback(() => setStallError(""), []);

  async function sendSos() {
    setSosBusy(true);
    setSosError("");
    try {
      const age = sos.age === "" || sos.age == null ? null : Number(sos.age);
      const next = await sendSimulationSos({ ...sos, age: Number.isFinite(age) ? age : null, people: Math.max(1, Number(sos.people) || 1) });
      if (next?.available === false || !Array.isArray(next?.citizens)) {
        setSosError(next?.message || next?.detail || "SOS was not accepted by the backend.");
      } else {
        setSim(next);
      }
    } catch (err) {
      setSosError(err?.message || "SOS failed to send.");
    } finally {
      setSosBusy(false);
    }
  }

  function useMyLocation() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition((pos) => {
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      setSos((s) => ({ ...s, lat, lon }));
      const distKm = haversineKm(lat, lon, SCENARIO_CENTER.lat, SCENARIO_CENTER.lon);
      setSosRegionWarning(
        distKm > 60
          ? `This device's location is ~${Math.round(distKm)} km from the simulated region (${SCENARIO_CENTER.label}). The SOS pin will be geographically inconsistent with the map, route, and shelters — edit lat/lon to a point inside the scenario area, or proceed only if you intend a real-world test pin.`
          : ""
      );
    });
  }

  function onSosLatLon(field, rawValue) {
    const value = Number(rawValue);
    const next = { ...sos, [field]: value };
    setSos(next);
    const distKm = haversineKm(next.lat, next.lon, SCENARIO_CENTER.lat, SCENARIO_CENTER.lon);
    setSosRegionWarning(
      distKm > 60
        ? `This point is ~${Math.round(distKm)} km from the simulated region (${SCENARIO_CENTER.label}) — the SOS pin will not line up with the map, route, or shelters.`
        : ""
    );
  }

  const onVoiceDraft = useCallback((d) => {
    setSos((prev) => ({
      ...prev,
      citizen_name: d.citizen_name || prev.citizen_name,
      people: d.people ?? prev.people,
      lat: d.lat ?? prev.lat,
      lon: d.lon ?? prev.lon,
      water_level_note: d.water_level_note || prev.water_level_note,
    }));
  }, []);
  const onVoiceSubmitted = useCallback((next) => {
    setSim(next);
    setVoiceOpen(false);
  }, [setSim]);
  const onVoiceClose = useCallback(() => setVoiceOpen(false), []);

  const wantTheater = typeof sessionStorage !== "undefined" && sessionStorage.getItem("flood_run_theater") === "1" && !showMap;
  const theater = wantTheater && status !== "completed" && status !== "paused" && status !== "idle";

  if (theater) {
    return (
      <div className="page">
        <TheaterView
          onWatchMap={() => {
            sessionStorage.removeItem("flood_run_theater");
            setShowMap(true);
          }}
          onPause={() => {
            sessionStorage.removeItem("flood_run_theater");
            setShowMap(true);
            pauseSimulation().then(setSim);
          }}
        />
      </div>
    );
  }

  return (
    <div className="page sim-execution">
      <ExplainController feats={feats} />
      <StatusHeader runMeta={runMeta} />
      <ProblemBanner stallError={stallError} onClear={clearStall} onReset={onReset} />

      <div className="hero-status-head">
        <h2>PRIMARY FLOOD STATUS</h2>
        <span className="hint">The four numbers that matter most, first — everything below is supporting detail.</span>
      </div>
      <PrimaryKpis />
      <InputsPanel />
      <div className="actions">
        {status === "running" ? (
          <button className="primary" onClick={onFullscreen}>
            Full-screen running view
          </button>
        ) : null}
        <button onClick={onPause}>Pause</button>
        <button onClick={onResume}>Resume</button>
        <button className="danger" onClick={onReset}>Reset</button>
        <button onClick={() => downloadSimReport().catch((e) => window.alert(e.message))}>Download after-action PDF</button>
      </div>
      <div className="hero-status-head">
        <h2>OPERATOR OVERRIDE</h2>
        <span className="hint">Edit a card to write a new value into the running simulation (what-if testing) — not a second live reading.</span>
      </div>
      <OverrideKpis onEdit={editCard} />
      <MlLayerPanel />
      <LazyMount minHeight={220}>
        <Suspense fallback={<div className="panel" style={{ minHeight: 220 }} />}>
          <ModelBenchmarkPanel />
        </Suspense>
      </LazyMount>
      <CardMonitorPanel />
      <div className="grid-2">
        <div className="panel">
          <h2>SIMULATION MAP</h2>
          <LazyMount minHeight={520}>
            <MapSection
              feats={feats}
              replayTick={replayTick}
              selectedName={selectedName}
              onSelectPerson={onSelectPerson}
              arenaPaths={feats.algorithm_arena ? arenaPaths : null}
              focusDam={runMeta?.dam}
            />
          </LazyMount>
          <NearestDamPanel focusDam={runMeta?.dam} />
        </div>
        <div className="panel">
          <h2>FLOOD DYNAMICS — LIVE</h2>
          <LazyMount minHeight={220}>
            <HistorySection />
          </LazyMount>
          <h3 style={{ marginTop: 12 }}>TIMELINE · SIMULATION TIME</h3>
          <TimelineSection />
        </div>
      </div>
      {feats.run_replay ? <ReplayPanel replayTick={replayTick} onReplayTick={setReplayTick} /> : null}
      {feats.model_disagreement ? <CrossCheckPanel onForceDispatch={onForceDispatch} /> : null}
      <div className="grid-2">
        {feats.explainable_ai ? <ExplainPanel showCounterfactual={feats.counterfactual} /> : <div />}
        <ClustersPanel vulnerableFirst={feats.vulnerable_first} />
      </div>
      {feats.counterfactual && !feats.explainable_ai ? <CounterfactualPanel /> : null}
      {/* Live rescue operation — map, event feed and the SOS roster. It reads
          the same store-backed `sim`, so it adds no second poller. */}
      <RescueSection />
      {/* The per-person contact log is merged into the Live SOS roster
          (expandable row details) — no separate copy. */}
      <div className="panel">
        <h2>ADD ANOTHER SOS</h2>
        <p className="hint">
          Extra caller joins the same queue. Radio uses their name. Or talk live to the Voice Agent.
          {" "}Scenario region: <b>{SCENARIO_CENTER.label}</b>.
        </p>
        <div className="form-grid">
          <label>Citizen name<input value={sos.citizen_name} onChange={(e) => setSos({ ...sos, citizen_name: e.target.value })} /></label>
          <label>Age<input type="number" min="0" max="120" value={sos.age ?? ""} onChange={(e) => setSos({ ...sos, age: e.target.value })} /></label>
          <label>People<input type="number" value={sos.people} onChange={(e) => setSos({ ...sos, people: Number(e.target.value) })} /></label>
          <label>Latitude<input type="number" step="0.0001" value={sos.lat} onChange={(e) => onSosLatLon("lat", e.target.value)} /></label>
          <label>Longitude<input type="number" step="0.0001" value={sos.lon} onChange={(e) => onSosLatLon("lon", e.target.value)} /></label>
          <label>Rainwater around them<input value={sos.water_level_note} onChange={(e) => setSos({ ...sos, water_level_note: e.target.value })} /></label>
        </div>
        {sosRegionWarning ? <div className="error-banner" role="alert"><p>{sosRegionWarning}</p></div> : null}
        {sosError ? <div className="error-banner" role="alert"><p>{sosError}</p></div> : null}
        <div className="actions" style={{ marginTop: 10 }}>
          <button type="button" onClick={useMyLocation}>Use my location</button>
          <button type="button" className="primary voice-sos-btn" onClick={() => setVoiceOpen(true)}>English Voice Agent</button>
          <button className="danger" type="button" disabled={sosBusy} onClick={sendSos}>{sosBusy ? "SENDING SOS…" : "SEND SOS"}</button>
        </div>
      </div>
      <VoiceSosAgent open={voiceOpen} onClose={onVoiceClose} onDraft={onVoiceDraft} onSubmitted={onVoiceSubmitted} />
      {feats.algorithm_arena ? <ArenaSection onMapPaths={setArenaPaths} /> : null}
      <div id="ieee-hqrl-panel" className="sim-hqrl-anchor">
        <HqrlSection runKey={runMeta?.runId} />
      </div>
      <div className="grid-2">
        <div className="panel">
          <h2>SIMULATION AGENTS</h2>
          <AgentsSection />
        </div>
        <ResultsPanel />
      </div>
      {feats.agent_talk ? <AgentTalkSection /> : null}
      <LazyMount minHeight={200}>
        <Suspense fallback={<div className="panel" style={{ minHeight: 200 }} />}>
          <DemoRunsSection feats={feats} />
        </Suspense>
      </LazyMount>
    </div>
  );
}

/* ------------------------------------------------------------------------ */
/* Sections — each subscribes to its own slice of the store.                  */
/* ------------------------------------------------------------------------ */

function TheaterView({ onWatchMap, onPause }) {
  const { sim, progress } = useSim((s) => ({ sim: s.sim, progress: s.progress }));
  return <ScenarioRunTheater sim={sim} progress={progress || sim?.progress} onWatchMap={onWatchMap} onPause={onPause} />;
}

const StatusHeader = memo(function StatusHeader({ runMeta }) {
  const { status, scenario, simTime, progress, modelId } = useSim(({ sim, progress }) => ({
    status: runStatusOf(sim),
    scenario: sim?.scenario,
    simTime: sim?.sim_time_sec,
    progress,
    modelId: sim?.pipeline?.prediction?.model_id,
  }));
  const scenarioTitle = runMeta?.title || String(scenario || "").replaceAll("_", " ");
  return (
    <div className="status-row">
      <h2 style={{ margin: 0 }}>2 · SCENARIO OUTPUT</h2>
      {scenarioTitle ? <span className="badge live">{String(scenarioTitle).toUpperCase()}</span> : null}
      <span className="badge">Status: {status || "loading"}</span>
      <span className="badge">Time: {simTime ?? 0}s</span>
      {status === "running" ? <span className="badge live">{prettyRunning(progress, modelId)}</span> : null}
    </div>
  );
});

const ProblemBanner = memo(function ProblemBanner({ stallError, onClear, onReset }) {
  const store = useSimStore();
  const connIssue = useSim((s) => s.connIssue);
  if (!stallError && !connIssue) return null;
  return (
    <div className="error-banner" role="alert">
      <p>{stallError || "Connection issue"}</p>
      {connIssue ? <p>{connIssue}</p> : null}
      <button
        type="button"
        className="primary"
        onClick={() => {
          onClear();
          store.setConnIssue("");
          store.refresh();
        }}
      >
        Retry now
      </button>
      <button
        type="button"
        className="danger"
        onClick={() => {
          onClear();
          store.setConnIssue("");
          onReset();
        }}
      >
        Reset simulation
      </button>
    </div>
  );
});

/* Canonical values (backend SimulationEngine.current_view()): every card that
 * shows the current flood probability / peak / run status reads sim.current,
 * so two cards can never disagree. Fallbacks only cover payloads without it. */
function runStatusOf(sim) {
  return sim?.current?.run_status ?? sim?.status;
}
function currentProbOf(sim) {
  const c = sim?.current;
  if (c && "flood_probability" in c) return c.flood_probability ?? null;
  return lastOf(sim?.history)?.flood_probability ?? sim?.pipeline?.prediction?.flood_probability ?? null;
}
function dualOf(sim) {
  return sim?.current?.dual || sim?.pipeline?.prediction?.dual;
}

function lastOf(arr) {
  return arr && arr.length ? arr[arr.length - 1] : null;
}

const PrimaryKpis = memo(function PrimaryKpis() {
  const { last, v2, pred, policy, status, primaryProb, peakLevel } = useSim(({ sim }) => ({
    last: lastOf(sim?.history),
    v2: sim?.pipeline?.prediction?.v2,
    pred: sim?.pipeline?.prediction,
    policy: sim?.pipeline?.policy,
    status: runStatusOf(sim),
    primaryProb: currentProbOf(sim),
    peakLevel: sim?.current?.predicted_peak_flood_level_m ?? sim?.pipeline?.prediction?.v2?.predicted_peak_flood_level_m ?? null,
  }));
  const l = last || {};
  const v = v2 || {};
  const awaitingData = status === "running" && !last;
  return (
    <div className="grid-4 hero-status-grid">
      <KpiCard
        label="Peak Flood Level"
        value={peakLevel}
        suffix=" m"
        sub={v.available ? `${v.stage1_model || "LightGBM V3"} model` : "Waiting for simulation"}
        loading={awaitingData}
      />
      <KpiCard
        label="Flood Probability"
        value={primaryProb != null ? `${(primaryProb * 100).toFixed(1)}%` : null}
        sub={status ? "hybrid ML + physics" : "Waiting for simulation"}
        loading={awaitingData}
      />
      <KpiCard
        label="Severity"
        value={v.available ? v.alert_level : (l.risk_category || pred?.risk_category)}
        sub={v.available ? "CatBoost alert model" : "Waiting for simulation"}
        loading={awaitingData}
      />
      <KpiCard
        label="Recommended Action"
        value={policy?.action || l.action}
        sub={policy?.reason ? String(policy.reason).slice(0, 60) : "Policy engine"}
        loading={awaitingData}
      />
    </div>
  );
});

const InputsPanel = memo(function InputsPanel() {
  const s = useSim(({ sim }) => {
    const l = lastOf(sim?.history) || {};
    return {
      story: sim?.story,
      scenario: Boolean(sim?.scenario),
      rain: l.rainfall_mm != null || sim?.pipeline?.weather?.rainfall_mm != null,
      river: l.river_m != null || sim?.pipeline?.river?.value_m != null,
      model: currentProbOf(sim) != null,
      sos: (sim?.citizens || []).length > 0,
    };
  });
  const steps = [
    { label: "Scenario", done: s.scenario },
    { label: "Rainfall", done: s.rain },
    { label: "River / dam", done: s.river },
    { label: "Model", done: s.model },
    { label: "SOS / dispatch", done: s.sos },
  ];
  return (
    <div className="panel">
      <h2>SIMULATION INPUTS — THIS RUN ONLY</h2>
      <p className="hint">
        {s.story || "Rainfall, river water and dam water fed into this scenario. Synthetic simulation input, not live sensor data."}
        {" "}<b>Scenario region: {SCENARIO_CENTER.label}.</b>
      </p>
      <div className="process-steps">
        {steps.map((st) => (
          <span key={st.label} className={`stage ${st.done ? "done" : ""}`}>{st.label}</span>
        ))}
      </div>
    </div>
  );
});

const OverrideKpis = memo(function OverrideKpis({ onEdit }) {
  const { last, status, prob } = useSim(({ sim }) => ({ last: lastOf(sim?.history), status: runStatusOf(sim), prob: currentProbOf(sim) }));
  const l = last || {};
  const awaitingData = status === "running" && !last;
  const onRain = useCallback((n) => onEdit({ rainfall_mm: n }), [onEdit]);
  const onRiver = useCallback((n) => onEdit({ river_m: n }), [onEdit]);
  const onDam = useCallback((n) => onEdit({ dam_m: n }), [onEdit]);
  const onProb = useCallback((n) => onEdit({ flood_probability: n }), [onEdit]);
  return (
    <div className="grid-4">
      <KpiCard label="Current Rainfall" value={l.rainfall_mm != null ? l.rainfall_mm.toFixed(1) : null} suffix=" mm" editable numericValue={l.rainfall_mm} onCommit={onRain} loading={awaitingData} />
      <KpiCard label="River Water Level" value={l.river_m != null ? l.river_m.toFixed(2) : null} suffix=" m" editable numericValue={l.river_m} onCommit={onRiver} loading={awaitingData} />
      <KpiCard label="Dam Water Level" value={l.dam_m != null ? l.dam_m.toFixed(2) : null} suffix=" m" editable numericValue={l.dam_m} onCommit={onDam} loading={awaitingData} />
      <KpiCard
        label="Flood Probability"
        value={prob != null ? `${(prob * 100).toFixed(1)}%` : null}
        sub={l.risk_category || "Edit as percent, e.g. 20"}
        editable
        numericValue={prob != null ? prob * 100 : ""}
        onCommit={onProb}
        loading={awaitingData}
      />
    </div>
  );
});

const MlLayerPanel = memo(function MlLayerPanel() {
  const v2 = useSim(({ sim }) => sim?.pipeline?.prediction?.v2) || {};
  return (
    <div className="panel layer-ml">
      <h2>ML PREDICTION — LAYER 1 OF 2</h2>
      <p className="hint">The trained model's own output, before physics/policy blending. See ALGORITHM ARENA below for the physics-twin comparison and final decision layer.</p>
      {v2.available ? (
        <>
          <div className="metric"><span>Predicted peak level</span><b>{v2.predicted_peak_flood_level_m} m</b></div>
          <div className="metric"><span>Severe-flood probability</span><b>{pct(v2.flood_type_probability)}</b></div>
          <div className="metric"><span>Alert level</span><b>{v2.alert_level || "n/a"}</b></div>
          <div className="metric"><span>Models</span><b>{v2.stage1_model || "n/a"} → {v2.stage2_model || "n/a"}</b></div>
        </>
      ) : (
        <p className="hint">{v2.message || "Waiting for simulation — V2 prediction not yet available."}</p>
      )}
    </div>
  );
});

const CardMonitorPanel = memo(function CardMonitorPanel() {
  const monitor = useSim(({ sim }) => sim?.pipeline?.card_monitor);
  if (!monitor?.sudden) return null;
  return (
    <div className="panel">
      <h2>CARD MONITOR (Isolation Forest + sudden-change)</h2>
      <div className="metric"><span>Seconds since last sample</span><b>{monitor.seconds_since_last} s</b></div>
      {(monitor.alerts || []).map((a, i) => (
        <div className="metric" key={i}><span>{a.label} went {a.direction}</span><b>{a.from_value} → {a.to_value} in {a.seconds}s</b></div>
      ))}
    </div>
  );
});

/** Live: the canonical current probability. Replay: the saved tick's value. */
function viewProbability(sim, replayTick) {
  const row = replayTick != null ? (sim?.history || [])[replayTick] : null;
  if (row && row.flood_probability != null) return row.flood_probability;
  return currentProbOf(sim);
}

const MapSection = memo(function MapSection({ feats, replayTick, selectedName, onSelectPerson, arenaPaths, focusDam }) {
  const { pipeline, citizens, teamPaths, beforeP, afterP, viewP } = useSim(({ sim }) => ({
    pipeline: sim?.pipeline,
    citizens: sim?.citizens,
    teamPaths: sim?.team_paths,
    beforeP: sim?.before_flood_p,
    afterP: sim?.after_flood_p,
    viewP: viewProbability(sim, replayTick),
  }));
  // The stage-machine fields (ops_status …) are read by FloodMap itself, so
  // the person objects are passed through untouched and keep their identity.
  const snapshot = useMemo(
    () => ({ ...(pipeline || {}), emergencies: citizens?.length ? citizens : pipeline?.emergencies || EMPTY }),
    [pipeline, citizens]
  );
  const selectedPerson = useMemo(
    () => (selectedName ? (snapshot.emergencies || EMPTY).find((e) => e.citizen_name === selectedName) || null : null),
    [snapshot.emergencies, selectedName]
  );
  return (
    <>
      <FloodMap
        snapshot={snapshot}
        floodProbability={viewP}
        mapFeatures={feats}
        teamPaths={teamPaths || EMPTY}
        beforeP={beforeP}
        afterP={afterP ?? viewP}
        selectedPerson={selectedPerson}
        onSelectPerson={onSelectPerson}
        arenaPaths={arenaPaths}
        focusDam={focusDam}
      />
      {feats.person_card && selectedPerson ? (
        <div className="person-card">
          <h3>PERSON CARD</h3>
          <div className="metric"><span>Name</span><b>{selectedPerson.citizen_name}</b></div>
          <div className="metric"><span>Age</span><b>{selectedPerson.age ?? "—"}</b></div>
          <div className="metric"><span>Water</span><b>{selectedPerson.water_level_note || "—"}</b></div>
          <div className="metric"><span>Status</span><b>{selectedPerson.ops_status || selectedPerson.live_status || selectedPerson.status || "—"}</b></div>
          <div className="metric"><span>Team</span><b>{selectedPerson.assigned_team_name || selectedPerson.assigned_team || "—"}</b></div>
          <div className="metric"><span>Triage</span><b>{selectedPerson.triage || selectedPerson.vulnerability || "—"}</b></div>
          <div className="metric"><span>GPS</span><b>{selectedPerson.lat}, {selectedPerson.lon}</b></div>
        </div>
      ) : null}
    </>
  );
});

function HistorySection() {
  const history = useSim(({ sim }) => sim?.history);
  return <HistoryChart history={history || EMPTY} />;
}

const TimelineRow = memo(function TimelineRow({ at, message, count }) {
  return (
    <div>
      <b>{formatSimClock(at)}</b> {message}
      {count > 1 ? <b className="feed-count"> ×{count}</b> : null}
    </div>
  );
});

const eventKey = (e) => e?.message;

function TimelineSection() {
  const events = useSim(({ sim }) => sim?.events);
  const rows = useMemo(() => collapseFeed(events || EMPTY, { key: eventKey, cap: 50 }), [events]);
  return (
    <div className="timeline">
      {rows.map((r) => (
        <TimelineRow key={`${r.first.sim_time_sec}-${r.key}`} at={r.last.sim_time_sec} message={r.key} count={r.count} />
      ))}
      {!rows.length ? <div className="muted">No simulation events yet. Start a scenario.</div> : null}
    </div>
  );
}

const ReplayPanel = memo(function ReplayPanel({ replayTick, onReplayTick }) {
  const { len, row, viewP } = useSim(({ sim }) => {
    const h = sim?.history || EMPTY;
    return {
      len: h.length,
      row: (replayTick != null ? h[replayTick] : null) || lastOf(h),
      viewP: viewProbability(sim, replayTick),
    };
  });
  if (len <= 1) return null;
  const r = row || {};
  return (
    <div className="panel">
      <h2>RUN REPLAY</h2>
      <p className="hint">Drag to any tick. Flood circle and probability follow the saved timeline. SOS pins stay on the map.</p>
      <div className="replay-row">
        <input type="range" min={0} max={len - 1} value={replayTick == null ? len - 1 : replayTick} onChange={(e) => onReplayTick(Number(e.target.value))} />
        <div className="metric">
          <span>Tick {r.tick ?? replayTick ?? len - 1} · {formatSimClock(r.sim_time_sec)}</span>
          <b>{viewP != null ? `${(viewP * 100).toFixed(1)}%` : "n/a"} · rain {r.rainfall_mm != null ? r.rainfall_mm.toFixed(1) : "n/a"} mm</b>
        </div>
      </div>
    </div>
  );
});

const CrossCheckPanel = memo(function CrossCheckPanel({ onForceDispatch }) {
  const { dual, override } = useSim(({ sim }) => ({ dual: dualOf(sim), override: sim?.human_dispatch_override }));
  const d = dual || {};
  return (
    <div className="panel">
      <h2>V1 SAFETY CROSS-CHECK — RANDOM FOREST vs XGBOOST</h2>
      <p className="hint">
        Independent auto-dispatch gate using the older v1 models, kept as a disagreement check.
        Production predictions above use V3 (LightGBM → CatBoost).
      </p>
      {!d.available ? <p className="hint">Both models load with the first tick.</p> : (
        <>
          <div className="metric"><span>Random Forest</span><b>{pct(d.random_forest)}</b></div>
          <div className="metric"><span>XGBoost</span><b>{pct(d.xgboost)}</b></div>
          <div className="metric"><span>Gap</span><b>{d.gap != null ? `${(d.gap * 100).toFixed(1)} pts` : "n/a"}</b></div>
          <p className={d.disagree ? "counterfactual" : "hint"}>{d.message}</p>
          {d.disagree && !override ? (
            <button className="primary" type="button" onClick={onForceDispatch}>Operator override — allow dispatch</button>
          ) : null}
          {override ? <p className="hint">Operator override is ON. Auto-dispatch is allowed.</p> : null}
        </>
      )}
    </div>
  );
});

/* ---------------------------- explainable AI ----------------------------- */

/** Runs explain-v2 only when the rain value it depends on actually changes
 * (debounced), never on every history tick. Results go into the store so the
 * XAI panel, the counterfactual panel and DemoRunPanels share one request. */
function ExplainController({ feats }) {
  const store = useSimStore();
  const rain = useSim(({ sim }) => {
    const v = lastOf(sim?.history)?.rainfall_mm;
    return v == null ? null : Math.round(v * 10) / 10;
  });
  const wanted = Boolean(feats.explainable_ai || feats.counterfactual);
  const [nonce, setNonce] = useState(0);
  const lastKey = useRef("");

  useEffect(() => {
    store.retryExplain = () => {
      lastKey.current = "";
      setNonce((n) => n + 1);
    };
    return () => {
      store.retryExplain = () => {};
    };
  }, [store]);

  useEffect(() => {
    if (rain == null || !wanted) return undefined;
    const key = `${rain}`;
    if (key === lastKey.current) return undefined;
    let alive = true;
    const t = window.setTimeout(() => {
      lastKey.current = key;
      store.setExplain({ loading: true, error: null });
      fetchMlExplainV2(rain)
        .then((res) => {
          if (!alive) return;
          if (res?.available === false && res?.message) store.setExplain({ data: null, error: res.message, loading: false });
          else store.setExplain({ data: res, error: null, loading: false });
        })
        .catch((err) => {
          if (alive) store.setExplain({ error: err?.message || "Explanation service did not return a result.", loading: false });
        });
    }, EXPLAIN_DEBOUNCE_MS);
    return () => {
      alive = false;
      window.clearTimeout(t);
    };
  }, [rain, wanted, nonce, store]);
  return null;
}

const ExplainPanel = memo(function ExplainPanel({ showCounterfactual }) {
  const store = useSimStore();
  const { explain, stage1 } = useSim((s) => ({ explain: s.explain, stage1: s.sim?.pipeline?.prediction?.v2?.stage1_model }));
  const onRetry = useCallback(() => store.retryExplain?.(), [store]);
  const ex = explain || {};
  return (
    <div className="panel">
      <h2>EXPLAINABLE AI — WHY {(stage1 || "LightGBM V3").toUpperCase()} SCORED THIS</h2>
      {/* Keep the previous explanation on screen while a refresh is in flight. */}
      <ShapBars explain={ex.data} loading={Boolean(ex.loading && !ex.data)} error={ex.error} onRetry={onRetry} showCounterfactual={showCounterfactual} />
    </div>
  );
});

const CounterfactualPanel = memo(function CounterfactualPanel() {
  const message = useSim((s) => s.explain?.data?.counterfactual?.message);
  if (!message) return null;
  return (
    <div className="panel">
      <h2>COUNTERFACTUAL RAIN</h2>
      <p className="counterfactual">{message}</p>
    </div>
  );
});

const ClustersPanel = memo(function ClustersPanel({ vulnerableFirst }) {
  const clusters = useSim(({ sim }) => sim?.pipeline?.clusters) || EMPTY;
  return (
    <div className="panel">
      <h2>K-MEANS TEAMS {vulnerableFirst ? "· VULNERABLE-FIRST ORDER" : ""}</h2>
      {clusters.length ? clusters.map((c) => (
        <div key={c.cluster_id}>
          <div className="metric">
            <span>{c.cluster_id} · {c.sos_count} SOS</span>
            <b>{c.assigned_team_name || c.assigned_team || "unassigned"}</b>
          </div>
          {vulnerableFirst && (c.priority_queue || []).length ? (
            <p className="hint">In cluster: {(c.priority_queue || []).map((p, i) => `${i + 1}. ${p.citizen_name} (${p.vulnerability})`).join(" → ")}</p>
          ) : null}
        </div>
      )) : <div className="hint">Clusters appear after the SOS queue is ingested.</div>}
    </div>
  );
});

/** Algorithm Arena runs once per run input: new run id, first model tick,
 * blocked-road set change, and completion — never on a timer. */
function ArenaSection({ onMapPaths }) {
  const runKey = useSim(({ sim }) =>
    [
      sim?.run_id || "",
      sim?.pipeline?.prediction ? "tick" : "no-tick",
      (sim?.blocked_roads || EMPTY).map((r) => r.road_id).join(","),
      sim?.status === "completed" ? "done" : "",
    ].join("|")
  );
  return <AlgorithmArena enabled onMapPaths={onMapPaths} runKey={runKey} />;
}

function RescueSection() {
  const sim = useSim((s) => s.sim);
  return <RescueOpsPanel sim={sim} />;
}

/* HQRL: narrowed props only (run key, the params it derives its planner
 * config from, and the SOS count) — the 1 s store commits do not reach it. */
function HqrlSection({ runKey }) {
  const { runId, params, citizensCount } = useSim(({ sim }) => ({
    runId: sim?.run_id,
    params: sim?.params,
    citizensCount: (sim?.citizens || EMPTY).length,
  }));
  const [visible, setVisible] = useState(true);
  return (
    <LazyMount minHeight={640} onVisibleChange={setVisible}>
      <Suspense fallback={<div className="panel" style={{ minHeight: 640 }} />}>
        <IeeeHqrlEmbed runId={runKey || runId} params={params} citizensCount={citizensCount} active={visible} />
      </Suspense>
    </LazyMount>
  );
}

function AgentsSection() {
  const { agents, status } = useSim(({ sim }) => ({ agents: sim?.pipeline?.agents, status: runStatusOf(sim) }));
  return <AgentList agents={agents || EMPTY} runStatus={status} />;
}

const ResultsPanel = memo(function ResultsPanel() {
  const { status, after, prob, peak } = useSim(({ sim }) => ({
    status: runStatusOf(sim),
    after: sim?.after,
    prob: currentProbOf(sim),
    peak: sim?.current?.peak_flood_probability ?? null,
  }));
  const a = after || {};
  const cmp = a.optimization_comparison || {};
  return (
    <div className="panel">
      <h2>RESULTS</h2>
      {status !== "completed" && prob == null ? <div className="muted">Results appear after ticks produce pipeline output.</div> : (
        <>
          <div className="metric"><span>{status === "completed" ? "Final flood probability" : "Current flood probability"}</span><b>{fmtP(prob)}</b></div>
          <div className="metric"><span>Peak flood probability (this run)</span><b>{fmtP(peak)}</b></div>
          <div className="metric"><span>Peak risk</span><b>{a.peak_risk || "DATA UNAVAILABLE"}</b></div>
          <div className="metric"><span>Affected population</span><b>{a.affected_population ?? "DATA UNAVAILABLE"}</b></div>
          <div className="metric"><span>Recommended shelter</span><b>{a.shelters?.[0]?.shelter_id || "DATA UNAVAILABLE"}</b></div>
          <div className="metric"><span>Recommended route</span><b>{a.routes?.[0]?.label || "DATA UNAVAILABLE"}</b></div>
          <div className="metric"><span>Evacuation time</span><b>{a.optimization?.evacuation_time_min ?? "DATA UNAVAILABLE"} min</b></div>
          <div className="metric"><span>Risk exposure</span><b>{a.optimization?.risk_exposure ?? "DATA UNAVAILABLE"}</b></div>
          <div className="metric"><span>Shelter utilization</span><b>{a.optimization?.shelter_utilization ?? "DATA UNAVAILABLE"}</b></div>
          <div className="metric"><span>Optimization method</span><b>{a.optimization?.method || "DATA UNAVAILABLE"}</b></div>
          <div className="metric"><span>Decision latency</span><b>{a.decision_latency_ms ?? "DATA UNAVAILABLE"} ms</b></div>
          <h3>BEFORE vs AFTER OPTIMIZATION</h3>
          {cmp.label ? <p className={cmp.status === "rejected" ? "counterfactual" : "hint"}>{cmp.label}</p> : null}
          <div className="metric"><span>Before cost (baseline)</span><b>{cmp.before_cost ?? "DATA UNAVAILABLE"}</b></div>
          <div className="metric"><span>After cost (latest plan)</span><b>{cmp.after_cost ?? "DATA UNAVAILABLE"}</b></div>
        </>
      )}
    </div>
  );
});

/** Agent conversation, grounded: the numbers shown beside it come from the
 * current simulation state, not from the generated text. */
function AgentTalkSection() {
  const store = useSimStore();
  const g = useSim(({ sim }) => {
    const l = lastOf(sim?.history) || {};
    const pred = sim?.pipeline?.prediction;
    const dual = dualOf(sim);
    return {
      conversation: sim?.conversation || sim?.pipeline?.conversation,
      probability: currentProbOf(sim),
      river_m: l.river_m ?? null,
      rainfall_mm: l.rainfall_mm ?? null,
      sim_time_sec: sim?.sim_time_sec ?? null,
      status: runStatusOf(sim),
      rf: dual?.random_forest ?? null,
      xgb: dual?.xgboost ?? null,
      severe: pred?.v2?.flood_type_probability ?? null,
    };
  });
  const grounding = useMemo(
    () => ({
      probability: g.probability,
      river_m: g.river_m,
      rainfall_mm: g.rainfall_mm,
      sim_time_sec: g.sim_time_sec,
      status: g.status,
      extraProbabilities: [g.rf, g.xgb, g.severe].filter((v) => v != null),
    }),
    [g.probability, g.river_m, g.rainfall_mm, g.sim_time_sec, g.status, g.rf, g.xgb, g.severe]
  );
  const onTalked = useCallback(
    (res) => {
      if (res?.conversation) store.setSim((prev) => ({ ...prev, conversation: res.conversation, contact_log: res.contact_log || prev?.contact_log }));
    },
    [store]
  );
  return (
    <LazyMount minHeight={320}>
      <Suspense fallback={<div className="panel" style={{ minHeight: 320 }} />}>
        <AgentTalk conversation={g.conversation} title="SIMULATION AGENT CONVERSATION" voiceEnabled={false} onTalked={onTalked} grounding={grounding} />
      </Suspense>
    </LazyMount>
  );
}

function DemoRunsSection({ feats }) {
  const store = useSimStore();
  const { sim, explain } = useSim((s) => ({ sim: s.sim, explain: s.explain?.data }));
  return <DemoRunPanels sim={sim} feats={feats} explain={explain} setSim={store.setSim} />;
}

/* ------------------------------------------------------------------------ */

// Matches FloodMap's default center and backend/services/seed.py ZONES — the
// scenario's one operational area. Used to flag SOS points that would render
// geographically inconsistent with the map/route/shelters.
const SCENARIO_CENTER = { lat: 28.6139, lon: 77.209, label: "Delhi NCR — Yamuna floodplain" };

function haversineKm(lat1, lon1, lat2, lon2) {
  if ([lat1, lon1, lat2, lon2].some((v) => v == null || Number.isNaN(v))) return 0;
  const R = 6371;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function pct(p) {
  return p == null ? "n/a" : `${(p * 100).toFixed(1)}%`;
}

function prettyRunning(progress, modelId) {
  const name = progress?.model_name || (String(modelId || "").includes("random_forest") ? "Random Forest" : "ML");
  return `${name} running`;
}

function fmtP(p) {
  return p == null ? "DATA UNAVAILABLE" : `${(p * 100).toFixed(1)}%`;
}

function formatSimClock(sec) {
  const s = Math.round(sec || 0);
  const m = String(Math.floor(s / 60)).padStart(2, "0");
  const r = String(s % 60).padStart(2, "0");
  return `${m}:${r}`;
}
