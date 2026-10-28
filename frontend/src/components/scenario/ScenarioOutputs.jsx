import { useMemo } from "react";
import KpiCard from "../KpiCard.jsx";
import DamStatusCard from "../DamMonitor/DamStatusCard.jsx";
import DamMlPredictionCard from "../DamMonitor/DamMlPredictionCard.jsx";
import DamRiskEnginePanel from "../DamMonitor/DamRiskEnginePanel.jsx";
import DamTimeSeriesChart from "../DamMonitor/DamTimeSeriesChart.jsx";
import DamDetailCard from "../DamMonitor/DamDetailCard.jsx";
import AiAssistant from "../agents/AiAssistant.jsx";
import ReplayPlayer from "../replay/ReplayPlayer.jsx";
import RouteBenchmarkCard from "./RouteBenchmarkCard.jsx";
import OpsBenchmarkCard from "./OpsBenchmarkCard.jsx";
import { AiEvalCard, ClosureValidationCard, FairnessCurveCard, HandCompareCard, LongRunCard, RegretCard, SensitivityCard, WarningSweepCard } from "./MeasuredCards.jsx";

/** Script-generated measured results (F23 …), each from a stored models/*.json. */
function MeasuredResults() {
  return (
    <>
      <WarningSweepCard />
      <LongRunCard />
      <FairnessCurveCard />
      <SensitivityCard />
      <AiEvalCard />
      <HandCompareCard />
      <ClosureValidationCard />
    </>
  );
}
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
  const text =
    hour === null ? (horizon ? `NOT IN ${horizon} H` : "NOT REACHED") : hour === 0 ? "ALREADY THERE" : `${hour} h`;
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

/** Tabs whose content comes from the evacuation engine run. */
const EVAC_TABS = new Set(["live", "agents", "people", "routes", "prediction", "algorithms", "report"]);

function EmptyTab({ onTab }) {
  return (
    <div className="panel sim-output-empty empty-state-card">
      <div className="empty-state-icon" aria-hidden>
        ◎
      </div>
      <h2>No run yet</h2>
      <p className="hint">
        This tab fills in from a scenario run. Pick a scenario in <b>Setup &amp; Run</b> and click <b>RUN SCENARIO</b>.
      </p>
      <button type="button" className="primary" onClick={() => onTab?.("setup")}>
        Go to Setup &amp; Run
      </button>
    </div>
  );
}

function ProjectionPanel({ projection }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h3>Reservoir level projection (m MSL)</h3>
        <span className="badge sim">{projection?.trend || "—"}</span>
      </div>
      <LazyMount minHeight={280}>
        <DamTimeSeriesChart projection={projection} />
      </LazyMount>
    </div>
  );
}

/** Results area, one tab at a time. Every value — including the header label
 * — comes from the CURRENT run record (ctx.currentRun), never from the active
 * selection. The evacuation view (SimulationExecution) stays mounted on every
 * tab because it owns the one live poller. */
