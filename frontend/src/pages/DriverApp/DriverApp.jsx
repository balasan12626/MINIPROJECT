import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { CircleMarker, MapContainer, Polyline, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { acceptJob, fetchUnitJob, rejectJob } from "../../services/api.js";
import "./driverApp.css";

const POLL_MS = 2000;
const TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const REASONS = ["Vehicle fault", "Road impassable", "Crew unavailable", "Already on another call"];

const pts = (route) => (route?.points || []).filter((p) => Array.isArray(p) && p.length === 2);

function JobMap({ job }) {
  const a = pts(job.route_to_person);
  const b = pts(job.route_to_shelter);
  const all = [...a, ...b];
  if (!all.length) return null;
  const lats = all.map((p) => p[0]);
  const lons = all.map((p) => p[1]);
  const bounds = [
    [Math.min(...lats), Math.min(...lons)],
    [Math.max(...lats), Math.max(...lons)],
  ];
  return (
    <MapContainer
      key={`${job.citizen_name}|${job.stage}|${job.shelter_name}`}
      bounds={bounds}
      boundsOptions={{ padding: [24, 24] }}
      className="drv-map"
      scrollWheelZoom={false}
    >
      <TileLayer attribution={TILE_ATTR} url={TILE_URL} maxZoom={19} />
      {a.length ? <Polyline positions={a} pathOptions={{ color: "#f59e0b", weight: 5 }} /> : null}
      {b.length ? <Polyline positions={b} pathOptions={{ color: "#34d399", weight: 5, dashArray: "8 6" }} /> : null}
      {job.lat != null ? (
        <CircleMarker center={[job.lat, job.lon]} radius={9} pathOptions={{ color: "#fff", fillColor: "#ef4444", fillOpacity: 1 }} />
      ) : null}
      {job.shelter_lat != null ? (
        <CircleMarker
          center={[job.shelter_lat, job.shelter_lon]}
          radius={8}
          pathOptions={{ color: "#fff", fillColor: "#22c55e", fillOpacity: 1 }}
        />
      ) : null}
    </MapContainer>
  );
}

/** F3 — phone-sized page for one unit (/driver/:unit). Reads only
 * GET /api/simulation/unit/{unit} (its own 2 s poll; this page is never
 * mounted inside /simulation) and posts Accept / Reject. */
export default function DriverApp() {
  const { unit = "" } = useParams();
  const [view, setView] = useState(null);
  const [error, setError] = useState("");
  const [posting, setPosting] = useState(false);
  const [note, setNote] = useState("");
  const [reason, setReason] = useState(REASONS[0]);
  const [left, setLeft] = useState(null);
  const fetchedAt = useRef(0);

  const load = useCallback(async () => {
    try {
      const data = await fetchUnitJob(unit);
      setView(data);
      setError("");
      fetchedAt.current = Date.now();
      setLeft(data?.job?.seconds_left ?? null);
    } catch (e) {
      setError(e?.response?.status === 404 ? `Unknown unit "${unit}".` : "Cannot reach the control room — retrying…");
    }
  }, [unit]);

  useEffect(() => {
    let alive = true;
    let timer;
    const tick = async () => {
      await load();
      if (alive) timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [load]);

  // Countdown between polls, from the backend's own seconds_left.
  const base = view?.job?.seconds_left;
  useEffect(() => {
    if (base == null) return undefined;
    const id = setInterval(() => setLeft(Math.max(0, base - (Date.now() - fetchedAt.current) / 1000)), 250);
    return () => clearInterval(id);
  }, [base]);

  async function answer(accepted) {
    setPosting(true);
    setNote("");
    try {
      if (accepted) await acceptJob(unit);
      else await rejectJob(unit, reason);
      setNote(accepted ? "Accepted — drive safely. Route below." : "Rejected — the job was offered to the next unit.");
      await load();
    } catch (e) {
      setNote(
        e?.response?.status === 409
          ? "Too late — this request was already answered, timed out or moved on."
          : `Failed: ${e?.response?.data?.detail || e?.message || "error"}`
      );
      await load();
    } finally {
      setPosting(false);
    }
  }

  const job = view?.job;
  const manual = view?.accept_mode === "manual";
  return (
    <div className="drv-page">
      <header className="drv-head">
        <div>
          <p className="drv-kicker">AQUASENTINEL · {view?.role === "ambulance" ? "AMBULANCE" : "RESCUE UNIT"}</p>
          <h1>{decodeURIComponent(unit)}</h1>
        </div>
        <span className={`drv-mode ${manual ? "is-manual" : ""}`}>{manual ? "Drivers decide" : "Auto-accept"}</span>
      </header>

      {error ? <p className="drv-banner is-error">{error}</p> : null}
      {view && !view.run_id ? <p className="drv-banner">No live operation. Start a scenario on the control room.</p> : null}

      {view && !job ? (
        <section className="drv-card drv-idle">
          <h2>No job</h2>
          <p>Waiting for the control room to send a request.</p>
          <p className="drv-muted">{view.trips_completed} trip(s) completed this run.</p>
        </section>
      ) : null}

      {job ? (
        <section className={`drv-card ${view.status === "request" ? "is-request" : ""}`}>
          <p className="drv-kicker">{view.status === "request" ? "NEW SOS REQUEST" : job.stage_label}</p>
          <h2>{job.citizen_name}</h2>
          <dl className="drv-facts">
            <div>
              <dt>People</dt>
              <dd>{job.people}</dd>
            </div>
            <div>
              <dt>Age</dt>
              <dd>{job.age ?? "—"}</dd>
            </div>
            <div>
              <dt>Water</dt>
              <dd>{job.water || "—"}</dd>
            </div>
            <div>
              <dt>Priority</dt>
              <dd>{job.vulnerability || "—"}</dd>
            </div>
            <div>
              <dt>To person</dt>
              <dd>
                {job.route_to_person?.km ?? "—"} km · {job.eta_min ?? "—"} min
              </dd>
            </div>
            <div>
              <dt>Shelter</dt>
              <dd>
                {job.shelter_name || "—"} · {job.eta_to_shelter_min ?? "—"} min
              </dd>
            </div>
          </dl>
          {job.rejected_by?.length ? (
            <p className="drv-muted">Already declined by: {job.rejected_by.join(", ")}</p>
          ) : null}

          <JobMap job={job} />
          <p className="drv-legend">
            <i className="leg-a" /> Depot → person <i className="leg-b" /> Person → shelter
          </p>

          {view.status === "request" ? (
            <>
              {left != null ? (
                <p className={`drv-countdown ${left < 6 ? "is-low" : ""}`}>
                  {manual
                    ? `Answer within ${Math.ceil(left)} s — otherwise the job goes to the next unit`
                    : `Control room is on auto-accept: accepted automatically in ${Math.ceil(left)} s`}
                </p>
              ) : null}
              <div className="drv-actions">
                <button type="button" className="drv-btn accept" disabled={posting} onClick={() => answer(true)}>
                  ✅ Accept
                </button>
                <button type="button" className="drv-btn reject" disabled={posting} onClick={() => answer(false)}>
                  ✖ Reject
                </button>
              </div>
              <label className="drv-reason">
                Reject reason
                <select value={reason} onChange={(e) => setReason(e.target.value)} disabled={posting}>
                  {REASONS.map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </select>
              </label>
            </>
          ) : (
            <p className="drv-banner is-ok">Job accepted — follow the route.</p>
          )}
        </section>
      ) : null}

      {note ? <p className="drv-banner">{note}</p> : null}
      <p className="drv-foot">
        Demo page: no driver login yet (anyone with the link answers for this unit). Data comes from the live
        simulation — the stage machine on the server decides every timing.
      </p>
    </div>
  );
}
