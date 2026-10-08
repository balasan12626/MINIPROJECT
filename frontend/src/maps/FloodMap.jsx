import { memo, useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, Circle, Marker, Popup, Polyline, CircleMarker, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

/* Pin colours are theme tokens (index.css). divIcon HTML is real DOM, so
 * var() resolves there and follows the active theme by itself. */
const STATUS_PIN = {
  sos: "var(--status-sos)",
  open: "var(--status-sos)",
  shared: "var(--status-assigned)",
  assigned: "var(--status-assigned)",
  en_route: "var(--status-enroute)",
  going: "var(--status-enroute)",
  pickup: "var(--status-transport)",
  to_shelter: "var(--status-transport)",
  moving: "var(--status-transport)",
  rescued: "var(--status-safe)",
  completed: "var(--status-safe)",
  declined: "var(--muted)",
  waiting: "var(--status-enroute)",
  trapped: "var(--status-enroute)",
  contacted: "var(--status-sos)",
};

const CENTER = [28.6139, 77.209];
const MAP_STYLE = { height: "100%", width: "100%" };
const EMPTY = [];

/** The person's live stage: the rescue stage machine's `ops_status` wins over
 * the older `live_status` / `status` fields (backend person_ops.py). */
function liveStatus(e) {
  return e.ops_status || e.live_status || e.status;
}

function pinColorFor(e, selectedName) {
  if (selectedName && selectedName === e.citizen_name) return "var(--accent)";
  if (e.pin_color) return e.pin_color;
  const st = String(liveStatus(e) || "sos").toLowerCase().replaceAll(" ", "_");
  return STATUS_PIN[st] || STATUS_PIN.sos;
}

/* Icons are cached by colour. Sharing one DivIcon instance is safe — Leaflet's
 * createIcon() builds a new element per marker from it — and a stable `icon`
 * prop means react-leaflet never calls marker.setIcon() on a re-render. */
const ICON_CACHE = new Map();

const icon = (color) => {
  const hit = ICON_CACHE.get(color);
  if (hit) return hit;
  const made = L.divIcon({
    className: "",
    html: `<div style="width:12px;height:12px;border-radius:50%;background:${color};border:2px solid var(--text)"></div>`,
    iconSize: [12, 12],
  });
  ICON_CACHE.set(color, made);
  return made;
};

let FOCUS_DAM_ICON = null;
const focusDamIcon = () => {
  if (!FOCUS_DAM_ICON) {
    FOCUS_DAM_ICON = L.divIcon({
      className: "",
      html: `<div style="width:22px;height:22px;border-radius:50%;background:var(--accent);border:2px solid var(--text);box-shadow:0 0 0 5px rgba(250,204,21,0.4)"></div>`,
      iconSize: [22, 22],
    });
  }
  return FOCUS_DAM_ICON;
};

/* Vector-layer styles. The map uses the canvas renderer (preferCanvas), which
 * cannot resolve CSS var(), so theme tokens are resolved to concrete colours
 * here (hex fallbacks = the dark theme) and rebuilt when the theme changes.
 * Objects stay frozen between theme changes: react-leaflet calls setStyle()
 * whenever the `pathOptions` identity changes, forcing a canvas redraw. */
const TOKEN_FALLBACK = {
  "--accent": "#5ce1ff",
  "--status-sos": "#ff5d6c",
  "--status-assigned": "#f5c542",
  "--status-enroute": "#f0a04a",
  "--status-transport": "#c084fc",
  "--status-safe": "#3ee0a0",
  "--axis": "#8aa3b0",
};

function token(name) {
  if (typeof document === "undefined" || typeof getComputedStyle !== "function") return TOKEN_FALLBACK[name];
  const v = getComputedStyle(document.body || document.documentElement).getPropertyValue(name).trim();
  return v || TOKEN_FALLBACK[name];
}

function buildPaths() {
  const accent = token("--accent");
  const sos = token("--status-sos");
  const assigned = token("--status-assigned");
  const enroute = token("--status-enroute");
  const transport = token("--status-transport");
  const safe = token("--status-safe");
  const axis = token("--axis");
  return {
    sos,
    before: { color: accent, fillOpacity: 0.06, dashArray: "4 6" },
    heat: { color: enroute, fillColor: sos, fillOpacity: 0.18, weight: 0 },
    weather: { color: accent },
    roadBlocked: { color: sos },
    roadOpen: { color: axis },
    arenaBefore: { color: accent, weight: 5, opacity: 0.9 },
    arenaAfter: { color: sos, weight: 5, opacity: 0.95 },
    route0: { color: safe, weight: 5 },
    route1: { color: assigned, weight: 3, dashArray: "6 6" },
    cluster: { color: transport, fillOpacity: 0.12 },
    linkAmb: { color: enroute, weight: 3, dashArray: "6 8", opacity: 0.7 },
    linkTeam: { color: transport, weight: 3, dashArray: "6 8", opacity: 0.7 },
  };
}

let PATH = buildPaths();

/** Re-resolve the canvas colours when the theme flips (body class / data-theme
 * or the app's "flood-theme" event). Returns a version number for memo deps. */
function useThemeVersion() {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    // Leaflet itself toggles body classes (e.g. leaflet-dragging), so only a
    // real theme change rebuilds the styles.
    const themeKey = () =>
      `${document.body?.classList.contains("light-theme")}|${document.body?.dataset.theme || ""}|${document.documentElement.dataset.theme || ""}`;
    let key = themeKey();
    const bump = () => {
      const next = themeKey();
      if (next === key) return;
      key = next;
      PATH = buildPaths();
      setVersion((v) => v + 1);
    };
    window.addEventListener("flood-theme", bump);
    let mo = null;
    if (typeof MutationObserver !== "undefined") {
      mo = new MutationObserver(bump);
      if (document.body) mo.observe(document.body, { attributes: true, attributeFilter: ["class", "data-theme"] });
      mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    }
    return () => {
      window.removeEventListener("flood-theme", bump);
      mo?.disconnect();
    };
  }, []);
  return version;
}

