import { useCallback, useEffect, useRef, useState } from "react";
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
  hqrlStart,
  hqrlState,
} from "../services/api.js";
import { connectSocket } from "../services/ws.js";
import IeeePaperPack from "./IeeePaperPack.jsx";
import BenchmarkEvidence from "./BenchmarkEvidence.jsx";
import DynamicRlXaiPanel from "./DynamicRlXaiPanel.jsx";
import { HqrlNetworkMap, HqrlResultCharts, HqrlResultsTable } from "./HqrlVisuals.jsx";
import "../pages/HqrlDemo/hqrl.css";

/**
 * IEEE HQRL research panel embedded in Scenario Lab.
 */
export default function IeeeHqrlEmbed({ sim, runMeta }) {
  const [state, setState] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [benchBusy, setBenchBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [benchN, setBenchN] = useState(10);
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

  const pull = useCallback(async () => {
    const s = await hqrlState();
    if (mountedRef.current && s && s.available !== false) setState(s);
    return s;
  }, []);

  const mapConfigFromSim = useCallback(() => {
    const rain = Number(sim?.params?.rainfall_intensity ?? sim?.history?.slice(-1)?.[0]?.rainfall_mm ?? 55);
    const traffic = Number(sim?.params?.traffic ?? 0.4);
    const blockage = Number(sim?.params?.road_blockage ?? 0);
    const cap = Number(sim?.params?.shelter_capacity_factor ?? 1);
    const flood = Math.min(0.95, Math.max(0.1, rain / 120));
    return {
      seed,
      n_groups: Math.min(12, Math.max(3, Math.round((sim?.citizens?.length || 6) / 2) || 6)),
      n_shelters: 3,
      shelter_capacity_scale: cap || 1,
      flood_severity: flood,
      traffic_level: traffic,
      n_road_closures: blockage >= 0.45 ? 2 : blockage >= 0.25 ? 1 : 0,
      vehicles_available: 8,
    };
  }, [sim?.params, sim?.citizens?.length, sim?.history?.length, seed]);

  // Sync once per scenario run id (do not depend on changing mapConfig identity)
  useEffect(() => {
    const runId = runMeta?.runId || sim?.run_id || "";
    if (!runId || bootRef.current === runId) return undefined;
    let alive = true;
    bootRef.current = runId;
    (async () => {
      setMsg("Syncing IEEE HQRL pipeline with scenario…");
      try {
        await hqrlConfigure(mapConfigFromSim());
        const s = await hqrlStart();
        if (alive && mountedRef.current) {
          setState(s);
          setMsg("HQRL live — initial route ready. Use Inject / Replan, then RUN BENCHMARK.");
        }
      } catch (err) {
        if (alive && mountedRef.current) setMsg(err.message || String(err));
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runMeta?.runId, sim?.run_id]);

  // Baseline once when no scenario run
  useEffect(() => {
    if (runMeta?.runId || sim?.run_id) return undefined;
    if (bootRef.current === "baseline") return undefined;
    let alive = true;
    bootRef.current = "baseline";
    (async () => {
      setMsg("Starting IEEE HQRL baseline…");
      try {
        await hqrlConfigure({ seed, n_groups: 6, n_shelters: 3, flood_severity: 0.35, traffic_level: 0.4 });
        const s = await hqrlStart();
        if (alive && mountedRef.current) {
          setState(s);
          setMsg("Baseline ready — RUN BENCHMARK for paper tables, or RUN SCENARIO to sync.");
        }
      } catch (err) {
        if (alive && mountedRef.current) {
          bootRef.current = "";
          setMsg(err.message || String(err));
        }
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runMeta?.runId, sim?.run_id]);

  useEffect(() => {
    pull();
  }, [pull]);

  // Always poll backend HQRL state (dynamic — no static cache)
  useEffect(() => {
    const id = setInterval(() => {
      if (!benchLock.current) pull();
    }, 2000);
    return () => clearInterval(id);
  }, [pull]);

  // Live WebSocket updates from backend
  useEffect(() => {
    const stop = connectSocket((ev) => {
      if (ev?.type === "hqrl_state" && ev.payload && !benchLock.current) {
        setState(ev.payload);
      }
    });
    return stop;
  }, []);

  // Light refresh while flood scenario ticks
  useEffect(() => {
    if (!sim || sim.status === "idle") return undefined;
    const id = setInterval(() => {
      if (!benchLock.current) pull();
    }, 5000);
    return () => clearInterval(id);
  }, [sim?.status, pull]);

  const act = async (fn, note) => {
    setActionBusy(true);
    if (note) setMsg(note);
    try {
      const s = await fn();
      if (mountedRef.current) setState(s);
      return s;
    } catch (err) {
      if (mountedRef.current) setMsg(err.message || String(err));
      throw err;
    } finally {
      if (mountedRef.current) setActionBusy(false);
    }
  };

  const runBenchmark = async () => {
    if (benchLock.current) return;
    benchLock.current = true;
    setBenchBusy(true);
    const n = Math.max(1, Math.min(Number(benchN) || 10, 50));
    setMsg(`Running IEEE benchmark: ${n} scenarios × 6 methods (seed=${seed})…`);
    try {
      const s = await hqrlBenchmark({ n_scenarios: n, seed: Number(seed) || 42 });
      if (mountedRef.current) {
        setState(s);
        if (s?.benchmark?.table?.length) {
          setMsg(`Benchmark complete — ${s.benchmark.n_scenarios} scenarios · seed ${s.benchmark.seed}. Scroll for tables & graphs.`);
        } else {
          setMsg("Benchmark returned no table — check backend logs.");
        }
      }
    } catch (err) {
      if (mountedRef.current) setMsg(`Benchmark failed: ${err.message || String(err)}`);
    } finally {
      benchLock.current = false;
      if (mountedRef.current) setBenchBusy(false);
    }
  };

  const runAblation = async () => {
    if (benchLock.current) return;
    benchLock.current = true;
    setBenchBusy(true);
    setMsg("Running ablation (RL only vs HQRL)…");
    try {
      const s = await hqrlAblation({ n_scenarios: Math.min(Number(benchN) || 10, 15), seed: Number(seed) || 42 });
      if (mountedRef.current) {
        setState(s);
        setMsg("Ablation complete — see Paper Pack contrast.");
      }
    } catch (err) {
      if (mountedRef.current) setMsg(`Ablation failed: ${err.message || String(err)}`);
    } finally {
      benchLock.current = false;
      if (mountedRef.current) setBenchBusy(false);
    }
  };

  const liveDemo = async () => {
    setActionBusy(true);
    try {
      setMsg("Live demo: initial evacuation…");
      await hqrlConfigure(mapConfigFromSim());
      let s = await hqrlStart();
      setState(s);
      await new Promise((r) => setTimeout(r, 600));
      setMsg("Injecting flood / road closure…");
      s = await hqrlInjectClosure();
      setState(s);
      await new Promise((r) => setTimeout(r, 600));
      setMsg("RL → QUBO → QAOA/classical replan…");
      s = await hqrlReplan();
      setState(s);
      s = await hqrlAccept();
      setState(s);
      setMsg("Shelter capacity event…");
      s = await hqrlInjectShelterFull();
      setState(s);
      s = await hqrlReplan();
      setState(s);
      setMsg("Dynamic replan complete — RUN BENCHMARK for paper results.");
    } catch (err) {
      setMsg(err.message || String(err));
    } finally {
      setActionBusy(false);
    }
  };

  const locked = actionBusy || benchBusy;

  if (!state) {
    return (
      <div className="panel hqrl-demo" style={{ padding: 14 }}>
        <h2>IEEE HQRL — PAPER DEMO (SCENARIO LAB)</h2>
        <p className="hqrl-muted">{msg || "Loading research pipeline…"}</p>
        <div className="actions" style={{ marginTop: 8 }}>
          <button type="button" className="primary" disabled={locked} onClick={liveDemo}>
            START IEEE PIPELINE
          </button>
          <button type="button" disabled={benchBusy} onClick={runBenchmark}>
            {benchBusy ? "RUNNING BENCHMARK…" : "RUN BENCHMARK"}
          </button>
        </div>
      </div>
    );
  }

  const qubo = state.qubo_panel || {};
  const solver = state.solver_panel || {};
  const xai = state.xai || {};
  const bench = state.benchmark;
  const tb = state.topbar || {};

  return (
    <div className="panel hqrl-demo ieee-embed" style={{ padding: 14 }}>
      <div className="status-row" style={{ flexWrap: "wrap", gap: 8 }}>
        <h2 style={{ margin: 0 }}>IEEE HQRL — LIVE RESEARCH DEMO</h2>
        <span className="hqrl-badge">SYNTHETIC · seed {state.seed}</span>
      </div>
      <p className="hqrl-muted" style={{ marginTop: 6 }}>
        Linked to Scenario Lab. RL candidates → QUBO safety → simulated QAOA / classical → XAI → human loop → dynamic
        replan. No quantum speedup claimed.
      </p>
      <div className="hqrl-badge" style={{ marginBottom: 8 }}>
        {(state.data_mode && state.data_mode.mode) || "DYNAMIC_BACKEND_ONLY"} · live poll 2s · websocket hqrl_state
      </div>

      {msg ? <div className="hqrl-notify info"><strong>STATUS</strong>{msg}</div> : null}
      {state.notification ? (
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

      <div className="hqrl-controls">
        <button type="button" className="primary" disabled={locked} onClick={liveDemo}>RUN LIVE DEMO</button>
        <button type="button" className="warn" disabled={locked} onClick={() => act(hqrlInjectClosure, "Road closure injected")}>Inject Road Closure</button>
        <button type="button" className="warn" disabled={locked} onClick={() => act(hqrlInjectConflict, "Sensor conflict")}>Inject Sensor Conflict</button>
        <button type="button" className="danger" disabled={locked} onClick={() => act(hqrlInjectShelterFull, "Shelter full")}>Shelter Full</button>
        <button type="button" disabled={locked} onClick={() => act(hqrlReplan, "Replanning…")}>Replan</button>
        <button type="button" className="primary" disabled={locked} onClick={() => act(hqrlAccept)}>Accept Route</button>
        <label className="hqrl-muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          Seed
          <input type="number" style={{ width: 72 }} value={seed} disabled={benchBusy} onChange={(e) => setSeed(Number(e.target.value))} />
        </label>
        <label className="hqrl-muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          N
          <input type="number" style={{ width: 64 }} value={benchN} disabled={benchBusy} onChange={(e) => setBenchN(Number(e.target.value))} />
        </label>
        <button type="button" className="primary" disabled={benchBusy} onClick={runBenchmark}>
          {benchBusy ? "RUNNING BENCHMARK…" : "RUN BENCHMARK"}
        </button>
        <button type="button" disabled={benchBusy} onClick={() => hqrlExportDownload().catch((e) => setMsg(e.message))}>Export Results</button>
      </div>

      <div className="hqrl-layout" style={{ marginTop: 8 }}>
        <div>
          <HqrlNetworkMap map={state.map} selected={state.selected_route} candidates={state.candidates} />
          <div className="hqrl-panel" style={{ marginTop: 10 }}>
            <h2>PPO candidates (safety later)</h2>
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
            <h2>QAOA / Classical (simulated)</h2>
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

      <BenchmarkEvidence
        benchmark={bench}
        busy={benchBusy}
        seed={seed}
        nScenarios={benchN}
        onSeed={setSeed}
        onN={setBenchN}
        onRun={runBenchmark}
      />

      {bench ? (
        <div className="hqrl-panel" style={{ marginTop: 10 }}>
          <h2>Result tables & mixed charts</h2>
          <p className="hqrl-muted">Backend-computed synthetic results · bars / line / area / radar</p>
          <HqrlResultsTable table={bench.table || []} />
          <HqrlResultCharts graphs={bench.graphs} />
        </div>
      ) : null}

      <IeeePaperPack
        pack={state.paper_pack}
        ablation={state.ablation}
        busy={benchBusy}
        onAblation={runAblation}
        onExportCsv={() => hqrlExportCsv().catch((e) => setMsg(e.message))}
        onExportTex={() => hqrlExportTex().catch((e) => setMsg(e.message))}
      />
    </div>
  );
}
