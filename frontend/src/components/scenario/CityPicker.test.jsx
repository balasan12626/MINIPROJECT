import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

const ctx = vi.hoisted(() => ({ value: null }));
vi.mock("../../state/ScenarioContext.jsx", () => ({ useScenario: () => ctx.value }));

import CityPicker from "./CityPicker.jsx";

const cities = [
  {
    id: "delhi",
    name: "Delhi",
    state: "Delhi",
    why: "Yamuna floodplain.",
    flood_driver: "river",
    gauge: { station: "delhi rly bridge", river: "Ganga/Yamuna", warning_level_m: 204.5, danger_level_m: 205.33, source: "INDOFLOODS" },
    counts: { junctions: 859, shelters: 10, depots: 6 },
    attribution: "© OpenStreetMap contributors",
  },
  {
    id: "chennai",
    name: "Chennai",
    state: "Tamil Nadu",
    why: "Adyar / Cooum.",
    flood_driver: "rainfall",
    gauge: { reason: "no INDOFLOODS gauge within 30 km — rainfall-driven city" },
    counts: { junctions: 670, shelters: 10, depots: 6 },
    attribution: "© OpenStreetMap contributors",
  },
];

describe("city picker (F7)", () => {
  it("shows each city from the backend and how its flood is driven", () => {
    const setCityId = vi.fn();
    ctx.value = { cities, cityId: "chennai", setCityId, running: false };
    render(<CityPicker />);
    expect(screen.getByText("River gauge: delhi rly bridge")).toBeTruthy();
    expect(screen.getByText("Rainfall-driven")).toBeTruthy();
    expect(screen.getByText(/rainfall only \(no river-stage term\)/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Chennai/ }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: /Delhi/ }));
    expect(setCityId).toHaveBeenCalledWith("delhi");
  });

  it("renders nothing until the city list arrives", () => {
    ctx.value = { cities: [], cityId: "delhi", setCityId: vi.fn() };
    const { container } = render(<CityPicker />);
    expect(container.innerHTML).toBe("");
  });
});
