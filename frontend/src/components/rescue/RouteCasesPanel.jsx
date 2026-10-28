import { memo, useMemo, useState } from "react";
import { STAGE_COLOR, STAGE_SHORT } from "../../data/rescueAssets.js";

const METHOD_LABEL = {
  "qaoa-flood": "QAOA (simulated) over Yen candidates",
  "dijkstra-flood": "Dijkstra (single open path)",
  direct: "Direct segment (no open road path)",
};

const FILTERS = [
  ["all", "All"],
  ["ambulance", "Ambulance"],
  ["rescue", "Rescue team"],
  ["active", "On the road now"],
  ["waiting", "Waiting"],
  ["rerouted", "Re-routed"],
];

const sum = (a, b) => (typeof a === "number" && typeof b === "number" ? Math.round((a + b) * 10) / 10 : null);

/** Route cases: every SOS person's two legs, as the backend computed them
 * (person_ops.road_route over the flood-aware road graph):
 *   leg 1  unit base  → person   (route_to_person)
 *   leg 2  person     → shelter  (route_to_shelter, recomputed at pickup) */
function RouteCasesPanel({ people = [], selectedKey, onSelect }) {
  const [filter, setFilter] = useState("all");

  const rows = useMemo(() => {
    return people.filter((p) => {
      if (filter === "ambulance") return p.unitRole === "ambulance" && p.stage !== "queued";
      if (filter === "rescue") return p.unitRole !== "ambulance" && p.stage !== "queued";
      if (filter === "active") return ["en_route", "to_shelter"].includes(p.stage);
      if (filter === "waiting") return p.stage === "queued";
      if (filter === "rerouted")
        return p.reroutes?.length > 0 || Boolean(p.routeAlert) || p.shelterChanges?.length > 0 || p.shelterWait;
      return true;
    });
  }, [people, filter]);

  const methods = useMemo(() => {
    const m = new Map();
    for (const p of people) if (p.routeMethod) m.set(p.routeMethod, (m.get(p.routeMethod) || 0) + 1);
    return [...m.entries()];
  }, [people]);

  const routed = people.filter((p) => p.routeKm != null);
  const rerouted = people.filter((p) => p.reroutes?.length).length;
  const alerts = people.filter((p) => p.routeAlert).length;
  const avgKm = routed.length ? routed.reduce((n, p) => n + (sum(p.routeKm, p.shelterKm ?? 0) || 0), 0) / routed.length : null;

  return (
    <div className="panel route-cases">
      <div className="panel-head">
        <h3>Route cases — unit → person → shelter</h3>
        <span className="badge sim">{routed.length} routed</span>
      </div>
      <div className="route-method-row">
        {methods.length ? (
          methods.map(([m, n]) => (
            <span className="badge" key={m}>
              {METHOD_LABEL[m] || m}: {n}
            </span>
          ))
        ) : (
          <span className="hint">Routes appear once units are allocated.</span>
        )}
        {avgKm != null ? <span className="badge live">avg {avgKm.toFixed(2)} km per case (both legs)</span> : null}
        {rerouted ? <span className="badge warn">⛔ {rerouted} re-routed after a road change</span> : null}
        {alerts ? <span className="badge crit">{alerts} with no open road</span> : null}
      </div>
      <div className="seg-control" role="radiogroup" aria-label="Filter route cases">
        {FILTERS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={filter === id}
            className={filter === id ? "is-active" : ""}
            onClick={() => setFilter(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Person</th>
              <th>Status</th>
              <th>Unit (from)</th>
              <th>Leg 1: unit → person</th>
              <th>Leg 2: person → shelter</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr
                key={p.key}
                className={p.key === selectedKey ? "is-selected" : ""}
                onClick={() => onSelect?.(p.key, { pan: true })}
                style={{ cursor: "pointer" }}
              >
                <td>{p.rescueOrder ?? "—"}</td>
                <td>
                  <b>{p.name}</b>
                  <div className="muted">{p.people ?? 1} people · {p.priority}</div>
                </td>
                <td>
                  <span className="status-pill" style={{ color: STAGE_COLOR[p.stage] }}>
                    {STAGE_SHORT[p.stage] || p.stage}
                  </span>
                  {p.waitReason ? <div className="muted">{p.waitReason}</div> : null}
                  {p.reroutes?.length ? (
                    <div
                      className="reroute-chip"
                      title={p.reroutes
                        .map((r) => `${r.reason}: ${r.old_minutes_left} → ${r.new_minutes} min`)
                        .join(" | ")}
                    >
                      ⛔ re-routed {p.reroutes.length}× · last {p.reroutes[p.reroutes.length - 1].delta_minutes >= 0 ? "+" : ""}
                      {p.reroutes[p.reroutes.length - 1].delta_minutes} min
                    </div>
                  ) : null}
                  {p.routeAlert ? <div className="reroute-chip is-alert">No open road — plan kept</div> : null}
                  {p.shelterChanges?.length ? (
                    <div
                      className="reroute-chip"
                      title={p.shelterChanges.map((s) => `${s.reason}: ${s.old_shelter} → ${s.new_shelter}`).join(" | ")}
                    >
                      🏠 shelter moved · {p.shelterChanges[p.shelterChanges.length - 1].old_shelter} →{" "}
                      {p.shelterChanges[p.shelterChanges.length - 1].new_shelter}
                    </div>
                  ) : null}
                  {p.shelterWait ? <div className="reroute-chip is-alert">No shelter with free seats</div> : null}
                </td>
                <td>
                  {p.unitName && p.stage !== "queued" ? (
                    <>
                      {p.unitRole === "ambulance" ? "🚑" : "🚒"} {p.unitName}
                      <div className="muted">{p.unitBaseName || "—"}</div>
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td>{p.routeKm != null ? `${p.routeKm} km · ${p.etaMin} min` : "—"}</td>
                <td>
                  {p.shelterKm != null ? `${p.shelterKm} km · ${p.etaShelterMin} min` : "—"}
                  <div className="muted">{p.shelter || ""}</div>
                </td>
                <td>
                  {p.routeKm != null && p.shelterKm != null
                    ? `${sum(p.routeKm, p.shelterKm)} km · ${sum(p.etaMin, p.etaShelterMin)} min`
                    : "—"}
                </td>
              </tr>
            ))}
            {!rows.length ? (
              <tr>
                <td colSpan={7} className="muted">
                  No cases match this filter.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <p className="hint">
        Times are simulated minutes at the rescue vehicle speed over flood-weighted roads; blocked roads are removed
        from the graph, and the route is the QAOA choice among up to 4 candidates. Leg 2 is recomputed at pickup against the road state at that moment. Click a row to draw its
        route on the map.
      </p>
    </div>
  );
}

export default memo(RouteCasesPanel);