function isValidCoord(lat, lon) {
  return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
}

/** Size the map when (and only when) its box changes or it scrolls into view —
 * not on every data update, which forced a synchronous layout per poll. Also:
 * the wheel only zooms after the map is clicked, and stops again on mouseout,
 * so scrolling the page past the map never hijacks into a zoom. */
function MapBehaviour() {
  const map = useMap();
  useEffect(() => {
    const el = map.getContainer();
    const fit = () => map.invalidateSize({ pan: false });
    let io = null;
    let ro = null;
    if (typeof IntersectionObserver !== "undefined") {
      io = new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting)) fit();
      });
      io.observe(el);
    }
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(() => fit());
      ro.observe(el);
    }
    const enableWheel = () => map.scrollWheelZoom.enable();
    const disableWheel = () => map.scrollWheelZoom.disable();
    map.on("click", enableWheel);
    map.on("mouseout", disableWheel);
    return () => {
      io?.disconnect();
      ro?.disconnect();
      map.off("click", enableWheel);
      map.off("mouseout", disableWheel);
    };
  }, [map]);
  return null;
}

// Centres on the scenario's selected reference dam (real backend lat/lon) —
// independent of the simulation zone circles, which stay fixed on Yamuna/Delhi.
// setView without animation: flyTo alongside live marker updates froze the
// renderer (CLAUDE.md, Leaflet rules).
function FocusDam({ dam }) {
  const map = useMap();
  const lat = dam?.lat;
  const lon = dam?.lon;
  useEffect(() => {
    if (!isValidCoord(lat, lon)) return;
    map.setView([lat, lon], 10, { animate: false });
  }, [dam?.id, lat, lon, map]);
  if (!dam || !isValidCoord(lat, lon)) return null;
  return (
    <Marker position={[lat, lon]} icon={focusDamIcon()}>
      <Popup>
        <b>{dam.name}</b>
        <br />
        {dam.state}
        <br />
        {dam.river}
      </Popup>
    </Marker>
  );
}

// `tv` (theme version) is only a re-render trigger for the memoised layers.
const ZoneCircles = memo(function ZoneCircles({ zones, p, beforeP, afterP, beforeAfter, tv }) {
  const floodRadius = 400 + p * 2800;
  const beforeValue = beforeP != null ? beforeP : p * 0.45;
  const beforeRadius = 400 + beforeValue * 2800;
  const afterRadius = 400 + (afterP != null ? afterP : p) * 2800;
  const nowFill = Math.min(0.35, 0.08 + p * 0.25);
  const afterFill = Math.min(0.28, 0.08 + p * 0.2);
  const nowStyle = useMemo(() => ({ color: PATH.sos, fillOpacity: nowFill }), [nowFill, tv]);
  const afterStyle = useMemo(() => ({ color: PATH.sos, fillOpacity: afterFill }), [afterFill, tv]);
  if (beforeAfter) {
    return (
      <>
        {zones.map((z) => (
          <Circle key={`before-${z.zone_id}`} center={[z.lat, z.lon]} radius={beforeRadius} pathOptions={PATH.before}>
            <Popup>Before radius · {(beforeValue * 100).toFixed(1)}%</Popup>
          </Circle>
        ))}
        {zones.map((z) => (
          <Circle key={`after-${z.zone_id}`} center={[z.lat, z.lon]} radius={afterRadius} pathOptions={afterStyle}>
            <Popup>After / now · {(p * 100).toFixed(1)}%</Popup>
          </Circle>
        ))}
      </>
    );
  }
  return zones.map((z) => (
    <Circle key={z.zone_id} center={[z.lat, z.lon]} radius={floodRadius} pathOptions={nowStyle}>
      <Popup>{z.name} · flood {(p * 100).toFixed(1)}%</Popup>
    </Circle>
  ));
});

