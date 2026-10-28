import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import FindPage from "./FindPage.jsx";

vi.mock("../../services/api.js", () => ({
  fetchSosStatus: vi.fn(() => Promise.resolve({ stage: "rescued", stage_text: "Safe at the shelter", safe_at: { name: "Talkatora", kind: "shelter", lat: 1, lon: 2 } })),
  fetchCities: vi.fn(() => Promise.resolve({ cities: [] })),
  sendPublicSos: vi.fn(),
}));

describe("/find family lookup", () => {
  it("states the privacy rule and refuses anything that is not a ticket", () => {
    render(
      <MemoryRouter initialEntries={["/find"]}>
        <FindPage />
      </MemoryRouter>
    );
    expect(screen.getByText(/Only people with the SOS ticket can see this/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/SOS ticket or link/), { target: { value: "Asha Devi" } });
    fireEvent.click(screen.getByRole("button", { name: "Show status" }));
    expect(screen.getByText(/That is not an SOS ticket/)).toBeTruthy();
  });

  it("shows where the person is safe from a shared link", async () => {
    render(
      <MemoryRouter initialEntries={[`/find?t=${"a".repeat(32)}`]}>
        <FindPage />
      </MemoryRouter>
    );
    expect(await screen.findByText("Talkatora")).toBeTruthy();
  });
});
