import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App.jsx";
import { formatUnavailable } from "./services/api.js";
import { mergeSnapshot } from "./state/snapshot.js";
import ScenarioRunTheater from "./components/ScenarioRunTheater.jsx";

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
    fetchHealth: () => Promise.resolve({ backend: "connected" }),
    fetchShelters: () => Promise.resolve({ shelters: [] }),
    fetchTeams: () => Promise.resolve({ teams: [] }),
    fetchEmergencies: () => Promise.resolve({ emergencies: [] }),
    fetchMlBenchmark: () => Promise.resolve({}),
    fetchSources: () => Promise.resolve({ live_apis: [] }),
    fetchClusters: () => Promise.resolve({ n_sos: 0, clusters: [] }),
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
    expect(screen.getAllByText(/AGENTIC REAL-TIME FLOOD RESPONSE/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Command Center/)).toBeTruthy();
  });

  it("renders simulation lab on one route", async () => {
    render(
      <MemoryRouter initialEntries={["/simulation"]}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getAllByText(/IEEE HQRL Demo/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Scenario Lab/i).length).toBeGreaterThan(0);
    expect(await screen.findByText(/CHOOSE SCENARIO/i)).toBeTruthy();
    expect(screen.getByText(/SIMULATION MODE/)).toBeTruthy();
    expect(screen.getByText(/^Simulation$/)).toBeTruthy();
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
