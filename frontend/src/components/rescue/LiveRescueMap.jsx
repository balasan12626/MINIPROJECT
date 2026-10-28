import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Circle, MapContainer, Marker, Polyline, Popup, TileLayer, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./rescueMap.css";
import {
  RESCUE_TEAMS,
  SEED_SHELTERS,
  STAGE_COLOR,
  STAGE_LABEL,
  STAGE_SHORT,
  cssToken,
  shelterLocation,
} from "../../data/rescueAssets.js";
import { positionAlong, slicePath } from "../../state/rescueOps.js";

const CENTER = [28.6139, 77.209];
// Same OpenStreetMap tiles as FloodMap / IndiaDamMap (CARTO now demands an
// API key). Dark mode darkens them in CSS (.lrm-map .leaflet-tile-pane).
const TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const CLUSTER_CELL_PX = 44;
const CLUSTER_MAX_ZOOM = 15; // at/above this zoom every SOS is drawn individually

const isValidCoord = (lat, lon) =>
  lat != null && lon != null && Number.isFinite(Number(lat)) && Number.isFinite(Number(lon)) &&
  Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

/* ------------------------------------------------------------------ icons */
/* Every icon is a cached L.divIcon keyed by its visual state. A stable icon
 * identity means react-leaflet never calls setIcon(), so a marker's DOM node
 * (and its CSS pulse) survives every 1.2 s poll. Leaflet's DivIcon.createIcon()
 * builds a fresh element per marker, so sharing one instance is safe. */
const ICON_CACHE = new Map();
/* Planned-leg styles, module-level so react-leaflet never sees new objects. */
const LEG_A = { color: "#f43f5e", weight: 2, opacity: 0.35, dashArray: "4 6" };
const LEG_A_SEL = { color: "#f43f5e", weight: 4, opacity: 0.9, dashArray: "8 6" };
const LEG_B = { color: "#34d399", weight: 2, opacity: 0.35, dashArray: "4 6" };
const LEG_B_SEL = { color: "#34d399", weight: 4, opacity: 0.9 };
const LEG_ALT = { color: "#a78bfa", weight: 2, opacity: 0.55, dashArray: "2 6" };
const LEG_A_GLOW = { color: "#f43f5e", weight: 12, opacity: 0.16, lineCap: "round" };
const LEG_B_GLOW = { color: "#34d399", weight: 12, opacity: 0.16, lineCap: "round" };
/* F1 road layer: open / closed-by-flood / operator styles (module-level). */
const ROAD_OPEN = { color: "#64748b", weight: 5, opacity: 0.45 };
const ROAD_OPEN_USED = { color: "#38bdf8", weight: 6, opacity: 0.6 };
const ROAD_FLOOD = { color: "#ef4444", weight: 6, opacity: 0.75, dashArray: "2 8", lineCap: "round" };
const ROAD_OPERATOR = { color: "#ef4444", weight: 7, opacity: 0.9, dashArray: "10 6" };
const ROAD_OPERATOR_OPEN = { color: "#22c55e", weight: 6, opacity: 0.7, dashArray: "10 6" };
// F10: open road the flood rule is forecast to close within 30 sim minutes.
const ROAD_CLOSING_SOON = { color: "#f59e0b", weight: 4, dashArray: "4 6", opacity: 0.9 };

function roadStyle(r) {
  if (r.blocked) return r.operator ? ROAD_OPERATOR : ROAD_FLOOD;
  if (r.operator) return ROAD_OPERATOR_OPEN;
  if (r.closes_in_sim_min != null && r.closes_in_sim_min <= 30) return ROAD_CLOSING_SOON;
  return r.active_legs ? ROAD_OPEN_USED : ROAD_OPEN;
}

function cached(key, make) {
  let ic = ICON_CACHE.get(key);
  if (!ic) {
    ic = make();
    ICON_CACHE.set(key, ic);
  }
  return ic;
}

/** Bubble diameter scales with the group size (1 … 5+). */
export function bubbleSize(people) {
  const n = Math.max(1, Math.min(5, Number(people) || 1));
  return 18 + n * 4;
}

function sosIconKey(p, selected) {
  return `sos|${p.stage}|${Number(p.people) || 1}|${p.priorityRing ? 1 : 0}|${selected ? 1 : 0}|${p.safeSmall ? 1 : 0}`;
}

