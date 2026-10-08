import { lazy, memo, Suspense, useCallback, useEffect, useRef, useState } from "react";
import {
  hqrlAccept,
  hqrlAblation,
  hqrlBenchmark,
  hqrlConfigure,
  hqrlExportCsv,
  hqrlExportDownload,
  hqrlExportTex,
  hqrlInjectClosure,
  hqrlInjectConflict,
  hqrlInjectShelterFull,
  hqrlReplan,
  hqrlState,
} from "../services/api.js";
import { connectSocket } from "../services/ws.js";
import { BENCHMARK_N_SCENARIOS, deriveHqrlConfig } from "../config/scenarios.js";
import { useScenario } from "../state/ScenarioContext.jsx";
import { createThrottle } from "../utils/feed.js";
import BenchmarkEvidence from "./BenchmarkEvidence.jsx";
import DynamicRlXaiPanel from "./DynamicRlXaiPanel.jsx";
import { HqrlNetworkMap } from "./HqrlVisuals.jsx";
import "../pages/HqrlDemo/hqrl.css";

const IeeePaperPack = lazy(() => import("./IeeePaperPack.jsx"));

const RESULTS_HREF = "#hqrl-results";

/**
 * IEEE HQRL research panel embedded in the /simulation run view.
 *
 * Data flow (no polling):
 *  - one GET of /hqrl/state on mount;
 *  - websocket `hqrl_state` pushes (every HQRL endpoint broadcasts), applied at
 *    most once per second;
 *  - responses of the manual actions below.
 * The HQRL engine only changes when an endpoint is called, so a periodic poll
 * returned the same payload forever.
 *
 * RUN SCENARIO (ScenarioContext) configures the engine and runs the benchmark.
 * Once that step has settled, this panel computes the live route once
 * (replan — it keeps the benchmark in engine state for the exports). The
 * benchmark table and charts are shown once, in the Results section; this
 * panel links there instead of rendering a second copy.
 */
