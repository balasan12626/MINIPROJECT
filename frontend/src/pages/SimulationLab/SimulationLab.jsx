import { useState } from "react";
import ScenarioBuilder from "../ScenarioBuilder/ScenarioBuilder.jsx";
import SimulationExecution from "../SimulationExecution/SimulationExecution.jsx";

/** Single /simulation route: fill above → Run → fresh output below. */
export default function SimulationLab() {
  const [runMeta, setRunMeta] = useState(null);

  return (
    <div className="simulation-lab">
      <ScenarioBuilder onStarted={setRunMeta} />
      <div id="sim-execution" className="sim-output-anchor">
        {runMeta ? (
          <SimulationExecution key={runMeta.runId} runMeta={runMeta} />
        ) : (
          <div className="page">
            <div className="panel sim-output-empty">
              <h2>2 · SCENARIO OUTPUT</h2>
              <p className="hint">
                Select a scenario, fill rainfall / river / dam details, set feature radios ON or OFF, then click
                <b> RUN SCENARIO</b>. Live model prediction, water levels, map, and dispatch appear here — one run at a time.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
