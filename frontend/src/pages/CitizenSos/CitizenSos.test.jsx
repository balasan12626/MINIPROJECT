import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const sendPublicSos = vi.fn();
const fetchSosStatus = vi.fn();
vi.mock("../../services/api.js", () => ({
  sendPublicSos: (...a) => sendPublicSos(...a),
  fetchSosStatus: (...a) => fetchSosStatus(...a),
}));
vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  Circle: () => null,
  Marker: () => <div data-testid="pin" />,
  useMapEvents: () => ({ setView: () => {} }),
}));

import CitizenSos from "./CitizenSos.jsx";

afterEach(() => {
  vi.unstubAllGlobals();
  try {
    window.localStorage.clear();
  } catch {
    /* ignore */
  }
});

const deny = () =>
  vi.stubGlobal("navigator", {
    ...navigator,
    geolocation: { getCurrentPosition: (_ok, bad) => bad({ code: 1 }) },
  });

describe("citizen SOS page (F4)", () => {
  it("validates the form before sending", () => {
    render(<CitizenSos />);
    fireEvent.click(screen.getByRole("button", { name: /Send SOS/ }));
    expect(screen.getByText("Please enter your name.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Meena" } });
    fireEvent.click(screen.getByRole("button", { name: /Send SOS/ }));
    expect(screen.getByText(/Share your location or place the pin/)).toBeTruthy();
    expect(sendPublicSos).not.toHaveBeenCalled();
  });

  it("geolocation denied → asks for a manual pin and shows the map", () => {
    deny();
    render(<CitizenSos />);
    fireEvent.click(screen.getByRole("button", { name: /Share my location/ }));
    expect(screen.getByText(/Location permission denied — tap the map or drag the pin/)).toBeTruthy();
    expect(screen.getByTestId("pin")).toBeTruthy();
  });

  it("sends the SOS and switches to the ticket status screen", async () => {
    deny();
    sendPublicSos.mockResolvedValueOnce({ ticket: "a".repeat(32) });
    fetchSosStatus.mockResolvedValue({ stage: "en_route", stage_text: "A rescue unit is on the way", unit: "Ambulance Unit 2", unit_role: "ambulance", eta_min: 7 });
    render(<CitizenSos />);
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Meena" } });
    fireEvent.click(screen.getByRole("button", { name: /Share my location/ }));
    fireEvent.click(screen.getByRole("button", { name: /Send SOS/ }));
    await waitFor(() => expect(sendPublicSos).toHaveBeenCalled());
    const form = sendPublicSos.mock.calls[0][0];
    expect(form.get("name")).toBe("Meena");
    expect(form.get("lat")).toBeTruthy();
    expect(await screen.findByText("A rescue unit is on the way")).toBeTruthy();
    expect(fetchSosStatus).toHaveBeenCalledWith("a".repeat(32));
  });
});

// F15: no signal → the SOS waits on the phone and is sent when the network returns.
let online = true;
const phone = () =>
  vi.stubGlobal("navigator", {
    get onLine() {
      return online;
    },
    geolocation: { getCurrentPosition: (_ok, bad) => bad({ code: 1 }) },
  });

const fillAndSend = () => {
  fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Meena" } });
  fireEvent.click(screen.getByRole("button", { name: /Share my location/ }));
  fireEvent.click(screen.getByRole("button", { name: /Send SOS/ }));
};

describe("citizen SOS offline queue (F15)", () => {
  beforeEach(() => {
    online = true;
    sendPublicSos.mockReset();
    fetchSosStatus.mockReset();
  });

  it("offline → keeps the SOS on the phone, sends it on 'online'", async () => {
    online = false;
    phone();
    sendPublicSos.mockResolvedValue({ ticket: "b".repeat(32) });
    fetchSosStatus.mockResolvedValue({ stage: "queued", stage_text: "Your SOS is in the queue" });
    render(<CitizenSos />);
    fillAndSend();
    expect(await screen.findByText(/No connection — your SOS is saved on this phone/)).toBeTruthy();
    expect(sendPublicSos).not.toHaveBeenCalled();
    const saved = JSON.parse(window.localStorage.getItem("aq_sos_outbox"));
    expect(saved.payload.name).toBe("Meena");

    online = true;
    window.dispatchEvent(new Event("online"));
    await waitFor(() => expect(sendPublicSos).toHaveBeenCalledTimes(1));
    expect(sendPublicSos.mock.calls[0][0].get("name")).toBe("Meena");
    await waitFor(() => expect(window.localStorage.getItem("aq_sos_outbox")).toBeNull());
    expect(window.localStorage.getItem("aq_sos_ticket")).toBe("b".repeat(32));
  });

  it("a send that gets no answer at all is queued, not lost", async () => {
    phone();
    sendPublicSos.mockRejectedValueOnce(new Error("Network Error"));
    render(<CitizenSos />);
    fillAndSend();
    expect(await screen.findByText(/No connection — your SOS is saved on this phone/)).toBeTruthy();
    expect(JSON.parse(window.localStorage.getItem("aq_sos_outbox")).payload.name).toBe("Meena");
  });

  it("a queued SOS the server refuses is dropped and the person is told why", async () => {
    phone();
    window.localStorage.setItem(
      "aq_sos_outbox",
      JSON.stringify({ payload: { name: "Ravi", people: 2, water: "knee-deep", lat: 28.65, lon: 77.26 }, photo: null })
    );
    sendPublicSos.mockRejectedValueOnce({ response: { status: 409, data: { detail: "No live run" } } });
    render(<CitizenSos />);
    expect(await screen.findByText(/Your saved SOS could not be delivered: No live run/)).toBeTruthy();
    expect(window.localStorage.getItem("aq_sos_outbox")).toBeNull();
  });
});
