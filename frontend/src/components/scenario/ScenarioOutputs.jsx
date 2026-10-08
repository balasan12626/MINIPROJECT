import { useMemo } from "react";
import KpiCard from "../KpiCard.jsx";
import DamStatusCard from "../DamMonitor/DamStatusCard.jsx";
import DamMlPredictionCard from "../DamMonitor/DamMlPredictionCard.jsx";
import DamRiskEnginePanel from "../DamMonitor/DamRiskEnginePanel.jsx";
import DamTimeSeriesChart from "../DamMonitor/DamTimeSeriesChart.jsx";
import IndiaDamMap from "../DamMonitor/IndiaDamMap.jsx";
import { HqrlResultCharts, HqrlResultsTable } from "../HqrlVisuals.jsx";
import ErrorBoundary from "../ErrorBoundary.jsx";
import LazyMount from "../LazyMount.jsx";
import MlBenchmarkPanel from "./MlBenchmarkPanel.jsx";
import SimulationExecution from "../../pages/SimulationExecution/SimulationExecution.jsx";
import { SkeletonKpi, SkeletonPanel, SkeletonTable } from "../Skeleton.jsx";
import { indianDams } from "../../data/indianDams.js";
import { useScenario } from "../../state/ScenarioContext.jsx";
import { formatTimeIST } from "../../utils/time.js";

const num = (v, digits = 2) => (typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : null);

/** Best benchmark arm: highest safe-evacuation %, then fastest clearance.
 * Arms tie on safe% often, so the second key keeps the pick deterministic
 * rather than "whichever row the backend happened to emit first". */
function bestArm(table = []) {
  if (!table.length) return null;
  return [...table].sort(
    (a, b) =>
      Number(b.safe_evacuation_pct) - Number(a.safe_evacuation_pct) ||
      Number(a.clearance_time_min) - Number(b.clearance_time_min)
  )[0];
}

/** Time-to-critical text. `threshold_crossing_hours` maps a band -> the first
 * forecast hour it is crossed. `spillway_hours` is a COUNT of hours spent
 * spilling, not a countdown, so it is never used here. */
function overflowInfo(projection) {
  if (projection == null) return { text: null, sub: undefined };
  const crossed = projection.threshold_crossing_hours || {};
  // Number(null) === 0 would render a missing crossing as "0 h" — require a number.
  const hitCritical = typeof crossed.critical === "number";
  const hitHigh = typeof crossed.high_risk === "number";
  const hour = hitCritical ? crossed.critical : hitHigh ? crossed.high_risk : null;
  const horizon = projection.series?.length ? projection.series.length - 1 : null;
  const text = hour === null ? (horizon ? `NOT IN ${horizon} H` : "NOT REACHED") : hour === 0 ? "ALREADY THERE" : `${hour} h`;
  const sub = hour === null ? "stays below the high-risk band" : hitCritical ? "to CRITICAL band" : "to HIGH RISK band";
  return { text, sub };
}

function StepError({ step, label, onRetry }) {
  return (
    <div className="panel output-step-error">
      <div className="panel-head">
        <h3>{label}</h3>
        <span className="badge crit">FAILED</span>
      </div>
      <p className="error-text">{step.error}</p>
      <button type="button" className="primary" onClick={onRetry}>
        Retry {label.toLowerCase()}
      </button>
    </div>
  );
}

/** Everything below RUN SCENARIO. Renders nothing but an empty state until a
 * run has happened. Every value — including the header label — comes from the
 * CURRENT run record (ctx.currentRun), never from the active selection. */
