import { Suspense, lazy, useCallback, useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import ScenarioPicker from "../../components/scenario/ScenarioPicker.jsx";
import CityPicker from "../../components/scenario/CityPicker.jsx";
import ScenarioInputs from "../../components/scenario/ScenarioInputs.jsx";
import RunScenarioBar from "../../components/scenario/RunScenarioBar.jsx";
import ScenarioOutputs from "../../components/scenario/ScenarioOutputs.jsx";
import { ScenarioProvider, useScenario } from "../../state/ScenarioContext.jsx";
import ErrorBoundary from "../../components/ErrorBoundary.jsx";

// The former top-level pages, now subtabs of /simulation. Each loads its own
// live data from the backend, mounted only while its tab is open.
const LiveCommandCenter = lazy(() => import("../LiveCommandCenter/LiveCommandCenter.jsx"));
const LiveResponse = lazy(() => import("../LiveResponse/LiveResponse.jsx"));
const RescueRoute = lazy(() => import("../RescueRoute/RescueRoute.jsx"));
const PAGE_TABS = { command: LiveCommandCenter, response: LiveResponse, rescue: RescueRoute };

/** /simulation — one scenario, one run button, results split into subtabs.
 *
 *   Setup → RUN SCENARIO → Live rescue · People · Routes · Prediction ·
 *                          Dam · Algorithms · Report
 *
 * Each tab shows only its own topic. The run's live poller lives inside
 * ScenarioOutputs and stays mounted across tabs, so switching tabs never
 * restarts anything. Nothing runs on mount. */
export const SIM_TABS = [
  { id: "setup", label: "Setup & Run", icon: "⚙", hint: "Pick a scenario, edit inputs, run" },
  { id: "command", label: "Command Center", icon: "🛰", hint: "Live environmental intelligence: risk, rainfall, river, alerts" },
  { id: "response", label: "Response", icon: "📡", hint: "Live response: teams, shelters and actions" },
  { id: "rescue", label: "Rescue Route", icon: "🗺", hint: "Rescue routing on the live road network" },
  { id: "live", label: "Live Rescue", icon: "🚑", hint: "SOS, ambulances, shelters, live map" },
  { id: "agents", label: "Agents", icon: "🤖", hint: "Multi-agent system: live controls, tiers, messages, playbook" },
  { id: "ai", label: "AI Assistant", icon: "💬", hint: "Ask about people, places, dams, ambulances and shelters" },
  { id: "people", label: "People", icon: "👥", hint: "Every SOS person and their status" },
  { id: "routes", label: "Routes", icon: "🧭", hint: "Route cases + QAOA (quantum, simulated) route choice" },
  { id: "prediction", label: "Prediction", icon: "📈", hint: "Flood prediction charts and ML" },
  { id: "dam", label: "Dam", icon: "🏞", hint: "Reservoir capacity, edit, risk" },
  { id: "algorithms", label: "Algorithms", icon: "🧠", hint: "K-means, Dijkstra, ML, HQRL" },
  { id: "report", label: "Report", icon: "📄", hint: "Per-person times and PDF" },
  { id: "history", label: "History", icon: "📼", hint: "Replay a past run (read-only)" },
];
const TAB_IDS = new Set(SIM_TABS.map((t) => t.id));

/** Keeps the tab bar stuck just below the app's own sticky top bar. */
function useTopbarOffset() {
  useEffect(() => {
    const bar = document.querySelector(".topbar");
    if (!bar || typeof ResizeObserver === "undefined") return undefined;
    const set = () => document.documentElement.style.setProperty("--topbar-h", `${bar.offsetHeight}px`);
    set();
    const ro = new ResizeObserver(set);
    ro.observe(bar);
    return () => ro.disconnect();
  }, []);
}

function TabBar({ tab, onTab }) {
  const { running, hasResults, isOutdated, runScenario } = useScenario();
  useTopbarOffset();
  return (
    <div className="sim-tabbar">
      <nav className="sim-tabs" role="tablist" aria-label="Simulation sections">
        {SIM_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`sim-tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls="sim-tabpanel"
            className={`sim-tab ${tab === t.id ? "is-active" : ""}`}
            title={t.hint}
            onClick={() => onTab(t.id)}
          >
            <span className="sim-tab-icon" aria-hidden>
              {t.icon}
            </span>
            {t.label}
          </button>
        ))}
      </nav>
      {tab !== "setup" ? (
        <div className="sim-tabbar-run">
          {isOutdated ? <span className="badge warn">Inputs changed</span> : null}
          {hasResults && !isOutdated && !running ? <span className="badge live">Results ready</span> : null}
          <button type="button" className="primary" disabled={running} onClick={() => runScenario()}>
            {running ? "Running…" : hasResults ? "↻ Re-run" : "▶ Run scenario"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function SimulationLabInner() {
  const { running, hasResults, steps, city } = useScenario();
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const tab = TAB_IDS.has(raw) ? raw : "setup";
  const onTab = useCallback(
    (id) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("tab", id);
          return next;
        },
        { replace: true }
      );
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    [setParams]
  );

  // A finished run jumps from Setup to the live rescue view.
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !running && hasResults && tab === "setup") {
      onTab(steps.evacuation?.status === "success" ? "live" : "dam");
    }
    wasRunning.current = running;
  }, [running, hasResults, tab, onTab, steps.evacuation?.status]);

  const meta = SIM_TABS.find((t) => t.id === tab);
  const PageTab = PAGE_TABS[tab];

  return (
    <div className="simulation-lab">
      <section className="page-hero page-hero-inline sim-hero">
        <div>
          <p className="eyebrow">Flood digital twin · {city?.name ? `${city.name}, ${city.state}` : "Delhi Yamuna floodplain"}</p>
          <h2 className="page-title">AI Dam Monitoring &amp; Disaster Simulation</h2>
          <p className="page-lead">
            Set up a scenario and run it once. Every tab below reads that same run: SOS calls, ambulances, shelters,
            routes, predictions and reports.
          </p>
        </div>
      </section>

      <TabBar tab={tab} onTab={onTab} />

      <div className="page sim-flow" id="sim-tabpanel" role="tabpanel" aria-labelledby={`sim-tab-${tab}`}>
        {tab !== "setup" && meta ? <p className="hint sim-tab-lead">{meta.hint}</p> : null}
        {PageTab ? (
          <ErrorBoundary name={meta.label} key={tab}>
            <Suspense fallback={<p className="hint">Loading {meta.label}…</p>}>
              <PageTab />
            </Suspense>
          </ErrorBoundary>
        ) : null}
        {tab === "setup" ? (
          <>
            <CityPicker />
            <ScenarioPicker />
            <ScenarioInputs />
            <RunScenarioBar />
          </>
        ) : null}
        {/* Always mounted: it owns the live poller. On the Setup tab it
            renders nothing visible. */}
        {/* On a page tab the run's outputs stay mounted but hidden (as on Setup). */}
        <ScenarioOutputs tab={PageTab ? "setup" : tab} onTab={onTab} />
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
