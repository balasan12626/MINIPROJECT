import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { WhatIfResults, applyCall, isStale } from "./WhatIfPanel.jsx";

vi.mock("../../services/api.js", () => ({
  fetchWhatIf: vi.fn(),
  runWhatIf: vi.fn(),
  setRoad: vi.fn(() => Promise.resolve({})),
  setShelter: vi.fn(() => Promise.resolve({})),
}));

const stats = (p50, p90) => ({ n: 10, mean: p50, p50, p90 });
const job = {
  job_id: "j1",
  status: "done",
  run_id: "SIM-1",
  tick: 4,
  runs: 10,
  horizon_min: 60,
  synthetic_arrivals: false,
  results: {
    options: [
      { key: "o0", label: "No change", option: { kind: "baseline" }, served_per_run: 8, still_waiting_per_run: 2, time_to_safe_censored_min: stats(30, 55) },
      {
        key: "o1",
        label: "+3 ambulances",
        option: { kind: "add_ambulances", n: 3 },
        served_per_run: 10,
        still_waiting_per_run: 0,
        time_to_safe_censored_min: stats(22, 40),
        vs_baseline: { runs: 10, mean_diff_min: -7.5, ci95_min: [-9.1, -5.9], faster_in_pct_of_runs: 100 },
      },
      {
        key: "o2",
        label: "Close Talkatora Indoor Stadium",
        option: { kind: "close_shelter", name: "Talkatora Indoor Stadium" },
        served_per_run: 7,
        still_waiting_per_run: 3,
        time_to_safe_censored_min: stats(33, 60),
        vs_baseline: { runs: 10, mean_diff_min: 2.1, ci95_min: [0.4, 3.8], faster_in_pct_of_runs: 10 },
      },
    ],
  },
};

describe("what-if planner", () => {
  it("shows measured per-option results with CI and the simulated label", () => {
    render(<WhatIfResults job={job} tick={5} runId="SIM-1" onApply={() => {}} busy={false} />);
    expect(screen.getByText(/Simulated from the live state at tick 4/)).toBeTruthy();
    expect(screen.getByText(/-7.5 min \[-9.1, -5.9\]/)).toBeTruthy();
    expect(screen.getByText("100% of runs")).toBeTruthy();
    expect(screen.queryByText(/stale/)).toBeNull();
    // live fleet is fixed: no Apply for extra ambulances, Apply for the shelter
    expect(screen.getAllByRole("button", { name: "Apply" })).toHaveLength(1);
    expect(screen.getByText("not live")).toBeTruthy();
  });

  it("marks a result stale after 5 ticks or a new run", () => {
    expect(isStale(job, 8, "SIM-1")).toBe(false);
    expect(isStale(job, 9, "SIM-1")).toBe(true);
    expect(isStale(job, 4, "SIM-2")).toBe(true);
    render(<WhatIfResults job={job} tick={9} runId="SIM-1" onApply={() => {}} busy={false} />);
    expect(screen.getByText(/stale — the run has moved on/)).toBeTruthy();
  });

  it("applies only through the existing shelter / road endpoints", () => {
    expect(applyCall({ kind: "close_shelter", name: "X" })).toBeTypeOf("function");
    expect(applyCall({ kind: "block_road", road_id: "R1" })).toBeTypeOf("function");
    expect(applyCall({ kind: "add_ambulances", n: 2 })).toBeNull();
    expect(applyCall({ kind: "dispatch_policy", policy: "optimal" })).toBeNull();
  });
});