function sosIcon(p, selected) {
  return cached(sosIconKey(p, selected), () => {
    const n = Number(p.people) || 1;
    const sz = p.safeSmall ? 10 : bubbleSize(n);
    const cls = [
      "lrm-sos",
      `lrm-${p.stage}`,
      p.priorityRing ? "lrm-ring" : "",
      selected ? "lrm-sel" : "",
      p.safeSmall ? "lrm-small" : "",
    ]
      .filter(Boolean)
      .join(" ");
    return L.divIcon({
      className: "lrm-sos-wrap",
      html: `<div class="${cls}" style="--sz:${sz}px"><span class="lrm-pulse"></span><b>${n}</b></div>`,
      iconSize: [sz, sz],
      iconAnchor: [sz / 2, sz / 2],
      popupAnchor: [0, -sz / 2],
    });
  });
}

function clusterIcon(count) {
  return cached(`cluster|${count}`, () => {
    const sz = 30 + Math.min(18, count * 2);
    return L.divIcon({
      className: "lrm-cluster-wrap",
      html: `<div class="lrm-cluster" style="--sz:${sz}px"><span class="lrm-pulse"></span>${count}</div>`,
      iconSize: [sz, sz],
      iconAnchor: [sz / 2, sz / 2],
    });
  });
}

/** Heading is constant for a leg, so it is baked into the (cached) icon in
 * 15° buckets instead of being written to the DOM every frame. */
function unitIcon(role, bearing) {
  if (role === "boat") {
    return cached("unit|boat", () =>
      L.divIcon({
        className: "lrm-unit-wrap",
        html: '<div class="lrm-unit lrm-boat">🚤</div>',
        iconSize: [22, 22],
        iconAnchor: [11, 11],
      })
    );
  }
  const b = Number.isFinite(bearing) ? Math.round(bearing / 15) * 15 : 0;
  const amb = role === "ambulance";
  return cached(`unit|${role}|${amb ? 0 : b}`, () =>
    L.divIcon({
      className: "lrm-unit-wrap",
      html:
        `<div class="lrm-unit lrm-${amb ? "ambulance" : "rescue"}">` +
        `<i${amb ? "" : ` style="transform:rotate(${b}deg)"`}>${amb ? "✚" : "▲"}</i></div>`,
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    })
  );
}

function depotIcon() {
  return cached("depot", () =>
    L.divIcon({ className: "lrm-depot-wrap", html: '<div class="lrm-depot"></div>', iconSize: [16, 16], iconAnchor: [8, 8] })
  );
}

/** F21: OSM hospital (cached, one instance). */
function hospitalIcon() {
  return cached("hospital", () =>
    L.divIcon({ className: "lrm-hospital-wrap", html: '<div class="lrm-hospital">🏥</div>', iconSize: [18, 18], iconAnchor: [9, 9] })
  );
}

/** F28: supply truck (cached, one instance). */
function truckIcon() {
  return cached("truck", () =>
    L.divIcon({ className: "lrm-truck-wrap", html: '<div class="lrm-truck">🚚</div>', iconSize: [18, 18], iconAnchor: [9, 9] })
  );
}

function idleAmbulanceIcon(kind) {
  return cached(`idle|${kind}`, () =>
    L.divIcon({
      className: "lrm-idle-wrap",
      html: `<div class="lrm-idle lrm-idle-${kind}">🚑</div>`,
      iconSize: [18, 18],
      iconAnchor: [9, 9],
    })
  );
}

function shelterIcon(used, full, closed) {
  return cached(`shelter|${used ? 1 : 0}|${full ? 1 : 0}|${closed ? 1 : 0}`, () =>
    L.divIcon({
      className: "lrm-shelter-wrap",
      html: `<div class="lrm-shelter${used ? " lrm-used" : ""}${full ? " lrm-full" : ""}${closed ? " lrm-closed" : ""}">${closed ? "🚫" : ""}</div>`,
      iconSize: [16, 16],
      iconAnchor: [8, 8],
    })
  );
}

/** Canvas polylines cannot use var(): resolve theme tokens once. */
let UNIT_COLORS = null;
function unitColor(role) {
  if (!UNIT_COLORS) {
    UNIT_COLORS = {
      ambulance: cssToken("--status-sos", "#ef4444"),
      rescue: cssToken("--accent", "#38bdf8"),
      boat: "#0284c7",
    };
  }
  return UNIT_COLORS[role] || UNIT_COLORS.rescue;
}

/* --------------------------------------------------------- clustering */

/** Lightweight screen-space grid clustering (no plugin). `project` maps
 * [lat, lon] to pixel {x, y} at the current zoom. Items in the same
 * CLUSTER_CELL_PX cell merge; a cell with one item stays a single marker. */
