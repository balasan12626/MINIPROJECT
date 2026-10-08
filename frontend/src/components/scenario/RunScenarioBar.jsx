import { RUN_STEPS, useScenario } from "../../state/ScenarioContext.jsx";
import { formatTimeIST } from "../../utils/time.js";

const MARK = { idle: "○", running: "", success: "✓", error: "✕" };

/** The ONE run control. Replaces the old RUN SIMULATION / RUN SCENARIO /
 * RUN BENCHMARK NOW trio — a single click drives all three backends. */
export default function RunScenarioBar() {
  const ctx = useScenario();
  if (!ctx) return null;
  const { scenario, steps, running, runScenario, hasResults, isOutdated, lastRun } = ctx;

  const failed = RUN_STEPS.filter((s) => steps[s.id]?.status === "error");

  return (
    <section className="run-bar-section" aria-label="Run scenario">
      <div className="panel run-bar-panel">
        <div className="run-bar-main">
          <button
            type="button"
            className="primary run-scenario-btn run-bar-btn"
            onClick={() => runScenario()}
            disabled={running}
            aria-busy={running}
          >
            {running ? (
              <>
                <span className="pdf-btn-spinner" /> RUNNING SCENARIO…
              </>
            ) : (
              <>RUN SCENARIO</>
            )}
          </button>
          <p className="hint run-scenario-hint">
            Runs <b>{scenario?.label}</b> through the dam model, the evacuation engine and the HQRL benchmark
            using the inputs above.
          </p>
        </div>

        {/* ---- step progress ---- */}
        <ol className="run-steps-row" aria-label="Run progress">
          {RUN_STEPS.map((step) => {
            const st = steps[step.id]?.status || "idle";
            return (
              <li key={step.id} className={`run-step-chip is-${st}`}>
                <span className="run-step-mark" aria-hidden>
                  {st === "running" ? <span className="run-spinner" /> : MARK[st]}
                </span>
                <span className="run-step-label">{step.label}</span>
                <span className="run-step-state">
                  {st === "idle" ? "waiting" : st === "running" ? "running…" : st === "success" ? "done" : "failed"}
                </span>
              </li>
            );
          })}
        </ol>

        {/* ---- per-step errors, with retry that keeps other results ---- */}
        {failed.length > 0 && !running ? (
          <div className="run-step-errors">
            {failed.map((step) => (
              <div className="error-banner run-step-error" key={step.id}>
                <span>
                  <b>{step.label} failed.</b> {steps[step.id]?.error}
                </span>
                <button type="button" onClick={() => runScenario({ only: step.id })}>
                  Retry {step.label.toLowerCase()}
                </button>
              </div>
            ))}
          </div>
        ) : null}

        {isOutdated ? (
          <div className="run-outdated-note">
            <span className="badge warn">OUTDATED</span>
            <span className="hint">
              Inputs changed since the last run{lastRun?.label ? ` (${lastRun.label})` : ""}. Outdated — re-run: click RUN SCENARIO to
              refresh the results below.
            </span>
          </div>
        ) : null}

        {hasResults && !isOutdated && !running ? (
          <p className="hint run-bar-stamp">
            Showing results for <b>{lastRun?.label}</b>
            {lastRun?.at ? ` · ${formatTimeIST(lastRun.at)}` : ""}
          </p>
        ) : null}
      </div>
    </section>
  );
}
