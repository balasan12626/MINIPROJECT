import { memo, useCallback, useMemo, useRef, useState } from "react";
import LiveRescueMap from "./LiveRescueMap.jsx";
import RoadControlPanel, { roadAction } from "./RoadControlPanel.jsx";
import { roadsForMap, useCityView } from "../../hooks/useCityView.js";
import LivePeopleTable from "./LivePeopleTable.jsx";
import FleetPanel from "./FleetPanel.jsx";
import ShelterCapacityPanel from "./ShelterCapacityPanel.jsx";
import SosQrCard from "./SosQrCard.jsx";
import DecisionCard from "./DecisionCard.jsx";
import DuplicateSosPanel from "./DuplicateSosPanel.jsx";
import SilentZonesPanel from "./SilentZonesPanel.jsx";
import SupplyPanel from "./SupplyPanel.jsx";
import EquityPanel from "./EquityPanel.jsx";
import RouteCasesPanel from "./RouteCasesPanel.jsx";
import QuantumRoutePanel from "./QuantumRoutePanel.jsx";
import PersonReportPanel from "./PersonReportPanel.jsx";
import RescueStepper from "./RescueStepper.jsx";
import PdfDownloadButton from "../PdfDownloadButton.jsx";
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

/** Selected person, as a card with the full rescue stepper. */
function PersonFocus({ p }) {
  if (!p) return null;
  return (
    <div className="panel person-focus">
      <div className="panel-head">
        <h3>
          {p.name} <span className="muted">· {p.people ?? 1} people{p.age != null ? ` · age ${p.age}` : ""}</span>
        </h3>
        <PdfDownloadButton personName={p.name} label="Person PDF" />
      </div>
      <RescueStepper p={p} />
      <p className="hint">
        {p.stage === "queued"
          ? p.waitReason
            ? `Waiting: ${p.waitReason}.`
            : "In the SOS queue — dispatch is vulnerable-first."
          : `${p.unitRole === "ambulance" ? "Ambulance" : "Rescue team"} ${p.unitName || ""} from ${p.unitBaseName || "base"} → ${p.name} → ${p.shelter || "shelter"}.`}
      </p>
      <DecisionCard d={p.decision} />
    </div>
  );
}

/** Live rescue operations, split by tab.
 *
 * Reads the same `sim` object SimulationExecution already polls — it adds no
 * second poller. Every view derives from one view model, so a stage change
 * shows up everywhere on the same poll.
 *
 *   view="live"    counters, map, driver inbox, fleet, shelters, event feed
 *   view="people"  the SOS roster + selected person
 *   view="routes"  route cases + map with planned legs
 *   view="report"  per-person timings + PDFs */
