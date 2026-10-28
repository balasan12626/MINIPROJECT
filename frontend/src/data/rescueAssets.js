/** Static rescue assets, mirrored from the backend.
 *
 * The live engine assigns a person a shelter by NAME only
 * (backend/services/person_ops.py SHELTER_POOL is five bare strings with no id
 * and no coordinates), so the frontend has to resolve that name to a location
 * before it can draw the drop-off leg. These tables are copies of the backend's
 * own data — if you change a coordinate there, change it here.
 *
 * Sources:
 *   backend/services/seed.py         SHELTERS (8, canonical geography)
 *   backend/services/rescue_desk.py  SHELTERS (5, the desk's own set)
 *   backend/services/seed.py         RESCUE_TEAMS (4 depots)
 *   backend/services/person_ops.py   STAGES / STAGE_LABEL / SHELTER_POOL
 *
 * NOTE: "Yamuna Sports Complex Shelter" exists ONLY in rescue_desk.py, and
 * person_ops assigns from a pool that includes it — so a seed-only lookup
 * would silently fail to place one person in five. Both sets are merged below.
 */

/** Seed geography (drawn on the map as the full shelter network). */
export const SEED_SHELTERS = [
  { id: "S01", name: "Thyagaraj Sports Complex", lat: 28.5786, lon: 77.2134, capacity: 1800, zone: "South-Central" },
  { id: "S02", name: "Jawaharlal Nehru Stadium", lat: 28.5828, lon: 77.2344, capacity: 4200, zone: "South-East" },
  { id: "S03", name: "Chhatrasal Stadium", lat: 28.6995, lon: 77.1918, capacity: 1600, zone: "North" },
  { id: "S04", name: "Talkatora Indoor Stadium", lat: 28.6254, lon: 77.1952, capacity: 1200, zone: "Central" },
  { id: "S05", name: "Commonwealth Games Village Hall", lat: 28.6098, lon: 77.2755, capacity: 900, zone: "East Yamuna" },
  { id: "S06", name: "Delhi University Sports Complex", lat: 28.6886, lon: 77.2095, capacity: 1400, zone: "North Campus" },
  { id: "S07", name: "IIT Delhi Lecture Hall Complex", lat: 28.5456, lon: 77.1926, capacity: 1100, zone: "South" },
  { id: "S08", name: "Akshardham Community Shelter", lat: 28.6127, lon: 77.2773, capacity: 800, zone: "East Yamuna" },
];

/** The rescue desk's set — the only source for "Yamuna Sports Complex Shelter". */
const DESK_SHELTERS = [
  { id: "SH-01", name: "Delhi University Sports Complex", lat: 28.688, lon: 77.209, capacity: 2000, zone: "North Campus" },
  { id: "SH-02", name: "Talkatora Indoor Stadium", lat: 28.625, lon: 77.195, capacity: 1800, zone: "Central" },
  { id: "SH-03", name: "Jawaharlal Nehru Stadium", lat: 28.583, lon: 77.234, capacity: 3200, zone: "South-East" },
  { id: "SH-04", name: "Commonwealth Games Village Hall", lat: 28.612, lon: 77.275, capacity: 1500, zone: "East Yamuna" },
  { id: "SH-05", name: "Yamuna Sports Complex Shelter", lat: 28.655, lon: 77.305, capacity: 1500, zone: "East Yamuna" },
];

/** name -> {lat, lon, capacity, zone}. Seed wins on collisions; the desk fills gaps. */
export const SHELTER_BY_NAME = (() => {
  const map = new Map();
  for (const s of DESK_SHELTERS) map.set(s.name, s);
  for (const s of SEED_SHELTERS) map.set(s.name, s);
  return map;
})();

export function shelterLocation(name) {
  if (!name) return null;
  return SHELTER_BY_NAME.get(String(name).trim()) || null;
}

/** Depots. Units start here; the backend never moves them. */
export const RESCUE_TEAMS = [
  { team_id: "RT-01", name: "NDRF 8th Bn Detachment", lat: 28.6698, lon: 77.4306, capacity: 12 },
  { team_id: "RT-02", name: "Delhi Fire Service HQ", lat: 28.6328, lon: 77.2197, capacity: 8 },
  { team_id: "RT-03", name: "Delhi Police Disaster Cell ITO", lat: 28.6288, lon: 77.2419, capacity: 10 },
  { team_id: "RT-04", name: "SDRF North District", lat: 28.7041, lon: 77.1025, capacity: 8 },
];

export const TEAM_BY_NAME = new Map(RESCUE_TEAMS.map((t) => [t.name, t]));

/* ------------------------------------------------------------------ stages */

/** backend/services/person_ops.py STAGES — the only five a live person can be in. */
export const STAGES = ["queued", "assigned", "en_route", "to_shelter", "rescued"];

/** Stage length is NOT fixed. person_ops.py times each stage from the real
 * route travel time and serialises it per person as `ops_stage_seconds`
 * (wall seconds), next to `ops_stage_at`. The frontend interpolates with those.
 * There is deliberately no fixed STAGE_SECONDS constant any more. */

/** One child definition, mirrored from backend/thresholds.py:
 * child = age < CHILD_MAX_AGE, elderly = age >= ELDERLY_MIN_AGE. */
export const CHILD_MAX_AGE = 12;
export const ELDERLY_MIN_AGE = 60;
export const isChild = (age) => age != null && age !== "" && Number(age) < CHILD_MAX_AGE;

/** Priority labels (backend priority.vulnerability_label) that get the thick ring. */
export const PRIORITY_LABELS = new Set(["child", "elderly", "chest-deep"]);

/** Mirrors person_ops.STAGE_LABEL, which is never serialised to the frontend. */
export const STAGE_LABEL = {
  queued: "In SOS queue — waiting for dispatch",
  assigned: "Unit + shelter assigned (K-means team linked)",
  en_route: "Unit en route to the person",
  to_shelter: "Picked up — transporting to shelter",
  rescued: "Completed — person at shelter (rescued)",
};

/** Short badge text. */
export const STAGE_SHORT = {
  queued: "WAITING",
  assigned: "ASSIGNED",
  en_route: "EN ROUTE",
  to_shelter: "TRANSPORT",
  rescued: "SAFE",
};

/** Stage colours — the theme tokens from index.css (with fallbacks), so the
 * roster pills, the feed and the map bubbles all read one palette.
 * Waiting=--status-sos, assigned=--status-assigned, en route=--status-enroute,
 * transport=--status-transport, safe=--status-safe. Use in CSS/inline styles
 * only; canvas layers must resolve them with cssToken(). */
export const STAGE_TOKEN = {
  queued: ["--status-sos", "#ef4444"],
  assigned: ["--status-assigned", "#818cf8"],
  en_route: ["--status-enroute", "#f97316"],
  to_shelter: ["--status-transport", "#a855f7"],
  rescued: ["--status-safe", "#22c55e"],
};
export const STAGE_COLOR = Object.fromEntries(
  Object.entries(STAGE_TOKEN).map(([k, [v, fb]]) => [k, `var(${v}, ${fb})`])
);

/** Resolve a CSS custom property to a concrete colour (for Leaflet's canvas
 * renderer, which cannot use var()). */
export function cssToken(name, fallback) {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  } catch {
    return fallback;
  }
}

export function stageIndex(stage) {
  const i = STAGES.indexOf(stage);
  return i < 0 ? 0 : i;
}
