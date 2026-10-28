import { describe, expect, it } from "vitest";
import { deriveRescueOps } from "./rescueOps.js";
import { frameTime, frameToView, messagesAt } from "./replay.js";

const T0 = Date.parse("2026-10-09T10:00:00Z");
const iso = (ms) => new Date(ms).toISOString();

const frame = {
  run_id: "SIM-1",
  seq: 3,
  tick: 2,
  at: iso(T0 + 5000),
  cause: "tick",
  status: "running",
  probability: 0.71,
  tier: "READY",
  citizens: [
    {
      citizen_name: "Asha",
      lat: 28.65,
      lon: 77.26,
      people: 2,
      ops_status: "en_route",
      ops_stage_at: iso(T0),
      ops_stage_seconds: 10,
      unit_name: "Ambulance Unit 1",
      unit_role: "ambulance",
      unit_base: [28.6, 77.2],
      shelter_name: "Chhatrasal Stadium",
      shelter_lat: 28.6995,
      shelter_lon: 77.1918,
      route_to_person: { points: [[28.6, 77.2], [28.65, 77.26]], km: 8, sim_minutes: 20 },
    },
    { citizen_name: "Ravi", lat: 28.7, lon: 77.1, people: 1, ops_status: "rescued", ops_stage_at: iso(T0) },
  ],
  fleet_board: { ambulances: [], ambulances_total: 10, ambulances_free: 9, ambulances_busy: 1 },
  shelter_allocation: [{ name: "Chhatrasal Stadium", capacity: 1600, seats_left: 1500 }],
  shelter_overrides: { "Talkatora Indoor Stadium": { closed: true } },
};

describe("replay frameToView (F5)", () => {
  it("produces the shape the live map derivation expects", () => {
    const view = frameToView(frame);
    expect(view.replay).toBe(true);
    expect(view.citizens).toBe(frame.citizens);
    expect(view.contact_log).toBe(frame.citizens);
    expect(view.shelter_allocation).toBe(frame.shelter_allocation);
    expect(view.current.flood_probability).toBe(0.71);

    const ops = deriveRescueOps(view, frameTime(frame));
    expect(ops.people.map((p) => p.name)).toEqual(["Asha", "Ravi"]);
    expect(ops.counters.rescued).toBe(1);
    // the moving unit is half-way along its leg at the frame's own time
    const asha = ops.people.find((p) => p.name === "Asha");
    expect(asha.progress).toBeCloseTo(0.5, 5);
    expect(ops.units).toHaveLength(1);
    expect(ops.closedShelters).toEqual(["Talkatora Indoor Stadium"]);
  });

  it("returns null for no frame", () => {
    expect(frameToView(null)).toBeNull();
    expect(frameTime({ at: "nope" })).toBeNull();
  });

  it("shows only messages posted up to the frame, newest first", () => {
    const msgs = [
      { id: 1, at: iso(T0 + 1000), text: "a" },
      { id: 2, at: iso(T0 + 4000), text: "b" },
      { id: 3, at: iso(T0 + 9000), text: "later" },
    ];
    expect(messagesAt(msgs, frame).map((m) => m.text)).toEqual(["b", "a"]);
  });
});