export function gridCluster(items, project, cellPx = CLUSTER_CELL_PX) {
  const cells = new Map();
  for (const it of items) {
    const pt = project([it.lat, it.lon]);
    const k = `${Math.floor(pt.x / cellPx)}:${Math.floor(pt.y / cellPx)}`;
    const cell = cells.get(k);
    if (cell) cell.push(it);
    else cells.set(k, [it]);
  }
  const singles = [];
  const clusters = [];
  for (const [k, members] of cells) {
    if (members.length === 1) {
      singles.push(members[0]);
      continue;
    }
    const lat = members.reduce((s, m) => s + m.lat, 0) / members.length;
    const lon = members.reduce((s, m) => s + m.lon, 0) / members.length;
    clusters.push({ id: k, lat, lon, members });
  }
  return { singles, clusters };
}

/* ------------------------------------------------------------ map helpers */

/** invalidateSize whenever the map is (re)shown; scroll-wheel zoom only after
 * the user clicks the map, so the page scroll is never hijacked. */
function MapBehaviour({ visible }) {
  const map = useMap();
  useEffect(() => {
    if (visible) map.invalidateSize({ animate: false });
  }, [map, visible]);
  useEffect(() => {
    const enable = () => map.scrollWheelZoom.enable();
    const disable = () => map.scrollWheelZoom.disable();
    map.on("click", enable);
    map.on("mouseout", disable);
    return () => {
      map.off("click", enable);
      map.off("mouseout", disable);
    };
  }, [map]);
  return null;
}

function MapEvents({ onZoom, onPopupClose }) {
  const map = useMapEvents({
    zoomend: () => onZoom(map.getZoom()),
    popupclose: (e) => onPopupClose(e.popup?.options?.lrmKey),
  });
  return null;
}

/** Roster → map: pan without animation. flyTo/animated pans while the unit
 * loop is calling setLatLng every frame froze the renderer, so never. */
function PanTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (!target || !isValidCoord(target.lat, target.lon)) return;
    map.setView([target.lat, target.lon], Math.max(map.getZoom(), CLUSTER_MAX_ZOOM), { animate: false });
    // nonce identifies one roster click; lat/lon of a person never change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, target?.nonce]);
  return null;
}

/* ---------------------------------------------------------------- markers */

const SosMarker = memo(
  function SosMarker({ p, selected, onPick }) {
    const position = useMemo(() => [p.lat, p.lon], [p.lat, p.lon]);
    const handlers = useMemo(() => ({ click: () => onPick(p.key) }), [onPick, p.key]);
    return (
      <Marker
        position={position}
        icon={sosIcon(p, selected)}
        eventHandlers={handlers}
        zIndexOffset={selected ? 1000 : p.stage === "queued" ? 500 : 0}
      />
    );
  },
  (a, b) =>
    a.p.key === b.p.key &&
    a.p.lat === b.p.lat &&
    a.p.lon === b.p.lon &&
    a.selected === b.selected &&
    a.onPick === b.onPick &&
    sosIconKey(a.p, a.selected) === sosIconKey(b.p, b.selected)
);

const ClusterMarker = memo(function ClusterMarker({ cluster, onZoomIn }) {
  const position = useMemo(() => [cluster.lat, cluster.lon], [cluster.lat, cluster.lon]);
  const handlers = useMemo(() => ({ click: () => onZoomIn(cluster) }), [onZoomIn, cluster]);
  return <Marker position={position} icon={clusterIcon(cluster.members.length)} eventHandlers={handlers} zIndexOffset={400} />;
});

function SosLayer({ people, selectedKey, zoom, onPick }) {
  const map = useMap();
  const { singles, clusters, safe } = useMemo(() => {
    const onMap = people.filter((p) => isValidCoord(p.lat, p.lon));
    // SAFE people are small dots and the selected person always stands alone.
    const safeDots = onMap.filter((p) => p.stage === "rescued" && p.key !== selectedKey);
    const active = onMap.filter((p) => p.stage !== "rescued" || p.key === selectedKey);
    if (zoom >= CLUSTER_MAX_ZOOM) return { singles: active, clusters: [], safe: safeDots };
    const pinned = active.filter((p) => p.key === selectedKey);
    const rest = active.filter((p) => p.key !== selectedKey);
    const g = gridCluster(rest, (ll) => map.project(ll, zoom));
    return { singles: [...g.singles, ...pinned], clusters: g.clusters, safe: safeDots };
  }, [people, selectedKey, zoom, map]);

  const zoomIn = useCallback(
    (cl) => map.setView([cl.lat, cl.lon], Math.min(map.getMaxZoom() || 18, zoom + 2), { animate: false }),
    [map, zoom]
  );

  return (
    <>
      {safe.map((p) => (
        <SosMarker key={p.key} p={p} selected={false} onPick={onPick} />
      ))}
      {clusters.map((cl) => (
        <ClusterMarker key={`cl-${cl.id}-${cl.members.length}`} cluster={cl} onZoomIn={zoomIn} />
      ))}
      {singles.map((p) => (
        <SosMarker key={p.key} p={p} selected={p.key === selectedKey} onPick={onPick} />
      ))}
    </>
  );
}

