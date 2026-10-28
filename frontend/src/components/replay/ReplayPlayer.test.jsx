import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

const fetchRuns = vi.fn();
const fetchRunFrames = vi.fn();
const fetchRunMessages = vi.fn();
vi.mock("../../services/api.js", () => ({
  fetchRuns: (...a) => fetchRuns(...a),
  fetchRunFrames: (...a) => fetchRunFrames(...a),
  fetchRunMessages: (...a) => fetchRunMessages(...a),
  fetchRunEquity: () => Promise.resolve(null),
  runReportUrl: (id) => `/api/simulation/runs/${id}/report.pdf`,
  setAcceptMode: vi.fn(),
  setShelter: vi.fn(),
}));
vi.mock("../rescue/LiveRescueMap.jsx", () => ({ default: () => <div data-testid="map" /> }));

import ReplayPlayer from "./ReplayPlayer.jsx";

const at = "2026-10-09T10:00:05Z";
const frame = (seq) => ({
  run_id: "SIM-9",
  seq,
  tick: seq,
  at,
  cause: "tick",
  probability: 0.5,
  tier: "READY",
  citizens: [],
  fleet_board: null,
  shelter_allocation: [],
});

describe("replay player (F5)", () => {
  it("lists runs, opens one, and labels it REPLAY with no edit controls", async () => {
    fetchRuns.mockResolvedValue({
      persisted: false,
      runs: [{ run_id: "SIM-9", scenario: "heavy_rainfall", frames: 2, sos: 3, rescued: 1, persisted: false }],
    });
    fetchRunFrames.mockResolvedValue({ frames: [frame(1), frame(2)], total: 2, persisted: false });
    fetchRunMessages.mockResolvedValue({ messages: [] });
    render(<ReplayPlayer />);
    expect(await screen.findByText(/MongoDB off — last run only, not persisted/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Replay/ }));
    expect(await screen.findByText(/REPLAY — not live\./)).toBeTruthy();
    expect(screen.getByText(/frame 1 of 2/)).toBeTruthy();
    expect(screen.getByTestId("map")).toBeTruthy();
    // read-only: no shelter Edit, no accept-mode toggle
    expect(screen.queryByRole("button", { name: /Edit/ })).toBeNull();
    expect(screen.queryByRole("radio", { name: /Drivers decide/ })).toBeNull();
    fireEvent.change(screen.getByLabelText("Replay position"), { target: { value: "1" } });
    expect(screen.getByText(/frame 2 of 2/)).toBeTruthy();
  });
});
