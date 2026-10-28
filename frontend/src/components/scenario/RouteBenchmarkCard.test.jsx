import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

const fetchRouteBenchmark = vi.fn();
vi.mock("../../services/api.js", () => ({ fetchRouteBenchmark: (...a) => fetchRouteBenchmark(...a) }));
// Recharts needs layout; the table + labels are what is under test.
vi.mock("recharts", () => {
  const Box = ({ children }) => <div>{children}</div>;
  const Nil = () => null;
  return {
    ResponsiveContainer: Box,
    BarChart: Box,
    LineChart: Box,
    Bar: Nil,
    Line: Nil,
    CartesianGrid: Nil,
    XAxis: Nil,
    YAxis: Nil,
    Tooltip: Nil,
    Legend: Nil,
  };
});

import RouteBenchmarkCard from "./RouteBenchmarkCard.jsx";

const stats = (mean) => ({ n: 10, mean, median: mean, p95: mean });
const level = (blockage, pct, single) => ({
  blockage,
  roads_closed: blockage ? ["R08"] : [],
  trips: 10,
  routed: 10,
  no_open_road: 0,
  same_junction: 0,
  single_candidate_trips: single,
  qaoa_equals_exhaustive_pct: pct,
  qaoa_equals_dijkstra_pct: pct,
  methods: {
    dijkstra: { travel_min: stats(60), hazard: stats(3) },
    qaoa: { travel_min: stats(60.1), hazard: stats(2.5) },
    exhaustive: { travel_min: stats(60.1), hazard: stats(2.5) },
    direct: { travel_min: stats(30) },
  },
});

describe("route benchmark card (F6)", () => {
  it("says when the benchmark was not generated", async () => {
    fetchRouteBenchmark.mockResolvedValueOnce(null);
    render(<RouteBenchmarkCard />);
    expect(await screen.findByText(/Not generated yet/)).toBeTruthy();
  });

  it("shows measured values and an honest 'nothing to choose'", async () => {
    fetchRouteBenchmark.mockResolvedValueOnce({
      settings: { trips: 10, seed: 42, candidates_k: 4, qaoa_layers: 3, qaoa_shots: 512 },
      code: { commit: "abcdef1234", dirty_worktree: true },
      levels: [level(0, 100, 3), level(0.1, null, 10)],
      timing: { levels: [{ qaoa_ms: { mean: 700 } }, { qaoa_ms: { mean: null } }] },
    });
    render(<RouteBenchmarkCard />);
    expect(await screen.findByText("10 synthetic trips · seed 42")).toBeTruthy();
    expect(screen.getByText("100%")).toBeTruthy();
    expect(screen.getByText("— (nothing to choose)")).toBeTruthy();
    expect(screen.getByText("700 ms")).toBeTruthy();
    expect(screen.getByText(/no speed-up is claimed/)).toBeTruthy();
  });
});