/** One moving unit: dashed remaining route, short solid trail, vehicle.
 * It never animates itself — it registers its Leaflet layers with the map's
 * single shared requestAnimationFrame loop. */
const UnitMarker = memo(
  function UnitMarker({ unit, register, onPick }) {
    const markerRef = useRef(null);
    const routeRef = useRef(null);
    const trailRef = useRef(null);

    // react-leaflet assigns ref.current in its OWN effect, after this one on
    // mount — so we register getters and the loop resolves them per frame.
    useEffect(() => {
      register(unit.key, {
        unit,
        getMarker: () => markerRef.current,
        getRoute: () => routeRef.current,
        getTrail: () => trailRef.current,
      });
      return () => register(unit.key, null);
    }, [unit, register]);

    const color = unitColor(unit.role);
    const routeStyle = useMemo(() => ({ color, weight: 2.5, dashArray: "6 8", opacity: 0.8 }), [color]);
    const trailStyle = useMemo(() => ({ color, weight: 4, opacity: 0.95 }), [color]);
    const handlers = useMemo(() => ({ click: () => onPick(unit.personKey) }), [onPick, unit.personKey]);
    const start = useMemo(() => [unit.position, unit.position], [unit.position]);

    return (
      <>
        <Polyline ref={routeRef} positions={unit.path} pathOptions={routeStyle} interactive={false} />
        <Polyline ref={trailRef} positions={start} pathOptions={trailStyle} interactive={false} />
        <Marker
          ref={markerRef}
          position={unit.position}
          icon={unitIcon(unit.role, unit.bearing)}
          eventHandlers={handlers}
          zIndexOffset={1500}
          title={`${unit.label} → ${unit.target || ""} (interpolated, not GPS)`}
        />
      </>
    );
  },
  (a, b) =>
    a.unit.key === b.unit.key &&
    a.unit.stageStartedAt === b.unit.stageStartedAt &&
    a.unit.stageMs === b.unit.stageMs &&
    a.unit.path.length === b.unit.path.length &&
    a.register === b.register &&
    a.onPick === b.onPick
);

function PersonPopup({ p }) {
  const eta =
    p.stage === "to_shelter" || p.stage === "rescued"
      ? p.etaShelterMin != null
        ? `${p.etaShelterMin} min to shelter`
        : "—"
      : p.etaMin != null
        ? `${p.etaMin} min`
        : "pending dispatch";
  return (
    <div className="lrm-popup">
      <h4>{p.name}</h4>
      <dl>
        <dt>Age</dt>
        <dd>{p.age ?? "—"}</dd>
        <dt>People</dt>
        <dd>{p.people ?? "—"}</dd>
        <dt>Triage</dt>
        <dd>{p.triage || p.priority || "—"}</dd>
        <dt>Stage</dt>
        <dd style={{ color: STAGE_COLOR[p.stage] }}>{STAGE_SHORT[p.stage]}</dd>
        <dt>Team</dt>
        <dd>{p.team || "—"}</dd>
        <dt>Ambulance</dt>
        <dd>{p.ambulance || "—"}</dd>
        <dt>Shelter</dt>
        <dd>{p.shelter || "—"}</dd>
        <dt>ETA</dt>
        <dd>{eta}</dd>
      </dl>
      {p.waitReason ? <div style={{ marginTop: 4, color: STAGE_COLOR.queued }}>{p.waitReason}</div> : null}
      {p.routeAlert ? <div className="lrm-route-alert">⛔ {p.routeAlert.reason}</div> : null}
      {p.reroutes?.length ? <div className="muted">Re-routed {p.reroutes.length}× this run</div> : null}
    </div>
  );
}

/** Re-centre once when the run's city changes (MapContainer's `center` only
 * applies on mount). setView without animation — see CLAUDE.md Leaflet notes. */
function CityFrame({ cityId, center, zoom }) {
  const map = useMap();
  const last = useRef(cityId);
  useEffect(() => {
    if (cityId && cityId !== last.current) {
      last.current = cityId;
      map.setView(center, zoom, { animate: false });
    }
  }, [cityId, center, zoom, map]);
  return null;
}

const WATER_STYLES = new Map();
/** Rivers / coast stronger than canals / ponds; a little bolder as P rises. */
function waterStyle(kind, p) {
  const major = kind === "river" || kind === "coastline";
  const band = p >= 0.75 ? 2 : p >= 0.5 ? 1 : 0;
  const key = `${major ? 1 : 0}|${band}`;
  if (!WATER_STYLES.has(key)) {
    WATER_STYLES.set(key, {
      color: "#3b82f6",
      weight: (major ? 3 : 1.2) + band,
      opacity: major ? 0.55 + 0.1 * band : 0.35,
    });
  }
  return WATER_STYLES.get(key);
}

