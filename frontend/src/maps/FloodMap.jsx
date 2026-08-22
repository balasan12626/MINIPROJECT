import { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, Circle, Marker, Popup, Polyline, CircleMarker, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const STATUS_PIN = {
  sos: "#ff5d6c",
  open: "#ff5d6c",
  shared: "#f5c542",
  assigned: "#4aa3ff",
  en_route: "#f0a04a",
  going: "#f0a04a",
  pickup: "#c084fc",
  to_shelter: "#5ce1ff",
  moving: "#5ce1ff",
  rescued: "#3ee0a0",
  completed: "#3ee0a0",
  declined: "#8aa3b0",
  waiting: "#ff8a5c",
  trapped: "#ff8a5c",
  contacted: "#ff5d6c",
};

function pinColorFor(e, selected) {
  if (selected?.citizen_name && selected.citizen_name === e.citizen_name) return "#f5c542";
  if (e.pin_color) return e.pin_color;
  const st = String(e.live_status || e.status || "sos").toLowerCase().replaceAll(" ", "_");
  return STATUS_PIN[st] || STATUS_PIN.sos;
}

const icon = (color) =>
  L.divIcon({
    className: "",
    html: `<div style="width:12px;height:12px;border-radius:50%;background:${color};border:2px solid #fff"></div>`,
    iconSize: [12, 12],
  });

function MapEffects({ version }) {
  const map = useMap();
  useEffect(() => {
    map.invalidateSize();
  }, [map, version]);
  return null;
}

function PathAnim({ path }) {
  const [t, setT] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setT((x) => (x + 0.02) % 1), 80);
    return () => clearInterval(id);
  }, [path?.citizen_name]);
  if (!path?.from || !path?.to) return null;
  const lat = path.from[0] + (path.to[0] - path.from[0]) * t;
  const lon = path.from[1] + (path.to[1] - path.from[1]) * t;
  const color = String(path.role || "").includes("ambulance") ? "#f0a04a" : "#c084fc";
  return (
    <>
      <Polyline positions={[path.from, path.to]} pathOptions={{ color, weight: 3, dashArray: "6 8", opacity: 0.7 }} />
      <Marker position={[lat, lon]} icon={icon(color)}>
        <Popup>{path.team_name || path.team_id} → {path.citizen_name}</Popup>
      </Marker>
    </>
  );
}

