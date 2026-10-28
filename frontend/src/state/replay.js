/** F5 — turn one stored replay frame into the same shape as a live
 * GET /api/simulation/state payload, so the existing components
 * (LiveRescueMap via deriveRescueOps, ShelterCapacityPanel, FleetPanel) render
 * it unchanged. Pure; no simulation — every value is copied from the frame. */

const EMPTY = [];

export function frameToView(frame) {
  if (!frame) return null;
  const citizens = frame.citizens || EMPTY;
  return {
    replay: true,
    run_id: frame.run_id,
    status: frame.status,
    scenario: frame.scenario,
    tick: frame.tick,
    // Rows carry their own ops fields; the live payload has them on both.
    citizens,
    contact_log: citizens,
    team_paths: EMPTY,
    eta_board: EMPTY,
    events: EMPTY,
    shelter_board: EMPTY,
    shelter_allocation: frame.shelter_allocation || EMPTY,
    shelter_overrides: frame.shelter_overrides || {},
    fleet_board: frame.fleet_board || null,
    accept_mode: frame.accept_mode || "auto",
    current: {
      flood_probability: frame.probability ?? null,
      risk_category: frame.risk_category ?? null,
      rainfall_mm: frame.rainfall_mm ?? null,
      river_m: frame.river_m ?? null,
      barrage_stage_m: frame.dam_m ?? null,
    },
  };
}

/** Frame time in ms (the replay clock), or null. */
export function frameTime(frame) {
  const t = Date.parse(frame?.at || "");
  return Number.isFinite(t) ? t : null;
}

/** Messages already posted at the moment of `frame`, newest first. */
export function messagesAt(messages, frame, limit = 40) {
  const t = frameTime(frame);
  if (t === null) return EMPTY;
  const out = [];
  for (const m of messages || EMPTY) {
    const at = Date.parse(m.at || "");
    if (Number.isFinite(at) && at <= t) out.push(m);
  }
  return out.reverse().slice(0, limit);
}