/** Roads as clickable lines. The popup offers Block / Open / Back to the
 * flood rule when the parent passes `onRoad` (Routes + Live maps). */
const RoadLayer = memo(function RoadLayer({ roads, onRoad }) {
  const [busy, setBusy] = useState("");
  const run = async (id, action) => {
    setBusy(id);
    try {
      await onRoad(id, action);
    } finally {
      setBusy("");
    }
  };
  return roads.flatMap((r) =>
    (r.segments || []).map((seg, i) => (
      <Polyline key={`${r.road_id}|${i}`} positions={seg} pathOptions={roadStyle(r)}>
        <Popup>
          <div className="lrm-popup lrm-road-pop">
            <h4>
              {r.blocked ? "⛔" : "✅"} {r.road_id} · {r.name}
            </h4>
            <div>
              {r.blocked ? (r.operator ? "Blocked by operator" : "Closed by the flood rule") : r.operator ? "Opened by operator" : "Open"}
              {" · "}
              {r.active_legs} active route leg(s)
              {!r.blocked && r.closes_in_sim_min != null ? (
                <> · ⚠ forecast to flood in ~{r.closes_in_sim_min} min (simulation rule)</>
              ) : null}
            </div>
            {onRoad ? (
              <div className="lrm-road-actions">
                {r.blocked ? (
                  <button type="button" disabled={!!busy} onClick={() => run(r.road_id, "open")}>
                    ✅ Open road
                  </button>
                ) : (
                  <button type="button" className="danger" disabled={!!busy} onClick={() => run(r.road_id, "block")}>
                    ⛔ Block road
                  </button>
                )}
                {r.operator ? (
                  <button type="button" className="link-btn" disabled={!!busy} onClick={() => run(r.road_id, "clear")}>
                    Back to flood rule
                  </button>
                ) : null}
                {busy ? <span className="muted">re-planning…</span> : null}
              </div>
            ) : null}
          </div>
        </Popup>
      </Polyline>
    ))
  );
});

/* -------------------------------------------------------------- the map */

