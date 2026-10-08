/** Derives a live rescue-operations view from authoritative backend state.
 *
 * ────────────────────────────────────────────────────────────────────────────
 * THIS IS NOT A SIMULATION. It invents no people, no stages and no outcomes.
 *
 * backend/services/person_ops.py is the stage machine. It advances every
 * person queued → assigned → en_route → to_shelter → rescued, times each stage
 * from the real route travel time, and serialises per person:
 *
 *     ops_stage_at        when the current stage began (server clock)
 *     ops_stage_seconds   how long the current stage lasts (wall seconds)
 *     route_to_person     { points: [[lat,lon]…], km, sim_minutes }  base → person
 *     route_to_shelter    { points, km, sim_minutes }                person → shelter
 *
 * The backend never stores where a vehicle IS at an instant. The only thing
 * computed here is POSITION ALONG THAT REAL ROUTE, clocked by the real stage
 * timestamps:
 *
 *     progress = (serverNow - ops_stage_at) / ops_stage_seconds
 *     en_route    -> along route_to_person
 *     to_shelter  -> along route_to_shelter
 *
 * It is a derived view-model interpolation — never GPS — and the UI says so.
 * ────────────────────────────────────────────────────────────────────────────
 */
import { formatTimeIST } from "../utils/time.js";
import { PRIORITY_LABELS, STAGES, shelterLocation, TEAM_BY_NAME } from "../data/rescueAssets.js";

const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

/** A SAFE bubble shrinks to a small dot this long after arrival. */
export const SAFE_SHRINK_MS = 5000;

export function lerp(a, b, t) {
  return a + (b - a) * t;
}

/** Bearing in degrees, 0 = north, for rotating a vehicle glyph. */
export function bearingDeg([lat1, lon1], [lat2, lon2]) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dLon = toRad(lon2 - lon1);
  const y = Math.sin(dLon) * Math.cos(toRad(lat2));
  const x =
    Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) -
    Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(dLon);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

const isNum = (v) => v !== null && v !== "" && Number.isFinite(Number(v));
const parseTs = (v) => {
  if (v == null || v === "") return null;
  const s = String(v);
  // Naive ISO from the backend is UTC (same rule as utils/time.js).
  const naive = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s);
  const t = Date.parse(naive ? `${s}Z` : s);
  return Number.isFinite(t) ? t : null;
};

const validPoint = (p) => Array.isArray(p) && isNum(p[0]) && isNum(p[1]);

/** Cumulative planar lengths of a polyline, for constant-speed interpolation. */
export function pathMetrics(points) {
  const cum = [0];
  for (let i = 1; i < points.length; i += 1) {
    const [a0, a1] = points[i - 1];
    const [b0, b1] = points[i];
    // cos(lat) scales longitude so north-south and east-west legs weigh fairly.
    const k = Math.cos(((a0 + b0) / 2) * (Math.PI / 180));
    cum.push(cum[i - 1] + Math.hypot(b0 - a0, (b1 - a1) * k));
  }
  return { cum, total: cum[cum.length - 1] || 0 };
}

/** Point at fraction `t` (0..1) of the polyline's length. */
export function positionAlong(points, cum, t) {
  if (!points?.length) return null;
  if (points.length === 1) return points[0];
  const total = cum[cum.length - 1];
  if (!(total > 0)) return points[t >= 1 ? points.length - 1 : 0];
  const d = clamp01(t) * total;
  let i = 1;
  while (i < cum.length - 1 && cum[i] < d) i += 1;
  const seg = cum[i] - cum[i - 1] || 1;
  const f = (d - cum[i - 1]) / seg;
  const a = points[i - 1];
  const b = points[i];
  return [lerp(a[0], b[0], f), lerp(a[1], b[1], f)];
}

/** Sub-polyline between fractions t0..t1 (for trails / remaining route). */
export function slicePath(points, cum, t0, t1) {
  if (!points?.length) return [];
  const total = cum[cum.length - 1];
  const d0 = clamp01(t0) * total;
  const d1 = clamp01(t1) * total;
  const out = [positionAlong(points, cum, t0)];
  for (let i = 1; i < points.length - 1; i += 1) {
    if (cum[i] > d0 && cum[i] < d1) out.push(points[i]);
  }
  out.push(positionAlong(points, cum, t1));
  return out;
}

/** Stage of a citizen, using the backend's own precedence. */
export function stageOf(c) {
  const s = c?.ops_status || c?.live_status || c?.status || "queued";
  return STAGES.includes(s) ? s : "queued";
}

/** Stable identity. `_id` only exists when Mongo is connected, and
 * `rescue_order` is re-ranked whenever the roster changes, so neither is safe
 * as a React key. The backend keeps citizen_name unique (SEND SOS suffixes a
 * duplicate name), and joins on it everywhere, so we do too. */
export function personKey(c) {
  return String(c?.citizen_name || "unknown");
}

/** The client and server clocks can disagree; every timestamp we interpolate
 * against is server-issued. Estimate the offset from the newest server stamp
 * we can see, so `progress` stays truthful. */
