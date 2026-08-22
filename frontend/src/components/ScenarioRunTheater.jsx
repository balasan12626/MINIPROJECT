const STEPS = [
  { id: "scenario", title: "Scenario launch" },
  { id: "ingest", title: "Live twin ingest" },
  { id: "ml", title: "Random Forest predicting" },
  { id: "risk", title: "Flood probability published" },
  { id: "policy", title: "Decision policy" },
  { id: "agents", title: "Agents running" },
  { id: "dispatch", title: "Rescue / ambulance call" },
  { id: "talk", title: "Agents talking" },
];

function prettyModel(pred = {}, progress = {}) {
  const id = progress.model_name || progress.model || pred.model_id || "";
  if (String(id).toLowerCase().includes("random_forest") || progress.model_name === "Random Forest") return "Random Forest";
  if (String(id).toLowerCase().includes("xgboost")) return "XGBoost";
  return progress.model_name || "Random Forest";
}

export default function ScenarioRunTheater({ sim, progress, onWatchMap, onPause }) {
  const pipe = sim?.pipeline || {};
  const pred = pipe.prediction || {};
  const history = Array.isArray(sim?.history) ? sim.history : [];
  const last = history[history.length - 1] || {};
  const p = last.flood_probability ?? pred.flood_probability;
  const model = prettyModel(pred, progress || {});
  const step = progress?.step || "scenario";
  const idx = Math.max(0, STEPS.findIndex((s) => s.id === step));
  const ticks = sim?.params?.ticks || 24;
  const pctDone = Math.min(100, Math.round(((sim?.tick || 0) / ticks) * 100));
  const agents = pipe.agents || [];
  const active = agents.filter((a) => String(a.status || "").toUpperCase() === "ACTIVE");
  const events = Array.isArray(sim?.events) ? sim.events : [];

  return (
    <div className="run-theater">
      <div className="run-pulse" />
      <div className="run-inner">
        <div className="badge sim">SCENARIO RUNNING</div>
        <h1>Digital twin is executing</h1>
        <p className="run-now">{progress?.label || "Starting pipeline…"}</p>
        <div className="run-model">
          <span className="run-spinner" />
          <div>
            <div className="run-model-name">{model} is running</div>
            <div className="muted">{pred.model_id || progress?.model || "random_forest_flood_v1"} · v{pred.model_version || progress?.model_version || "1.1.0"}</div>
          </div>
        </div>
        <div className="run-kpis">
          <div><span>Flood probability</span><b>{p != null ? `${(p * 100).toFixed(1)}%` : "predicting…"}</b></div>
          <div><span>Tick</span><b>{sim?.tick ?? 0}/{ticks}</b></div>
          <div><span>Sim clock</span><b>{Math.round(sim?.sim_time_sec || 0)}s</b></div>
          <div><span>SOS queue</span><b>{(sim?.citizens || []).length || sim?.params?.sos_count || 0}</b></div>
        </div>
        <div className="run-bar"><i style={{ width: `${pctDone}%` }} /></div>
        <div className="run-steps">
          {STEPS.map((s, i) => (
            <div key={s.id} className={`run-step ${i < idx ? "done" : i === idx ? "now" : ""}`}>
              <b>{i < idx ? "done" : i === idx ? "running" : "wait"}</b>
              <span>{s.title}</span>
            </div>
          ))}
        </div>
        <div className="run-agents">
          <h3>AGENTS RUNNING</h3>
          {agents.length ? agents.map((a) => (
            <div className="metric" key={a.name}>
              <span>{String(a.status).toUpperCase() === "ACTIVE" ? "●" : "○"} {a.name}</span>
              <b>{a.current_action || a.last_event || "idle"}</b>
            </div>
          )) : <div className="muted">Waiting for first agent heartbeat…</div>}
        </div>
        <div className="timeline run-log">
          {events.slice(-8).reverse().map((e, i) => (
            <div key={i}><b>{formatClock(e.sim_time_sec)}</b> {e.message}</div>
          ))}
          {!events.length ? <div className="muted">Waiting for first tick…</div> : null}
        </div>
        <div className="actions" style={{ marginTop: 16 }}>
          <button className="primary" onClick={onWatchMap}>Open map + SOS roster</button>
          <button onClick={onPause}>Pause</button>
        </div>
      </div>
    </div>
  );
}

function formatClock(sec) {
  const s = Math.round(sec || 0);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
