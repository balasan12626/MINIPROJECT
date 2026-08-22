import { useEffect, useState } from "react";
import { fetchSimState, pauseSimulation, resumeSimulation, resetSimulation, overrideSimulation, sendSimulationSos, fetchMlExplain, downloadSimReport, forceDispatch } from "../../services/api.js";
import { connectSocket } from "../../services/ws.js";
import { useLivePipeline } from "../../hooks/useLivePipeline.js";
import FloodMap from "../../maps/FloodMap.jsx";
import AgentList from "../../components/AgentList.jsx";
import AgentTalk from "../../components/AgentTalk.jsx";
import ScenarioRunTheater from "../../components/ScenarioRunTheater.jsx";
import ShapBars from "../../components/ShapBars.jsx";
import { DEFAULT_FEATURES } from "../../components/FeatureToggles.jsx";
import DemoRunPanels from "../../components/DemoRunPanels.jsx";
import KpiCard from "../../components/KpiCard.jsx";
import HistoryChart from "../../charts/HistoryChart.jsx";
import PdfDownloadButton from "../../components/PdfDownloadButton.jsx";
import AlgorithmArena from "../../components/AlgorithmArena.jsx";
import VoiceSosAgent from "../../components/VoiceSosAgent.jsx";

export default function SimulationExecution({ runMeta = null }) {
  const [sim, setSim] = useState(null);
  const [progress, setProgress] = useState(null);
  const [sos, setSos] = useState({ citizen_name: "Priya Sharma", people: 2, lat: 28.651, lon: 77.262, water_level_note: "knee-deep rainwater" });
  const [sosBusy, setSosBusy] = useState(false);
  const [showMap, setShowMap] = useState(true);
  const [explain, setExplain] = useState(null);
  const [replayTick, setReplayTick] = useState(null);
  const [selectedPerson, setSelectedPerson] = useState(null);
  const [arenaPaths, setArenaPaths] = useState(null);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const { snapshot } = useLivePipeline(30000);

  useEffect(() => {
    let cancelled = false;
    let failStreak = 0;

    async function pull() {
      try {
        const d = await fetchSimState();
        if (cancelled) return;
        // Ignore soft network fallbacks so we don't wipe a good run
        if (d && d.available === false && d.message) {
          failStreak += 1;
          return;
        }
        failStreak = 0;
        setSim(d);
        if (d?.progress) setProgress(d.progress);
      } catch {
        failStreak += 1;
      }
    }

    pull();
    if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();

    const stop = connectSocket((ev) => {
      if (ev.type === "pipeline_progress" && ev.payload?.mode === "simulation") {
        setProgress(ev.payload);
      }
      if (ev.type === "agent_talk") {
        setSim((prev) => ({ ...(prev || {}), conversation: ev.payload }));
      }
      if (ev.type === "simulation_state" || ev.type === "simulation_event" || ev.type === "pipeline_progress") {
        pull();
      }
    });

    const id = setInterval(() => {
      // Back off polling during network flaps
      if (failStreak > 3 && failStreak % 3 !== 0) return;
      pull();
    }, 1200);

    return () => {
      cancelled = true;
      stop();
      clearInterval(id);
      if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
    };
  }, []);

  useEffect(() => {
    if (sim?.status === "completed") setShowMap(true);
  }, [sim?.status]);

  useEffect(() => {
    const rain = lastRain(sim);
    if (rain == null) return;
    if (!(sim?.features || DEFAULT_FEATURES).explainable_ai && !(sim?.features || DEFAULT_FEATURES).counterfactual) return;
    fetchMlExplain(rain).then(setExplain);
  }, [sim?.history?.length, sim?.status, sim?.features?.explainable_ai, sim?.features?.counterfactual]);

  async function editCard(body) {
    const next = await overrideSimulation(body);
    setSim(next);
  }

  async function sendSos() {
    setSosBusy(true);
    try {
      const next = await sendSimulationSos(sos);
      setSim(next);
    } finally {
      setSosBusy(false);
    }
  }

  function useMyLocation() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition((pos) => {
      setSos((s) => ({ ...s, lat: pos.coords.latitude, lon: pos.coords.longitude }));
    });
  }

  const last = (sim?.history || [])[(sim?.history || []).length - 1] || {};
  const after = sim?.after || {};
  const before = sim?.before || {};
  const feats = { ...DEFAULT_FEATURES, ...(sim?.features || runMeta?.features || {}) };
  const history = sim?.history || [];
  const replay = replayTick != null ? history[replayTick] || last : last;
  const viewP = replay.flood_probability != null ? replay.flood_probability : last.flood_probability;
  const dual = sim?.pipeline?.prediction?.dual || {};
  const wantTheater = typeof sessionStorage !== "undefined" && sessionStorage.getItem("flood_run_theater") === "1" && !showMap;
  const status = sim?.status;
  const theater = wantTheater && status !== "completed" && status !== "paused" && status !== "idle";
  const scenarioTitle = runMeta?.title || String(sim?.scenario || "").replaceAll("_", " ");
  const weather = sim?.pipeline?.weather || {};
  const river = sim?.pipeline?.river || {};
  const dam = sim?.pipeline?.dam || {};

  if (theater && sim?.status !== "completed") {
    return (
      <div className="page">
        <ScenarioRunTheater
          sim={sim}
          progress={progress || sim?.progress}
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
      <div className="status-row">
        <h2 style={{ margin: 0 }}>2 · SCENARIO OUTPUT</h2>
        {scenarioTitle ? <span className="badge live">{String(scenarioTitle).toUpperCase()}</span> : null}
        <span className="badge">Status: {sim?.status || "loading"}</span>
        <span className="badge">Time: {sim?.sim_time_sec ?? 0}s</span>
        {sim?.status === "running" ? <span className="badge live">{prettyRunning(progress, sim)}</span> : null}
      </div>
      <div className="panel">
        <h2>LIVE ENVIRONMENT — THIS RUN ONLY</h2>
        <p className="hint">{sim?.story || "Rainfall, river water, dam water and model score for the scenario you just ran."}</p>
        <div className="scenario-preview">
          <div className="metric"><span>Rainfall</span><b>{fmtNum(last.rainfall_mm ?? weather.rainfall_mm, "mm")}</b></div>
          <div className="metric"><span>River water</span><b>{fmtNum(last.river_m ?? river.value_m, "m")}</b></div>
          <div className="metric"><span>Dam water</span><b>{fmtNum(last.dam_m ?? dam.value_m, "m")}</b></div>
          <div className="metric"><span>Flood probability</span><b>{fmtP(last.flood_probability ?? sim?.pipeline?.prediction?.flood_probability)}</b></div>
          <div className="metric"><span>Risk</span><b>{last.risk_category || sim?.pipeline?.prediction?.risk_category || "—"}</b></div>
          <div className="metric"><span>Action</span><b>{last.action || sim?.pipeline?.policy?.action || "—"}</b></div>
        </div>
        <div className="process-steps">
          {[
            { label: "Scenario", done: Boolean(sim?.scenario) },
            { label: "Rainfall", done: last.rainfall_mm != null || weather.rainfall_mm != null },
            { label: "River / dam", done: last.river_m != null || river.value_m != null },
            { label: "Model", done: last.flood_probability != null || sim?.pipeline?.prediction?.flood_probability != null },
            { label: "SOS / dispatch", done: (sim?.citizens || []).length > 0 },
          ].map((s) => (
            <span key={s.label} className={`stage ${s.done ? "done" : ""}`}>{s.label}</span>
          ))}
        </div>
      </div>
      <div className="actions">
        {sim?.status === "running" ? (
          <button className="primary" onClick={() => { sessionStorage.setItem("flood_run_theater", "1"); setShowMap(false); }}>
            Full-screen running view
          </button>
        ) : null}
        <button onClick={() => pauseSimulation().then(setSim)}>Pause</button>
        <button onClick={() => {
          sessionStorage.removeItem("flood_run_theater");
          setShowMap(true);
          resumeSimulation().then(setSim);
        }}>Resume</button>
        <button className="danger" onClick={() => {
          sessionStorage.removeItem("flood_run_theater");
          setShowMap(true);
          resetSimulation().then(setSim);
        }}>Reset</button>
        <button onClick={() => downloadSimReport().catch((e) => window.alert(e.message))}>Download after-action PDF</button>
      </div>
      <div className="grid-4">
        <KpiCard
          label="Current Rainfall"
          value={last.rainfall_mm != null ? last.rainfall_mm.toFixed(1) : null}
          suffix=" mm"
          editable
          numericValue={last.rainfall_mm}
          onCommit={(n) => editCard({ rainfall_mm: n })}
        />
        <KpiCard
          label="River Water Level"
          value={last.river_m != null ? last.river_m.toFixed(2) : null}
          suffix=" m"
          editable
          numericValue={last.river_m}
          onCommit={(n) => editCard({ river_m: n })}
        />
        <KpiCard
          label="Dam Water Level"
          value={last.dam_m != null ? last.dam_m.toFixed(2) : null}
          suffix=" m"
          editable
          numericValue={last.dam_m}
          onCommit={(n) => editCard({ dam_m: n })}
        />
        <KpiCard
          label="Flood Probability"
          value={last.flood_probability != null ? `${(last.flood_probability * 100).toFixed(1)}%` : null}
          sub={last.risk_category || "Edit as percent, e.g. 20"}
          editable
          numericValue={last.flood_probability != null ? last.flood_probability * 100 : ""}
          onCommit={(n) => editCard({ flood_probability: n })}
        />
      </div>
      {(sim?.pipeline?.card_monitor?.sudden) ? (
        <div className="panel">
          <h2>CARD MONITOR (Isolation Forest + sudden-change)</h2>
          <div className="metric"><span>Seconds since last sample</span><b>{sim.pipeline.card_monitor.seconds_since_last} s</b></div>
          {(sim.pipeline.card_monitor.alerts || []).map((a, i) => (
            <div className="metric" key={i}><span>{a.label} went {a.direction}</span><b>{a.from_value} → {a.to_value} in {a.seconds}s</b></div>
          ))}
        </div>
      ) : null}
      <div className="grid-2">
        <div className="panel">
          <h2>SIMULATION MAP</h2>
          <FloodMap
            snapshot={{
              ...(sim?.pipeline || snapshot || {}),
              emergencies: (sim?.citizens?.length ? sim.citizens : (sim?.pipeline?.emergencies || snapshot?.emergencies || [])).map((e) => ({
                ...e,
                live_status: e.ops_status || e.live_status || e.status,
                pin_color: e.pin_color,
              })),
            }}
            floodProbability={viewP}
            mapFeatures={feats}
            teamPaths={sim?.team_paths || []}
            beforeP={sim?.before_flood_p}
            afterP={sim?.after_flood_p ?? viewP}
            selectedPerson={selectedPerson}
            onSelectPerson={setSelectedPerson}
            arenaPaths={feats.algorithm_arena ? arenaPaths : null}
            mode={`simulation-${viewP}-${replay.rainfall_mm}-${(sim?.citizens || []).length}-${replayTick}`}
          />
          {feats.person_card && selectedPerson ? (
            <div className="person-card">
              <h3>PERSON CARD</h3>
              <div className="metric"><span>Name</span><b>{selectedPerson.citizen_name}</b></div>
              <div className="metric"><span>Age</span><b>{selectedPerson.age ?? "—"}</b></div>
              <div className="metric"><span>Water</span><b>{selectedPerson.water_level_note || "—"}</b></div>
              <div className="metric"><span>Status</span><b>{selectedPerson.live_status || selectedPerson.status || "—"}</b></div>
              <div className="metric"><span>Team</span><b>{selectedPerson.assigned_team_name || selectedPerson.assigned_team || "—"}</b></div>
              <div className="metric"><span>Triage</span><b>{selectedPerson.triage || selectedPerson.vulnerability || "—"}</b></div>
              <div className="metric"><span>GPS</span><b>{selectedPerson.lat}, {selectedPerson.lon}</b></div>
            </div>
          ) : null}
        </div>
        <div className="panel">
          <h2>TIMELINE</h2>
          <HistoryChart history={sim?.history || []} />
          <div className="timeline">
            {(sim?.events || []).map((e, i) => (
              <div key={i}>
                <b>{formatSimClock(e.sim_time_sec)}</b> {e.message}
              </div>
            ))}
            {!sim?.events?.length ? <div className="muted">No simulation events yet. Start a scenario.</div> : null}
          </div>
        </div>
      </div>
      {feats.run_replay && history.length > 1 ? (
        <div className="panel">
          <h2>RUN REPLAY</h2>
          <p className="hint">Drag to any tick. Flood circle and probability follow the saved timeline. SOS pins stay on the map.</p>
          <div className="replay-row">
            <input
              type="range"
              min={0}
              max={history.length - 1}
              value={replayTick == null ? history.length - 1 : replayTick}
              onChange={(e) => setReplayTick(Number(e.target.value))}
            />
            <div className="metric">
              <span>Tick {replay.tick ?? replayTick ?? history.length - 1} · {formatSimClock(replay.sim_time_sec)}</span>
              <b>{viewP != null ? `${(viewP * 100).toFixed(1)}%` : "n/a"} · rain {replay.rainfall_mm != null ? replay.rainfall_mm.toFixed(1) : "n/a"} mm</b>
            </div>
          </div>
        </div>
      ) : null}
      {feats.model_disagreement ? (
        <div className="panel">
          <h2>RANDOM FOREST vs XGBOOST</h2>
          {!dual.available ? <p className="hint">Both models load with the first tick.</p> : (
            <>
              <div className="metric"><span>Random Forest</span><b>{pct(dual.random_forest)}</b></div>
              <div className="metric"><span>XGBoost</span><b>{pct(dual.xgboost)}</b></div>
              <div className="metric"><span>Gap</span><b>{dual.gap != null ? `${(dual.gap * 100).toFixed(1)} pts` : "n/a"}</b></div>
              <p className={dual.disagree ? "counterfactual" : "hint"}>{dual.message}</p>
              {dual.disagree && !sim?.human_dispatch_override ? (
                <button className="primary" type="button" onClick={() => forceDispatch().then(setSim)}>Operator override — allow dispatch</button>
              ) : null}
              {sim?.human_dispatch_override ? <p className="hint">Operator override is ON. Auto-dispatch is allowed.</p> : null}
            </>
          )}
        </div>
      ) : null}
      <div className="grid-2">
        {feats.explainable_ai ? (
          <div className="panel">
            <h2>EXPLAINABLE ML — WHY RANDOM FOREST SCORED THIS</h2>
            <ShapBars explain={explain} showCounterfactual={feats.counterfactual} />
          </div>
        ) : <div />}
        <div className="panel">
          <h2>K-MEANS TEAMS {feats.vulnerable_first ? "· VULNERABLE-FIRST ORDER" : ""}</h2>
          {(sim?.pipeline?.clusters || []).length ? (sim.pipeline.clusters || []).map((c) => (
            <div key={c.cluster_id}>
              <div className="metric">
                <span>{c.cluster_id} · {c.sos_count} SOS</span>
                <b>{c.assigned_team_name || c.assigned_team || "unassigned"}</b>
              </div>
              {feats.vulnerable_first && (c.priority_queue || []).length ? (
                <p className="hint">In cluster: {(c.priority_queue || []).map((p, i) => `${i + 1}. ${p.citizen_name} (${p.vulnerability})`).join(" → ")}</p>
              ) : null}
            </div>
          )) : <div className="hint">Clusters appear after the SOS queue is ingested.</div>}
        </div>
      </div>
      {feats.counterfactual && !feats.explainable_ai && explain?.counterfactual?.message ? (
        <div className="panel">
          <h2>COUNTERFACTUAL RAIN</h2>
          <p className="counterfactual">{explain.counterfactual.message}</p>
        </div>
      ) : null}
      <div className="panel">
        <h2>COLLECTED SOS — LIVE PERSON DETAIL</h2>
        <p className="hint">
          {(sim?.citizens || []).length || 0} citizens. Status every ~12s: queued → assigned → en_route → to_shelter → rescued.
          <b> Generate PDF</b> works anytime for that person (SOS → ambulance → shelter + rainfall / ML details).
        </p>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Person</th>
                <th>Name</th>
                <th>Age</th>
                <th>Latitude</th>
                <th>Longitude</th>
                <th>People</th>
                <th>Water depth</th>
                <th>Priority</th>
                <th>Cluster</th>
                <th>Ambulance</th>
                <th>Shelter</th>
                <th>Status</th>
                <th>PDF</th>
              </tr>
            </thead>
            <tbody>
              {sortedCitizens(sim).map((c, i) => {
                const log = (sim?.contact_log || []).find((r) => r.citizen_name === c.citizen_name) || {};
                const status = c.ops_status || c.live_status || log.ops_status || log.status || "queued";
                return (
                <tr key={c._id || `${c.citizen_name}-${i}`}>
                  <td>{c.rescue_order || log.person_index || i + 1}</td>
                  <td>{c.citizen_name}</td>
                  <td>{c.age ?? "—"}</td>
                  <td>{c.lat}</td>
                  <td>{c.lon}</td>
                  <td>{c.people}</td>
                  <td>{c.water_level_note}</td>
                  <td>{c.vulnerability || log.vulnerability || "—"}</td>
                  <td>{c.cluster_id || log.cluster_id || "—"}</td>
                  <td>{c.ambulance_name || log.ambulance_name || "—"}</td>
                  <td>{c.shelter_name || log.shelter_name || "—"}</td>
                  <td><span className={`status-pill ${status}`}>{status}</span></td>
                  <td>
                    <PdfDownloadButton personName={c.citizen_name} />
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      {feats.contact_log ? (
        <div className="panel">
          <h2>PER-PERSON CONTACT LOG</h2>
          <p className="hint">Rescue called each person and asked status. Yes/No rescue at the bottom of the radio updates this table.</p>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Person</th>
                  <th>Name</th>
                  <th>Called</th>
                  <th>Answered</th>
                  <th>Team</th>
                  <th>Status</th>
                  <th>Rescued</th>
                </tr>
              </thead>
              <tbody>
                {(sim?.contact_log || []).map((r) => (
                  <tr key={`${r.person_index}-${r.citizen_name}`}>
                    <td>{r.person_index}</td>
                    <td>{r.citizen_name}</td>
                    <td>{r.called_at ? String(r.called_at).slice(11, 19) : "—"}</td>
                    <td>{r.answered ? "Yes" : "No"}</td>
                    <td>{r.assigned_team || "—"}</td>
                    <td><span className={`status-pill ${r.status || ""}`}>{r.status}</span></td>
                    <td>{r.rescued == null ? "pending" : r.rescued}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!(sim?.contact_log || []).length ? <p className="hint">Log fills when the scenario starts.</p> : null}
          </div>
        </div>
      ) : null}
      <div className="panel">
        <h2>ADD ANOTHER SOS</h2>
        <p className="hint">Extra caller joins the same queue. Radio uses their name. Or talk live to the Voice Agent.</p>
        <div className="form-grid">
          <label>Citizen name<input value={sos.citizen_name} onChange={(e) => setSos({ ...sos, citizen_name: e.target.value })} /></label>
          <label>People<input type="number" value={sos.people} onChange={(e) => setSos({ ...sos, people: Number(e.target.value) })} /></label>
          <label>Latitude<input type="number" step="0.0001" value={sos.lat} onChange={(e) => setSos({ ...sos, lat: Number(e.target.value) })} /></label>
          <label>Longitude<input type="number" step="0.0001" value={sos.lon} onChange={(e) => setSos({ ...sos, lon: Number(e.target.value) })} /></label>
          <label>Rainwater around them<input value={sos.water_level_note} onChange={(e) => setSos({ ...sos, water_level_note: e.target.value })} /></label>
        </div>
        <div className="actions" style={{ marginTop: 10 }}>
          <button type="button" onClick={useMyLocation}>Use my location</button>
          <button type="button" className="primary voice-sos-btn" onClick={() => setVoiceOpen(true)}>தமிழ் குரல் முகவர்</button>
          <button className="danger" type="button" disabled={sosBusy} onClick={sendSos}>{sosBusy ? "SENDING SOS…" : "SEND SOS"}</button>
        </div>
      </div>
      <VoiceSosAgent
        open={voiceOpen}
        onClose={() => setVoiceOpen(false)}
        onDraft={(d) => {
          setSos((prev) => ({
            ...prev,
            citizen_name: d.citizen_name || prev.citizen_name,
            people: d.people ?? prev.people,
            lat: d.lat ?? prev.lat,
            lon: d.lon ?? prev.lon,
            water_level_note: d.water_level_note || prev.water_level_note,
          }));
        }}
        onSubmitted={(next) => {
          setSim(next);
          setVoiceOpen(false);
        }}
      />
      {feats.algorithm_arena ? (
        <AlgorithmArena enabled onMapPaths={setArenaPaths} />
      ) : null}
      <div className="grid-2">
        <div className="panel">
          <h2>SIMULATION AGENTS</h2>
          <AgentList agents={sim?.pipeline?.agents || snapshot?.agents} />
        </div>
        <div className="panel">
          <h2>RESULTS</h2>
          {sim?.status !== "completed" && !after.flood_probability ? <div className="muted">Results appear after ticks produce pipeline output.</div> : (
            <>
              <div className="metric"><span>Final flood probability</span><b>{fmtP(after.flood_probability)}</b></div>
              <div className="metric"><span>Peak risk</span><b>{after.peak_risk || "DATA UNAVAILABLE"}</b></div>
              <div className="metric"><span>Affected population</span><b>{after.affected_population ?? "DATA UNAVAILABLE"}</b></div>
              <div className="metric"><span>Recommended shelter</span><b>{after.shelters?.[0]?.shelter_id || "DATA UNAVAILABLE"}</b></div>
              <div className="metric"><span>Recommended route</span><b>{after.routes?.[0]?.label || "DATA UNAVAILABLE"}</b></div>
              <div className="metric"><span>Evacuation time</span><b>{after.optimization?.evacuation_time_min ?? "DATA UNAVAILABLE"} min</b></div>
              <div className="metric"><span>Risk exposure</span><b>{after.optimization?.risk_exposure ?? "DATA UNAVAILABLE"}</b></div>
              <div className="metric"><span>Shelter utilization</span><b>{after.optimization?.shelter_utilization ?? "DATA UNAVAILABLE"}</b></div>
              <div className="metric"><span>Optimization method</span><b>{after.optimization?.method || "DATA UNAVAILABLE"}</b></div>
              <div className="metric"><span>Decision latency</span><b>{after.decision_latency_ms ?? "DATA UNAVAILABLE"} ms</b></div>
              <h3>BEFORE vs AFTER OPTIMIZATION</h3>
              <div className="metric"><span>Before cost</span><b>{before.optimization?.solution_cost ?? "DATA UNAVAILABLE"}</b></div>
              <div className="metric"><span>After cost</span><b>{after.optimization?.solution_cost ?? "DATA UNAVAILABLE"}</b></div>
            </>
          )}
        </div>
      </div>
      {feats.agent_talk ? (
      <AgentTalk
        conversation={sim?.conversation || sim?.pipeline?.conversation}
        title="SIMULATION AGENT CONVERSATION"
        voiceEnabled={false}
        onTalked={(res) => {
          if (res?.conversation) setSim((prev) => ({ ...prev, conversation: res.conversation, contact_log: res.contact_log || prev?.contact_log }));
        }}
      />
      ) : null}
      <DemoRunPanels sim={sim} feats={feats} explain={explain} setSim={setSim} />
    </div>
  );
}

function sortedCitizens(sim) {
  const rows = [...(sim?.citizens || [])];
  rows.sort((a, b) => (a.rescue_order || 99) - (b.rescue_order || 99));
  return rows;
}

function pct(p) {
  return p == null ? "n/a" : `${(p * 100).toFixed(1)}%`;
}

function lastRain(sim) {
  const hist = sim?.history || [];
  const v = hist[hist.length - 1]?.rainfall_mm;
  return v == null ? null : v;
}

function prettyRunning(progress, sim) {
  const name = progress?.model_name || (String(sim?.pipeline?.prediction?.model_id || "").includes("random_forest") ? "Random Forest" : "ML");
  return `${name} running`;
}

function fmtP(p) {
  return p == null ? "DATA UNAVAILABLE" : `${(p * 100).toFixed(1)}%`;
}

function fmtNum(v, unit) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const text = Math.abs(n) >= 100 ? n.toFixed(1) : n.toFixed(2);
  return unit ? `${text} ${unit}` : text;
}

function formatSimClock(sec) {
  const s = Math.round(sec || 0);
  const m = String(Math.floor(s / 60)).padStart(2, "0");
  const r = String(s % 60).padStart(2, "0");
  return `${m}:${r}`;
}
