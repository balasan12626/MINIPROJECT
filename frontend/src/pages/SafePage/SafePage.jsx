import { useCallback, useEffect, useState } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { fetchSafety } from "../../services/api.js";
import { registerPhoneOffline } from "../../utils/offlinePages.js";
import "../DriverApp/driverApp.css";
import { usePhoneLang } from "../../i18n/phonePages.js";
import LangPicker from "../../i18n/LangPicker.jsx";

const POLL_MS = 30000;
const TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const TIER = { ADMIN: "Watch", READY: "Be ready", FIELD: "Evacuate", WAITING: "No operation" };

function RouteMap({ me, shelter }) {
  const pts = shelter?.route_points || [];
  const all = [[me.lat, me.lon], ...pts, [shelter.lat, shelter.lon]];
  const lats = all.map((p) => p[0]);
  const lons = all.map((p) => p[1]);
  return (
    <MapContainer
      bounds={[
        [Math.min(...lats), Math.min(...lons)],
        [Math.max(...lats), Math.max(...lons)],
      ]}
      boundsOptions={{ padding: [24, 24] }}
      className="drv-map"
      scrollWheelZoom={false}
    >
      <TileLayer attribution={TILE_ATTR} url={TILE_URL} maxZoom={19} />
      {pts.length ? <Polyline positions={pts} pathOptions={{ color: "#22c55e", weight: 5 }} /> : null}
      <CircleMarker center={[me.lat, me.lon]} radius={8} pathOptions={{ color: "#fff", fillColor: "#3b82f6", fillOpacity: 1 }} />
      <CircleMarker center={[shelter.lat, shelter.lon]} radius={9} pathOptions={{ color: "#fff", fillColor: "#22c55e", fillOpacity: 1 }} />
    </MapContainer>
  );
}

/** F15 — public "Am I safe?" page (/safe). Location → the live operation's
 * alert level, nearest open shelter with seats and its road route, and closed
 * roads around you. Reads GET /api/public/safety only; nothing is stored. */
export default function SafePage() {
  const [lang, setLang, t] = usePhoneLang();
  // F15: cache this page's shell so it opens again without signal.
  useEffect(() => {
    registerPhoneOffline();
  }, []);
  const [me, setMe] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [locating, setLocating] = useState(false);

  const load = useCallback(async (pos) => {
    try {
      setData(await fetchSafety(pos.lat, pos.lon));
      setError("");
    } catch (e) {
      setError(
        e?.response?.status === 422
          ? "This location is outside the area the service covers."
          : e?.response?.status === 429
            ? "Too many requests — try again in a minute."
            : "Cannot reach the service — check your connection."
      );
    }
  }, []);

  useEffect(() => {
    if (!me) return undefined;
    load(me);
    const id = setInterval(() => load(me), POLL_MS);
    return () => clearInterval(id);
  }, [me, load]);

  function locate() {
    setError("");
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setError("This browser cannot share location.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (g) => {
        setLocating(false);
        setMe({ lat: g.coords.latitude, lon: g.coords.longitude, acc: Math.round(g.coords.accuracy) });
      },
      (e) => {
        setLocating(false);
        setError(e?.code === 1 ? "Location permission denied — allow it to check your area." : "Could not get your location.");
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 }
    );
  }

  const a = data?.alert;
  const s = data?.shelter;
  return (
    <div className="drv-page">
      <header className="drv-head">
        <div>
          <p className="drv-kicker">AQUASENTINEL · FLOOD SAFETY</p>
          <h1>{t("safe_title")}</h1>
        </div>
      </header>
      <LangPicker lang={lang} setLang={setLang} t={t} />
      {!me ? (
        <section className="drv-card">
          <p>Share your location to see the flood alert for your area and the nearest open shelter.</p>
          <button type="button" className="drv-btn sos-locate" onClick={locate} disabled={locating}>
            {locating ? t("locating") : t("safe_locate")}
          </button>
        </section>
      ) : null}
      {error ? <p className="drv-banner is-error">{error}</p> : null}
      {data ? (
        <>
          <section className={`drv-card safe-alert tier-${a?.tier || "NONE"}`}>
            <p className="drv-kicker">{data.city?.name}</p>
            <h2>{data.live ? TIER[a?.tier] || a?.tier || "—" : "No live operation"}</h2>
            {a?.flood_probability != null ? <p>Flood probability now: {(a.flood_probability * 100).toFixed(0)}%</p> : null}
            <p>{a?.advice}</p>
            {data.signal_warning ? <p className="drv-banner is-error">📵 {data.signal_warning}</p> : null}
          </section>
          {s ? (
            <section className="drv-card">
              <p className="drv-kicker">{t("nearest_shelter")}</p>
              <h2>{s.name}</h2>
              {s.no_open_road ? (
                <p className="drv-banner is-error">No open road to it right now — stay where you are if it is safe and send an SOS.</p>
              ) : (
                <p>
                  {s.road_km} km by road · about {s.vehicle_min} min by vehicle
                  {s.walk_min != null ? ` · about ${s.walk_min} min on foot` : ""}
                </p>
              )}
              <RouteMap me={me} shelter={s} />
              {s.flood_forecast ? <p className="drv-muted">Route avoids roads forecast to flood: {s.flood_forecast.note}</p> : null}
            </section>
          ) : (
            <p className="drv-banner">{t("no_shelter")}</p>
          )}
          {data.hospital ? (
            <section className="drv-card">
              <p className="drv-kicker">{t("nearest_hospital")}</p>
              <h2>🏥 {data.hospital.name}</h2>
              <p>
                {data.hospital.km} km by road · about {data.hospital.minutes_by_vehicle} min by vehicle · beds:{" "}
                {data.hospital.beds != null ? data.hospital.beds : "unknown"}
              </p>
            </section>
          ) : null}
          {data.roads_near_you?.length ? (
            <section className="drv-card">
              <p className="drv-kicker">{t("roads_near")}</p>
              <ul className="safe-roads">
                {data.roads_near_you.map((r) => (
                  <li key={r.road_id}>
                    <b>{r.name}</b> · {r.km} km · {r.status}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {data.river?.level_m != null ? (
            <p className="drv-muted">
              {data.river.river} at {data.river.station}: {Number(data.river.level_m).toFixed(2)} m (danger {data.river.danger_level_m} m)
            </p>
          ) : null}
          <a className="drv-btn reject safe-sos" href="/sos">
            🆘 I need rescue — send SOS
          </a>
          <p className="drv-foot">
            {(data.notes || []).join(" ")} Updates every 30 s. Demo service — in a real emergency also call the official helpline.
          </p>
        </>
      ) : null}
    </div>
  );
}
