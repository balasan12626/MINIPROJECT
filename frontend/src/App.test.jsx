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

  it("renders simulation lab on one route", () => {
    render(
      <MemoryRouter initialEntries={["/simulation"]}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getByText(/CHOOSE SCENARIO/i)).toBeTruthy();
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
