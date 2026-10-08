import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App.jsx";
import { formatUnavailable } from "./services/api.js";
import { mergeSnapshot } from "./state/snapshot.js";
import ScenarioRunTheater from "./components/ScenarioRunTheater.jsx";
import { SCENARIOS, SCENARIO_GROUPS } from "./config/scenarios.js";

vi.mock("./hooks/useLivePipeline.js", () => ({
  useLivePipeline: () => ({
    snapshot: { prediction: { flood_probability: 0.42, risk_category: "MODERATE", available: true } },
    wsStatus: "connected",
    lastEventAt: "2026-08-18T12:00:00Z",
    reload: () => {},
  }),
}));

vi.mock("./maps/FloodMap.jsx", () => ({
  default: () => <div>map</div>,
}));

vi.mock("./charts/HistoryChart.jsx", () => ({
  default: () => <div>chart</div>,
}));

vi.mock("./services/api.js", async (orig) => {
  const actual = await orig();
  const hqrlStub = {
    available: true,
    seed: 42,
    demo_phase: "decision",
    topbar: { simulation_time: "08:00:00", graph_version: 1, road_closures: 0, source_reliability: 0.9, conflict_level: "LOW", system_status: "ADVISORY" },
    map: { nodes: [], edges: [], width: 1000, height: 640 },
    candidates: [],
    qubo_panel: {},
    solver_panel: { disclaimer: "test" },
    xai: {},
    disclaimers: [],
  };
  return {
    ...actual,
    fetchSimState: () => Promise.resolve({ status: "idle", history: [], events: [], pipeline: {} }),
    fetchScenarios: () => Promise.resolve({ scenarios: [] }),
    fetchDams: () => Promise.resolve({ available: true, dams: [{ id: "bhakra", name: "Bhakra Dam", state: "HP", current_level_m: 488.83 }] }),
    runDamSimulation: () => Promise.resolve({ available: true }),
    startSimulation: () => Promise.resolve({ run_id: "run-1" }),
    fetchHealth: () => Promise.resolve({ backend: "connected" }),
    fetchShelters: () => Promise.resolve({ shelters: [] }),
    fetchTeams: () => Promise.resolve({ teams: [] }),
    fetchEmergencies: () => Promise.resolve({ emergencies: [] }),
    fetchMlBenchmark: () => Promise.resolve({}),
    fetchSources: () => Promise.resolve({ live_apis: [] }),
    fetchClusters: () => Promise.resolve({ n_sos: 0, clusters: [] }),
    fetchModelsV2: () => Promise.resolve({ available: true, version: "3.0.0" }),
    hqrlState: () => Promise.resolve(hqrlStub),
    hqrlConfigure: () => Promise.resolve(hqrlStub),
    hqrlStart: () => Promise.resolve(hqrlStub),
    hqrlBenchmark: () => Promise.resolve({ ...hqrlStub, benchmark: { n_scenarios: 1, seed: 42, table: [], graphs: {}, disclaimer: "test" } }),
  };
});

describe("routing", () => {
  it("renders command center chrome", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getAllByText(/AQUASENTINEL/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Command Center/).length).toBeGreaterThan(0);
  });

  it("renders the unified simulation page: picker, inputs, one run button", async () => {
    render(
      <MemoryRouter initialEntries={["/simulation"]}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getAllByText(/AI Dam Monitoring & Disaster Simulation/i).length).toBeGreaterThan(0);
    expect(await screen.findByText(/Choose scenario/i)).toBeTruthy();
    expect(screen.getByRole("combobox", { name: /search scenarios/i })).toBeTruthy();
    // Exactly one run control — the old RUN SIMULATION / RUN BENCHMARK NOW are gone.
    const runButtons = screen.getAllByRole("button", { name: /^RUN SCENARIO$/i });
    expect(runButtons).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /RUN SIMULATION/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /RUN BENCHMARK/i })).toBeNull();
  });

  it("shows only an empty state before a run", () => {
    render(
      <MemoryRouter initialEntries={["/simulation"]}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getByText(/No results yet/i)).toBeTruthy();
    expect(screen.getByText(/Select a scenario and click/i)).toBeTruthy();
  });

  it("offers every scenario, grouped, with exactly one selected", () => {
    render(
      <MemoryRouter initialEntries={["/simulation"]}>
        <App />
      </MemoryRouter>
    );
    for (const g of SCENARIO_GROUPS) {
      expect(screen.getAllByRole("radiogroup", { name: g.label }).length).toBe(1);
    }
    for (const s of SCENARIOS) {
      expect(screen.getAllByText(s.label).length).toBeGreaterThan(0);
    }
    const checked = screen.getAllByRole("radio").filter((r) => r.getAttribute("aria-checked") === "true");
    expect(checked).toHaveLength(1);
  });
});

describe("risk display helpers", () => {
  it("does not invent values", () => {
    expect(formatUnavailable(null)).toBe("DATA UNAVAILABLE");
    expect(formatUnavailable(12, " mm")).toBe("12 mm");
  });

  it("merges websocket risk updates", () => {
    const next = mergeSnapshot({ prediction: { flood_probability: 0.2 } }, "risk_update", { flood_probability: 0.61 });
    expect(next.prediction.flood_probability).toBe(0.61);
  });
});

describe("scenario run theater", () => {
  it("renders loading page when sim is still null", () => {
    render(<ScenarioRunTheater sim={null} progress={null} onWatchMap={() => {}} onPause={() => {}} />);
    expect(screen.getByText(/Random Forest is running/i)).toBeTruthy();
    expect(screen.getByText(/SCENARIO RUNNING/i)).toBeTruthy();
  });
});

describe("scenario run theater", () => {
  it("renders loading page when sim is still null", () => {
    render(<ScenarioRunTheater sim={null} progress={null} onWatchMap={() => {}} onPause={() => {}} />);
    expect(screen.getByText(/Random Forest is running/i)).toBeTruthy();
    expect(screen.getByText(/SCENARIO RUNNING/i)).toBeTruthy();
  });
});
