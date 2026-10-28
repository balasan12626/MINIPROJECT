import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartTheme } from "../../config/chartTheme.js";
import StoredResultCard from "./StoredResultCard.jsx";

const f1 = (v) => (v == null ? "—" : Number(v).toFixed(1));
const pct = (v) => (v == null ? "—" : `${(Number(v) * 100).toFixed(1)}%`);
const f3 = (v) => (v == null ? "—" : Number(v).toFixed(3));

/** F34 — hindsight regret of stored runs (the bound is a lower bound, NOT achievable live). */
export function RegretCard() {
  return (
    <StoredResultCard name="ops_regret_v1" title="Hindsight check of past runs (regret)" perCity={false}>
      {(d) => (
        <>
          <p className="hint">
            <b>Hindsight bound:</b> {d.hindsight_bound} Regret = mean time to safety − mean bound (simulated minutes).
          </p>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>City</th>
                  <th>SOS</th>
                  <th>Bound</th>
                  <th>Recorded (regret)</th>
                  <th>Replayed first free / greedy / optimal</th>
                  <th>Replay fidelity</th>
                </tr>
              </thead>
              <tbody>
                {(d.runs || []).map((r) => (
                  <tr key={r.run_id}>
                    <td>{r.run_id}</td>
                    <td>{r.city}</td>
                    <td>{r.people}</td>
                    <td>{f1(r.hindsight_bound_mean_min)}</td>
                    <td>
                      {f1(r.recorded?.mean_min)} ({f1(r.recorded?.regret_min)})
                    </td>
                    <td>
                      {["first_free", "greedy", "optimal"].map((p) => f1(r.replayed?.[p]?.mean_min)).join(" / ")}
                      {r.best_policy_in_hindsight ? ` · best: ${r.best_policy_in_hindsight}` : ""}
                    </td>
                    <td>
                      {r.fidelity?.mean_abs_diff_min != null
                        ? `±${f1(r.fidelity.mean_abs_diff_min)} min (${r.fidelity.policy})`
                        : r.fidelity?.policy}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(d.notes || []).map((n) => (
            <p className="hint" key={n}>
              {n}
            </p>
          ))}
          <p className="hint">Regenerate: python scripts/regret_runs.py</p>
        </>
      )}
    </StoredResultCard>
  );
}

/** F33 — tornado: change in mean time to safety at the low / high end of each assumption's stated range. */
export function SensitivityCard() {
  return (
    <StoredResultCard name="ops_sensitivity_v1" title="Which assumptions matter — sensitivity (tornado)">
      {(d) => {
        const rows = (d.tornado || []).map((r) => ({ name: r.parameter, low: r.effect_low_min, high: r.effect_high_min }));
        return (
          <>
            <p className="hint">
              Baseline mean time to safety {f1(d.baseline?.mean_time_to_safety_min)} min ({d.settings?.runs} synthetic operations in {d.city},
              policy {d.settings?.policy}). Bars = change when one assumption moves to the end of its range; everything else at default.
            </p>
            <div style={{ width: "100%", height: Math.max(160, 34 * rows.length + 40) }}>
              <ResponsiveContainer>
                <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
                  <CartesianGrid {...chartTheme.grid} />
                  <XAxis type="number" {...chartTheme.axis} unit=" min" />
                  <YAxis type="category" dataKey="name" width={170} {...chartTheme.axis} />
                  <Tooltip {...chartTheme.tooltip} />
                  <Legend />
                  <ReferenceLine x={0} stroke="var(--axis)" />
                  <Bar dataKey="low" name="at low end" fill={chartTheme.series?.[0]} isAnimationActive={false} />
                  <Bar dataKey="high" name="at high end" fill={chartTheme.series?.[1]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Assumption</th>
                  <th>Range (default)</th>
                  <th>Why this range</th>
                </tr>
              </thead>
              <tbody>
                {(d.tornado || []).map((r) => (
                  <tr key={r.parameter}>
                    <td>{r.parameter}</td>
                    <td>
                      {r.low} – {r.high} ({r.default})
                    </td>
                    <td>{r.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {d.sobol ? (
              <p className="hint">
                Sobol (N={d.sobol.n_base}):{" "}
                {d.sobol.indices.map((s) => `${s.parameter} S1 ${s.S1} [${s.S1_ci95.join(", ")}], ST ${s.ST}`).join(" · ")}. {d.sobol.note}
              </p>
            ) : null}
            <p className="hint">Not varied: {Object.entries(d.not_varied || {}).map(([k, v]) => `${k} — ${v}`).join("; ")}</p>
          </>
        );
      }}
    </StoredResultCard>
  );
}

/** F32 — measured fair-vs-fast curve: mean time to safety vs worst group's median (with 95 % CI). */
export function FairnessCurveCard() {
  return (
    <StoredResultCard name="ops_fairness_v1" title="Fair vs fast dispatch — measured trade-off">
      {(d) => (
        <>
          <p className="hint">
            {d.settings?.runs} synthetic operations in {d.city}; every point replays the same operations. Worst group ={" "}
            {d.settings?.worst_group}.
          </p>
          <table className="data-table">
            <thead>
              <tr>
                <th>Policy</th>
                <th>Mean time to safety [95% CI]</th>
                <th>Worst group&apos;s median [95% CI]</th>
                <th>Served</th>
              </tr>
            </thead>
            <tbody>
              {(d.curve || []).map((p) => (
                <tr key={p.point}>
                  <td>{p.point}</td>
                  <td>
                    {f1(p.mean_time_to_safety_min?.mean)} [{f1(p.mean_time_to_safety_min?.ci95?.[0])}, {f1(p.mean_time_to_safety_min?.ci95?.[1])}]
                  </td>
                  <td>
                    {f1(p.worst_group_median_min?.mean)} [{f1(p.worst_group_median_min?.ci95?.[0])}, {f1(p.worst_group_median_min?.ci95?.[1])}]
                  </td>
                  <td>
                    {p.served} / {p.people}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(d.notes || []).map((n) => (
            <p className="hint" key={n}>
              {n}
            </p>
          ))}
        </>
      )}
    </StoredResultCard>
  );
}

/** F25 — 72 h operation with vs without (assumed) crew rules. */
export function LongRunCard() {
  return (
    <StoredResultCard name="ops_long_v1" title="Long operation (72 h) — time to safety with vs without crew limits">
      {(d) => {
        const on = d.summary?.crew_rules_on;
        const off = d.summary?.crew_rules_off;
        const p = d.paired_on_vs_off?.crew_rules_on;
        return (
          <>
            <p className="hint">
              {d.settings?.runs} synthetic {d.settings?.hours} h operations in {d.city} ({d.settings?.sos_per_hour} SOS / h,{" "}
              {d.settings?.ambulances} ambulances, policy {d.settings?.policy}). {d.crew_rules_source}
            </p>
            <table className="data-table">
              <thead>
                <tr>
                  <th />
                  <th>Served</th>
                  <th>Time to safety mean / p50 / p90</th>
                </tr>
              </thead>
              <tbody>
                {[["Unlimited crews", off], ["Crew rules on", on]].map(([label, s]) => (
                  <tr key={label}>
                    <td>{label}</td>
                    <td>
                      {s?.served} / {s?.people}
                    </td>
                    <td>
                      {f1(s?.time_to_safety_min?.mean)} / {f1(s?.time_to_safety_min?.p50)} / {f1(s?.time_to_safety_min?.p90)} min
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {p ? (
              <p className="hint">
                Paired difference (rules on − off): {p.mean_diff_min > 0 ? "+" : ""}
                {f1(p.mean_diff_min)} min [95% CI {f1(p.ci95_min[0])}, {f1(p.ci95_min[1])}] over {p.runs} runs.
              </p>
            ) : null}
          </>
        );
      }}
    </StoredResultCard>
  );
}

/** F23 — SOS avoided vs ASSUMED early-warning compliance (a curve, never one number). */
export function WarningSweepCard() {
  return (
    <StoredResultCard name="ops_warning_sweep_v1" title="Early zone warnings — SOS avoided vs assumed compliance">
      {(d) => {
        const rows = (d.curve || []).map((p) => ({
          c: `${Math.round(p.compliance * 100)}%`,
          avoided: p.sos_avoided_per_run,
          mean: p.time_to_safety_min?.mean,
        }));
        return (
          <>
            <p className="hint">
              {d.settings?.runs} synthetic operations in {d.city}, policy {d.settings?.policy}, warning lead {d.settings?.warning_lead_sim_min} sim
              min. Compliance is <b>assumed, not measured</b> — read the whole curve.
            </p>
            <div style={{ width: "100%", height: 220 }}>
              <ResponsiveContainer>
                <LineChart data={rows} margin={{ left: 4, right: 12, top: 6, bottom: 4 }}>
                  <CartesianGrid {...chartTheme.grid} />
                  <XAxis dataKey="c" {...chartTheme.axis} />
                  <YAxis yAxisId="a" {...chartTheme.axis} width={40} />
                  <YAxis yAxisId="m" orientation="right" {...chartTheme.axis} width={48} unit=" min" />
                  <Tooltip {...chartTheme.tooltip} />
                  <Legend />
                  <Line yAxisId="a" dataKey="avoided" name="SOS avoided per run" stroke={chartTheme.series?.[0]} isAnimationActive={false} />
                  <Line yAxisId="m" dataKey="mean" name="mean time to safety" stroke={chartTheme.series?.[1]} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Compliance (assumed)</th>
                  <th>SOS avoided / run</th>
                  <th>Time to safety mean / p90</th>
                  <th>Total wait / run</th>
                </tr>
              </thead>
              <tbody>
                {(d.curve || []).map((p) => (
                  <tr key={p.compliance}>
                    <td>{Math.round(p.compliance * 100)}%</td>
                    <td>{f1(p.sos_avoided_per_run)}</td>
                    <td>
                      {f1(p.time_to_safety_min?.mean)} / {f1(p.time_to_safety_min?.p90)} min
                    </td>
                    <td>{f1(p.total_wait_min_per_run)} min</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(d.notes || []).map((n) => (
              <p className="hint" key={n}>
                {n}
              </p>
            ))}
          </>
        );
      }}
    </StoredResultCard>
  );
}

/** F35 — AI assistant accuracy evaluation (grounded vs ablation). */
export function AiEvalCard() {
  return (
    <StoredResultCard name="ai_eval_v1" title="AI Assistant accuracy evaluation (grounded vs ablation)" perCity={false}>
      {(d) => {
        const prod = d.with_grounding || {};
        const raw = d.without_grounding_ablation || {};
        const cats = prod.by_category || {};
        return (
          <>
            <p className="hint">
              Evaluated {d.total_questions} questions against {d.model} with seed {d.seed}.
              Production system enforces grounding checks (hallucinated figures rejected → rules fallback).
            </p>
            <div className="grid-3 output-kpi-row" style={{ marginBottom: "1rem" }}>
              <div className="card kpi">
                <span className="kpi-label">Production Accuracy</span>
                <b className="kpi-value">{prod.accuracy_pct}%</b>
                <span className="muted">with grounding filter</span>
              </div>
              <div className="card kpi">
                <span className="kpi-label">Groundedness</span>
                <b className="kpi-value">{prod.grounded_pct}%</b>
                <span className="muted">vs {raw.grounded_pct}% raw LLM</span>
              </div>
              <div className="card kpi">
                <span className="kpi-label">Refusal Accuracy</span>
                <b className="kpi-value">{prod.refusal_accuracy_pct}%</b>
                <span className="muted">unknown entities refused</span>
              </div>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Questions</th>
                    <th>Production Accuracy</th>
                    <th>Grounded Rate</th>
                    <th>Raw LLM Accuracy (Ablation)</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(cats).map(([cat, c]) => (
                    <tr key={cat}>
                      <td><b>{cat}</b></td>
                      <td>{c.total}</td>
                      <td>{c.accuracy_pct}%</td>
                      <td>{c.grounded_pct}%</td>
                      <td>{raw.by_category?.[cat]?.accuracy_pct ?? "—"}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {(d.notes || []).map((n) => (
              <p className="hint" key={n}>
                {n}
              </p>
            ))}
          </>
        );
      }}
    </StoredResultCard>
  );
}

/** F26 — Height-based road flood risk (HAND vs distance proxy). */
export function HandCompareCard() {
  return (
    <StoredResultCard name="hand_compare_v1" title="Road flood exposure: HAND (Copernicus DEM) vs distance">
      {(d) => {
        const stats = d.hand_stats || {};
        const earlier = d.roads_closing_earlier_in_v2 || [];
        const later = d.roads_closing_later_in_v2 || [];
        return (
          <>
            <p className="hint">
              Comparing road closure order under <b>v1 (planar distance to water)</b> vs{" "}
              <b>v2 (Height Above Nearest Drainage, HAND, Rennó 2008)</b> from Copernicus DEM GLO-30 (30 m).
              Rank correlation: <b>{d.spearman_rank_correlation}</b> across {d.total_roads} roads.
            </p>
            <div className="grid-3 output-kpi-row" style={{ marginBottom: "1rem" }}>
              <div className="card kpi">
                <span className="kpi-label">Median HAND</span>
                <b className="kpi-value">{stats.median_m} m</b>
                <span className="muted">range {stats.min_m} to {stats.max_m} m</span>
              </div>
              <div className="card kpi">
                <span className="kpi-label">Mean HAND</span>
                <b className="kpi-value">{stats.mean_m} m</b>
                <span className="muted">height above drainage</span>
              </div>
              <div className="card kpi">
                <span className="kpi-label">Rank Correlation</span>
                <b className="kpi-value">{d.spearman_rank_correlation}</b>
                <span className="muted">Spearman v1 vs v2</span>
              </div>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Road</th>
                    <th>Type</th>
                    <th>HAND (m)</th>
                    <th>v1 Exposure</th>
                    <th>v2 Exposure</th>
                    <th>Effect</th>
                  </tr>
                </thead>
                <tbody>
                  {earlier.map((r) => (
                    <tr key={`earlier|${r.road_id}`}>
                      <td><b>{r.road_id}</b> · {r.name}</td>
                      <td><span className="badge crit">Low-lying</span></td>
                      <td>{r.hand_m} m</td>
                      <td>{r.v1_exposure}</td>
                      <td><b>{r.v2_exposure}</b></td>
                      <td>Floods earlier in v2 (topographical basin)</td>
                    </tr>
                  ))}
                  {later.map((r) => (
                    <tr key={`later|${r.road_id}`}>
                      <td><b>{r.road_id}</b> · {r.name}</td>
                      <td><span className="badge safe">Elevated / Ridge</span></td>
                      <td>{r.hand_m} m</td>
                      <td>{r.v1_exposure}</td>
                      <td><b>{r.v2_exposure}</b></td>
                      <td>Stays open longer in v2 (high ground)</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {(d.notes || []).map((n) => (
              <p className="hint" key={n}>
                {n}
              </p>
            ))}
          </>
        );
      }}
    </StoredResultCard>
  );
}

/** F20 — road closure validation against satellite / crowdsourced flood maps. */
export function ClosureValidationCard() {
  return (
    <StoredResultCard
      name="closure_validation_v1"
      title="Road closure validation — satellite flood map check (F20)"
      perCity={true}
    >
      {(d) => {
        const m = d.metrics_at_default_blockage || {};
        const best = d.best_f1 || {};
        const sweep = (d.threshold_sweep || []).filter((_, i) => i % 2 === 0); // every other row for readability
        const byClass = Object.entries(d.metrics_by_road_class || {});
        const srcLabel = d.ground_truth_source === "unosat_satellite"
          ? "UNOSAT Sentinel-1 satellite (24 Nov 2015)"
          : "OSM crowdsourced flooded-streets (Dec 2015)";
        return (
          <>
            <p className="hint">
              <b>Ground truth:</b> {srcLabel}. Event: {d.event}.{" "}
              {d.ground_truth?.licence && <span>Licence: {d.ground_truth.licence}.</span>}
            </p>
            <p className="hint">
              Closure rule: <code>flood_exposure ≥ 0.85 − blockage</code> (same rule as live engine).
              Default blockage: {d.default_blockage}. Threshold sweep not tuned on this event.
            </p>

            {/* Summary KPI row */}
            <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
              {[
                { label: "Precision", value: pct(m.precision) },
                { label: "Recall", value: pct(m.recall) },
                { label: "F1", value: f3(m.f1) },
                { label: "Observed flooded", value: m.observed_flooded ?? "—" },
                { label: "Predicted closed", value: m.predicted_closed ?? "—" },
                { label: "Total roads", value: m.total_roads ?? "—" },
              ].map(({ label, value }) => (
                <div key={label} style={{ minWidth: "110px", textAlign: "center" }}>
                  <div style={{ fontSize: "1.3rem", fontWeight: 700 }}>{value}</div>
                  <div className="hint" style={{ margin: 0 }}>{label}</div>
                </div>
              ))}
            </div>

            <p className="hint">
              Best F1 {f3(best.f1)} at blockage {best.blockage} (Precision {pct(best.precision)}, Recall {pct(best.recall)}).
              Reported at default blockage ({d.default_blockage}) above — not at the best-F1 blockage.
            </p>

            {/* Threshold sweep */}
            <details open style={{ marginBottom: "0.75rem" }}>
              <summary><b>Threshold sweep</b> (blockage 0.00–0.70)</summary>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Blockage</th>
                      <th>Predicted closed</th>
                      <th>Precision</th>
                      <th>Recall</th>
                      <th>F1</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sweep.map((s) => (
                      <tr key={s.blockage} style={s.blockage === best.blockage ? { fontWeight: 700 } : {}}>
                        <td>{s.blockage}</td>
                        <td>{s.predicted_closed}</td>
                        <td>{pct(s.precision)}</td>
                        <td>{pct(s.recall)}</td>
                        <td>{f3(s.f1)}{s.blockage === best.blockage ? " ★" : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>

            {/* By road class */}
            {byClass.length > 0 && (
              <details style={{ marginBottom: "0.75rem" }}>
                <summary><b>By road class</b> (at default blockage)</summary>
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Highway class</th>
                        <th>Roads</th>
                        <th>Observed flooded</th>
                        <th>Precision</th>
                        <th>Recall</th>
                        <th>F1</th>
                      </tr>
                    </thead>
                    <tbody>
                      {byClass.map(([hw, bc]) => (
                        <tr key={hw}>
                          <td>{hw}</td>
                          <td>{bc.count}</td>
                          <td>{bc.observed_flooded}</td>
                          <td>{pct(bc.precision)}</td>
                          <td>{pct(bc.recall)}</td>
                          <td>{f3(bc.f1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}

            {/* Notes */}
            {(d.notes || []).map((n) => (
              <p className="hint" key={n}>{n}</p>
            ))}
            <p className="hint">Regenerate: python scripts/validate_closures.py</p>
          </>
        );
      }}
    </StoredResultCard>
  );
}
