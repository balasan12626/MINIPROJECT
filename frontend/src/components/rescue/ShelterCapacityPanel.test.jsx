import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const setShelter = vi.fn();
vi.mock("../../services/api.js", () => ({ setShelter: (...a) => setShelter(...a) }));

import ShelterCapacityPanel, { shelterChangeNote } from "./ShelterCapacityPanel.jsx";

const row = (name, extra = {}) => ({
  name,
  capacity: 1400,
  base_capacity: 1400,
  baseline_occupancy: 110,
  allocated_this_run: 6,
  incoming: 4,
  delivered_this_run: 2,
  seats_left: 1284,
  utilisation_pct: 8.3,
  closed: false,
  operator: false,
  moved_away: 0,
  ...extra,
});

describe("shelter capacity panel (F2)", () => {
  it("shows a closed shelter greyed with 0 free and delivered-before-closing", () => {
    render(
      <ShelterCapacityPanel
        allocation={[row("Delhi University Sports Complex", { closed: true, seats_left: 0, operator: true, moved_away: 3 }), row("Chhatrasal Stadium")]}
      />
    );
    expect(screen.getByText("🚫 1 closed")).toBeTruthy();
    expect(screen.getByText(/arrived before closing/)).toBeTruthy();
    expect(screen.getByText(/3 moved away/)).toBeTruthy();
    // no edit controls without onState (read-only)
    expect(screen.queryByRole("button", { name: /Edit/ })).toBeNull();
  });

  it("closes a shelter through the backend and reports the reallocation", async () => {
    const res = { shelter_change: { name: "Chhatrasal Stadium", action: "closed", cleared: false, moved: 4, no_seats: 1 } };
    setShelter.mockResolvedValueOnce(res);
    const onState = vi.fn();
    render(<ShelterCapacityPanel allocation={[row("Chhatrasal Stadium")]} onState={onState} />);
    fireEvent.click(screen.getByRole("button", { name: /Edit/ }));
    fireEvent.click(screen.getByRole("button", { name: /Close/ }));
    await waitFor(() => expect(onState).toHaveBeenCalledWith(res));
    expect(setShelter).toHaveBeenCalledWith({ name: "Chhatrasal Stadium", closed: true });
    expect(screen.getByText(/4 group\(s\) moved · 1 group\(s\) have no shelter/)).toBeTruthy();
  });

  it("describes a reset", () => {
    const note = shelterChangeNote({ shelter_change: { name: "X", action: "reopened", cleared: true, moved: 0, no_seats: 0 } });
    expect(note).toContain("reset to the seeded capacity");
  });
});