export default function FloodMap({
  snapshot,
  mode = "live",
  floodProbability,
  mapFeatures = {},
  teamPaths = [],
  beforeP,
  afterP,
  onSelectPerson,
  selectedPerson,
  arenaPaths = null,
}) {
  const center = [28.6139, 77.209];
  const weather = snapshot?.weather || {};
  const river = snapshot?.river || {};
  const dam = snapshot?.dam || {};
  const shelters = snapshot?.shelters || [];
  const allShelters = shelters.length ? shelters : snapshot?.all_shelters || [];
  const routes = snapshot?.routes || [];
  const roads = snapshot?.roads || [];
  const zones = snapshot?.zones || [];
  const teams = snapshot?.teams || [];
  const emergencies = snapshot?.emergencies || [];
  const p = floodProbability != null ? floodProbability : snapshot?.prediction?.flood_probability || 0;
  const floodRadius = 400 + p * 2800;
  const beforeRadius = 400 + (beforeP != null ? beforeP : p * 0.45) * 2800;
  const afterRadius = 400 + (afterP != null ? afterP : p) * 2800;
  const version = `${p}-${weather.rainfall_mm}-${river.value_m}-${emergencies.length}-${mode}-${teamPaths.length}`;

  const heat = useMemo(() => {
    if (!mapFeatures.sos_heatmap) return [];
    return emergencies.filter((e) => e.lat != null && e.lon != null);
  }, [emergencies, mapFeatures.sos_heatmap]);

  return (
    <div className="map-wrap">
      <MapContainer center={center} zoom={11} style={{ height: "100%", width: "100%" }}>
        <MapEffects version={version} />
        <TileLayer
          attribution="&copy; OpenStreetMap"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {mapFeatures.before_after_radius ? (
          <>
            {zones.map((z) => (
              <Circle key={`before-${z.zone_id}`} center={[z.lat, z.lon]} radius={beforeRadius} pathOptions={{ color: "#5ce1ff", fillOpacity: 0.06, dashArray: "4 6" }}>
                <Popup>Before radius · {((beforeP != null ? beforeP : p * 0.45) * 100).toFixed(1)}%</Popup>
              </Circle>
            ))}
            {zones.map((z) => (
              <Circle key={`after-${z.zone_id}`} center={[z.lat, z.lon]} radius={afterRadius} pathOptions={{ color: "#ff5d6c", fillOpacity: Math.min(0.28, 0.08 + p * 0.2) }}>
                <Popup>After / now · {(p * 100).toFixed(1)}%</Popup>
              </Circle>
            ))}
          </>
        ) : (
          zones.map((z) => (
            <Circle key={`${z.zone_id}-${floodRadius}`} center={[z.lat, z.lon]} radius={floodRadius} pathOptions={{ color: "#ff5d6c", fillOpacity: Math.min(0.35, 0.08 + p * 0.25) }}>
              <Popup>{z.name} · flood {(p * 100).toFixed(1)}%</Popup>
            </Circle>
          ))
        )}
        {heat.map((e, i) => (
          <Circle
            key={`heat-${e._id || i}`}
            center={[e.lat, e.lon]}
            radius={550}
            pathOptions={{ color: "#ff8a5c", fillColor: "#ff5d6c", fillOpacity: 0.18, weight: 0 }}
          />
        ))}
        {weather.lat && (
          <CircleMarker center={[weather.lat, weather.lon]} radius={8} pathOptions={{ color: "#5ce1ff" }}>
            <Popup>Rainfall {weather.rainfall_mm ?? "n/a"} mm</Popup>
          </CircleMarker>
        )}
        {river.lat && (
          <Marker position={[river.lat, river.lon]} icon={icon("#4aa3ff")}>
            <Popup>{river.station || "River"} {river.value_m ?? "n/a"} m</Popup>
          </Marker>
        )}
        {dam.lat && dam.lon && (
          <Marker position={[dam.lat, dam.lon]} icon={icon("#f0a04a")}>
            <Popup>{dam.station || "Dam"} {dam.value_m ?? "n/a"} m</Popup>
          </Marker>
        )}
        {roads.map((r) => (
          <CircleMarker key={r.road_id} center={[r.lat, r.lon]} radius={5} pathOptions={{ color: r.blocked ? "#ff5d6c" : "#8aa3b0" }}>
            <Popup>{r.name} {r.blocked ? "BLOCKED" : "open"}</Popup>
          </CircleMarker>
        ))}
        {(allShelters.length ? allShelters : shelters).map((s) => (
          <Marker key={s.shelter_id} position={[s.lat, s.lon]} icon={icon("#3ee0a0")}>
            <Popup>{s.name} seats {s.available_seats ?? s.capacity - (s.occupancy || 0)}</Popup>
          </Marker>
        ))}
        {!mapFeatures.team_paths && teams.map((t) => (
          <Marker key={t.team_id} position={[t.lat, t.lon]} icon={icon("#c084fc")}>
            <Popup>{t.name} {t.status}</Popup>
          </Marker>
        ))}
        {emergencies.map((e, i) => (
          <Marker
            key={e._id || e.id || i}
            position={[e.lat, e.lon]}
            icon={icon(pinColorFor(e, selectedPerson))}
            eventHandlers={{
              click: () => {
                if (mapFeatures.person_card) onSelectPerson?.(e);
              },
            }}
          >
            <Popup>
              <b>{e.citizen_name || e.emergency_type}</b><br />
              age {e.age ?? "—"} · {e.people} people · {e.water_level_note || ""}<br />
              status {e.live_status || e.status || "open"} · team {e.assigned_team_name || e.assigned_team || "—"}<br />
              triage {e.triage || e.vulnerability || "—"}<br />
              {e.lat}, {e.lon}
            </Popup>
          </Marker>
        ))}
        {mapFeatures.team_paths && teamPaths.map((path) => (
          <PathAnim key={`${path.team_id}-${path.citizen_name}`} path={path} />
        ))}
        {arenaPaths?.before?.coordinates?.length ? (
          <Polyline
            positions={arenaPaths.before.coordinates.map((c) => [c.lat, c.lon])}
            pathOptions={{ color: "#5ce1ff", weight: 5, opacity: 0.9 }}
          >
            <Popup>Before flood · {arenaPaths.before.label || "shortest km"} · {arenaPaths.before.distance_km} km</Popup>
          </Polyline>
        ) : null}
        {arenaPaths?.after?.coordinates?.length ? (
          <Polyline
            positions={arenaPaths.after.coordinates.map((c) => [c.lat, c.lon])}
            pathOptions={{ color: "#ff5d6c", weight: 5, opacity: 0.95 }}
          >
            <Popup>After flood · {arenaPaths.after.label || "flood-aware"} · {arenaPaths.after.distance_km} km</Popup>
          </Polyline>
        ) : null}
        {routes[0]?.coordinates && !arenaPaths?.after && (
          <Polyline positions={routes[0].coordinates.map((c) => [c.lat, c.lon])} pathOptions={{ color: "#3ee0a0", weight: 5 }} />
        )}
        {routes[1]?.coordinates && !arenaPaths?.before && (
          <Polyline positions={routes[1].coordinates.map((c) => [c.lat, c.lon])} pathOptions={{ color: "#f5c542", weight: 3, dashArray: "6 6" }} />
        )}
        {(snapshot?.clusters || []).map((c) => (
          <Circle key={c.cluster_id} center={[c.lat, c.lon]} radius={900} pathOptions={{ color: "#c084fc", fillOpacity: 0.12 }}>
            <Popup>K-means {c.cluster_id}: {c.sos_count} SOS → {c.assigned_team || "unassigned"}</Popup>
          </Circle>
        ))}
      </MapContainer>
    </div>
  );
}
