import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ScenarioProvider, useScenario } from "./ScenarioContext.jsx";
import ScenarioOutputs from "../components/scenario/ScenarioOutputs.jsx";
import {
  BENCHMARK_N_SCENARIOS,
  SCENARIOS,
  SCENARIO_GROUPS,
  divergedFields,
  getScenario,
  scenarioInputs,
  searchScenarios,
} from "../config/scenarios.js";

const damResult = { available: true, dam_id: "bhakra", status_box: { status: "LOW", fill_percentage: 64.8 }, projection: {}, risk_engine: { risk: "LOW" }, inputs: {} };

const api = vi.hoisted(() => ({
  fetchDams: vi.fn(),
  runDamSimulation: vi.fn(),
  startSimulation: vi.fn(),
  hqrlConfigure: vi.fn(),
  hqrlBenchmark: vi.fn(),
  fetchMlBenchmarkV4: vi.fn(),
  hqrlAblation: vi.fn(),
}));

vi.mock("../services/api.js", () => api);
// Heavy children of ScenarioOutputs are irrelevant to what these tests check.
vi.mock("../pages/SimulationExecution/SimulationExecution.jsx", () => ({ default: () => <div>evac</div> }));
vi.mock("../components/DamMonitor/IndiaDamMap.jsx", () => ({ default: () => <div>map</div> }));
vi.mock("../components/DamMonitor/DamTimeSeriesChart.jsx", () => ({ default: () => <div>chart</div> }));
vi.mock("../components/HqrlVisuals.jsx", () => ({ HqrlResultCharts: () => <div>charts</div>, HqrlResultsTable: () => <div>table</div> }));

let ctx = null;
function Probe() {
  ctx = useScenario();
  return <span>{ctx.scenario.label}</span>;
}

