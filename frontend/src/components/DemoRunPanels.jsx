import { memo, useEffect, useState } from "react";
import { overrideSimulation, askSimAgent, setSimChecklist, forceDispatch, fetchSources, fetchMetrics } from "../services/api.js";

function DemoRunPanels({ sim, feats, explain, setSim }) {
  const [askQ, setAskQ] = useState("What is status?");
  const [askA, setAskA] = useState("");
  const [askStats, setAskStats] = useState(null);
  const [askBusy, setAskBusy] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("flood_theme") || "dark");
  const [sources, setSources] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [whatIf, setWhatIf] = useState(null);
  const dual = sim?.pipeline?.prediction?.dual || {};
  const latencies = sim?.pipeline?.latencies || {};

  useEffect(() => {
    if (!feats.theme_toggle) return;
    document.body.classList.toggle("light-theme", theme === "light");
    localStorage.setItem("flood_theme", theme);
    window.dispatchEvent(new CustomEvent("flood-theme", { detail: theme }));
  }, [theme, feats.theme_toggle]);

  useEffect(() => {
    function sync(e) {
      if (e.detail) setTheme(e.detail);
    }
    window.addEventListener("flood-theme", sync);
    return () => window.removeEventListener("flood-theme", sync);
  }, []);

  useEffect(() => {
    document.body.classList.toggle("jury-mode", Boolean(feats.jury_mode));
    return () => document.body.classList.remove("jury-mode");
  }, [feats.jury_mode]);

  // Once per status change (start / complete), not once per tick — per-tick
  // latencies already arrive in sim.pipeline.latencies.
  useEffect(() => {
    if (feats.api_health) fetchSources().then(setSources).catch(() => {});
    if (feats.latency_meter) fetchMetrics().then(setMetrics).catch(() => {});
  }, [feats.api_health, feats.latency_meter, sim?.status]);

  useEffect(() => {
    if (!feats.scenario_compare || !sim?.run_id || sim?.status !== "completed") return;
    // Canonical run peak from the backend (current_view) — not recomputed here.
    const peak = sim?.current?.peak_flood_probability ?? null;
    const entry = {
      run_id: sim.run_id,
      scenario: sim.scenario,
      peak_p: peak,
      sos: (sim.citizens || []).length,
      rescued: (sim.contact_log || []).filter((r) => r.rescued === "yes").length,
      at: new Date().toISOString(),
    };
    const prev = JSON.parse(sessionStorage.getItem("flood_run_compare") || "[]");
    if (!prev.find((p) => p.run_id === entry.run_id)) {
      sessionStorage.setItem("flood_run_compare", JSON.stringify([entry, ...prev].slice(0, 4)));
    }
  }, [sim?.status, sim?.run_id, feats.scenario_compare]);

  async function ask(question) {
    const q = typeof question === "string" ? question : askQ;
    if (typeof question === "string") setAskQ(question);
    setAskBusy(true);
    try {
      const res = await askSimAgent(q);
      setAskA(res.answer || res.message || "No answer");
      setAskStats(res.stats || null);
    } finally {
      setAskBusy(false);
    }
  }

    const ASK_CHIPS = [
    "What is status?",
    "How many citizens?",
    "How many shelters?",
    "How many vacant seats?",
    "Who is missing?",
    "Who declined?",
    "Which ambulance accepted?",
    "Who not rescued yet?",
    "Any mistakes?",
    "Who is first?",
  ];

  function toggleCheck(id) {
    const next = (sim?.checklist || []).map((c) => (c.id === id ? { ...c, done: !c.done } : c));
    setSimChecklist(next).then(setSim);
  }

  const compare = (() => {
    try {
      return JSON.parse(sessionStorage.getItem("flood_run_compare") || "[]");
    } catch {
      return [];
    }
  })();

  return (
    <>
      {feats.transfer_warning ? (
        <div className="panel transfer-banner">
          <h2>TRANSFER WARNING</h2>
          <p className="hint">{sim?.transfer_warning || "Model trained on INDOFLOODS (Indonesia), applied to Delhi Yamuna floodplain."}</p>
        </div>
      ) : null}

      {feats.theme_toggle ? (
        <div className="panel">
          <h2>PRESENTATION THEME</h2>
          <div className="actions">
            <button type="button" className={theme === "dark" ? "primary" : ""} onClick={() => setTheme("dark")}>Dark</button>
            <button type="button" className={theme === "light" ? "primary" : ""} onClick={() => setTheme("light")}>Light</button>
          </div>
        </div>
      ) : null}

      {feats.api_health ? (
        <div className="panel">
          <h2>LIVE API HEALTH</h2>
          <div className="status-row">
            {(sources?.live_apis || []).map((s) => (
              <span key={s.id} className={`badge ${(s.ok || s.available || s.keyed !== false) ? "live" : "warn"}`}>
                {s.id}: {s.keyed === false ? "OK" : s.keyed ? "KEYED" : "CHECK"}
              </span>
            ))}
            {!sources?.live_apis?.length ? <span className="hint">Loading sources…</span> : null}
          </div>
        </div>
      ) : null}

      {feats.latency_meter ? (
        <div className="panel">
          <h2>LATENCY METER (ms)</h2>
          <div className="metric"><span>Ingest</span><b>{latencies.ingestion ?? metrics?.ingestion ?? "—"}</b></div>
          <div className="metric"><span>ML</span><b>{latencies.ml ?? metrics?.ml ?? "—"}</b></div>
          <div className="metric"><span>Agent</span><b>{latencies.agent ?? metrics?.agent ?? "—"}</b></div>
          <div className="metric"><span>End-to-end</span><b>{latencies.end_to_end ?? metrics?.end_to_end ?? "—"}</b></div>
        </div>
      ) : null}

      {feats.confidence_band && sim?.confidence?.available ? (
        <div className="panel">
          <h2>CONFIDENCE / UNCERTAINTY BAND</h2>
          <p className="hint">{sim.confidence.message}</p>
          <div className="metric"><span>Low</span><b>{pct(sim.confidence.low)}</b></div>
          <div className="metric"><span>Mid</span><b>{pct(sim.confidence.mid)}</b></div>
          <div className="metric"><span>High</span><b>{pct(sim.confidence.high)}</b></div>
        </div>
      ) : null}

      {/* Citizen Status Board + ETA per citizen are merged into the Live SOS
          roster (RescueOpsPanel) as expandable row details — one table. */}

      {feats.shelter_board ? (
        <div className="panel">
          <h2>SHELTER CAPACITY BOARD</h2>
          {(sim?.shelter_board || []).map((s) => (
            <div className={`metric ${s.full ? "full-shelter" : ""}`} key={s.shelter_id}>
              <span>{s.name || s.shelter_id}</span>
              <b className={s.full ? "crit-text" : ""}>
                {s.seats_left} seats left / {s.capacity}
                {s.used_this_run ? ` · delivered this run ${s.delivered_this_run ?? 0}` : ""}
              </b>
            </div>
          ))}
        </div>
      ) : null}

      {feats.disagreement_debate ? (
        <div className="panel">
          <h2>AGENT DISAGREEMENT DEBATE</h2>
          {!dual.disagree ? <p className="hint">Models agree enough — debate stays calm.</p> : (
            <p className="counterfactual">RF {pct(dual.random_forest)} vs XGBoost {pct(dual.xgboost)} — hold until override.</p>
          )}
          <div className="talk-log" style={{ maxHeight: 220 }}>
            {(sim?.disagreement_debate || []).map((t, i) => (
              <div className={`talk-bubble ${i % 2 ? "right" : "left"}`} key={`deb-${i}`}>
                <div className="talk-meta">{t.from} → {t.to}</div>
                <div>{t.text}</div>
              </div>
            ))}
          </div>
          {dual.disagree && !sim?.human_dispatch_override ? (
            <button className="primary" type="button" style={{ marginTop: 8 }} onClick={() => forceDispatch().then(setSim)}>
              Human override — allow dispatch
            </button>
          ) : null}
        </div>
      ) : null}

      {feats.ask_agent ? (
        <div className="panel">
          <h2>ASK THE AGENT</h2>
          <p className="hint">Click a question or type your own — answers include citizens, shelters, vacant seats, missing, and mistakes.</p>
          <div className="ask-chips" role="radiogroup" aria-label="Quick questions">
            {ASK_CHIPS.map((chip) => (
              <label key={chip} className={`radio-pill ${askQ === chip ? "active" : ""}`}>
                <input
                  type="radio"
                  name="ask-chip"
                  checked={askQ === chip}
                  onChange={() => ask(chip)}
                />
                {chip}
              </label>
            ))}
          </div>
          <div className="form-grid">
            <label>Question
              <input value={askQ} onChange={(e) => setAskQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask()} />
            </label>
          </div>
          <div className="actions" style={{ marginTop: 8 }}>
            <button className="primary" type="button" disabled={askBusy} onClick={() => ask()}>{askBusy ? "Asking…" : "Ask"}</button>
          </div>
          {askStats ? (
            <div className="ask-stats scenario-preview" style={{ marginTop: 12 }}>
              <div className="metric"><span>Citizens</span><b>{askStats.citizens ?? "—"}</b></div>
              <div className="metric"><span>Rescued</span><b>{askStats.rescued ?? "—"}</b></div>
              <div className="metric"><span>Missing / trapped</span><b>{askStats.missing ?? "—"}</b></div>
              <div className="metric"><span>Shelters</span><b>{askStats.shelters ?? "—"}</b></div>
              <div className="metric"><span>Vacant seats</span><b>{sim?.shelter_totals?.vacant_seats ?? askStats.vacant_seats ?? "—"}</b></div>
              <div className="metric"><span>Full shelters</span><b>{askStats.full_shelters ?? "—"}</b></div>
            </div>
          ) : null}
          {askA ? <pre className="ask-answer">{askA}</pre> : null}
          {askStats?.mistakes?.length ? (
            <div className="counterfactual" style={{ marginTop: 10 }}>
              {(askStats.mistakes || []).map((m, i) => <div key={i}>{m}</div>)}
            </div>
          ) : null}
        </div>
      ) : null}

      {feats.after_action_summary ? (
        <div className="panel">
          <h2>AUTO AFTER-ACTION SUMMARY</h2>
          <ol className="summary-list">
            {(sim?.after_action_summary || []).map((line, i) => <li key={i}>{line}</li>)}
          </ol>
          {!(sim?.after_action_summary || []).length ? <p className="hint">Summary fills as the run progresses / completes.</p> : null}
        </div>
      ) : null}

      {feats.operator_checklist ? (
        <div className="panel">
          <h2>OPERATOR CHECKLIST</h2>
          {(sim?.checklist || []).map((c) => (
            <label key={c.id} className="check-row">
              <input type="checkbox" checked={Boolean(c.done)} onChange={() => toggleCheck(c.id)} />
              <span>{c.label}</span>
            </label>
          ))}
        </div>
      ) : null}

      {feats.false_alarm_drill && sim?.false_alarm?.active ? (
        <div className="panel">
          <h2>FALSE-ALARM DRILL</h2>
          <p className="counterfactual">{sim.false_alarm.message}</p>
        </div>
      ) : null}

      {feats.road_blockage_impact ? (
        <div className="panel">
          <h2>ROAD BLOCKAGE IMPACT</h2>
          {(sim?.blocked_roads || []).length ? (sim.blocked_roads || []).map((r) => (
            <div className="metric" key={r.road_id}><span>{r.name || r.road_id}</span><b>{r.reason}</b></div>
          )) : <p className="hint">No blocked roads yet — blockage grows with the scenario.</p>}
        </div>
      ) : null}

      {feats.scenario_compare ? (
        <div className="panel">
          <h2>SCENARIO COMPARISON (A vs B)</h2>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr><th>Run</th><th>Scenario</th><th>Peak P</th><th>SOS</th><th>Rescued</th></tr>
              </thead>
              <tbody>
                {compare.map((r) => (
                  <tr key={r.run_id}>
                    <td>{r.run_id}</td>
                    <td>{r.scenario}</td>
                    <td>{r.peak_p != null ? `${(r.peak_p * 100).toFixed(1)}%` : "—"}</td>
                    <td>{r.sos}</td>
                    <td>{r.rescued}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!compare.length ? <p className="hint">Complete a run to store it for comparison.</p> : null}
          </div>
        </div>
      ) : null}

      {feats.whatif_rain ? (
        <div className="panel">
          <h2>WHAT-IF RAINFALL</h2>
          <p className="hint">Drag rain (mm). Commits into the live card override so P / SHAP update.</p>
          <input
            type="range"
            min={5}
            max={200}
            value={whatIf ?? Math.round(sim?.history?.[(sim.history?.length || 1) - 1]?.rainfall_mm || 55)}
            onChange={(e) => setWhatIf(Number(e.target.value))}
            onMouseUp={(e) => overrideSimulation({ rainfall_mm: Number(e.target.value) }).then(setSim)}
            onTouchEnd={(e) => overrideSimulation({ rainfall_mm: Number(e.target.value) }).then(setSim)}
          />
          <div className="metric"><span>What-if rain</span><b>{whatIf ?? Math.round(sim?.history?.[(sim.history?.length || 1) - 1]?.rainfall_mm || 55)} mm</b></div>
        </div>
      ) : null}
    </>
  );
}

function pct(p) {
  return p == null ? "n/a" : `${(p * 100).toFixed(1)}%`;
}

export default memo(DemoRunPanels);
