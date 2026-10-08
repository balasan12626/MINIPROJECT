import { memo, useCallback, useMemo, useRef, useState } from "react";
import LiveRescueMap from "./LiveRescueMap.jsx";
import LivePeopleTable from "./LivePeopleTable.jsx";
import { STAGE_COLOR, STAGE_SHORT } from "../../data/rescueAssets.js";
import { useNewSosToasts, useRescueOps } from "../../hooks/useRescueOps.js";
import { formatClock } from "../../state/rescueOps.js";

/** Live event feed: engine events + every per-person stage transition,
 * merged and sorted by real server timestamp (rendered in IST). */
const EventFeed = memo(function EventFeed({ feed = [], onSelect }) {
  return (
    <div className="panel rescue-feed-panel">
      <div className="panel-head">
        <h3>Live event feed</h3>
        <span className="badge sim">{feed.length}</span>
      </div>
      {feed.length === 0 ? (
        <p className="hint">Events appear once the scenario starts.</p>
      ) : (
        <div className="timeline rescue-feed">
          {feed.map((e, i) => (
            <div
              key={`${e.at}-${e.personKey || "engine"}-${i}`}
              className={e.personKey ? "rescue-feed-row is-person" : "rescue-feed-row"}
              onClick={() => e.personKey && onSelect?.(e.personKey, { pan: true })}
            >
              <b>{formatClock(e.at)}</b>{" "}
              {e.stage ? (
                <span className="status-pill" style={{ color: STAGE_COLOR[e.stage] || undefined }}>
                  {STAGE_SHORT[e.stage] || e.stage}
                </span>
              ) : (
                <span className="badge live">ENGINE</span>
              )}{" "}
              <span className="muted">[{e.who}]</span> {e.text}
              {e.count > 1 ? <b className="muted"> ×{e.count}</b> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

/** Shelters this run actually uses. "Delivered this run" is people rescue
 * units dropped there; the backend's board occupancy is a separate growth
 * curve and is labelled as such — the two are never added together. */
function ShelterUsage({ shelters = [] }) {
  const used = shelters.filter((s) => s.usedThisRun);
  if (!used.length) return null;
  return (
    <div className="panel">
      <div className="panel-head">
        <h3>Shelters used this run ({used.length})</h3>
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Shelter</th>
              <th>Assigned (people)</th>
              <th>Inbound</th>
              <th>Delivered this run</th>
              <th>Board occupancy / capacity</th>
            </tr>
          </thead>
          <tbody>
            {used.map((s) => (
              <tr key={s.id}>
                <td>{s.name}</td>
                <td>{s.assignedThisRun}</td>
                <td>{s.inboundThisRun}</td>
                <td>
                  <b>{s.arrivedThisRun}</b>
                </td>
                <td className="muted">
                  {s.backendOccupancy ?? "—"} / {s.capacity ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">
        Board occupancy is the backend&apos;s shelter-demand growth curve, reported separately from people delivered
        by rescue units this run.
      </p>
    </div>
  );
}

/** Live rescue operations view.
 *
 * Reads the same `sim` object SimulationExecution already polls — it adds no
 * second poller. Map, roster and feed all derive from the same view model, so
 * a stage change shows up in all three on the same poll. */
export default function RescueOpsPanel({ sim }) {
  const { ops, feed, offset, paused, togglePaused } = useRescueOps(sim);
  const [selectedKey, setSelectedKey] = useState(null);
  const [panTarget, setPanTarget] = useState(null);
  const nonceRef = useRef(0);
  const { toasts, dismiss } = useNewSosToasts(sim?.run_id, ops.people);

  const peopleByKey = useMemo(() => new Map(ops.people.map((p) => [p.key, p])), [ops.people]);
  const peopleRef = useRef(peopleByKey);
  peopleRef.current = peopleByKey;

  /** select(key, {pan}) — the roster/feed/toast pan the map; map clicks don't. */
  const select = useCallback((key, opts = {}) => {
    setSelectedKey(key);
    if (opts.pan) {
      const p = peopleRef.current.get(key);
      if (p && p.lat != null && p.lon != null) {
        nonceRef.current += 1;
        setPanTarget({ nonce: nonceRef.current, lat: p.lat, lon: p.lon });
      }
    }
  }, []);

  const onToast = useCallback(
    (t) => {
      select(t.key, { pan: true });
      dismiss(t.id);
    },
    [select, dismiss]
  );

  const floodP =
    sim?.current?.flood_probability ??
    sim?.history?.[sim.history.length - 1]?.flood_probability ??
    sim?.pipeline?.prediction?.flood_probability ??
    0;

  const c = ops.counters;
  const clock = sim?.ops_clock;

  return (
    <section className="rescue-ops" aria-label="Live rescue operations">
      <div className="status-row section-head">
        <h3 className="section-title">Live rescue operation</h3>
        <span className={`badge ${paused ? "warn" : "live"}`}>{paused ? "VIEW PAUSED" : "LIVE"}</span>
        <button type="button" onClick={togglePaused}>
          {paused ? "▶ Resume view" : "⏸ Pause view"}
        </button>
        <span className="hint rescue-ops-note">
          Pause freezes this view only — the backend run keeps going.
          {clock?.time_scale ? ` Stage times follow route travel time (demo clock ×${clock.time_scale}).` : ""}
        </span>
      </div>

      <div className="grid-3 rescue-kpi-row">
        {[
          ["Total SOS", c.totalSos],
          ["Waiting", c.waiting],
          ["En route", c.enRoute],
          ["Transporting", c.transporting],
          ["Rescued", c.rescued],
          ["People delivered", c.peopleRescued],
        ].map(([label, value]) => (
          <div className="panel kpi kpi-card" key={label}>
            <div className="label">{label}</div>
            <div className="value">{value ?? 0}</div>
          </div>
        ))}
      </div>

      <div className="grid-2 rescue-main-grid">
        <div className="panel rescue-map-panel">
          <div className="panel-head">
            <h3>Rescue map</h3>
            <span className="badge sim">{c.unitsMoving} unit(s) moving</span>
          </div>
          <LiveRescueMap
            ops={ops}
            offset={offset}
            paused={paused}
            selectedKey={selectedKey}
            panTarget={panTarget}
            onSelect={select}
            floodProbability={floodP}
            toasts={toasts}
            onToast={onToast}
          />
        </div>
        <EventFeed feed={feed} onSelect={select} />
      </div>

      <LivePeopleTable people={ops.people} selectedKey={selectedKey} onSelect={select} />
      <ShelterUsage shelters={ops.shelters} />
    </section>
  );
}
