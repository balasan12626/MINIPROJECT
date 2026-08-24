import { useState } from "react";

/**
 * IEEE / M.Tech submission helpers shown on the simulation route.
 */
export default function IeeePaperPack({ pack, ablation, onAblation, onExportCsv, onExportTex, busy }) {
  const [open, setOpen] = useState(true);
  if (!pack && !ablation) return null;

  const contrib = pack?.contributions || [];
  const non = pack?.non_claims || [];
  const viva = pack?.viva_script || [];
  const metrics = pack?.metric_definitions || {};

  return (
    <div className="hqrl-panel ieee-paper-pack">
      <div className="status-row" style={{ flexWrap: "wrap", gap: 8 }}>
        <h2 style={{ margin: 0 }}>IEEE / M.TECH PAPER PACK</h2>
        <button type="button" onClick={() => setOpen((v) => !v)}>{open ? "Hide" : "Show"}</button>
      </div>
      {!open ? null : (
        <>
          <p className="hqrl-muted" style={{ marginTop: 8 }}>
            Use this block in your viva: contribution story, honest non-claims, ablation contrast, and exportable
            tables for the thesis/IEEE paper.
          </p>

          <div className="hqrl-layout" style={{ marginTop: 8 }}>
            <div className="hqrl-panel">
              <h2>Claimed contributions</h2>
              <ul className="hqrl-check">
                {contrib.map((c) => (
                  <li key={c} className="pass">✓ {c}</li>
                ))}
              </ul>
              <h3>Explicit non-claims</h3>
              <ul className="hqrl-check">
                {non.map((c) => (
                  <li key={c} className="fail">✗ {c}</li>
                ))}
              </ul>
            </div>
            <div className="hqrl-panel">
              <h2>Viva demo script (3–5 min)</h2>
              <ol className="hqrl-muted" style={{ paddingLeft: 18, lineHeight: 1.55 }}>
                {viva.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ol>
              <h3>Metric definitions</h3>
              <div className="hqrl-mono" style={{ maxHeight: 160, overflow: "auto" }}>
                {Object.entries(metrics).map(([k, v]) => (
                  <div key={k}><b>{k}</b>: {v}</div>
                ))}
              </div>
            </div>
          </div>

          <div className="hqrl-panel" style={{ marginTop: 10 }}>
            <div className="status-row" style={{ flexWrap: "wrap", gap: 8 }}>
              <h2 style={{ margin: 0 }}>Ablation — without safety vs HQRL</h2>
              <button type="button" className="primary" disabled={busy} onClick={onAblation}>
                {busy ? "RUNNING…" : "RUN ABLATION"}
              </button>
              <button type="button" disabled={busy} onClick={onExportCsv}>Export CSV</button>
              <button type="button" disabled={busy} onClick={onExportTex}>Export LaTeX table</button>
            </div>
            {ablation ? (
              <>
                <p className="hqrl-muted">{ablation.takeaway}</p>
                <p className="hqrl-muted">
                  n={ablation.n_scenarios} · seed={ablation.seed}
                </p>
                <div className="hqrl-charts">
                  <div className="hqrl-panel" style={{ borderColor: "rgba(232,93,108,0.45)" }}>
                    <h2>WITHOUT safety layer</h2>
                    <div className="hqrl-mono">
{`${ablation.without_safety?.name}
Safe %:     ${ablation.without_safety?.safe_evacuation_pct}
Unsafe %:   ${ablation.without_safety?.unsafe_route_pct}
Capacity v: ${ablation.without_safety?.capacity_violations}
Clearance:  ${ablation.without_safety?.clearance_time_min} min

${ablation.without_safety?.story}`}
                    </div>
                  </div>
                  <div className="hqrl-panel" style={{ borderColor: "rgba(62,207,142,0.45)" }}>
                    <h2>WITH HQRL</h2>
                    <div className="hqrl-mono">
{`${ablation.with_hqrl?.name}
Safe %:     ${ablation.with_hqrl?.safe_evacuation_pct}
Unsafe %:   ${ablation.with_hqrl?.unsafe_route_pct}
Capacity v: ${ablation.with_hqrl?.capacity_violations}
Clearance:  ${ablation.with_hqrl?.clearance_time_min} min

Δ Safe %:   ${ablation.delta?.safe_evacuation_pct}
Δ Unsafe %: ${ablation.delta?.unsafe_route_pct}

${ablation.with_hqrl?.story}`}
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <p className="hqrl-muted" style={{ marginTop: 8 }}>
                Run ablation to show examiners why QUBO safety matters versus RL alone.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
