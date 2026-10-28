import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const fetchUnitJob = vi.fn();
const acceptJob = vi.fn();
const rejectJob = vi.fn();
vi.mock("../../services/api.js", () => ({
  fetchUnitJob: (...a) => fetchUnitJob(...a),
  acceptJob: (...a) => acceptJob(...a),
  rejectJob: (...a) => rejectJob(...a),
}));
// Leaflet needs a real layout engine; the job card is what is under test.
vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  Polyline: () => null,
  CircleMarker: () => null,
}));

import DriverApp from "./DriverApp.jsx";

const request = {
  unit: "Ambulance Unit 3",
  role: "ambulance",
  accept_mode: "manual",
  run_id: "SIM-1",
  status: "request",
  trips_completed: 0,
  job: {
    citizen_name: "Priya Sharma",
    age: 80,
    people: 2,
    water: "chest-deep",
    vulnerability: "elderly",
    stage: "assigned",
    shelter_name: "Chhatrasal Stadium",
    eta_min: 9.5,
    eta_to_shelter_min: 12,
    route_to_person: { km: 3.1, points: [[28.6, 77.2], [28.65, 77.26]] },
    route_to_shelter: { km: 5, points: [[28.65, 77.26], [28.69, 77.19]] },
    seconds_left: 14,
    rejected_by: ["Ambulance Unit 1"],
  },
};

const renderAt = (unit) =>
  render(
    <MemoryRouter initialEntries={[`/driver/${encodeURIComponent(unit)}`]}>
      <Routes>
        <Route path="/driver/:unit" element={<DriverApp />} />
      </Routes>
    </MemoryRouter>
  );

describe("driver app (F3)", () => {
  it("renders the waiting job from the backend", async () => {
    fetchUnitJob.mockResolvedValue(request);
    renderAt("Ambulance Unit 3");
    expect(await screen.findByText("Priya Sharma")).toBeTruthy();
    expect(fetchUnitJob).toHaveBeenCalledWith("Ambulance Unit 3");
    expect(screen.getByText("NEW SOS REQUEST")).toBeTruthy();
    expect(screen.getByText(/Answer within 14 s/)).toBeTruthy();
    expect(screen.getByText(/Already declined by: Ambulance Unit 1/)).toBeTruthy();
  });

  it("disables both buttons while the answer is posting", async () => {
    fetchUnitJob.mockResolvedValue(request);
    let release;
    acceptJob.mockReturnValueOnce(new Promise((r) => (release = r)));
    renderAt("Ambulance Unit 3");
    fireEvent.click(await screen.findByRole("button", { name: /Accept/ }));
    expect(screen.getByRole("button", { name: /Accept/ }).disabled).toBe(true);
    expect(screen.getByRole("button", { name: /Reject/ }).disabled).toBe(true);
    release({});
    await waitFor(() => expect(screen.getByText(/Accepted — drive safely/)).toBeTruthy());
    expect(acceptJob).toHaveBeenCalledWith("Ambulance Unit 3");
  });

  it("explains a double tap (409)", async () => {
    fetchUnitJob.mockResolvedValue(request);
    rejectJob.mockRejectedValueOnce({ response: { status: 409 } });
    renderAt("Ambulance Unit 3");
    fireEvent.click(await screen.findByRole("button", { name: /Reject/ }));
    expect(await screen.findByText(/Too late/)).toBeTruthy();
  });
});