function LiveRescueMapInner({
  ops,
  offset = 0,
  paused = false,
  selectedKey = null,
  panTarget = null,
  onSelect,
  floodProbability = 0,
  toasts = [],
  onToast,
  plannedRoutes = "none",
  roads = EMPTY_ROADS,
  onRoad = null,
  cityView = null,
  silentZones = EMPTY_ROADS,
  supplyTrucks = EMPTY_ROADS,
}) {
  // F7: the run's city. Without it (demo network / old payload) the Delhi
  // mirrors in data/rescueAssets.js are used, exactly as before.
  const depots = cityView?.rescue_teams?.length ? cityView.rescue_teams : RESCUE_TEAMS;
  const seedShelters = cityView?.shelters?.length ? cityView.shelters : SEED_SHELTERS;
  const mapCenter = cityView?.center?.length === 2 ? cityView.center : CENTER;
  const water = cityView?.water || EMPTY_ROADS;
  const reduced = useMemo(
    () =>
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    []
  );

  const people = ops?.people || [];
  const units = ops?.units || [];
  const shelters = ops?.shelters || [];
  const closedShelters = ops?.closedShelters || [];
  const closedKey = closedShelters.join("|");
  const counters = ops?.counters || {};
  const selected = people.find((p) => p.key === selectedKey) || null;

  const [zoom, setZoom] = useState(11);
  const [legendOpen, setLegendOpen] = useState(false);
  const [dismissedKey, setDismissedKey] = useState(null);
  const selectedRef = useRef(selectedKey);
  selectedRef.current = selectedKey;

  useEffect(() => setDismissedKey(null), [selectedKey, panTarget?.nonce]);

  const pick = useCallback(
    (key) => {
      setDismissedKey(null);
      onSelect?.(key, { pan: false });
    },
    [onSelect]
  );
  const onPopupClose = useCallback((key) => {
    if (key && key === selectedRef.current) setDismissedKey(key);
  }, []);

  /* ---- visibility: pause the loop when off-screen ---- */
  const shellRef = useRef(null);
  const [onScreen, setOnScreen] = useState(true);
  useEffect(() => {
    const el = shellRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return undefined;
    const io = new IntersectionObserver((entries) => setOnScreen(entries.some((e) => e.isIntersecting)), {
      threshold: 0.01,
    });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Shelters the run actually uses + the wider seed network for context.
  const shelterPins = useMemo(() => {
    const byName = new Map();
    for (const s of seedShelters) byName.set(s.name, { ...s, full: false, usedThisRun: false });
    for (const s of shelters) {
      if (!isValidCoord(s.lat, s.lon)) continue;
      byName.set(s.name, { ...(byName.get(s.name) || {}), ...s });
    }
    for (const p of people) {
      if (p.shelter && p.shelterLoc && !byName.has(p.shelter)) {
        byName.set(p.shelter, { name: p.shelter, lat: p.shelterLoc.lat, lon: p.shelterLoc.lon, usedThisRun: true });
      }
    }
    // Operator-closed shelters (F2) always show, with the closed icon.
    const closed = closedKey ? closedKey.split("|") : [];
    for (const name of closed) {
      const loc = byName.get(name) || shelterLocation(name);
      if (loc) byName.set(name, { name, ...byName.get(name), lat: loc.lat, lon: loc.lon });
    }
    return [...byName.values()]
      .map((s) => ({ ...s, closed: closed.includes(s.name) }))
      .filter((s) => isValidCoord(s.lat, s.lon));
  }, [shelters, people, closedKey, seedShelters]);

  const p = Number(floodProbability) || 0;

  // Planned legs from the backend's own route polylines: unit base -> person
  // (to_person) and person -> shelter (to_shelter). "selected" draws the
  // selected person's two legs; "all" also draws every leg still ahead.
  const planned = useMemo(() => {
    if (plannedRoutes === "none") return [];
    const out = [];
    for (const q of people) {
      const sel = q.key === selectedKey;
      if (!sel && plannedRoutes !== "all") continue;
      const ahead = (leg) =>
        sel || (leg === "a" ? ["assigned", "en_route"].includes(q.stage) : ["assigned", "en_route", "to_shelter"].includes(q.stage));
      // The QAOA candidates it did NOT pick, for the selected person.
      if (sel && q.quantum) {
        for (const [leg, qq] of [["a", q.quantum.toPerson], ["b", q.quantum.toShelter]]) {
          (qq?.candidates || []).forEach((c, i) => {
            if (i !== qq.chosen && c.points?.length > 1) out.push({ key: `${q.key}|${leg}|alt${i}`, pts: c.points, style: LEG_ALT });
          });
        }
      }
      if (sel && q.routeToPerson) out.push({ key: `${q.key}|a|glow`, pts: q.routeToPerson, style: LEG_A_GLOW });
      if (sel && q.routeToShelter) out.push({ key: `${q.key}|b|glow`, pts: q.routeToShelter, style: LEG_B_GLOW });
      if (q.routeToPerson && ahead("a")) out.push({ key: `${q.key}|a`, pts: q.routeToPerson, style: sel ? LEG_A_SEL : LEG_A });
      if (q.routeToShelter && ahead("b")) out.push({ key: `${q.key}|b`, pts: q.routeToShelter, style: sel ? LEG_B_SEL : LEG_B });
    }
    return out;
  }, [people, selectedKey, plannedRoutes]);

  /* ---- ONE shared animation loop for every unit ----
   * setLatLng on markers ~30 fps; route/trail polylines ~10 fps. No setState
   * per frame. Markers are resolved inside the loop (refs arrive late). */
  const registryRef = useRef(new Map());
  const register = useCallback((key, entry) => {
    if (entry) registryRef.current.set(key, entry);
    else registryRef.current.delete(key);
  }, []);

  useEffect(() => {
    if (paused || !onScreen) return undefined;
    let raf = 0;
    let last = 0;
    let frame = 0;
    const FRAME_MS = reduced ? 1000 : 33;
    const step = (ts) => {
      raf = window.requestAnimationFrame(step);
      if (typeof document !== "undefined" && document.hidden) return;
      if (ts - last < FRAME_MS) return;
      last = ts;
      frame += 1;
      const lines = reduced || frame % 3 === 0;
      const now = Date.now() + offset;
      for (const entry of registryRef.current.values()) {
        const u = entry.unit;
        const marker = entry.getMarker?.();
        if (!marker || !u?.path?.length) continue;
        const frac =
          u.stageStartedAt == null || !u.stageMs ? u.progress : clamp01((now - u.stageStartedAt) / u.stageMs);
        const pos = positionAlong(u.path, u.cum, frac);
        if (pos) marker.setLatLng(pos);
        if (!lines) continue;
        const route = entry.getRoute?.();
        const trail = entry.getTrail?.();
        if (route) {
          if (frac >= 1) {
            if (!entry.arrived) {
              route.setStyle({ opacity: 0 });
              entry.arrived = true;
            }
          } else {
            route.setLatLngs(slicePath(u.path, u.cum, frac, 1));
          }
        }
        if (trail) trail.setLatLngs(slicePath(u.path, u.cum, Math.max(0, frac - 0.15), frac));
      }
    };
    raf = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(raf);
  }, [paused, reduced, offset, onScreen]);

  const showPopup = selected && dismissedKey !== selected.key && isValidCoord(selected.lat, selected.lon);
  const popupPos = useMemo(
    () => (selected ? [selected.lat, selected.lon] : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selected?.key, selected?.lat, selected?.lon]
  );

  return (
    <div className="lrm-shell" ref={shellRef}>
      <MapContainer center={mapCenter} zoom={cityView?.zoom || 11} preferCanvas scrollWheelZoom={false} className="lrm-map">
        <MapBehaviour visible={onScreen} />
        <MapEvents onZoom={setZoom} onPopupClose={onPopupClose} />
        <PanTo target={panTarget} />
        <CityFrame cityId={cityView?.id} center={mapCenter} zoom={cityView?.zoom || 11} />
        <TileLayer attribution={cityView ? `${TILE_ATTR} · ${cityView.attribution || ""}` : TILE_ATTR} url={TILE_URL} maxZoom={19} />

        {/* Real cities: the mapped rivers / coast / canals (OSM) the exposure
            proxy is computed from. Demo network: the old probability-scaled extent. */}
        {water.length
          ? water.map((w, i) => (
              <Polyline key={`w${i}`} positions={w.pts} interactive={false} pathOptions={waterStyle(w.kind, p)} />
            ))
          : p > 0 ? (
              <Circle
                center={CENTER}
                radius={2000 + p * 9000}
                interactive={false}
                pathOptions={{ color: "#4aa8ff", weight: 1, fillColor: "#4aa8ff", fillOpacity: 0.06 }}
              />
            ) : null}

        {depots.map((t) => (
          <Marker key={t.team_id} position={[t.lat, t.lon]} icon={depotIcon()} title={`${t.name} (depot)`}>
            <Popup>
              <b>{t.name}</b>
              <br />
              {t.scope ? <>Rescue depot · {t.scope}</> : <>Rescue depot · {t.capacity} personnel</>}
            </Popup>
          </Marker>
        ))}

        {silentZones.map((z) => (
          <Circle
            key={`silent|${z.zone_id}`}
            center={z.centre}
            radius={Math.max(300, Math.sqrt((z.area_km2 * 1e6) / Math.PI))}
            pathOptions={{ color: "#a3a3a3", weight: 1, dashArray: "4 4", fillColor: "#525252", fillOpacity: 0.25 }}
          >
            <Popup>
              📵 Silent area near {z.name} · ~{z.area_km2} km² (modelled: towers under the flood)
            </Popup>
          </Circle>
        ))}

        {supplyTrucks.map((t) => (
          <Marker key={`truck|${t.name}`} position={t.position} icon={truckIcon()} title={`${t.name} (supply truck)`}>
            <Popup>
              <b>{t.name}</b> · supply truck (assumed fleet)
              <br />
              {t.leg ? `To ${t.leg.to} · ${t.leg.km} km by road` : `Idle · ${t.trips} trip(s) done`}
            </Popup>
          </Marker>
        ))}

        {(cityView?.hospitals || EMPTY_ROADS).map((h) => (
          <Marker key={`hosp|${h.hospital_id || h.name}`} position={[h.lat, h.lon]} icon={hospitalIcon()} title={`${h.name} (hospital)`}>
            <Popup>
              <b>{h.name}</b>
              <br />
              Hospital (OpenStreetMap) · beds: {h.beds != null ? `${h.beds} (OSM tag)` : "capacity unknown"}
            </Popup>
          </Marker>
        ))}

        {(ops?.idleUnits || EMPTY_ROADS).map((a) => (
          <Marker key={`idle|${a.name}`} position={[a.lat, a.lon]} icon={idleAmbulanceIcon(a.kind)} title={`${a.name} — free, ${a.place}`}>
            <Popup>
              <b>{a.name}</b> · free
              <br />
              {a.place}
              {a.kind === "staging" ? <> · pre-positioned near predicted hotspots</> : null}
            </Popup>
          </Marker>
        ))}

        {shelterPins.map((s) => (
          <Marker key={s.id || s.name} position={[s.lat, s.lon]} icon={shelterIcon(s.usedThisRun, s.full, s.closed)} title={s.name}>
            <Popup>
              <b>{s.name}</b>
              {s.closed ? <> · 🚫 closed by operator</> : null}
              <br />
              {s.capacity ? `Capacity ${s.capacity}` : "Capacity unknown"}
              {s.backendOccupancy != null ? <> · board occupancy {s.backendOccupancy}</> : null}
              <br />
              Delivered this run: {s.arrivedThisRun || 0}
              {s.inboundThisRun ? <> · inbound {s.inboundThisRun}</> : null}
            </Popup>
          </Marker>
        ))}

        <RoadLayer roads={roads} onRoad={onRoad} />

        {planned.map((r) => (
          <Polyline key={r.key} positions={r.pts} pathOptions={r.style} interactive={false} />
        ))}

        <SosLayer people={people} selectedKey={selectedKey} zoom={zoom} onPick={pick} />

        {units.map((u) => (
          <UnitMarker key={u.key} unit={u} register={register} onPick={pick} />
        ))}

        {showPopup ? (
          <Popup key={selected.key} position={popupPos} autoPan={false} lrmKey={selected.key} closeOnClick={false}>
            <PersonPopup p={selected} />
          </Popup>
        ) : null}
      </MapContainer>

      {/* ---- live counters ---- */}
      <div className="lrm-hud" aria-live="polite">
        {[
          ["SOS", counters.totalSos, ""],
          ["Waiting", counters.waiting, "lrm-chip-waiting"],
          ["En route", counters.enRoute, "lrm-chip-enroute"],
          ["Transport", counters.transporting, "lrm-chip-transport"],
          ["Safe", counters.rescued, "lrm-chip-safe"],
          ["Units moving", counters.unitsMoving, ""],
        ].map(([label, value, cls]) => (
          <span className={`lrm-chip ${cls}`} key={label}>
            <b>{value ?? 0}</b>
            {label}
          </span>
        ))}
      </div>

      {toasts.length ? (
        <div className="lrm-toasts">
          {toasts.map((t) => (
            <div key={t.id} className="lrm-toast" role="status" onClick={() => onToast?.(t)}>
              New SOS · {t.name} · {t.people ?? 1} people
            </div>
          ))}
        </div>
      ) : null}

      {/* ---- legend ---- */}
      <button type="button" className="lrm-legend-toggle" aria-expanded={legendOpen} onClick={() => setLegendOpen((v) => !v)}>
        {legendOpen ? "✕ Hide legend" : "ⓘ Legend"}
      </button>
      <div className="lrm-legend" hidden={!legendOpen}>
        {["queued", "assigned", "en_route", "to_shelter", "rescued"].map((s) => (
          <div className="lrm-legend-row" key={s} title={STAGE_LABEL[s]}>
            <i className="lrm-legend-dot" style={{ background: STAGE_COLOR[s] }} />
            {STAGE_SHORT[s]}
          </div>
        ))}
        <div className="lrm-legend-row">
          <i className="lrm-legend-dot" style={{ background: "#fff", boxShadow: `0 0 0 2px ${STAGE_COLOR.queued}` }} />
          Thick ring = child / elderly / chest-deep
        </div>
        <div className="lrm-legend-row">
          <i className="lrm-legend-dot" style={{ background: "var(--status-sos, #ef4444)" }} /> Ambulance ·{" "}
          <i className="lrm-legend-dot" style={{ background: "var(--accent, #38bdf8)", borderRadius: 2 }} /> Rescue team ·{" "}
          <i className="lrm-legend-dot" style={{ background: "#0284c7", borderRadius: 2 }} /> Rescue boat ·{" "}
          <i className="lrm-legend-dot" style={{ background: "var(--status-safe, #22c55e)", borderRadius: 2 }} /> Shelter
        </div>
        {plannedRoutes !== "none" ? (
          <div className="lrm-legend-row">
            <i className="lrm-legend-dot" style={{ background: "#f43f5e", borderRadius: 2 }} /> Route: unit → person ·{" "}
            <i className="lrm-legend-dot" style={{ background: "#34d399", borderRadius: 2 }} /> Route: person → shelter ·{" "}
            <i className="lrm-legend-dot" style={{ background: "#a78bfa", borderRadius: 2 }} /> QAOA candidates not chosen
          </div>
        ) : null}
        {roads.length ? (
          <div className="lrm-legend-row">
            <i className="lrm-legend-dot" style={{ background: "#64748b", borderRadius: 2 }} /> Open road ·{" "}
            <i className="lrm-legend-dot" style={{ background: "#38bdf8", borderRadius: 2 }} /> in use ·{" "}
            <i className="lrm-legend-dot" style={{ background: "#ef4444", borderRadius: 2 }} /> Closed (dotted = flood,
            dashed = operator) — click a road to block / open it
          </div>
        ) : null}
        <div className="lrm-legend-note">
          Unit positions are interpolated along the backend-computed route from its stage timestamps — derived view,
          not GPS.
        </div>
      </div>
      <div className="lrm-wheel-hint">Click map to enable scroll-zoom</div>
    </div>
  );
}

const EMPTY_ROADS = [];

/* The /simulation tree re-renders every 1.2 s. Memoising keeps the map from
 * re-rendering unless its derived inputs actually change. */
export default memo(LiveRescueMapInner);
