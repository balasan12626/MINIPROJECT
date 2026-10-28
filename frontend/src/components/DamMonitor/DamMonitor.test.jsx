import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DamMonitor from "./DamMonitor.jsx";

afterEach(() => cleanup());

const DAM_LIST = [
  {
    id: "mettur",
    name: "Mettur Dam",
    state: "Tamil Nadu",
    river: "Cauvery",
    lat: 11.7898,
    lon: 77.7996,
    full_reservoir_level_m: 121.92,
    current_level_m: 88.5,
    historical_normal_level_m: 100.0,
    downstream_region: "Cauvery delta",
    capacity_note: "~93.4 TMC",
    risk_threshold_pct: 90,
    fill_percentage: 72.59,
    status: "HIGH",
    figures_are_approximate: true,
    last_updated: "2026-09-16T00:00:00Z",
  },
  {
    id: "bhakra",
    name: "Bhakra Dam",
    state: "Himachal Pradesh / Punjab",
    river: "Sutlej",
    lat: 31.4166,
    lon: 76.4327,
    full_reservoir_level_m: 512.06,
    current_level_m: 333.0,
    historical_normal_level_m: 495.0,
    downstream_region: "Sutlej command",
    capacity_note: "~9.34 MAF",
    risk_threshold_pct: 92,
    fill_percentage: 65.03,
    status: "MODERATE",
    figures_are_approximate: true,
    last_updated: "2026-09-16T00:00:00Z",
  },
];

function statusBoxFor(id) {
  const dam = DAM_LIST.find((d) => d.id === id);
  return {
    current_level_m: dam.current_level_m,
    full_reservoir_level_m: dam.full_reservoir_level_m,
    fill_percentage: dam.fill_percentage,
    remaining_level_m: Number((dam.full_reservoir_level_m - dam.current_level_m).toFixed(2)),
    status: dam.status,
    overflow: false,
    recommended_response_level: "ALERT",
    calculation: "fill_percentage = (current_level_m / full_reservoir_level_m) * 100",
    data_source: "calculated",
  };
}

const ML_BOX = {
  available: true,
  predicted_peak_level_m: 90.1,
  probability_severe: 0.42,
  risk_category: "MODERATE",
  recommended_response_level: "MONITOR",
  stage1_model: "lightgbm_tail_weighted",
  stage2_model: "catboost",
  model_version: "3.0.0",
  catchment_note: "note",
  model_evaluation: { available: true, regression_holdout: { r2: 0.52 }, classifier_holdout: { accuracy: 0.63 } },
};

vi.mock("../../maps/FloodMap.jsx", () => ({ default: () => <div>map</div> }));
vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }) => <div data-testid="map-container">{children}</div>,
  TileLayer: () => null,
  Marker: ({ children }) => <div>{children}</div>,
  Popup: ({ children }) => <div>{children}</div>,
  useMap: () => ({ flyTo: () => {}, setView: () => {}, invalidateSize: () => {} }),
}));

vi.mock("../../services/api.js", () => ({
  fetchDams: () =>
    Promise.resolve({
      available: true,
      dams: DAM_LIST,
      scenarios: {
        normal: { title: "Normal", story: "Baseline", defaults: { rainfall_mm: 15 } },
        worst_case: { title: "Worst-Case Scenario", story: "compounding risk", defaults: { rainfall_mm: 260 } },
      },
    }),
  fetchDam: (id) => Promise.resolve({ ...DAM_LIST.find((d) => d.id === id), status_box: statusBoxFor(id) }),
  predictDamRisk: () => Promise.resolve(ML_BOX),
  runDamSimulation: (body) =>
    Promise.resolve({
      available: true,
      status_box: statusBoxFor(body.dam_id),
      ml_prediction_box: ML_BOX,
      projection: {
        series: [{ hour: 0, predicted_level_m: statusBoxFor(body.dam_id).current_level_m, fill_percentage: statusBoxFor(body.dam_id).fill_percentage }],
        thresholds_m: {},
        trend: "STABLE",
      },
      risk_engine: {
        risk: "HIGH",
        composite_score: 0.6,
        fill_percentage: statusBoxFor(body.dam_id).fill_percentage,
        trend: "STABLE",
        predicted_level_m: statusBoxFor(body.dam_id).current_level_m,
        ml_confidence: 0.42,
        main_drivers: ["Conditions within normal operating range"],
        formula: "test",
        recommended_response_level: "ALERT",
      },
    }),
}));

describe("DamMonitor", () => {
  it("stays idle with no data until a dam is selected and explicitly loaded", async () => {
    render(<DamMonitor />);
    expect((await screen.findAllByText("Mettur Dam")).length).toBeGreaterThan(0);
    // Nothing pre-selected: no calculated/ML boxes and no LOAD SCENARIO button yet.
    expect(screen.queryByText(/Calculated reservoir status/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /^LOAD SCENARIO$/i })).toBeNull();
  });

  it("select -> LOAD SCENARIO -> ready populates the full workspace, never faking the % label", async () => {
    render(<DamMonitor />);
    await screen.findAllByText("Mettur Dam");

    fireEvent.click(screen.getAllByText("Mettur Dam")[0]);
    const loadBtn = await screen.findByText(/^LOAD SCENARIO$/i, {}, { timeout: 5000 });
    expect(screen.getByText(/Dam selected — click LOAD SCENARIO/i)).toBeTruthy();

    fireEvent.click(loadBtn);

    await waitFor(() => expect(screen.getByText(/Scenario ready/i)).toBeTruthy(), { timeout: 5000 });
    expect(
      await screen.findByText(
        /fill_percentage = \(current_level_m \/ full_reservoir_level_m\) \* 100/,
        {},
        { timeout: 5000 }
      )
    ).toBeTruthy();
    expect(screen.getByRole("heading", { name: /ML risk prediction/i })).toBeTruthy();

    // Run Simulation must be enabled only once ready.
    const runBtn = screen.getByText(/^RUN SIMULATION$/i);
    expect(runBtn.closest("button").disabled).toBe(false);
  }, 15000);

  it("switching dams resets state — no stale previous-dam data survives", async () => {
    render(<DamMonitor />);
    await screen.findAllByText("Mettur Dam");
    fireEvent.click(screen.getAllByText("Mettur Dam")[0]);
    fireEvent.click(await screen.findByText(/^LOAD SCENARIO$/i, {}, { timeout: 5000 }));
    await waitFor(() => expect(screen.getByText(/Scenario ready/i)).toBeTruthy(), { timeout: 5000 });

    fireEvent.click(screen.getAllByText("Bhakra Dam")[0]);

    // Back to "selected" for the new dam — old Mettur calculated status is gone.
    await waitFor(() => expect(screen.getByText(/Dam selected — click LOAD SCENARIO/i)).toBeTruthy(), { timeout: 5000 });
    expect(screen.queryByText(/Calculated reservoir status/i)).toBeNull();
  }, 15000);
});