function IeeeHqrlEmbed({ runId, params, citizensCount = 0, active = true }) {
  const ctx = useScenario();
  const benchStatus = ctx?.steps?.benchmark?.status;
  const [state, setState] = useState(null);
  const [preparing, setPreparing] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [benchBusy, setBenchBusy] = useState(false);
  const [note, setNote] = useState("");
  const [benchN, setBenchN] = useState(BENCHMARK_N_SCENARIOS);
  const [seed, setSeed] = useState(42);
  const bootRef = useRef("");
  const benchLock = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const apply = useCallback((s) => {
    if (mountedRef.current && s && s.available !== false) setState(s);
  }, []);

  // One read on mount.
  useEffect(() => {
    hqrlState().then(apply).catch(() => {});
  }, [apply]);

  // Live pushes, throttled to ≤ 1 commit/s.
  useEffect(() => {
    const push = createThrottle((payload) => {
      if (!benchLock.current) apply(payload);
    }, 1000);
    const stop = connectSocket((ev) => {
      if (ev?.type === "hqrl_state" && ev.payload) push(ev.payload);
    });
    return () => {
      push.cancel();
      stop();
    };
  }, [apply]);

  // Live route for this run — once, after the benchmark step has finished
  // (it reconfigures/resets the engine, so running earlier would race it).
  useEffect(() => {
    if (!runId || bootRef.current === runId) return;
    if (benchStatus === "running") return;
    bootRef.current = runId;
    setPreparing(true);
    setNote("");
    hqrlReplan()
      .then(apply)
      .catch((err) => {
        if (mountedRef.current) setNote(`Live route failed: ${err?.response?.data?.detail || err?.message || String(err)}`);
      })
      .finally(() => {
        if (mountedRef.current) setPreparing(false);
      });
  }, [runId, benchStatus, apply]);

  const act = async (fn, label) => {
    setActionBusy(true);
    setNote(label ? `${label}…` : "");
    try {
      const s = await fn();
      apply(s);
      if (mountedRef.current) setNote(label ? `${label} — done.` : "");
      return s;
    } catch (err) {
      if (mountedRef.current) setNote(`${label || "Action"} failed: ${err?.message || String(err)}`);
      return null;
    } finally {
      if (mountedRef.current) setActionBusy(false);
    }
  };

  const runLocked = async (fn, label) => {
    if (benchLock.current) return;
    benchLock.current = true;
    setBenchBusy(true);
    setNote(`${label}…`);
    try {
      const s = await fn();
      apply(s);
      if (mountedRef.current) setNote(`${label} — done. These manual results update the exports; the Results table shows the RUN SCENARIO benchmark.`);
    } catch (err) {
      if (mountedRef.current) setNote(`${label} failed: ${err?.message || String(err)}`);
    } finally {
      benchLock.current = false;
      if (mountedRef.current) setBenchBusy(false);
    }
  };

  const nClamped = () => Math.max(1, Math.min(Number(benchN) || BENCHMARK_N_SCENARIOS, 50));
  const runManualBenchmark = () =>
    runLocked(() => hqrlBenchmark({ n_scenarios: nClamped(), seed: Number(seed) || 42 }), `Manual benchmark (${nClamped()} scenarios, seed ${seed})`);
  const runManualAblation = () =>
    runLocked(() => hqrlAblation({ n_scenarios: nClamped(), seed: Number(seed) || 42 }), "Manual ablation");

  const liveDemo = () =>
    act(async () => {
      await hqrlConfigure({ ...deriveHqrlConfig(params || {}, citizensCount), seed: Number(seed) || 42 });
      await hqrlReplan();
      await hqrlInjectClosure();
      await hqrlReplan();
      await hqrlAccept();
      await hqrlInjectShelterFull();
      return hqrlReplan();
    }, "Guided live-demo sequence");

  const locked = actionBusy || benchBusy;

  // Status is derived from what is actually in flight — never a sticky message.
  const status = preparing
    ? "Computing the live HQRL route for this run…"
    : benchStatus === "running"
      ? "Waiting for the RUN SCENARIO benchmark step to finish…"
      : note;

  const advanced = (
    <details className="hqrl-advanced" style={{ marginTop: 10 }}>
      <summary>Advanced (manual HQRL controls)</summary>
      <p className="hqrl-muted">
        Manual what-if actions on the HQRL engine. RUN SCENARIO already configures the planner and runs the benchmark —
        nothing here is needed for the normal flow.
      </p>
      <div className="hqrl-controls">
        <button type="button" disabled={locked} onClick={() => act(hqrlInjectClosure, "Road closure injected")}>Inject road closure</button>
        <button type="button" disabled={locked} onClick={() => act(hqrlInjectConflict, "Sensor conflict injected")}>Inject sensor conflict</button>
        <button type="button" disabled={locked} onClick={() => act(hqrlInjectShelterFull, "Shelter marked full")}>Mark shelter full</button>
        <button type="button" disabled={locked} onClick={() => act(hqrlReplan, "Replan")}>Replan route</button>
        <button type="button" disabled={locked} onClick={() => act(hqrlAccept, "Route accepted")}>Accept route</button>
        <button type="button" disabled={locked} onClick={liveDemo}>Play guided demo sequence</button>
      </div>
      <div className="hqrl-controls" style={{ marginTop: 8 }}>
        <label className="hqrl-muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          Seed
          <input type="number" style={{ width: 72 }} value={seed} disabled={benchBusy} onChange={(e) => setSeed(Number(e.target.value))} />
        </label>
        <label className="hqrl-muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          N
          <input type="number" style={{ width: 64 }} value={benchN} disabled={benchBusy} onChange={(e) => setBenchN(Number(e.target.value))} />
        </label>
        <button type="button" disabled={locked} onClick={runManualBenchmark}>
          {benchBusy ? "Manual run in progress…" : "Manual benchmark run"}
        </button>
        <button type="button" disabled={locked} onClick={runManualAblation}>Manual ablation run</button>
        <button type="button" disabled={locked} onClick={() => hqrlExportDownload().catch((e) => setNote(e.message))}>Export results</button>
      </div>
    </details>
  );

  if (!state) {
    return (
      <div className="panel hqrl-demo" style={{ padding: 14 }}>
        <h2>IEEE HQRL — LIVE RESEARCH VIEW</h2>
        <p className="hqrl-muted">{status || "Loading HQRL engine state…"}</p>
        {advanced}
      </div>
    );
  }

  const qubo = state.qubo_panel || {};
  const solver = state.solver_panel || {};
  const xai = state.xai || {};
  const tb = state.topbar || {};

  return (
    <div className="panel hqrl-demo ieee-embed" style={{ padding: 14 }}>
      <div className="status-row" style={{ flexWrap: "wrap", gap: 8 }}>
        <h2 style={{ margin: 0 }}>IEEE HQRL — LIVE RESEARCH VIEW</h2>
        <span className="hqrl-badge">SYNTHETIC · seed {state.seed}</span>
      </div>
      <p className="hqrl-muted" style={{ marginTop: 6 }}>
        RL candidates → QUBO safety → simulated QAOA / classical → XAI → human loop → dynamic replan. No quantum speedup
        claimed. Updates arrive over the websocket; nothing is polled.
      </p>

      {status ? <div className="hqrl-notify info"><strong>STATUS</strong>{status}</div> : null}
      {state.notification && !preparing ? (
        <div className={`hqrl-notify ${state.notification.level || "info"}`}>
          <strong>{state.notification.title}</strong>
          {state.notification.body}
        </div>
      ) : null}

      <div className="hqrl-topbar" style={{ marginTop: 8 }}>
        <div className="cell"><span>Sim time</span><b>{tb.simulation_time}</b></div>
        <div className="cell"><span>Graph</span><b>#{tb.graph_version}</b></div>
        <div className="cell"><span>Closures</span><b>{tb.road_closures}</b></div>
        <div className="cell"><span>Reliability</span><b>{((tb.source_reliability || 0) * 100).toFixed(0)}%</b></div>
        <div className="cell"><span>Conflict</span><b>{tb.conflict_level}</b></div>
        <div className="cell"><span>Status</span><b>{tb.system_status}</b></div>
      </div>

      <div className="hqrl-layout" style={{ marginTop: 8 }}>
        <div>
          <HqrlNetworkMap map={state.map} selected={state.selected_route} candidates={state.candidates} animate={active} />
          <div className="hqrl-panel" style={{ marginTop: 10 }}>
            <h2>Policy-based route candidates (heuristic — not trained PPO)</h2>
            {(state.candidates || []).map((c) => {
              const ok = c.qubo_pass || c.status === "FEASIBLE" || c.status === "SELECTED";
              return (
                <div key={c.id} className={`hqrl-cand ${ok ? "ok" : "bad"}`}>
                  <span className="tag">{ok ? "FEASIBLE ✅" : "REJECTED ❌"}</span>
                  <b>{c.id}</b> · {c.label}
                  <div className="hqrl-muted">
                    {c.travel_min} min · hazard {c.hazard_exposure}
                    {c.violations?.length ? ` · ${c.violations.join(", ")}` : ""}
                  </div>
                </div>
              );
            })}
            {!(state.candidates || []).length ? <p className="hqrl-muted">No route candidates yet.</p> : null}
          </div>
        </div>
        <div>
          <div className="hqrl-panel">
            <h2>QUBO safety</h2>
            <div className="hqrl-mono">
{`Candidates: ${qubo.n_candidates ?? "—"}
Closed-road: ${qubo.closed_road_violations ?? "—"}
Capacity:    ${qubo.capacity_violations ?? "—"}
Feasible:    ${qubo.feasible_routes ?? "—"}
Selected:    ${qubo.selected_route ?? "—"}`}
            </div>
          </div>
          <div className="hqrl-panel">
            <h2>QAOA simulation / classical (quantum-inspired)</h2>
            <table className="hqrl-table">
              <thead><tr><th>Solver</th><th>Feasible</th><th>ms</th></tr></thead>
              <tbody>
                <tr>
                  <td>Classical QUBO</td>
                  <td>{solver.classical?.feasible ? "Yes" : "No"}</td>
                  <td className="num">{solver.classical?.execution_ms ?? "—"}</td>
                </tr>
                <tr>
                  <td>QAOA (sim)</td>
                  <td>{solver.qaoa?.feasible ? "Yes" : "No"}</td>
                  <td className="num">{solver.qaoa?.execution_ms ?? "—"}</td>
                </tr>
              </tbody>
            </table>
            <p className="hqrl-muted">{solver.disclaimer}</p>
          </div>
          <div className="hqrl-panel">
            <h2>XAI + final route</h2>
            <div className="hqrl-mono">
{`Selected: ${xai.selected_label || state.selected_route?.label || "—"}
Risk: ${xai.risk || "—"} · Rel: ${xai.reliability_score ?? "—"}

${(xai.why_selected || []).map((w) => `✓ ${w}`).join("\n")}
${(xai.rejected || []).map((r) => `✗ ${r.id}: ${r.reason}`).join("\n")}`}
            </div>
          </div>
        </div>
      </div>

      <DynamicRlXaiPanel state={state} />

      <BenchmarkEvidence benchmark={state.benchmark} busy={benchBusy} resultsHref={RESULTS_HREF} />

      <Suspense fallback={<div className="hqrl-panel" style={{ minHeight: 60 }} />}>
        <IeeePaperPack
          pack={state.paper_pack}
          ablation={state.ablation}
          busy={benchBusy}
          defaultOpen={false}
          onExportCsv={() => hqrlExportCsv().catch((e) => setNote(e.message))}
          onExportTex={() => hqrlExportTex().catch((e) => setNote(e.message))}
        />
      </Suspense>

      {advanced}
    </div>
  );
}

export default memo(IeeeHqrlEmbed);
