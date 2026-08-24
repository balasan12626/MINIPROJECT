import { HqrlResultCharts, HqrlResultsTable } from "./HqrlVisuals.jsx";

/**
 * Explains how IEEE benchmark works + shows results / evidence / outputs.
 */
export default function BenchmarkEvidence({ benchmark, busy, onRun, seed, nScenarios, onSeed, onN }) {
  const table = benchmark?.table || [];
  const scenarios = benchmark?.scenarios || [];
  const defs = benchmark?.metric_definitions || {};
  const bestSafe = table.length
    ? [...table].sort((a, b) => b.safe_evacuation_pct - a.safe_evacuation_pct)[0]
    : null;
  const lowestUnsafe = table.length
    ? [...table].sort((a, b) => a.unsafe_route_pct - b.unsafe_route_pct)[0]
    : null;

  return (
    <div className="hqrl-panel benchmark-evidence">
      <h2>Benchmark — how it works · evidence · output</h2>

      <div className="hqrl-layout" style={{ marginTop: 8 }}>
        <div className="hqrl-panel">
          <h2>1 · Procedure (reproducible)</h2>
          <ol className="hqrl-muted" style={{ paddingLeft: 18, lineHeight: 1.55, margin: 0 }}>
            <li>Fix random <b>seed</b> (shown on every run).</li>
            <li>Generate <b>N synthetic flood scenarios</b>.</li>
            <li>Inject a mid-run road closure (forces replanning).</li>
            <li>Run all <b>6 methods</b> on the identical scenario set.</li>
            <li>Score with shared metric definitions — computed, not hard-coded.</li>
          </ol>
        </div>

        <div className="hqrl-panel">
          <h2>2 · Evidence rules</h2>
          <ul className="hqrl-check">
            <li className="pass">✓ Same seed → same synthetic outcomes</li>
            <li className="pass">✓ Same scenarios for every method</li>
            <li className="pass">✓ QAOA labeled simulated (no speedup claim)</li>
            <li className="fail">✗ No fabricated paper numbers</li>
          </ul>
          <h3>Metric definitions</h3>
          <div className="hqrl-mono" style={{ maxHeight: 140, overflow: "auto" }}>
            {Object.keys(defs).length
              ? Object.entries(defs).map(([k, v]) => (
                  <div key={k}><b>{k}</b>: {v}</div>
                ))
              : <div>Run benchmark to load metric definitions from backend.</div>}
          </div>
        </div>
      </div>

      <div className="hqrl-controls" style={{ marginTop: 10 }}>
        <label className="hqrl-muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          Seed
          <input type="number" style={{ width: 80 }} value={seed} onChange={(e) => onSeed?.(Number(e.target.value))} />
        </label>
        <label className="hqrl-muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          Scenarios (N)
          <input type="number" style={{ width: 72 }} value={nScenarios} onChange={(e) => onN?.(Number(e.target.value))} />
        </label>
        <button type="button" className="primary" disabled={busy} onClick={onRun}>
          {busy ? "RUNNING BENCHMARK…" : "RUN BENCHMARK NOW"}
        </button>
      </div>

      {benchmark ? (
        <div style={{ marginTop: 12 }}>
          <div className="hqrl-notify info">
            <strong>3 · OUTPUT EVIDENCE</strong>
            Synthetic Simulation Results · N={benchmark.n_scenarios} · seed={benchmark.seed}
            <div style={{ marginTop: 6 }}>{benchmark.disclaimer}</div>
          </div>

          <div className="grid-3" style={{ marginTop: 10 }}>
            <div className="metric">
              <span>Best safe evacuation</span>
              <b>{bestSafe ? `${bestSafe.method}` : "—"}</b>
              <small className="hint">{bestSafe ? `${bestSafe.safe_evacuation_pct}%` : ""}</small>
            </div>
            <div className="metric">
              <span>Lowest unsafe routes</span>
              <b>{lowestUnsafe ? `${lowestUnsafe.method}` : "—"}</b>
              <small className="hint">{lowestUnsafe ? `${lowestUnsafe.unsafe_route_pct}%` : ""}</small>
            </div>
            <div className="metric">
              <span>Scenarios completed</span>
              <b>{scenarios.filter((s) => s.ok).length}/{benchmark.n_scenarios}</b>
            </div>
          </div>

          <h3 style={{ marginTop: 12 }}>Comparison table</h3>
          <HqrlResultsTable table={table} />
          <h3 style={{ marginTop: 12 }}>Mixed charts (bar · line · area · radar)</h3>
          <HqrlResultCharts graphs={benchmark.graphs} />

          <h3>Scenario run log</h3>
          <div className="hqrl-scenario-log">
            {scenarios.map((s) => (
              <span key={s.id} className={`hqrl-scenario-chip ${s.ok ? "ok" : "bad"}`}>
                #{String(s.id).padStart(2, "0")} · seed {s.seed} {s.ok ? "✓" : "✗"}
              </span>
            ))}
          </div>
        </div>
      ) : (
        <p className="hqrl-muted" style={{ marginTop: 10 }}>
          No benchmark output yet. Click <b>RUN BENCHMARK NOW</b>.
        </p>
      )}
    </div>
  );
}