const StaticLayers = memo(function StaticLayers({ weather, river, dam, roads, shelters, teams, showTeams, tv }) {
  return (
    <>
      {weather?.lat ? (
        <CircleMarker center={[weather.lat, weather.lon]} radius={8} pathOptions={PATH.weather}>
          <Popup>Rainfall {weather.rainfall_mm ?? "n/a"} mm</Popup>
        </CircleMarker>
      ) : null}
      {river?.lat ? (
        <Marker position={[river.lat, river.lon]} icon={icon("var(--accent)")}>
          <Popup>{river.station || "River"} {river.value_m ?? "n/a"} m</Popup>
        </Marker>
      ) : null}
      {dam?.lat && dam?.lon ? (
        <Marker position={[dam.lat, dam.lon]} icon={icon("var(--status-enroute)")}>
          <Popup>{dam.station || "Dam"} {dam.value_m ?? "n/a"} m</Popup>
        </Marker>
      ) : null}
      {roads.map((r) => (
        <CircleMarker key={r.road_id} center={[r.lat, r.lon]} radius={5} pathOptions={r.blocked ? PATH.roadBlocked : PATH.roadOpen}>
          <Popup>{r.name} {r.blocked ? "BLOCKED" : "open"}</Popup>
        </CircleMarker>
      ))}
      {shelters.map((s) => (
        <Marker key={s.shelter_id} position={[s.lat, s.lon]} icon={icon("var(--status-safe)")}>
          <Popup>{s.name} seats {s.available_seats ?? s.capacity - (s.occupancy || 0)}</Popup>
        </Marker>
      ))}
      {showTeams
        ? teams.map((t) => (
            <Marker key={t.team_id} position={[t.lat, t.lon]} icon={icon("var(--status-transport)")}>
              <Popup>{t.name} {t.status}</Popup>
            </Marker>
          ))
        : null}
    </>
  );
});

/** One SOS pin. Memoised on the person object — the sim store keeps unchanged
 * people referentially stable, so a poll only touches pins that moved stage. */
const EmergencyMarker = memo(function EmergencyMarker({ e, color, onSelect }) {
  const position = useMemo(() => [e.lat, e.lon], [e.lat, e.lon]);
  const handlers = useMemo(() => ({ click: () => onSelect?.(e) }), [e, onSelect]);
  return (
    <Marker position={position} icon={icon(color)} eventHandlers={handlers}>
      <Popup>
        <b>{e.citizen_name || e.emergency_type}</b>
        <br />
        age {e.age ?? "—"} · {e.people} people · {e.water_level_note || ""}
        <br />
        status {liveStatus(e) || "open"} · team {e.assigned_team_name || e.assigned_team || "—"}
        <br />
        triage {e.triage || e.vulnerability || "—"}
        <br />
        {e.lat}, {e.lon}
      </Popup>
    </Marker>
  );
});

const EmergencyLayer = memo(function EmergencyLayer({ emergencies, heatmap, selectedName, onSelect, tv }) {
  return (
    <>
      {heatmap
        ? emergencies
            .filter((e) => e.lat != null && e.lon != null)
            .map((e, i) => <Circle key={`heat-${e._id || e.id || e.citizen_name || i}`} center={[e.lat, e.lon]} radius={550} pathOptions={PATH.heat} />)
        : null}
      {emergencies.map((e, i) =>
        isValidCoord(e.lat, e.lon) ? (
          <EmergencyMarker key={e._id || e.id || e.citizen_name || i} e={e} color={pinColorFor(e, selectedName)} onSelect={onSelect} />
        ) : null
      )}
    </>
  );
});

/** Assignment segment: which team is responsible for which person. Static by
 * design — real, state-driven unit movement lives in
 * components/rescue/LiveRescueMap.jsx. */
const PathLink = memo(function PathLink({ path, tv }) {
  if (!path?.from || !path?.to) return null;
  const amb = String(path.role || "").includes("ambulance");
  return (
    <>
      <Polyline positions={[path.from, path.to]} pathOptions={amb ? PATH.linkAmb : PATH.linkTeam} />
      <Marker position={path.from} icon={icon(amb ? "var(--status-enroute)" : "var(--status-transport)")}>
        <Popup>
          {path.team_name || path.team_id} → {path.citizen_name}
        </Popup>
      </Marker>
    </>
  );
});