export function serverClockOffset(sim, clientNowMs = Date.now()) {
  let newest = null;
  for (const c of sim?.citizens || []) {
    const t = parseTs(c?.ops_stage_at);
    if (t !== null && (newest === null || t > newest)) newest = t;
  }
  for (const e of sim?.events || []) {
    const t = parseTs(e?.timestamp);
    if (t !== null && (newest === null || t > newest)) newest = t;
  }
  if (newest === null) return 0;
  // Only correct forward: a stage cannot have started in the future.
  return Math.max(0, newest - clientNowMs);
}

/** Where the unit serving this person starts (its depot / staging base). */
function baseFor(c, pathsByName) {
  if (validPoint(c?.unit_base)) return [Number(c.unit_base[0]), Number(c.unit_base[1])];
  const path = pathsByName.get(personKey(c));
  if (path && validPoint(path.from)) return [Number(path.from[0]), Number(path.from[1])];
  const team = TEAM_BY_NAME.get(c?.assigned_team_name || c?.assigned_team);
  if (team) return [team.lat, team.lon];
  return null;
}

function routePoints(route) {
  const pts = (route?.points || []).filter(validPoint).map((p) => [Number(p[0]), Number(p[1])]);
  return pts.length >= 2 ? pts : null;
}

/**
 * @param {object} sim   raw GET /api/simulation/state payload
 * @param {number} nowMs server-corrected "now" in ms
 */
