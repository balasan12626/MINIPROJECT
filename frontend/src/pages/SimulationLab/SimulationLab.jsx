import { useEffect, useState } from "react";
import HqrlDemo from "../HqrlDemo/HqrlDemo.jsx";
import ScenarioBuilder from "../ScenarioBuilder/ScenarioBuilder.jsx";
import SimulationExecution from "../SimulationExecution/SimulationExecution.jsx";
import IeeeHqrlEmbed from "../../components/IeeeHqrlEmbed.jsx";
import { AgentExecutionTrace } from "../../components/DataSourceBadge.jsx";

/** /simulation — Scenario Lab (classic + IEEE) and dedicated HQRL demo tab. */
export default function SimulationLab() {
  const [tab, setTab] = useState("scenario"); // scenario | hqrl
  const [runMeta, setRunMeta] = useState(null);

  // After RUN SCENARIO, scroll output into view then soft-focus IEEE HQRL graph
  useEffect(() => {
    if (!runMeta?.runId) return undefined;
    const t1 = window.setTimeout(() => {
      document.getElementById("sim-execution")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
    const t2 = window.setTimeout(() => {
      document.getElementById("ieee-hqrl-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 900);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [runMeta?.runId]);

  return (
    <div className="simulation-lab">
      <div className="sim-mode-tabs" role="tablist" aria-label="Simulation modes">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "scenario"}
          className={tab === "scenario" ? "active" : ""}
          onClick={() => setTab("scenario")}
        >
          Scenario Lab
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "hqrl"}
          className={tab === "hqrl" ? "active" : ""}
          onClick={() => setTab("hqrl")}
        >
          IEEE HQRL Demo
        </button>
      </div>

      {tab === "hqrl" ? (
        <HqrlDemo />
      ) : (
        <>
          <ScenarioBuilder onStarted={setRunMeta} />
          <div className="page" style={{ paddingTop: 0 }}>
            <AgentExecutionTrace mode="simulation" />
          </div>
          <div id="sim-execution" className="sim-output-anchor">
            {runMeta ? (
              <SimulationExecution key={runMeta.runId} runMeta={runMeta} />
            ) : (
              <div className="page">
                <div className="panel sim-output-empty">
                  <h2>2 · SCENARIO OUTPUT</h2>
                  <p className="hint">
                    Select a scenario, fill rainfall / river / dam details, set feature radios ON or OFF, then click
                    <b> RUN SCENARIO</b>. Live model prediction, water levels, map, and dispatch appear here — one run at a
                    time. IEEE HQRL research tools below (live graph is <b>drag-and-drop</b>).
                  </p>
                </div>
                <div id="ieee-hqrl-panel">
                  <IeeeHqrlEmbed sim={null} runMeta={null} />
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