const toLatLngs = (coords) => (coords || []).map((c) => [c.lat, c.lon]);

const RouteLayers = memo(function RouteLayers({ routes, arenaPaths, tv }) {
  const before = useMemo(() => toLatLngs(arenaPaths?.before?.coordinates), [arenaPaths?.before?.coordinates]);
  const after = useMemo(() => toLatLngs(arenaPaths?.after?.coordinates), [arenaPaths?.after?.coordinates]);
  const r0 = useMemo(() => toLatLngs(routes[0]?.coordinates), [routes]);
  const r1 = useMemo(() => toLatLngs(routes[1]?.coordinates), [routes]);
  return (
    <>
      {before.length ? (
        <Polyline positions={before} pathOptions={PATH.arenaBefore}>
          <Popup>Before flood · {arenaPaths.before.label || "shortest km"} · {arenaPaths.before.distance_km} km</Popup>
        </Polyline>
      ) : null}
      {after.length ? (
        <Polyline positions={after} pathOptions={PATH.arenaAfter}>
          <Popup>After flood · {arenaPaths.after.label || "flood-aware"} · {arenaPaths.after.distance_km} km</Popup>
        </Polyline>
      ) : null}
      {r0.length && !arenaPaths?.after ? <Polyline positions={r0} pathOptions={PATH.route0} /> : null}
      {r1.length && !arenaPaths?.before ? <Polyline positions={r1} pathOptions={PATH.route1} /> : null}
    </>
  );
});

const ClusterLayer = memo(function ClusterLayer({ clusters, tv }) {
  return clusters.map((c) => (
    <Circle key={c.cluster_id} center={[c.lat, c.lon]} radius={900} pathOptions={PATH.cluster}>
      <Popup>K-means {c.cluster_id}: {c.sos_count} SOS → {c.assigned_team || "unassigned"}</Popup>
    </Circle>
  ));
});

function FloodMap({
  snapshot,
  floodProbability,
  mapFeatures = {},
  teamPaths = EMPTY,
  beforeP,
  afterP,
  onSelectPerson,
  selectedPerson,
  arenaPaths = null,
  focusDam = null,
}) {
  const shelters = snapshot?.shelters || EMPTY;
  const allShelters = shelters.length ? shelters : snapshot?.all_shelters || EMPTY;
  // Missing stays missing: no probability means no flood extent is drawn
  // (a `|| 0` here used to render an unknown value as a 0% flood).
  const p = floodProbability != null ? floodProbability : snapshot?.prediction?.flood_probability ?? null;
  const personCard = Boolean(mapFeatures.person_card);
  const tv = useThemeVersion();

  // Stable click handler: only forwards when the person card is enabled.
  const selectRef = useRef(onSelectPerson);
  selectRef.current = onSelectPerson;
  const onSelect = useMemo(() => (personCard ? (e) => selectRef.current?.(e) : null), [personCard]);

  return (
    <div className="map-wrap">
      <MapContainer center={CENTER} zoom={11} style={MAP_STYLE} preferCanvas scrollWheelZoom={false}>
        <MapBehaviour />
        <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {p != null ? <ZoneCircles
          zones={snapshot?.zones || EMPTY}
          p={p}
          beforeP={beforeP}
          afterP={afterP}
          beforeAfter={Boolean(mapFeatures.before_after_radius)}
          tv={tv}
        /> : null}
        <StaticLayers
          weather={snapshot?.weather}
          river={snapshot?.river}
          dam={snapshot?.dam}
          roads={snapshot?.roads || EMPTY}
          shelters={allShelters}
          teams={snapshot?.teams || EMPTY}
          showTeams={!mapFeatures.team_paths}
          tv={tv}
        />
        <FocusDam dam={focusDam} />
        <EmergencyLayer
          emergencies={snapshot?.emergencies || EMPTY}
          heatmap={Boolean(mapFeatures.sos_heatmap)}
          selectedName={selectedPerson?.citizen_name}
          onSelect={onSelect}
          tv={tv}
        />
        {mapFeatures.team_paths ? teamPaths.map((path) => <PathLink key={`${path.team_id}-${path.citizen_name}`} path={path} tv={tv} />) : null}
        <RouteLayers routes={snapshot?.routes || EMPTY} arenaPaths={arenaPaths} tv={tv} />
        <ClusterLayer clusters={snapshot?.clusters || EMPTY} tv={tv} />
      </MapContainer>
    </div>
  );
}

export default memo(FloodMap);