async function mount({ outputs = false } = {}) {
  ctx = null;
  await act(async () => {
    render(
      <ScenarioProvider>
        <Probe />
        {outputs ? <ScenarioOutputs /> : null}
      </ScenarioProvider>
    );
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchDams.mockResolvedValue({
    available: true,
    // Mettur is row 0 on purpose: the default must follow the region, not the row order.
    dams: [
      { id: "mettur", name: "Mettur Dam", state: "Tamil Nadu", river: "Cauvery", lat: 11.79, lon: 77.8, current_level_m: 234.94 },
      { id: "bhakra", name: "Bhakra Dam", state: "HP", river: "Sutlej", lat: 31.42, lon: 76.43, current_level_m: 488.83 },
    ],
    evacuation_region: { id: "delhi_yamuna", name: "Delhi — Yamuna floodplain", river: "Yamuna", lat: 28.63, lon: 77.27 },
    region_dam: { dam_id: "bhakra", name: "Bhakra Dam", river: "Sutlej", distance_km: 320, same_river: false },
  });
  api.runDamSimulation.mockResolvedValue(damResult);
  api.startSimulation.mockResolvedValue({ run_id: "run-1", status: "running" });
  api.hqrlConfigure.mockResolvedValue({});
  api.fetchMlBenchmarkV4.mockResolvedValue({ available: false, message: "MODEL UNAVAILABLE" });
  api.hqrlBenchmark.mockResolvedValue({ benchmark: { table: [{ method: "PPO + QAOA", safe_evacuation_pct: 91 }], n_scenarios: 6, seed: 42 } });
  api.hqrlAblation.mockResolvedValue({ ablation: { takeaway: "x", n_scenarios: 10, seed: 42 } });
});

describe("scenario catalogue", () => {
  it("every scenario maps onto backend ids that actually exist", () => {
    // Guards against inventing presets the backends cannot run.
    const engineIds = [
      "heavy_rainfall",
      "dam_overflow",
      "river_rise",
      "road_blockage",
      "shelter_congestion",
      "mass_evacuation",
      "multiple_sos",
    ];
    const damIds = ["normal", "heavy_rainfall", "extreme_rainfall", "emergency_release", "worst_case"];
    const groupIds = SCENARIO_GROUPS.map((g) => g.id);
    for (const s of SCENARIOS) {
      expect(engineIds).toContain(s.sim.scenario);
      if (s.dam.preset !== null) expect(damIds).toContain(s.dam.preset);
      expect(groupIds).toContain(s.group);
      expect(["benchmark", "ablation"]).toContain(s.hqrl.mode);
      expect(s.dam.controls.inflow_cumec).toBeGreaterThanOrEqual(0);
    }
  });

  it("sends the engine a complete parameter set", () => {
    // backend/api/simulation.py does NOT merge a scenario's defaults, so a
    // partial params object would silently run with the wrong numbers.
    const required = [
      "rainfall_intensity", "dam_level", "river_level", "road_blockage", "population",
      "shelter_capacity_factor", "traffic", "sos_count", "ticks", "tick_seconds",
    ];
    for (const s of SCENARIOS) {
      for (const key of required) expect(s.sim.params[key]).toBeDefined();
    }
  });

  it("covers every group and finds scenarios by keyword", () => {
    for (const g of SCENARIO_GROUPS) {
      expect(SCENARIOS.filter((s) => s.group === g.id).length).toBeGreaterThan(0);
    }
    expect(searchScenarios("benchmark").length).toBeGreaterThan(0);
    expect(searchScenarios("drought").map((s) => s.id)).toContain("drought_low_inflow");
    expect(searchScenarios("zzzzz")).toEqual([]);
  });

  it("divergedFields ignores unset values", () => {
    const s = getScenario("heavy_rainfall");
    expect(divergedFields(s, scenarioInputs(s))).toEqual([]);
    expect(divergedFields(s, { ...scenarioInputs(s), inflow_cumec: undefined })).toEqual([]);
  });
});

describe("unified scenario state", () => {
  it("does not run anything on mount — only reads the dam registry", async () => {
    await mount();
    expect(api.fetchDams).toHaveBeenCalled();
    expect(api.runDamSimulation).not.toHaveBeenCalled();
    expect(api.startSimulation).not.toHaveBeenCalled();
    expect(api.hqrlBenchmark).not.toHaveBeenCalled();
  });

  it("selecting a scenario fills inputs but runs nothing", async () => {
    await mount();
    const before = ctx.inputs;
    await act(async () => ctx.selectScenario("extreme_rainfall"));
    expect(ctx.activeId).toBe("extreme_rainfall");
    expect(ctx.inputs).not.toEqual(before);
    expect(ctx.inputs.rainfall_intensity_mm_hr).toBe(45);
    expect(ctx.isCustom).toBe(false);
    expect(api.runDamSimulation).not.toHaveBeenCalled();
    expect(api.startSimulation).not.toHaveBeenCalled();
    expect(api.hqrlBenchmark).not.toHaveBeenCalled();
  });

  it("manual edits flag Custom and name the changed field", async () => {
    await mount();
    await act(async () => ctx.selectScenario("heavy_rainfall"));
    expect(ctx.isCustom).toBe(false);
    await act(async () => ctx.patchInputs({ inflow_cumec: 9999 }));
    expect(ctx.isCustom).toBe(true);
    expect(ctx.changedFields).toContain("inflow_cumec");
  });

  it("reset restores the preset and clears Custom", async () => {
    await mount();
    await act(async () => ctx.selectScenario("heavy_rainfall"));
    await act(async () => ctx.patchInputs({ inflow_cumec: 9999 }));
    await act(async () => ctx.resetToScenario());
    expect(ctx.isCustom).toBe(false);
    expect(ctx.inputs.inflow_cumec).toBe(1600);
  });

  it("re-selecting the same scenario bumps revision", async () => {
    await mount();
    const r0 = ctx.revision;
    await act(async () => ctx.selectScenario("heavy_rainfall"));
    const r1 = ctx.revision;
    await act(async () => ctx.selectScenario("heavy_rainfall"));
    expect(r1).toBeGreaterThan(r0);
    expect(ctx.revision).toBeGreaterThan(r1);
  });

  it("one run drives all three backends and marks every step done", async () => {
    await mount();
    await act(async () => {
      await ctx.runScenario();
    });
    expect(api.runDamSimulation).toHaveBeenCalledTimes(1);
    expect(api.startSimulation).toHaveBeenCalledTimes(1);
    expect(api.hqrlConfigure).toHaveBeenCalledTimes(1);
    expect(api.hqrlBenchmark).toHaveBeenCalledTimes(1);
    expect(ctx.steps.dam.status).toBe("success");
    expect(ctx.steps.evacuation.status).toBe("success");
    expect(ctx.steps.benchmark.status).toBe("success");
    expect(ctx.results.run.runId).toBe("run-1");
    expect(ctx.hasResults).toBe(true);
    expect(ctx.running).toBe(false);
  });

  it("never sends `scenario` to the dam endpoint", async () => {
    // backend/api/dams.py:50 would overwrite every typed input with the
    // preset's defaults, making the input boxes decorative.
    await mount();
    await act(async () => {
      await ctx.runScenario();
    });
    expect(api.runDamSimulation.mock.calls[0][0].scenario).toBeUndefined();
    expect(api.runDamSimulation.mock.calls[0][0].rainfall_mm).toBe(15);
  });

  it("sends the edited roster and the edited inputs, not the preset", async () => {
    await mount();
    await act(async () => ctx.patchInputs({ rainfall_mm: 123, sos_count: 3 }));
    await act(async () => {
      await ctx.runScenario();
    });
    expect(api.runDamSimulation.mock.calls[0][0].rainfall_mm).toBe(123);
    const simBody = api.startSimulation.mock.calls[0][0];
    expect(simBody.sos_count).toBe(3);
    expect(simBody.citizens).toHaveLength(3);
  });

  it("a failing step keeps the other steps' results", async () => {
    api.startSimulation.mockRejectedValueOnce(new Error("engine down"));
    await mount();
    await act(async () => {
      await ctx.runScenario();
    });
    expect(ctx.steps.evacuation.status).toBe("error");
    expect(ctx.steps.evacuation.error).toMatch(/engine down/);
    expect(ctx.steps.dam.status).toBe("success");
    expect(ctx.steps.benchmark.status).toBe("success");
    expect(ctx.results.dam).not.toBeNull();
    expect(ctx.results.benchmark).not.toBeNull();
  });

  it("retrying one step does not re-run the others", async () => {
    api.startSimulation.mockRejectedValueOnce(new Error("engine down"));
    await mount();
    await act(async () => {
      await ctx.runScenario();
    });
    await act(async () => {
      await ctx.runScenario({ only: "evacuation" });
    });
    expect(api.startSimulation).toHaveBeenCalledTimes(2);
    expect(api.runDamSimulation).toHaveBeenCalledTimes(1);
    expect(api.hqrlBenchmark).toHaveBeenCalledTimes(1);
    expect(ctx.steps.evacuation.status).toBe("success");
  });

  it("marks results outdated when the scenario changes after a run", async () => {
    await mount();
    await act(async () => {
      await ctx.runScenario();
    });
    expect(ctx.isOutdated).toBe(false);
    await act(async () => ctx.selectScenario("worst_case"));
    expect(ctx.isOutdated).toBe(true);
    // Switching must NOT auto-rerun.
    expect(api.runDamSimulation).toHaveBeenCalledTimes(1);
  });

  it("marks results outdated when an input is edited after a run", async () => {
    await mount();
    await act(async () => {
      await ctx.runScenario();
    });
    await act(async () => ctx.patchInputs({ outflow_cumec: 1234 }));
    expect(ctx.isOutdated).toBe(true);
  });

  it("uses the ablation endpoint for the ablation scenario", async () => {
    await mount();
    await act(async () => ctx.selectScenario("hqrl_ablation"));
    await act(async () => {
      await ctx.runScenario();
    });
    expect(api.hqrlAblation).toHaveBeenCalledTimes(1);
    expect(api.hqrlBenchmark).not.toHaveBeenCalled();
    expect(ctx.results.benchmark.mode).toBe("ablation");
  });

  it("renders the active scenario label", async () => {
    await mount();
    expect(screen.getByText("Normal Operation")).toBeTruthy();
  });

  it("defaults the reservoir to the flood region's dam, not the first registry row", async () => {
    await mount();
    expect(ctx.damId).toBe("bhakra");
    expect(ctx.evacuationRegion.name).toMatch(/Yamuna/);
    await act(async () => ctx.setDamId("mettur"));
    await act(async () => ctx.selectScenario("extreme_rainfall"));
    expect(ctx.damId).toBe("bhakra");
  });

  it("never copies the reservoir level into the barrage stage; a dam switch drops a typed reservoir level", async () => {
    await mount();
    await act(async () => ctx.selectScenario("emergency_release"));
    expect(ctx.damLevel).toBe(488.83); // reservoir, m MSL
    expect(ctx.inputs.dam_level).toBe(206.5); // Yamuna barrage stage from the scenario
    await act(async () => ctx.patchInputs({ current_level_m: 500 }));
    expect(ctx.damLevel).toBe(500);
    expect(ctx.inputs.dam_level).toBe(206.5);
    await act(async () => ctx.setDamId("mettur"));
    expect(ctx.damLevel).toBe(234.94);
  });

  it("one benchmark N for descriptions and requests", async () => {
    for (const s of SCENARIOS) expect(s.hqrl.n_scenarios).toBe(BENCHMARK_N_SCENARIOS);
    for (const s of SCENARIOS.filter((x) => x.group === "hqrl")) {
      expect(s.description).toContain(`${BENCHMARK_N_SCENARIOS} seeded scenarios`);
    }
    await mount();
    await act(async () => {
      await ctx.runScenario();
    });
    expect(api.hqrlBenchmark.mock.calls[0][0].n_scenarios).toBe(BENCHMARK_N_SCENARIOS);
  });
});

describe("results are keyed by run id", () => {
  it("keeps the producing scenario's label and numbers after the selection changes", async () => {
    api.runDamSimulation.mockImplementation(async (body) => ({ ...damResult, inputs: { ...body } }));
    await mount({ outputs: true });
    await act(async () => ctx.selectScenario("heavy_rainfall"));
    await act(async () => {
      await ctx.runScenario();
    });
    const firstRun = ctx.currentRunId;
    expect(ctx.currentRun.label).toBe("Heavy Rainfall");
    expect(ctx.results.dam.inputs.inflow_cumec).toBe(1600);

    await act(async () => ctx.selectScenario("drought_low_inflow"));
    // Header still names the run that produced the numbers, and they are outdated.
    expect(screen.getByTestId("results-scenario").textContent).toBe("Heavy Rainfall");
    expect(ctx.isOutdated).toBe(true);
    expect(ctx.results.dam.inputs.inflow_cumec).toBe(1600);

    await act(async () => {
      await ctx.runScenario();
    });
    expect(ctx.currentRunId).not.toBe(firstRun);
    expect(ctx.currentRun.label).toBe("Drought / Low Inflow");
    expect(ctx.results.dam.inputs.inflow_cumec).toBe(260);
    expect(ctx.runs[firstRun]).toBeUndefined();
    expect(screen.getByTestId("results-scenario").textContent).toBe("Drought / Low Inflow");
  });

  it("dims the VALUES (not just a label) when outdated", async () => {
    await mount({ outputs: true });
    await act(async () => {
      await ctx.runScenario();
    });
    const section = document.getElementById("scenario-output");
    const values = section.querySelector(".scenario-output-values");
    expect(section.className).not.toMatch(/is-outdated/);
    expect(values.getAttribute("data-outdated")).toBe("false");
    await act(async () => ctx.patchInputs({ outflow_cumec: 1234 }));
    expect(section.className).toMatch(/is-outdated/);
    expect(values.getAttribute("data-outdated")).toBe("true");
    expect(screen.getByText(/OUTDATED — RE-RUN/)).toBeTruthy();
    expect(document.getElementById("hqrl-results")).toBeTruthy();
  });

  it("a single-step retry on changed inputs becomes a full new run", async () => {
    api.startSimulation.mockRejectedValueOnce(new Error("engine down"));
    await mount();
    await act(async () => {
      await ctx.runScenario();
    });
    const firstRun = ctx.currentRunId;
    await act(async () => ctx.patchInputs({ rainfall_mm: 77 }));
    await act(async () => {
      await ctx.runScenario({ only: "evacuation" });
    });
    expect(ctx.currentRunId).not.toBe(firstRun);
    expect(api.runDamSimulation).toHaveBeenCalledTimes(2);
    expect(ctx.isOutdated).toBe(false);
  });
});
