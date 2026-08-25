import { useCallback, useEffect, useRef, useState } from "react";
import {
  hqrlAccept,
  hqrlAblation,
  hqrlBenchmark,
  hqrlConfigure,
  hqrlExportCsv,
  hqrlExportDownload,
  hqrlExportTex,
  hqrlFailures,
  hqrlInjectClosure,
  hqrlInjectConflict,
  hqrlInjectShelterFull,
  hqrlReject,
  hqrlReplan,
  hqrlReset,
  hqrlStart,
  hqrlState,
} from "../../services/api.js";
import IeeePaperPack from "../../components/IeeePaperPack.jsx";
import BenchmarkEvidence from "../../components/BenchmarkEvidence.jsx";
import { HqrlNetworkMap, HqrlResultCharts, HqrlResultsTable } from "../../components/HqrlVisuals.jsx";
import "./hqrl.css";

const STAGE_LABELS = {
  synthetic_data: "Synthetic Disaster Data",
  reliability_conflict: "Reliability & Conflict",
  dynamic_graph: "Dynamic Road Graph",
  ppo_candidates: "Heuristic policy route scores",
  topk_routes: "Top-K Candidate Routes",
  qubo_filter: "QUBO Safety Filter",
  qaoa_solver: "QAOA simulation (quantum-inspired)",
  classical_fallback: "Classical QUBO Fallback",
  safety_validation: "Deterministic Safety Validation",
  xai_explanation: "Explainable Decision",
  final_route: "Final Evacuation Route",
};

const FAILURE_OPTS = [
  ["weather_outage", "Weather API outage"],
  ["delayed_radar", "Delayed radar"],
  ["sensor_drift", "Sensor drift"],
  ["outdated_road_data", "Outdated road data"],
  ["citizen_conflict", "Citizen report conflict"],
  ["shelter_failure", "Shelter failure"],
  ["comms_failure", "Communication failure"],
];