export default function ScenarioOutputs() {
  const ctx = useScenario();
  const currentRun = ctx?.currentRun || null;
  const results = ctx?.results;
  const dams = ctx?.dams;

  const dam = results?.dam || null;
  const bench = results?.benchmark || null;
  const projection = dam?.projection;

  // Derived data, memoised: the /simulation tree re-renders every poll.
  const benchTable = useMemo(() => (bench?.mode === "ablation" ? [] : bench?.table || []), [bench]);
  const best = useMemo(() => bestArm(benchTable), [benchTable]);
  const overflow = useMemo(() => overflowInfo(projection), [projection]);
  const runDam = useMemo(() => (dams || []).find((d) => d.id === dam?.dam_id) || null, [dams, dam?.dam_id]);

  if (!ctx) return null;
  const { steps, running, hasResults, isOutdated, runScenario } = ctx;

  // Page load: no outputs at all.
  if (!hasResults && !running) {
    return (
      <section className="scenario-outputs" id="scenario-output">
        <div className="panel sim-output-empty empty-state-card">
          <div className="empty-state-icon" aria-hidden>
            ◎
          </div>
          <h2>No results yet</h2>
          <p className="hint">
            Select a scenario and click <b>RUN SCENARIO</b> to see results.
          </p>
        </div>
      </section>
    );
  }

  const risk = dam?.risk_engine;
  const status = dam?.status_box;
  const damBusy = steps.dam?.status === "running";
  const benchBusy = steps.benchmark?.status === "running";
  const evacBusy = steps.evacuation?.status === "running";
  const mlBusy = steps.ml?.status === "running";

  return (
    <section className={`scenario-outputs ${isOutdated ? "is-outdated" : ""}`} id="scenario-output" data-run-id={currentRun?.runId || ""}>
      <div className="status-row section-head">
        <h3 className="section-title">Results</h3>
        {/* The label of the scenario that PRODUCED these numbers. */}
        <span className="badge sim" data-testid="results-scenario">{currentRun?.label}</span>
        {currentRun?.finishedAt ? <span className="hint">{formatTimeIST(currentRun.finishedAt)}</span> : null}
        {isOutdated ? (
          <span className="badge warn" role="status">
            OUTDATED — RE-RUN
          </span>
        ) : null}
      </div>

      {/* Every value lives in this wrapper so "outdated" dims ALL of them
          (index.css: .scenario-outputs.is-outdated > *:not(.section-head)). */}
      <div className="scenario-output-values" data-outdated={isOutdated ? "true" : "false"} aria-disabled={isOutdated || undefined}>
        {/* ------------------------------- KPI row ------------------------------- */}
        <div className="grid-3 output-kpi-row">
          {damBusy ? (
            <>
              <SkeletonKpi label="Reservoir risk" />
              <SkeletonKpi label="Projected peak level" />
              <SkeletonKpi label="Time to critical level" />
              <SkeletonKpi label="Reservoir state" />
              <SkeletonKpi label="Release / outflow" />
            </>
          ) : (
            <>
              <KpiCard label="Reservoir risk" value={risk?.risk ?? status?.status ?? null} sub={risk ? `Composite ${num(risk.composite_score)}` : undefined} />
              <KpiCard
                label="Projected peak level"
                // Canonical: projection.peak_level_m (max of the series). The
                // final level is NOT the peak under emergency release.
                value={num(projection?.peak_level_m)}
                suffix=" m"
                sub={
                  projection
                    ? `reservoir ${projection.level_unit || "m"} ${projection.level_datum || ""} · hour ${projection.peak_hour ?? "—"} · final ${num(projection.final_level_m) ?? "—"} m`
                    : undefined
                }
              />
              <KpiCard label="Time to critical level" value={overflow.text} sub={overflow.sub} />
              <KpiCard
                label="Reservoir state"
                value={projection?.reservoir_state ?? null}
                sub={projection ? `${projection.spillway_hours ?? 0} h spilling (count) · overtopping ${projection.overtopping_risk ? "YES" : "no"}` : undefined}
              />
              <KpiCard
                label="Release / outflow"
                value={num(dam?.inputs?.outflow_cumec, 0)}
                suffix=" cumec"
                sub={dam?.inputs ? `Inflow ${num(dam.inputs.inflow_cumec, 0)} cumec` : undefined}
              />
            </>
          )}

          {benchBusy ? (
            <>
              <SkeletonKpi label="Best planner" />
              <SkeletonKpi label="Safe evacuation" />
            </>
          ) : (
            <>
              <KpiCard
                label="Best planner"
                value={best?.method ?? (bench?.mode === "ablation" ? "ABLATION" : null)}
                sub={bench ? `${bench.n_scenarios} seeded scenarios · seed ${bench.seed}` : undefined}
              />
              <KpiCard
                label="Safe evacuation"
                value={best ? num(Number(best.safe_evacuation_pct), 1) : null}
                suffix="%"
                sub={best ? `Clearance ${num(Number(best.clearance_time_min), 1)} min` : undefined}
              />
            </>
          )}
        </div>

        {/* ------------------------------ dam block ------------------------------ */}
        {steps.dam?.status === "error" ? (
          <StepError step={steps.dam} label="Dam simulation" onRetry={() => runScenario({ only: "dam" })} />
        ) : damBusy ? (
          <>
            <div className="grid-2">
              <SkeletonPanel title="Reservoir status" lines={5} />
              <SkeletonPanel title="ML prediction" lines={4} />
            </div>
            <SkeletonPanel title="Water level projection" tall />
          </>
        ) : dam ? (
          <>
            <div className="risk-split glass-panel">
              <DamStatusCard status={status} />
              <div className="risk-split-arrow" aria-hidden>
                →
              </div>
              <DamMlPredictionCard prediction={dam.ml_prediction_box} />
            </div>

            <DamRiskEnginePanel risk={risk} />

            <div className="grid-2">
              <div className="panel">
                <div className="panel-head">
                  <h3>Reservoir level projection (m MSL)</h3>
                  <span className="badge sim">{projection?.trend || "—"}</span>
                </div>
                <LazyMount minHeight={280}>
                  <DamTimeSeriesChart projection={projection} />
                </LazyMount>
              </div>
              <div className="panel">
                <div className="panel-head">
                  <h3>Reservoir location</h3>
                  <span className="badge live">{runDam?.name || dam.dam_id || "—"}</span>
                </div>
                {runDam?.distance_to_region_km != null ? (
                  <p className="hint">
                    {runDam.distance_to_region_km} km from the evacuation region ({runDam.river}). Reservoir level is m MSL —
                    a different quantity from the Yamuna barrage stage used by the evacuation run.
                  </p>
                ) : null}
                <LazyMount minHeight={320}>
                  <IndiaDamMap dams={dams} selectedId={dam.dam_id} topDams={indianDams} />
                </LazyMount>
              </div>
            </div>
          </>
        ) : null}

        {/* --------------------------- benchmark block --------------------------- */}
        {/* THE canonical HQRL table + charts. Other pages link here. */}
        <div id="hqrl-results">
          {steps.benchmark?.status === "error" ? (
            <StepError step={steps.benchmark} label="HQRL benchmark" onRetry={() => runScenario({ only: "benchmark" })} />
          ) : benchBusy ? (
            <SkeletonTable title="HQRL benchmark" rows={6} />
          ) : bench ? (
            <div className="panel benchmark-output">
              <div className="panel-head">
                <h3>{bench.mode === "ablation" ? "HQRL safety-layer ablation" : "HQRL vs baselines"}</h3>
                <span className="badge sim">
                  {bench.n_scenarios} scenarios · seed {bench.seed}
                </span>
              </div>

              {bench.mode === "ablation" ? (
                <>
                  {bench.takeaway ? <p className="hint">{bench.takeaway}</p> : null}
                  <div className="grid-3">
                    {[
                      ["Without safety layer", bench.without_safety],
                      ["Full HQRL", bench.with_hqrl],
                      ["Delta", bench.delta],
                    ].map(([label, obj]) => (
                      <div className="panel" key={label}>
                        <h3>{label}</h3>
                        {obj && typeof obj === "object" ? (
                          Object.entries(obj).map(([k, v]) => (
                            <div className="metric" key={k}>
                              <span>{k.replace(/_/g, " ")}</span>
                              <b>{typeof v === "number" ? num(v, 2) : String(v)}</b>
                            </div>
                          ))
                        ) : (
                          <p className="muted">DATA UNAVAILABLE</p>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <>
                  <HqrlResultsTable table={benchTable} />
                  <LazyMount minHeight={360}>
                    <ErrorBoundary name="HQRL charts">
                      <HqrlResultCharts graphs={bench.graphs} />
                    </ErrorBoundary>
                  </LazyMount>
                </>
              )}

              {bench.disclaimer ? <p className="hint">{bench.disclaimer}</p> : null}
            </div>
          ) : null}
        </div>

        {/* ------------------------- ML benchmark block -------------------------- */}
        {steps.ml?.status === "error" ? (
          <StepError step={steps.ml} label="ML model benchmark" onRetry={() => runScenario({ only: "ml" })} />
        ) : mlBusy ? (
          <SkeletonTable title="ML model benchmark (re-scoring on unseen gauges…)" rows={6} />
        ) : (
          <ErrorBoundary name="ML model benchmark">
            <MlBenchmarkPanel ml={results.ml} />
          </ErrorBoundary>
        )}

        {/* --------------------------- evacuation block -------------------------- */}
        {steps.evacuation?.status === "error" ? (
          <StepError step={steps.evacuation} label="Evacuation scenario" onRetry={() => runScenario({ only: "evacuation" })} />
        ) : evacBusy && !results.run ? (
          <>
            <div className="grid-3">
              <SkeletonKpi label="Flood probability" />
              <SkeletonKpi label="Severity" />
              <SkeletonKpi label="Recommended action" />
            </div>
            <SkeletonPanel title="Flood map & evacuation routes" tall />
            <SkeletonTable title="Collected SOS" rows={6} />
          </>
        ) : results.run ? (
          <ErrorBoundary name="Evacuation scenario" key={results.run.runId}>
            <LazyMount minHeight={900}>
              <SimulationExecution key={results.run.runId} runMeta={results.run} />
            </LazyMount>
          </ErrorBoundary>
        ) : null}
      </div>
    </section>
  );
}
