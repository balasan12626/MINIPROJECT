import { memo, useMemo, useState } from "react";
import { STAGE_COLOR, STAGE_SHORT } from "../../data/rescueAssets.js";
import { setAcceptMode } from "../../services/api.js";
import { formatTimeIST, toDate } from "../../utils/time.js";
import RescueStepper from "./RescueStepper.jsx";

export const driverHref = (unit) => `/driver/${encodeURIComponent(unit)}`;

/** When the driver must answer by (request time + backend timeout) — from
 * backend timestamps only, so no client clock is involved. */
function answerDue(sentAt, timeoutS) {
  const d = toDate(sentAt);
  return d && timeoutS ? new Date(d.getTime() + timeoutS * 1000).toISOString() : null;
}

/** Auto-accept (simulated crews) vs Drivers decide (driver app answers). */
export function AcceptModeToggle({ mode = "auto", onState }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function pick(next) {
    if (next === mode || busy) return;
    setBusy(true);
    setErr("");
    try {
      onState?.(await setAcceptMode(next));
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || "failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <span className="accept-toggle seg-control" role="radiogroup" aria-label="Who accepts dispatch requests">
      {[
        ["auto", "Auto-accept"],
        ["manual", "Drivers decide"],
      ].map(([id, label]) => (
        <button
          key={id}
          type="button"
          role="radio"
          aria-checked={mode === id}
          className={mode === id ? "is-active" : ""}
          disabled={busy || !onState}
          onClick={() => pick(id)}
        >
          {label}
        </button>
      ))}
      {err ? <span className="error-text">{err}</span> : null}
    </span>
  );
}

/** Dispatch requests the drivers / crew leads received, newest first. Each
 * card is one person's SOS as the unit sees it, plus whether it was accepted.
 * Every field comes from the backend row (dispatch_request, accepted_at). */
const DriverInbox = memo(function DriverInbox({ people, onSelect, acceptMode, acceptTimeout }) {
  const jobs = useMemo(
    () =>
      people
        .filter((p) => p.dispatchRequest && ["assigned", "en_route", "to_shelter"].includes(p.stage))
        .sort((a, b) => String(b.dispatchRequest.sent_at).localeCompare(String(a.dispatchRequest.sent_at))),
    [people]
  );
  return (
    <div className="panel driver-inbox">
      <div className="panel-head">
        <h3>Driver inbox — SOS requests sent to units</h3>
        <span className="badge sim">{jobs.length} active</span>
      </div>
      {jobs.length === 0 ? (
        <p className="hint">
          No active requests. When an SOS is dispatched, its details (name, people, GPS, water level, shelter) are sent
          to the unit here, and the driver&apos;s accept shows up on the card.
        </p>
      ) : (
        <div className="driver-inbox-list">
          {jobs.map((p) => {
            const r = p.dispatchRequest;
            return (
              <article key={p.key} className={`driver-card ${p.accepted ? "is-accepted" : "is-pending"}`}>
                <header>
                  <span className={`unit-role-tag role-${p.unitRole}`}>{p.unitRole === "ambulance" ? "🚑 Ambulance" : "🚒 Rescue team"}</span>
                  <b>{r.to}</b>
                  {p.accepted ? (
                    <span className="badge live">
                      ✓ ACCEPTED {formatTimeIST(p.acceptedAt)}
                      {p.acceptedVia === "driver app" ? " · driver app" : ""}
                    </span>
                  ) : (
                    <span className="badge warn pulse">
                      {acceptMode === "manual"
                        ? `WAITING FOR DRIVER · answer by ${formatTimeIST(answerDue(r.sent_at, acceptTimeout))}`
                        : "AWAITING DRIVER"}
                    </span>
                  )}
                  <a className="link-btn" href={driverHref(r.to)} target="_blank" rel="noreferrer">
                    Open driver view ↗
                  </a>
                </header>
                <button type="button" className="driver-card-body link-like" onClick={() => onSelect?.(p.key, { pan: true })}>
                  <span>
                    <b>{r.citizen_name}</b> · {r.people} people{r.age != null ? ` · age ${r.age}` : ""}
                    {r.vulnerability && r.vulnerability !== "standard" ? <em className="prio-tag"> {r.vulnerability}</em> : null}
                  </span>
                  <span className="muted">
                    GPS {Number(r.lat).toFixed(4)}, {Number(r.lon).toFixed(4)} · {r.water_level_note || "flood water"}
                  </span>
                  <span>
                    Drop at <b>{r.shelter_name}</b> · {r.km} km · ETA {r.eta_min} min
                  </span>
                  <span className="muted">Request sent {formatTimeIST(r.sent_at)}</span>
                </button>
                <RescueStepper p={p} compact />
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
});

/** Live ambulance pool: which are free, which are on a job and where. */
function FleetPanel({ fleet, people = [], onSelect, acceptMode = "auto", acceptTimeout = null, onState = null, replay = false }) {
  const ambulances = fleet?.ambulances || [];
  const teams = fleet?.rescue_units_active || [];
  const waiting = fleet?.waiting_for_ambulance || [];
  const byName = useMemo(() => new Map(people.map((p) => [p.name, p])), [people]);

  return (
    <>
      <div className="panel fleet-panel">
        <div className="panel-head">
          <h3>Ambulance fleet — live</h3>
          {onState ? <AcceptModeToggle mode={acceptMode} onState={onState} /> : null}
          {fleet ? (
            <span className="fleet-summary">
              <span className="badge live">{fleet.ambulances_free} free</span>
              <span className="badge crit">{fleet.ambulances_busy} busy</span>
              {fleet.ambulances_off_duty ? <span className="badge warn">{fleet.ambulances_off_duty} resting / refuelling</span> : null}
              <span className="badge">{fleet.ambulances_total} total</span>
            </span>
          ) : null}
        </div>
        {!fleet ? (
          <p className="hint">Fleet status appears once the run starts.</p>
        ) : (
          <>
            <div className="fleet-meter" aria-label={`${fleet.ambulances_busy} of ${fleet.ambulances_total} ambulances busy`}>
              {ambulances.map((a) => (
                <i key={a.name} className={a.status === "busy" ? "is-busy" : "is-free"} title={`${a.name}: ${a.status}`} />
              ))}
            </div>
            <div className="fleet-grid">
              {ambulances.map((a) => {
                const p = a.job ? byName.get(a.job.citizen_name) : null;
                return (
                  <button
                    key={a.name}
                    type="button"
                    className={`fleet-card is-${a.status}`}
                    disabled={!p}
                    onClick={() => p && onSelect?.(p.key, { pan: true })}
                  >
                    <span className="fleet-card-name">🚑 {a.name.replace("Ambulance Unit", "Unit")}</span>
                    {a.job ? (
                      <>
                        <span className="status-pill" style={{ color: STAGE_COLOR[a.job.stage] }}>
                          {STAGE_SHORT[a.job.stage] || a.job.stage}
                        </span>
                        <span className="fleet-card-job">
                          {a.job.citizen_name} → {a.job.shelter_name}
                        </span>
                        <span className="muted">{a.job.accepted ? "driver accepted" : "awaiting driver"}</span>
                      </>
                    ) : a.crew ? (
                      <span className="fleet-card-free">
                        {a.crew.state === "resting" ? "😴 RESTING" : "⛽ REFUELLING"} · back in {Math.round(a.crew.left_min)} min
                      </span>
                    ) : (
                      <span className="fleet-card-free">FREE · ready</span>
                    )}
                    <span className="muted fleet-card-trips">{a.trips_completed} trip(s) done</span>
                  </button>
                );
              })}
            </div>
            {fleet.crew_rules ? <p className="hint">Crew rules on: {fleet.crew_rules_source}</p> : null}
            {waiting.length ? (
              <p className="error-text">
                {waiting.length} SOS waiting for a free ambulance: {waiting.join(", ")}
              </p>
            ) : null}
            <p className="hint">
              Children, elderly, chest-deep and injured callers get the first free ambulance; everyone else is moved
              by their K-means cluster&apos;s rescue team. Active rescue teams: {teams.length ? teams.map((t) => t.name).join(", ") : "none"}.
            </p>
            <p className="hint">
              {acceptMode === "manual"
                ? `Drivers decide: each request waits for Accept / Reject in the driver view; no answer within ${acceptTimeout ?? "the timeout"} s sends it to the next free unit.`
                : "Auto-accept: simulated crews accept every request when roll-out ends."}{" "}
              Demo only — the driver view has no driver login.
            </p>
            <div className="driver-links" hidden={replay}>
              <span className="muted">Driver views:</span>
              {ambulances.map((a) => (
                <a key={a.name} href={driverHref(a.name)} target="_blank" rel="noreferrer">
                  {a.name.replace("Ambulance Unit", "Unit")} ↗
                </a>
              ))}
              {teams.map((t) => (
                <a key={t.name} href={driverHref(t.name)} target="_blank" rel="noreferrer">
                  {t.name} ↗
                </a>
              ))}
            </div>
          </>
        )}
      </div>
      {replay ? null : (
        <DriverInbox people={people} onSelect={onSelect} acceptMode={acceptMode} acceptTimeout={acceptTimeout} />
      )}
    </>
  );
}

export default memo(FleetPanel);