export default function HqrlDemo() {
  const [state, setState] = useState(null);
  const [view, setView] = useState("landing"); // landing | live | results | architecture | failures
  const [busy, setBusy] = useState(false);
  const [focusCand, setFocusCand] = useState(null);
  const [cfg, setCfg] = useState({
    seed: 42,
    n_groups: 6,
    n_shelters: 3,
    shelter_capacity_scale: 1,
    flood_severity: 0.35,
    traffic_level: 0.4,
    n_road_closures: 0,
    vehicles_available: 8,
  });
  const [benchN, setBenchN] = useState(10);
  const [failLocal, setFailLocal] = useState({});
  const [liveMsg, setLiveMsg] = useState("");
  const autoRef = useRef(null);

  const refresh = useCallback(async () => {
    const s = await hqrlState();
    setState(s);
    return s;
  }, []);

  useEffect(() => {
    refresh();
    return () => {
      if (autoRef.current) clearTimeout(autoRef.current);
    };
  }, [refresh]);

  const apply = async (fn, nextView) => {
    setBusy(true);
    try {
      const s = await fn();
      setState(s);
      if (nextView) setView(nextView);
      return s;
    } finally {
      setBusy(false);
    }
  };

  const sleep = (ms) => new Promise((r) => {
    autoRef.current = setTimeout(r, ms);
  });

  const runLiveDemo = async () => {
    setBusy(true);
    setView("live");
    try {
      setLiveMsg("Minute 1 — Initial evacuation");
      await hqrlConfigure(cfg);
      let s = await hqrlStart();
      setState(s);
      await sleep(2200);

      setLiveMsg("Minute 2 — Inject flood / road closure");
      s = await hqrlInjectClosure();
      setState(s);
      await sleep(2500);

      setLiveMsg("Minute 3 — RL candidates + QUBO safety filter");
      s = await hqrlReplan();
      setState(s);
      await sleep(2800);

      setLiveMsg("Minute 4 — QAOA / classical + validation + XAI");
      await sleep(1800);

      setLiveMsg("Accepting feasible route…");
      s = await hqrlAccept();
      setState(s);
      await sleep(1600);

      setLiveMsg("Minute 5 — Shelter full → automatic replanning");
      s = await hqrlInjectShelterFull();
      setState(s);
      await sleep(2200);
      s = await hqrlReplan();
      setState(s);
      setLiveMsg("Live demo sequence complete — inspect panels & run benchmark for paper tables.");
    } finally {
      setBusy(false);
    }
  };

  const runBenchmark = async () => {
    setBusy(true);
    setView("results");
    setLiveMsg(`Running benchmark (${benchN} scenarios, seed=${cfg.seed})…`);
    try {
      const s = await hqrlBenchmark({ n_scenarios: benchN, seed: cfg.seed });
      setState(s);
      setLiveMsg("Benchmark complete — Synthetic Simulation Results");
    } finally {
      setBusy(false);
    }
  };

  const applyFailures = async () => {
    const failures = { ...failLocal };
    FAILURE_OPTS.forEach(([k]) => {
      if (failures[k] == null) failures[k] = false;
    });
    await apply(() => hqrlFailures(failures), "live");
  };

  if (!state) {
    return (
      <div className="hqrl-demo">
        <div className="hqrl-panel">Loading IEEE HQRL simulation…</div>
      </div>
    );
  }

  if (view === "landing") {
    return (
      <div className="hqrl-demo">
        <div className="hqrl-landing hqrl-panel">
          <div className="hqrl-badge">SYNTHETIC DISASTER SIMULATION / PROTOTYPE</div>
          <h1>HQRL DISASTER EVACUATION SIMULATOR</h1>
          <p className="abstract">
            Hybrid Quantum Reinforcement Learning with Explainable AI for Dynamic Disaster Evacuation Route Optimization.
            This live demo shows: RL candidate generation → QUBO hard safety constraints → simulated QAOA / classical
            solver → deterministic validation → XAI explanation → human-in-the-loop → dynamic replanning.
            No quantum speedup, real-world deployment, or guaranteed safety is claimed.
          </p>
          <div className="cta">
            <button type="button" className="primary" disabled={busy} onClick={runLiveDemo}>
              RUN LIVE DEMO
            </button>
            <button type="button" disabled={busy} onClick={runBenchmark}>
              RUN BENCHMARK
            </button>
            <button type="button" disabled={busy} onClick={() => setView("failures")}>
              FAILURE INJECTION
            </button>
            <button type="button" disabled={busy} onClick={() => { setView("results"); refresh(); }}>
              VIEW RESULTS
            </button>
            <button type="button" onClick={() => setView("architecture")}>
              VIEW ARCHITECTURE
            </button>
          </div>
          <div className="hqrl-config">
            <label>Seed<input type="number" value={cfg.seed} onChange={(e) => setCfg({ ...cfg, seed: +e.target.value })} /></label>
            <label>Groups<input type="number" value={cfg.n_groups} onChange={(e) => setCfg({ ...cfg, n_groups: +e.target.value })} /></label>
            <label>Shelters<input type="number" value={cfg.n_shelters} onChange={(e) => setCfg({ ...cfg, n_shelters: +e.target.value })} /></label>
            <label>Capacity×<input type="number" step="0.1" value={cfg.shelter_capacity_scale} onChange={(e) => setCfg({ ...cfg, shelter_capacity_scale: +e.target.value })} /></label>
            <label>Flood<input type="number" step="0.05" value={cfg.flood_severity} onChange={(e) => setCfg({ ...cfg, flood_severity: +e.target.value })} /></label>
            <label>Traffic<input type="number" step="0.05" value={cfg.traffic_level} onChange={(e) => setCfg({ ...cfg, traffic_level: +e.target.value })} /></label>
            <label>Closures<input type="number" value={cfg.n_road_closures} onChange={(e) => setCfg({ ...cfg, n_road_closures: +e.target.value })} /></label>
            <label>Vehicles<input type="number" value={cfg.vehicles_available} onChange={(e) => setCfg({ ...cfg, vehicles_available: +e.target.value })} /></label>
            <label>Benchmark N<input type="number" value={benchN} onChange={(e) => setBenchN(+e.target.value)} /></label>
          </div>
          <IeeePaperPack
            pack={state.paper_pack}
            ablation={state.ablation}
            busy={busy}
            onAblation={async () => {
              setBusy(true);
              try {
                const s = await hqrlAblation({ n_scenarios: Math.min(benchN, 20), seed: cfg.seed });
                setState(s);
              } finally {
                setBusy(false);
              }
            }}
            onExportCsv={() => hqrlExportCsv()}
            onExportTex={() => hqrlExportTex()}
          />
          <BenchmarkEvidence
            benchmark={state.benchmark}
            busy={busy}
            seed={cfg.seed}
            nScenarios={benchN}
            onSeed={(v) => setCfg({ ...cfg, seed: v })}
            onN={setBenchN}
            onRun={runBenchmark}
          />
          <p className="hqrl-stack">
            Stack: React + FastAPI · NetworkX synthetic research network · heuristic policy candidate sampling · QUBO filter ·
            Simulated QAOA + classical annealing fallback · XAI cards · reproducible seeds.
            Seed displayed on every experiment: <b>{cfg.seed}</b>
          </p>
        </div>
      </div>
    );
  }

  if (view === "architecture") {
    return (
      <div className="hqrl-demo">
        <div className="hqrl-controls">
          <button type="button" onClick={() => setView("landing")}>Back</button>
          <button type="button" className="primary" onClick={runLiveDemo}>RUN LIVE DEMO</button>
        </div>
        <div className="hqrl-panel">
          <h2>Research pipeline</h2>
          <pre className="hqrl-arch">{`DISASTER EVENT
      |
REAL-TIME / SYNTHETIC DATA
      |
RELIABILITY / CONFLICT ANALYSIS
      |
RL / PPO ROUTE CANDIDATES
      |
QUBO SAFETY FILTER
      |
QAOA / CLASSICAL SOLVER
      |
SAFETY VALIDATION
      |
XAI EXPLANATION
      |
HUMAN APPROVAL
      |
FINAL EVACUATION ROUTE  (+ dynamic replan)`}</pre>
          <p className="hqrl-muted" style={{ marginTop: 12 }}>
            Without safety layer: RL may propose a fast but unsafe route. With HQRL: candidates are filtered by hard
            constraints before any final recommendation.
          </p>
        </div>
      </div>
    );
  }

  if (view === "failures") {
    return (
      <div className="hqrl-demo">
        <div className="hqrl-controls">
          <button type="button" onClick={() => setView("landing")}>Back</button>
          <button type="button" className="warn" disabled={busy} onClick={applyFailures}>APPLY FAILURE INJECTION</button>
          <button type="button" onClick={() => setView("live")}>Open live panels</button>
        </div>
        <div className="hqrl-panel">
          <h2>Failure injection mode</h2>
          <p className="hqrl-muted">Select degradations to lower reliability and force human review.</p>
          <div className="hqrl-fail-grid">
            {FAILURE_OPTS.map(([k, label]) => (
              <label key={k}>
                <input
                  type="checkbox"
                  checked={!!failLocal[k]}
                  onChange={(e) => setFailLocal({ ...failLocal, [k]: e.target.checked })}
                />
                {label}
              </label>
            ))}
          </div>
          <p className="hqrl-muted" style={{ marginTop: 10 }}>
            Current reliability: <b>{((state.topbar?.source_reliability || 0) * 100).toFixed(0)}%</b> ·
            Auto dispatch: <b>{state.auto_dispatch_allowed ? "ALLOWED" : "BLOCKED"}</b> ·
            Conflict: <b>{state.topbar?.conflict_level}</b>
          </p>
        </div>
      </div>
    );
  }

  const tb = state.topbar || {};
  const qubo = state.qubo_panel || {};
  const solver = state.solver_panel || {};
  const xai = state.xai || {};
  const decision = state.decision || {};
  const safety = state.safety_check || {};
  const bench = state.benchmark;
  const stages = state.pipeline_stages || [];
  const progress = state.pipeline_progress || {};

  return (
    <div className="hqrl-demo">
      <div className="hqrl-banner">
        <div>
          <h1>HQRL — Dynamic Disaster Evacuation (IEEE Demo)</h1>
          <p className="sub">
            Prototype architecture · seed <b>{state.seed}</b> · graph v{state.graph_version} ·
            RL generates candidates — safety is enforced later.
          </p>
        </div>
        <div className="hqrl-badge">SYNTHETIC SIMULATION / PROTOTYPE</div>
      </div>

      <div className="hqrl-topbar">
        <div className="cell"><span>Disaster</span><b>{tb.disaster}</b></div>
        <div className="cell"><span>Sim time</span><b>{tb.simulation_time}</b></div>
        <div className="cell"><span>Graph</span><b>#{tb.graph_version}</b></div>
        <div className="cell"><span>Active groups</span><b>{tb.active_groups}</b></div>
        <div className="cell"><span>Shelters</span><b>{tb.available_shelters}</b></div>
        <div className="cell"><span>Closures</span><b>{tb.road_closures}</b></div>
        <div className="cell"><span>Status</span><b>{tb.system_status}</b></div>
        <div className="cell"><span>Freshness</span><b>{tb.data_freshness}</b></div>
        <div className="cell"><span>Reliability</span><b>{((tb.source_reliability || 0) * 100).toFixed(0)}%</b></div>
        <div className="cell"><span>Conflict</span><b>{tb.conflict_level}</b></div>
      </div>

      {liveMsg ? (
        <div className="hqrl-notify info"><strong>DEMO NARRATION</strong>{liveMsg}</div>
      ) : null}
      {state.notification ? (
        <div className={`hqrl-notify ${state.notification.level || "info"}`}>
          <strong>{state.notification.title}</strong>
          {state.notification.body}
        </div>
      ) : null}

      <div className="hqrl-controls">
        <button type="button" className="primary" disabled={busy} onClick={runLiveDemo}>START DISASTER SIMULATION</button>
        <button type="button" className="warn" disabled={busy} onClick={() => apply(hqrlInjectClosure)}>Inject Road Closure</button>
        <button type="button" className="warn" disabled={busy} onClick={() => apply(hqrlInjectConflict)}>Inject Sensor Conflict</button>
        <button type="button" className="danger" disabled={busy} onClick={() => apply(hqrlInjectShelterFull)}>Shelter Full</button>
        <button type="button" disabled={busy} onClick={() => apply(hqrlReplan)}>Replan</button>
        <button type="button" disabled={busy} onClick={runBenchmark}>Run Benchmark</button>
        <button type="button" disabled={busy} onClick={() => hqrlExportDownload()}>Export Results</button>
        <button type="button" disabled={busy} onClick={() => apply(hqrlReset, "landing")}>Reset</button>
        <button type="button" onClick={() => setView("landing")}>Landing</button>
        <button type="button" onClick={() => setView("results")}>Results</button>
        <button type="button" onClick={() => setView("failures")}>Failures</button>
      </div>

      {view === "results" ? (
        <>
          <BenchmarkEvidence
            benchmark={bench}
            busy={busy}
            seed={cfg.seed}
            nScenarios={benchN}
            onSeed={(v) => setCfg({ ...cfg, seed: v })}
            onN={setBenchN}
            onRun={runBenchmark}
          />
          {bench ? (
            <div className="hqrl-panel">
              <h2>Result tables & mixed charts</h2>
              <HqrlResultsTable table={bench.table || []} />
              <HqrlResultCharts graphs={bench.graphs} />
            </div>
          ) : null}
        </>
      ) : null}

      <div className="hqrl-layout">
        <div>
          <div className="hqrl-panel">
            <h2>Live disaster map</h2>
            <HqrlNetworkMap map={state.map} selected={state.selected_route} candidates={state.candidates} />
          </div>

          <div className="hqrl-panel">
            <h2>Replanning story</h2>
            <div className="hqrl-mono">
{`Initial Route
${(state.previous_route || state.selected_route)?.label || "(none yet)"}

${state.selected_route?.status === "INVALID" ? `EVENT: ${state.selected_route.invalid_reason}\nReplanning...` : ""}

Current / New Route
${state.selected_route?.label || "(awaiting pipeline)"}
status: ${state.selected_route?.status || "n/a"}`}
            </div>
          </div>

          <div className="hqrl-panel">
            <h2>Heuristic policy route candidates (not trained PPO)</h2>
            <p className="hqrl-muted">{state.last_pipeline?.label || "RL generates candidates — safety is enforced later."}</p>
            {(state.candidates || []).map((c) => {
              const ok = c.qubo_pass || c.status === "FEASIBLE" || c.status === "SELECTED";
              const bad = c.status === "REJECTED" || c.qubo_pass === false;
              return (
                <div
                  key={c.id}
                  className={`hqrl-cand ${ok ? "ok" : ""} ${bad ? "bad" : ""} ${focusCand === c.id ? "selected" : ""}`}
                  onClick={() => setFocusCand(c.id)}
                  onKeyDown={() => {}}
                  role="button"
                  tabIndex={0}
                >
                  <span className="tag">{ok ? "FEASIBLE ✅" : "REJECTED ❌"}</span>
                  <b>{c.id}</b> · {c.label}
                  <div className="hqrl-muted">
                    travel {c.travel_min} min · hazard {c.hazard_exposure} · shelter {c.shelter} · cost {c.cost}
                    {c.violations?.length ? ` · violations: ${c.violations.join(", ")}` : ""}
                  </div>
                </div>
              );
            })}
            {!state.candidates?.length ? <p className="hqrl-muted">Run simulation to generate candidates.</p> : null}
          </div>
        </div>

        <div>
          <div className="hqrl-panel">
            <h2>Pipeline</h2>
            <div className="hqrl-pipeline">
              {stages.map((s) => {
                const st = progress[s] || "pending";
                return (
                  <div key={s} className={`stage ${st}`}>
                    <span className="dot" />
                    {STAGE_LABELS[s] || s}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="hqrl-panel">
            <h2>Data sources & conflict</h2>
            {(state.sources || []).map((s) => (
              <div key={s.id} className="hqrl-muted" style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{s.name} · {s.status}</span>
                <b>{(s.reliability * 100).toFixed(0)}%</b>
              </div>
            ))}
            {(state.conflict?.messages || []).length ? (
              <div className="hqrl-mono" style={{ marginTop: 8 }}>
                {`CONFLICT SCORE: ${state.conflict.score}
${(state.conflict.messages || []).join("\n")}
AUTO DISPATCH: ${state.conflict.auto_dispatch_blocked ? "BLOCKED" : "OK"}
HUMAN REVIEW: ${state.conflict.human_review ? "REQUIRED" : "optional"}`}
              </div>
            ) : null}
          </div>

          <div className="hqrl-panel">
            <h2>QUBO safety filter</h2>
            <div className="hqrl-mono">
{`Candidate Routes:       ${qubo.n_candidates ?? "—"}
Closed-Road Violations: ${qubo.closed_road_violations ?? "—"}
Capacity Violations:    ${qubo.capacity_violations ?? "—"}
Feasible Routes:        ${qubo.feasible_routes ?? "—"}
Selected Route:         ${qubo.selected_route ?? "—"}`}
            </div>
            <h3>Constraints</h3>
            <ul className="hqrl-check">
              {(qubo.constraints || []).map((c) => (
                <li key={c} className="pass">✓ {c}</li>
              ))}
            </ul>
          </div>

          <div className="hqrl-panel">
            <h2>QAOA optimization — experimental backend</h2>
            <p className="hqrl-muted">{solver.disclaimer}</p>
            <pre className="hqrl-arch" style={{ fontSize: 11 }}>
              {solver.qaoa?.meta?.circuit_ascii || "q0 ──H────●────R────●────M"}
            </pre>
            <div className="hqrl-muted">
              Qubits: {solver.qaoa?.meta?.qubits ?? "—"} · Depth: {solver.qaoa?.meta?.circuit_depth ?? "—"} ·
              Shots: {solver.qaoa?.meta?.shots ?? "—"} · {solver.qaoa?.meta?.optimization_status || "—"}
            </div>
            <table className="hqrl-table" style={{ marginTop: 8 }}>
              <thead>
                <tr><th>Solver</th><th>Feasible</th><th>Time (ms)</th></tr>
              </thead>
              <tbody>
                <tr>
                  <td>Classical QUBO</td>
                  <td>{solver.classical?.feasible ? "Yes" : "No"}</td>
                  <td className="num">{solver.classical?.execution_ms ?? "—"}</td>
                </tr>
                <tr>
                  <td>QAOA (simulated)</td>
                  <td>{solver.qaoa?.feasible ? "Yes" : "No"}</td>
                  <td className="num">{solver.qaoa?.execution_ms ?? "—"}</td>
                </tr>
              </tbody>
            </table>
            {solver.used_fallback ? <p className="hqrl-muted">Fallback path used: QAOA → Classical QUBO</p> : null}
          </div>

          <div className="hqrl-panel">
            <h2>Final safety check</h2>
            <ul className="hqrl-check">
              {(safety.checks || []).map((c) => (
                <li key={c.name} className={c.ok ? "pass" : "fail"}>
                  {c.ok ? "✓" : "✗"} {c.name}
                </li>
              ))}
            </ul>
            <b>FINAL DECISION: {safety.final || "—"}</b>
          </div>

          <div className="hqrl-panel">
            <h2>Explainable decision</h2>
            <div className="hqrl-mono">
{`FINAL DECISION
Selected: ${xai.selected_label || "—"}
Risk: ${xai.risk || "—"} · Reliability: ${xai.reliability_score ?? "—"} · Travel: ${xai.travel_min ?? "—"} min

Why selected?
${(xai.why_selected || []).map((w) => `✓ ${w}`).join("\n") || "—"}

Rejected alternatives
${(xai.rejected || []).map((r) => `✗ ${r.id || ""} ${r.route}\n  ${r.reason}`).join("\n") || "—"}`}
            </div>
          </div>

          <div className="hqrl-panel hqrl-decision">
            <h2>Emergency decision (human-in-the-loop)</h2>
            {decision.human_required ? (
              <p className="hqrl-muted">⚠ HUMAN APPROVAL REQUIRED — automatic dispatch disabled (conflict / reliability).</p>
            ) : null}
            <div className="hqrl-mono">
{`Recommended: ${decision.recommended || "—"}
Risk: ${decision.risk || "—"}
Evidence reliability: ${decision.evidence_reliability ?? "—"}
Source conflict: ${decision.source_conflict || "—"}
Reason: ${decision.reason || "—"}`}
            </div>
            <div className="actions">
              <button type="button" className="primary" disabled={busy} onClick={() => apply(hqrlAccept)}>ACCEPT ROUTE</button>
              <button type="button" disabled={busy} onClick={() => apply(hqrlReplan)}>MODIFY / REPLAN</button>
              <button type="button" className="danger" disabled={busy} onClick={() => apply(hqrlReject)}>REJECT</button>
            </div>
          </div>

          <div className="hqrl-panel">
            <h2>Current disaster state</h2>
            <div className="hqrl-muted">
              Vehicles left: <b>{state.vehicles_left}</b>
            </div>
            {(state.shelters || []).map((s) => (
              <div key={s.id} className="hqrl-muted">
                {s.name}: {s.occupancy}/{s.capacity} ({s.status}) · remaining {s.remaining}
              </div>
            ))}
            <h3>Event log</h3>
            <div className="hqrl-mono" style={{ maxHeight: 160, overflow: "auto" }}>
              {(state.event_log || []).slice().reverse().map((e, i) => (
                <div key={`${e.t}-${i}`}>[{e.t}] {e.title} {e.detail ? `— ${e.detail}` : ""}</div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <IeeePaperPack
        pack={state.paper_pack}
        ablation={state.ablation}
        busy={busy}
        onAblation={async () => {
          setBusy(true);
          try {
            const s = await hqrlAblation({ n_scenarios: Math.min(benchN, 20), seed: cfg.seed });
            setState(s);
          } finally {
            setBusy(false);
          }
        }}
        onExportCsv={() => hqrlExportCsv()}
        onExportTex={() => hqrlExportTex()}
      />

      <p className="hqrl-muted" style={{ marginTop: 8 }}>
        {(state.disclaimers || []).join(" · ")}
      </p>
    </div>
  );
}