export function deriveRescueOps(sim, nowMs) {
  const citizens = sim?.citizens || [];
  const pathsByName = new Map();
  for (const p of sim?.team_paths || []) {
    if (p?.citizen_name) pathsByName.set(String(p.citizen_name), p);
  }
  const etaByName = new Map();
  for (const e of sim?.eta_board || []) {
    if (e?.citizen_name) etaByName.set(String(e.citizen_name), e);
  }
  const logByName = new Map();
  for (const r of sim?.contact_log || []) {
    if (r?.citizen_name) logByName.set(String(r.citizen_name), r);
  }

  const people = [];
  const units = [];

  for (const c of citizens) {
    const key = personKey(c);
    const log = logByName.get(key) || {};
    const stage = stageOf(c);
    const lat = Number(c.lat);
    const lon = Number(c.lon);
    const hasPos = isNum(c.lat) && isNum(c.lon);

    const stageStartedAt = parseTs(c.ops_stage_at);
    const stageSeconds = Number(c.ops_stage_seconds ?? log.ops_stage_seconds);
    const stageMs = Number.isFinite(stageSeconds) && stageSeconds > 0 ? stageSeconds * 1000 : null;
    const progress =
      stageStartedAt === null || stageMs === null ? 0 : clamp01((nowMs - stageStartedAt) / stageMs);

    const shelterName = c.shelter_name || log.shelter_name || null;
    const shelterLoc =
      isNum(c.shelter_lat) && isNum(c.shelter_lon)
        ? { name: shelterName, lat: Number(c.shelter_lat), lon: Number(c.shelter_lon) }
        : shelterLocation(shelterName);
    const base = baseFor(c, pathsByName);
    const priority = c.vulnerability || log.vulnerability || "standard";
    const unitRole = c.unit_role || log.unit_role || (c.ambulance_name ? "ambulance" : "rescue");
    const unitName =
      c.unit_name || log.unit_name || (unitRole === "ambulance" ? c.ambulance_name : null) ||
      c.assigned_team_name || c.assigned_team || null;
    const eta = etaByName.get(key);

    const person = {
      key,
      name: c.citizen_name,
      age: c.age ?? null,
      people: c.people ?? null,
      waterNote: c.water_level_note || "",
      lat: hasPos ? lat : null,
      lon: hasPos ? lon : null,
      stage,
      stageStartedAt,
      stageSeconds: stageMs === null ? null : stageMs / 1000,
      progress,
      rescueOrder: c.rescue_order ?? log.person_index ?? null,
      priority,
      priorityRing: PRIORITY_LABELS.has(priority),
      triage: c.triage || null,
      cluster: c.cluster_id || log.cluster_id || null,
      team: c.assigned_team_name || c.assigned_team || log.assigned_team || null,
      unitRole,
      unitName,
      unitBaseName: c.unit_base_name || null,
      ambulance: c.ambulance_name || null,
      shelter: shelterName,
      shelterLoc,
      depot: base,
      // Route travel time (simulated minutes) computed by the backend.
      etaMin: c.eta_min ?? eta?.eta_min ?? null,
      etaShelterMin: c.eta_to_shelter_min ?? eta?.eta_to_shelter_min ?? null,
      routeKm: c.route_to_person?.km ?? null,
      shelterKm: c.route_to_shelter?.km ?? null,
      waitReason: c.ops_wait_reason || null,
      calledAt: c.called_at || log.called_at || null,
      answered: c.answered ?? log.answered ?? null,
      rescued: c.rescued ?? log.rescued ?? null,
      journey: c.journey || log.journey || [],
      timestamps: c.timestamps || log.timestamps || {},
      safeSmall: stage === "rescued" && stageStartedAt !== null && nowMs - stageStartedAt > SAFE_SHRINK_MS,
      role: unitRole,
    };
    people.push(person);

    // ---- moving unit for this person -------------------------------------
    // Only en_route and to_shelter have a unit in motion; nothing else is drawn.
    let path = null;
    if (stage === "en_route" && hasPos) {
      path = routePoints(c.route_to_person) || (base ? [base, [lat, lon]] : null);
    } else if (stage === "to_shelter" && hasPos) {
      path = routePoints(c.route_to_shelter) || (shelterLoc ? [[lat, lon], [shelterLoc.lat, shelterLoc.lon]] : null);
    }
    if (path) {
      const { cum } = pathMetrics(path);
      const position = positionAlong(path, cum, progress);
      units.push({
        key: `${unitName || "unit"}|${key}|${stage}`,
        personKey: key,
        role: unitRole,
        label: unitName || (unitRole === "ambulance" ? "Ambulance" : "Rescue team"),
        personName: person.name,
        people: person.people,
        stage,
        target: stage === "to_shelter" ? shelterName : person.name,
        stageStartedAt,
        stageMs,
        path,
        cum,
        from: path[0],
        to: path[path.length - 1],
        position,
        progress,
        moving: stageMs !== null && stageStartedAt !== null && progress < 1,
        bearing: bearingDeg(path[0], path[path.length - 1]),
      });
    }
  }

  people.sort((a, b) => (a.rescueOrder || 99) - (b.rescueOrder || 99));

  // ---- shelters: backend occupancy + what THIS run actually delivered -----
  // The backend's occupancy is a growth curve unrelated to rescues, so the two
  // numbers are reported separately rather than blended.
  const arrivedByShelter = new Map();
  const inboundByShelter = new Map();
  const assignedByShelter = new Map();
  for (const p of people) {
    if (!p.shelter) continue;
    const n = Number(p.people) || 1;
    assignedByShelter.set(p.shelter, (assignedByShelter.get(p.shelter) || 0) + n);
    const bucket = p.stage === "rescued" ? arrivedByShelter : p.stage === "to_shelter" ? inboundByShelter : null;
    if (bucket) bucket.set(p.shelter, (bucket.get(p.shelter) || 0) + n);
  }
  const shelters = (sim?.shelter_board || []).map((s) => {
    const loc = shelterLocation(s.name);
    return {
      id: s.shelter_id || s.name,
      name: s.name,
      lat: loc?.lat ?? null,
      lon: loc?.lon ?? null,
      capacity: s.capacity ?? loc?.capacity ?? null,
      backendOccupancy: s.occupancy ?? null,
      seatsLeft: s.seats_left ?? null,
      full: Boolean(s.full),
      usedThisRun: Boolean(s.used_this_run) || assignedByShelter.has(s.name),
      assignedThisRun: assignedByShelter.get(s.name) || 0,
      arrivedThisRun: arrivedByShelter.get(s.name) || 0,
      inboundThisRun: inboundByShelter.get(s.name) || 0,
    };
  });

  // ---- counters ----------------------------------------------------------
  const by = (stage) => people.filter((p) => p.stage === stage).length;
  const counters = {
    totalSos: people.length,
    waiting: by("queued"),
    assigned: by("assigned"),
    enRoute: by("en_route"),
    transporting: by("to_shelter"),
    rescued: by("rescued"),
    peopleRescued: people.filter((p) => p.stage === "rescued").reduce((n, p) => n + (Number(p.people) || 0), 0),
    // Units genuinely in motion right now (arrived-but-not-yet-advanced excluded).
    unitsMoving: units.filter((u) => u.moving).length,
  };

  return { people, units, shelters, counters };
}

/** Unified live event feed: the engine's own events merged with every
 * per-person stage transition. Both carry real server timestamps. */
export function buildEventFeed(sim, limit = 60) {
  const out = [];
  for (const e of sim?.events || []) {
    const at = parseTs(e?.timestamp);
    if (at === null) continue;
    out.push({ at, kind: "engine", text: e.message || "", simTime: e.sim_time_sec ?? null, who: "Engine" });
  }
  for (const c of sim?.citizens || []) {
    for (const j of c?.journey || []) {
      const at = parseTs(j?.at);
      if (at === null) continue;
      out.push({
        at,
        kind: "person",
        stage: j.status || String(j.event || "").toLowerCase(),
        text: `${c.citizen_name} — ${j.detail || j.event}`,
        who: j.agent || "Ops",
        personKey: personKey(c),
      });
    }
  }
  out.sort((a, b) => b.at - a.at);
  return out.slice(0, limit);
}

/** Every rendered timestamp goes through the one IST formatter. */
export function formatClock(ms) {
  return formatTimeIST(ms, "--:--:--");
}