export default function RescueOpsPanel({ sim, view = "live", sosSlot = null, onState = null }) {
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
  const fleet = sim?.fleet_board || null;
  const allocation = sim?.shelter_allocation || EMPTY_LIST;
  const seatsFree = allocation.reduce((n, s) => n + (s.seats_left || 0), 0);
  const selected = selectedKey ? peopleByKey.get(selectedKey) || null : null;

  // Roads change rarely; keep one array identity until they do, so the map's
  // road lines are not re-pushed to Leaflet on every 1.2 s poll.
  const roadsRaw = sim?.road_status;
  const roadsKey = (roadsRaw || EMPTY_LIST)
    .map((r) => `${r.road_id}:${r.blocked ? 1 : 0}:${r.operator ? 1 : 0}:${r.active_legs}:${r.closes_in_sim_min ?? ""}`)
    .join("|");
  // F7: static map data for the run's city (centre, shelters, depots, rivers, road shapes).
  const cityView = useCityView(sim?.city?.id || null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const roads = useMemo(() => roadsRaw || EMPTY_LIST, [roadsKey]);
  const mapRoads = useMemo(() => roadsForMap(roads, cityView), [roads, cityView]);
  const onRoad = useCallback(
    async (roadId, action) => {
      const res = await roadAction(roadId, action);
      onState?.(res);
      return res;
    },
    [onState]
  );

  const map = (planned) => (
    <div className="panel rescue-map-panel">
      <div className="panel-head">
        <h3>{planned === "all" ? "Route map" : "Rescue map"}</h3>
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
        toasts={view === "live" ? toasts : EMPTY_LIST}
        onToast={onToast}
        plannedRoutes={planned}
        roads={mapRoads}
        silentZones={sim?.silent_zones?.zones || EMPTY_LIST}
        supplyTrucks={sim?.supply?.trucks || EMPTY_LIST}
        onRoad={onState ? onRoad : null}
        cityView={cityView}
      />
    </div>
  );

  return (
    <section className="rescue-ops" aria-label="Live rescue operations">
      <div className="status-row section-head">
        <span className={`badge ${paused ? "warn" : "live"}`}>{paused ? "VIEW PAUSED" : "LIVE"}</span>
        <button type="button" onClick={togglePaused}>
          {paused ? "▶ Resume view" : "⏸ Pause view"}
        </button>
        <span className="hint rescue-ops-note">
          Pause freezes this view only — the backend run keeps going.
          {clock?.time_scale ? ` Stage times follow route travel time (demo clock ×${clock.time_scale}).` : ""}
        </span>
      </div>

      {view === "live" || view === "people" ? (
        <div className="rescue-kpi-strip">
          {[
            ["SOS received", c.totalSos, ""],
            ["Waiting", c.waiting, "is-waiting"],
            ["Driver requested", c.assigned, "is-assigned"],
            ["Driving to person", c.enRoute, "is-enroute"],
            ["To shelter", c.transporting, "is-transport"],
            ["Safe", c.rescued, "is-safe"],
            ...(view === "live"
              ? [
                  ["Ambulances free", fleet ? `${fleet.ambulances_free}/${fleet.ambulances_total}` : "—", ""],
                  ["Shelter seats free", allocation.length ? seatsFree.toLocaleString("en-IN") : "—", ""],
                ]
              : [["People delivered", c.peopleRescued, "is-safe"]]),
          ].map(([label, value, cls]) => (
            <div className={`rescue-kpi ${cls}`} key={label}>
              <b>{value ?? 0}</b>
              <span>{label}</span>
            </div>
          ))}
        </div>
      ) : null}

      {view === "live" && sim?.zone_warnings?.length ? (
        <div className="zone-warning-strip" role="status">
          {sim.zone_warnings.map((w) => (
            <span className="badge warn" key={w.zone_id} title={`Road ${w.road_name}; warning lead ${w.lead_min} sim min (playbook)`}>
              ⚠ Evacuation warning: {w.name} — {w.closes_in_min <= 0 ? "roads already flooding" : `first road floods in ~${Math.round(w.closes_in_min)} min`}
            </span>
          ))}
        </div>
      ) : null}

      {view === "live" && sim?.status ? <SilentZonesPanel view={sim.silent_zones} onState={onState} /> : null}
      {view === "live" ? <SupplyPanel supply={sim?.supply} /> : null}

      {view === "live" ? (
        <>
          <div className="grid-2 rescue-main-grid">
            {map("selected")}
            <div className="rescue-side">
              {sosSlot}
              <PersonFocus p={selected} />
              <SosQrCard />
            </div>
          </div>
          <FleetPanel
            fleet={fleet}
            people={ops.people}
            onSelect={select}
            acceptMode={sim?.accept_mode || "auto"}
            acceptTimeout={sim?.accept_timeout_seconds ?? null}
            onState={onState}
          />
          <div className="grid-2">
            <ShelterCapacityPanel allocation={allocation} onState={onState} />
            <EventFeed feed={feed} onSelect={select} />
          </div>
        </>
      ) : null}

      {view === "people" ? (
        <>
          <PersonFocus p={selected} />
          <DuplicateSosPanel candidates={sim?.duplicate_candidates || EMPTY_LIST} merged={ops.merged || EMPTY_LIST} onState={onState} />
          <LivePeopleTable people={ops.people} selectedKey={selectedKey} onSelect={select} />
          <ShelterUsage shelters={ops.shelters} />
        </>
      ) : null}

      {view === "routes" ? (
        <>
          {map("all")}
          <RoadControlPanel roads={roads} log={sim?.road_log || EMPTY_LIST} onState={onState} />
          <QuantumRoutePanel people={ops.people} selectedKey={selectedKey} onSelect={select} />
          <RouteCasesPanel people={ops.people} selectedKey={selectedKey} onSelect={select} />
        </>
      ) : null}

      {view === "report" ? (
        <>
          <EquityPanel equity={sim?.equity} />
          <PersonReportPanel people={ops.people} selectedKey={selectedKey} onSelect={select} />
        </>
      ) : null}
    </section>
  );
}

const EMPTY_LIST = [];
