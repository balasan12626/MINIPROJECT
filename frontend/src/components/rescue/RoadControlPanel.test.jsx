import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const setRoad = vi.fn();
vi.mock("../../services/api.js", () => ({ setRoad: (...a) => setRoad(...a) }));

import RoadControlPanel, { roadChangeNote } from "./RoadControlPanel.jsx";

const roads = [
  { road_id: "R04", name: "Mathura Road Nizamuddin", blocked: false, source: "open", operator: false, active_legs: 7, flood_exposure: 0.33, segments: [] },
  { road_id: "R08", name: "Yamuna Bank Road", blocked: true, source: "flood", operator: false, active_legs: 0, flood_exposure: 0.82, segments: [] },
  { road_id: "R02", name: "NH-9 Geeta Colony", blocked: true, source: "operator", operator: true, active_legs: 0, flood_exposure: 0.61, segments: [] },
];

describe("road control panel (F1)", () => {
  it("shows who closed each road and the active legs from state", () => {
    render(<RoadControlPanel roads={roads} />);
    expect(screen.getByText("2/3 closed")).toBeTruthy();
    expect(screen.getByText(/Closed by flood/)).toBeTruthy();
    expect(screen.getByText(/Blocked by operator/)).toBeTruthy();
    expect(screen.getByText("7 active leg(s)")).toBeTruthy();
    // only operator-controlled roads can be handed back to the flood rule
    expect(screen.getAllByRole("button", { name: /Back to flood rule/ })).toHaveLength(1);
  });

  it("blocks a road through the backend and reports the re-plan", async () => {
    const res = { road_change: { road_id: "R04", name: "Mathura Road Nizamuddin", blocked: true, cleared: false, rerouted: 5, no_open_road: 1 } };
    setRoad.mockResolvedValueOnce(res);
    const onState = vi.fn();
    render(<RoadControlPanel roads={roads} onState={onState} />);
    fireEvent.click(screen.getByRole("button", { name: /Block/ }));
    await waitFor(() => expect(onState).toHaveBeenCalledWith(res));
    expect(setRoad).toHaveBeenCalledWith({ road_id: "R04", blocked: true });
    expect(screen.getByText(/5 route leg\(s\) re-planned · 1 with no open road/)).toBeTruthy();
  });

  it("describes a hand-back to the flood rule", () => {
    const note = roadChangeNote({ road_change: { road_id: "R02", name: "NH-9", blocked: false, cleared: true, rerouted: 0 } });
    expect(note).toContain("handed back to the flood rule");
  });
});
