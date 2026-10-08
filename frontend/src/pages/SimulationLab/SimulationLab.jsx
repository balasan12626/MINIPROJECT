import { useEffect, useRef } from "react";
import ScenarioPicker from "../../components/scenario/ScenarioPicker.jsx";
import ScenarioInputs from "../../components/scenario/ScenarioInputs.jsx";
import RunScenarioBar from "../../components/scenario/RunScenarioBar.jsx";
import ScenarioOutputs from "../../components/scenario/ScenarioOutputs.jsx";
import { ScenarioProvider, useScenario } from "../../state/ScenarioContext.jsx";

/** /simulation — one page, one scenario, one run button.
 *
 * Replaces the old three-section switcher (Dam Monitor / Scenario Lab / IEEE
 * HQRL) and its three separate run buttons. The page is now a straight
 * top-to-bottom flow:
 *
 *   pick scenario -> review/edit inputs -> RUN SCENARIO -> results
 *
 * Nothing runs on mount. The only load-time request is the dam registry that
 * populates the dam selector (see ScenarioProvider). */
function SimulationLabInner() {
  const { running, hasResults } = useScenario();
  const wasRunning = useRef(false);

  // Scroll to the results once a run finishes (not while it is still going).
  useEffect(() => {
    if (wasRunning.current && !running && hasResults) {
      const t = window.setTimeout(() => {
        document.getElementById("scenario-output")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 120);
      wasRunning.current = running;
      return () => window.clearTimeout(t);
    }
    wasRunning.current = running;
    return undefined;
  }, [running, hasResults]);

  return (
    <div className="simulation-lab">
      <section className="page-hero page-hero-inline">
        <div>
          <p className="eyebrow">Pick a scenario · edit the inputs · run once</p>
          <h2 className="page-title">AI Dam Monitoring &amp; Disaster Simulation</h2>
          <p className="page-lead">
            One scenario fills every input below. One RUN SCENARIO click drives the reservoir water-balance model,
            the flood/evacuation engine and the IEEE HQRL benchmark, and every result on this page comes from that
            run.
          </p>
        </div>
      </section>

      <div className="page sim-flow">
        <ScenarioPicker />
        <ScenarioInputs />
        <RunScenarioBar />
        <ScenarioOutputs />
      </div>
    </div>
  );
}

export default function SimulationLab() {
  return (
    <ScenarioProvider>
      <SimulationLabInner />
    </ScenarioProvider>
  );
}
