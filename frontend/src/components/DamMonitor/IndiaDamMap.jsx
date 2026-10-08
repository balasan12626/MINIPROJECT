import { memo, useEffect, useRef } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

function isValidCoord(lat, lon) {
  return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
}

// divIcons are cached: building one per render makes react-leaflet call
// setIcon() and rebuild the marker DOM on every parent re-render.
const ICON_CACHE = new Map();
function cachedIcon(key, build) {
  if (!ICON_CACHE.has(key)) ICON_CACHE.set(key, build());
  return ICON_CACHE.get(key);
}

function topPin(selected) {
  return cachedIcon(`top:${selected ? 1 : 0}`, () => buildTopPin(selected));
}

function buildTopPin(selected) {
  const size = selected ? 22 : 14;
  return L.divIcon({
    className: "",
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:#4aa8ff;border:2px solid #fff;${
      selected ? "box-shadow:0 0 0 5px rgba(74,168,255,0.3);" : ""
    }"></div>`,
    iconSize: [size, size],
  });
}

const STATUS_COLOR = {
  LOW: "#3ee0a0",
  MODERATE: "#f5c542",
  HIGH: "#f0a04a",
  VERY_HIGH: "#ff8a5c",
  CRITICAL: "#ff5d6c",
};

function pin(color, selected) {
  return cachedIcon(`pin:${color}:${selected ? 1 : 0}`, () => buildPin(color, selected));
}

function buildPin(color, selected) {
  const size = selected ? 20 : 14;
  return L.divIcon({
    className: "",
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2px solid #fff;${
      selected ? "box-shadow:0 0 0 4px rgba(255,255,255,0.25);" : ""
    }"></div>`,
    iconSize: [size, size],
  });
}

// Jump, don't fly: an animated flyTo while another map on the page moves
// markers every frame crashed Edge's renderer (STATUS_BREAKPOINT) on /simulation.
function FlyToSelected({ dam }) {
  const map = useMap();
  useEffect(() => {
    if (!dam) return;
    map.setView([dam.lat, dam.lon], 8, { animate: false });
  }, [dam?.id, map]);
  return null;
}

function MapEffects() {
  const map = useMap();
  useEffect(() => {
    map.invalidateSize?.();
    if (typeof map.on !== "function") return undefined;
    // Page scroll must not zoom the map: wheel zoom only after a click on it,
    // and off again once the pointer leaves.
    const on = () => map.scrollWheelZoom.enable();
    const off = () => map.scrollWheelZoom.disable();
    map.on("click", on);
    map.on("mouseout", off);
    return () => {
      map.off("click", on);
      map.off("mouseout", off);
    };
  }, [map]);
  return null;
}

// Stable reference: MapContainer is created once and never re-created.
const INDIA_CENTER = [22.9, 79.5];

// Flies to a Top-10-dams entry (latitude/longitude) independently of the
// scenario-dam selection above — a separate, additive navigation action.
function FlyToTopDam({ dam }) {
  const map = useMap();
  useEffect(() => {
    if (!dam || !isValidCoord(dam.latitude, dam.longitude)) return;
    map.setView([dam.latitude, dam.longitude], 11, { animate: false });
  }, [dam?.id, map]);
  return null;
}

function TopDamMarker({ dam, selected, onSelect }) {
  const markerRef = useRef(null);
  useEffect(() => {
    if (selected) markerRef.current?.openPopup();
  }, [selected]);

  if (!isValidCoord(dam.latitude, dam.longitude)) return null;
  return (
    <Marker
      ref={markerRef}
      position={[dam.latitude, dam.longitude]}
      icon={topPin(selected)}
      eventHandlers={{ click: () => onSelect?.(dam.id) }}
    >
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

/** Interactive India dam map — real OpenStreetMap tiles. Renders the live
 * scenario-dam markers (status-colored) plus, additively, the fixed
 * "Top 10 Dams in India" reference markers with independent fly-to. */
function IndiaDamMap({
  dams = [],
  selectedId,
  onSelect,
  topDams = [],
  selectedTopDamId = null,
  onSelectTopDam,
}) {
  const selected = dams.find((d) => d.id === selectedId) || null;
  const selectedTopDam = topDams.find((d) => d.id === selectedTopDamId) || null;

  return (
    <div className="map-wrap dam-map-wrap">
      <MapContainer center={INDIA_CENTER} zoom={5} preferCanvas scrollWheelZoom={false} style={{ height: "100%", width: "100%" }}>
        <MapEffects />
        <FlyToSelected dam={selected} />
        <FlyToTopDam dam={selectedTopDam} />
        <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {dams.map((dam) => (
          <Marker
            key={dam.id}
            position={[dam.lat, dam.lon]}
            icon={pin(STATUS_COLOR[dam.status] || STATUS_COLOR.LOW, dam.id === selectedId)}
            eventHandlers={{ click: () => onSelect?.(dam.id) }}
          >
            <Popup>
              <b>{dam.name}</b>
              <br />
              {dam.state}
              <br />
              Current {dam.current_level_m} m / Full {dam.full_reservoir_level_m} m
              <br />
              Storage {dam.fill_percentage}% · <b>{dam.status}</b>
            </Popup>
          </Marker>
        ))}
        {topDams.map((dam) => (
          <TopDamMarker key={dam.id} dam={dam} selected={dam.id === selectedTopDamId} onSelect={onSelectTopDam} />
        ))}
      </MapContainer>
    </div>
  );
}

export default memo(IndiaDamMap);