export default function ScenarioOutputs({ tab = "live", onTab }) {
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
  const { steps, running, hasResults, isOutdated, runScenario, setDamId, damId } = ctx;

  const risk = dam?.risk_engine;
  const status = dam?.status_box;
  const damBusy = steps.dam?.status === "running";
  const benchBusy = steps.benchmark?.status === "running";
  const evacBusy = steps.evacuation?.status === "running";
  const mlBusy = steps.ml?.status === "running";
  const isEvacTab = EVAC_TABS.has(tab);
  const noRun = !hasResults && !running;

  // The live run view: mounted whenever a run exists, whatever the tab.
  const evacView = results?.run ? (
    <ErrorBoundary name="Evacuation scenario" key={results.run.runId}>
      <SimulationExecution key={results.run.runId} runMeta={results.run} tab={tab} onTab={onTab} />
    </ErrorBoundary>
  ) : null;

  const outdatedCls = `scenario-outputs ${isOutdated ? "is-outdated" : ""}`;

  // Fixed three-slot layout so the evacuation view never changes position in
  // the tree — moving it would remount it and restart the live poller.
  return (
    <>
      {tab === "setup" ? null : (
        <section className={outdatedCls} id="scenario-output" data-run-id={currentRun?.runId || ""}>
          {hasResults || running ? (
            <div className="status-row section-head">
              <h3 className="section-title">Run results</h3>
              {/* The label of the scenario that PRODUCED these numbers. */}
              <span className="badge sim" data-testid="results-scenario">
                {currentRun?.label}
              </span>
              {currentRun?.finishedAt ? <span className="hint">{formatTimeIST(currentRun.finishedAt)}</span> : null}
              {isOutdated ? (
                <span className="badge warn" role="status">
                  OUTDATED — RE-RUN
                </span>
              ) : null}
            </div>
          ) : null}

          {/* Every value lives in this wrapper so "outdated" dims ALL of them. */}
          <div
            className="scenario-output-values"
            data-outdated={isOutdated ? "true" : "false"}
            aria-disabled={isOutdated || undefined}
          >
            {tab === "ai" ? <AiAssistant /> : null}
            {tab === "history" ? (
          <>
            <ReplayPlayer />
            <ErrorBoundary name="Regret">
              <RegretCard />
            </ErrorBoundary>
          </>
        ) : null}

            {/* ------------------------------- Dam tab ------------------------------- */}
            {tab === "dam" ? (
              <>
                <DamDetailCard />
                {noRun ? null : steps.dam?.status === "error" ? (
                  <StepError step={steps.dam} label="Dam simulation" onRetry={() => runScenario({ only: "dam" })} />
                ) : damBusy ? (
                  <>
                    <div className="grid-3 output-kpi-row">
                      <SkeletonKpi label="Reservoir risk" />
                      <SkeletonKpi label="Projected peak level" />
                      <SkeletonKpi label="Time to critical level" />
                    </div>
                    <SkeletonPanel title="Water level projection" tall />
                  </>
                ) : dam ? (
                  <>
                    <div className="status-row dam-run-for">
                      <span className="hint">
                        Run results for <b>{runDam?.name || dam.dam_id}</b>
                      </span>
                      {runDam && runDam.id !== damId ? (
                        <span className="badge warn">
                          You selected {(dams || []).find((d) => d.id === damId)?.name} — re-run to see its results
                        </span>
                      ) : null}
                    </div>
                    <div className="grid-3 output-kpi-row">
                      <KpiCard
                        label="Reservoir risk"
                        value={risk?.risk ?? status?.status ?? null}
                        sub={risk ? `Composite ${num(risk.composite_score)}` : undefined}
                      />
                      <KpiCard
                        label="Projected peak level"
                        // Canonical: projection.peak_level_m (max of the series).
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
                        sub={
                          projection
                            ? `${projection.spillway_hours ?? 0} h spilling (count) · overtopping ${projection.overtopping_risk ? "YES" : "no"}`
                            : undefined
                        }
                      />
                      <KpiCard
                        label="Release / outflow"
                        value={num(dam?.inputs?.outflow_cumec, 0)}
                        suffix=" cumec"
                        sub={dam?.inputs ? `Inflow ${num(dam.inputs.inflow_cumec, 0)} cumec` : undefined}
                      />
                      <KpiCard
                        label="Full capacity level used"
                        value={num(dam?.inputs?.capacity_override_m ?? runDam?.full_reservoir_level_m)}
                        suffix=" m MSL"
                        sub={[
                          dam?.inputs?.capacity_override_m ? "edited value" : "registry FRL",
                          runDam?.gauge_unit === "ft" && typeof runDam.gauge_zero_m === "number"
                            ? `${(((dam?.inputs?.capacity_override_m ?? runDam.full_reservoir_level_m) - runDam.gauge_zero_m) / 0.3048).toFixed(1)} ft on the dam gauge`
                            : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      />
                    </div>

                    <div className="risk-split glass-panel">
                      <DamStatusCard status={status} />
                      <div className="risk-split-arrow" aria-hidden>
                        →
                      </div>
                      <DamMlPredictionCard prediction={dam.ml_prediction_box} />
                    </div>

                    <DamRiskEnginePanel risk={risk} />
                    <ProjectionPanel projection={projection} />
                  </>
                ) : null}

                <div className="panel">
                  <div className="panel-head">
                    <h3>Dams on the map — click one to open it</h3>
                    <span className="badge live">{(dams || []).find((d) => d.id === damId)?.name || "—"}</span>
                  </div>
                  {runDam?.distance_to_region_km != null ? (
                    <p className="hint">
                      {runDam.name} is {runDam.distance_to_region_km} km from the evacuation region ({runDam.river}).
                      Reservoir level is m MSL — a different quantity from the Yamuna barrage stage used by the
                      evacuation run.
                    </p>
                  ) : null}
                  <LazyMount minHeight={320}>
                    <IndiaDamMap
                      dams={dams}
                      selectedId={damId}
                      topDams={indianDams}
                      onSelect={running ? undefined : setDamId}
                    />
                  </LazyMount>
                </div>
              </>
            ) : null}

            {tab !== "dam" && tab !== "ai" && tab !== "history" && noRun ? <EmptyTab onTab={onTab} /> : null}

            {/* ------------------------ evacuation-driven tabs ----------------------- */}
            {isEvacTab && !noRun && steps.evacuation?.status === "error" ? (
              <StepError
                step={steps.evacuation}
                label="Evacuation scenario"
                onRetry={() => runScenario({ only: "evacuation" })}
              />
            ) : null}
            {isEvacTab && !noRun && evacBusy && !results.run ? (
              <>
                <div className="grid-3">
                  <SkeletonKpi label="SOS received" />
                  <SkeletonKpi label="Ambulances free" />
                  <SkeletonKpi label="Shelter seats" />
                </div>
                <SkeletonPanel title="Live rescue map" tall />
                <SkeletonTable title="SOS people" rows={6} />
              </>
            ) : null}
          </div>
        </section>
      )}

      <div className={`sim-evac-slot ${isOutdated ? "is-outdated" : ""}`} hidden={tab === "setup" || tab === "dam" || tab === "ai" || tab === "history"}>
        {evacView}
      </div>

      {tab === "prediction" || tab === "algorithms" ? (
        <section className={outdatedCls}>
          <div className="scenario-output-values">
            {/* ------------------------- Prediction extras --------------------------- */}
            {tab === "prediction" && !noRun ? (
              <>
                {dam ? <ProjectionPanel projection={projection} /> : null}
                {steps.ml?.status === "error" ? (
                  <StepError step={steps.ml} label="ML model benchmark" onRetry={() => runScenario({ only: "ml" })} />
                ) : mlBusy ? (
                  <SkeletonTable title="ML model benchmark (re-scoring on unseen gauges…)" rows={6} />
                ) : (
                  <ErrorBoundary name="ML model benchmark">
                    <MlBenchmarkPanel ml={results.ml} />
                  </ErrorBoundary>
                )}
              </>
            ) : null}

            {/* ------------- Algorithms: measured route benchmark (F6, stored file) ------------- */}
            {tab === "algorithms" ? (
              <>
                <ErrorBoundary name="Route benchmark">
                  <RouteBenchmarkCard />
                </ErrorBoundary>
                <ErrorBoundary name="Ops benchmark">
                  <OpsBenchmarkCard />
                </ErrorBoundary>
                <ErrorBoundary name="Measured results">
                  <MeasuredResults />
                </ErrorBoundary>
              </>
            ) : null}

            {/* ------------------------- Algorithms: HQRL ---------------------------- */}
            {tab === "algorithms" && !noRun ? (
              <div id="hqrl-results">
                {steps.benchmark?.status === "error" ? (
                  <StepError
                    step={steps.benchmark}
                    label="HQRL benchmark"
                    onRetry={() => runScenario({ only: "benchmark" })}
                  />
                ) : benchBusy ? (
                  <SkeletonTable title="HQRL benchmark" rows={6} />
                ) : bench ? (
                  <div className="panel benchmark-output">
                    <div className="panel-head">
                      <h3>
                        {bench.mode === "ablation"
                          ? "HQRL safety-layer ablation"
                          : "HQRL evacuation planner vs baselines"}
                      </h3>
                      <span className="badge sim">
                        {bench.n_scenarios} scenarios · seed {bench.seed}
                      </span>
                    </div>
                    <ol className="bench-steps" aria-label="How the benchmark works">
                      <li>
                        <b>1 · Build {bench.n_scenarios} scenarios</b>
                        <span>Seeded road networks from this run&apos;s inputs (seed {bench.seed}, +17 per scenario)</span>
                      </li>
                      <li>
                        <b>2 · Run every planner</b>
                        <span>Each planner routes every evacuation group on the same scenarios</span>
                      </li>
                      <li>
                        <b>3 · Check safety</b>
                        <span>Closed roads, shelter capacity, vehicles and accessibility are validated</span>
                      </li>
                      <li>
                        <b>4 · Score</b>
                        <span>Safe evacuation %, unsafe routes %, clearance time and replanning time</span>
                      </li>
                    </ol>
                    {best ? (
                      <div className="grid-3">
                        <KpiCard
                          label="Best planner"
                          value={best.method}
                          sub={`${bench.n_scenarios} seeded scenarios · seed ${bench.seed}`}
                        />
                        <KpiCard
                          label="Safe evacuation"
                          value={num(Number(best.safe_evacuation_pct), 1)}
                          suffix="%"
                          sub={`Clearance ${num(Number(best.clearance_time_min), 1)} min`}
                        />
                      </div>
                    ) : null}

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
            ) : null}
          </div>
        </section>
      ) : null}
    </>
  );
}
