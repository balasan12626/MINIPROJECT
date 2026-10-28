import { memo, useState } from "react";
import { setRoad } from "../../services/api.js";
import { formatTimeIST } from "../../utils/time.js";

const SOURCE_LABEL = {
  open: "Open",
  flood: "Closed by flood",
  operator: "Operator",
};

/** Ask the backend to block / open a road. Shared by the panel, the map
 * popup and the live-controls quick button; returns the new state. */
export async function roadAction(roadId, action) {
  const body = action === "clear" ? { road_id: roadId, clear: true } : { road_id: roadId, blocked: action === "block" };
  return setRoad(body);
}

export function roadChangeNote(res) {
  const ch = res?.road_change;
  if (!ch) return "Done.";
  const what = ch.cleared ? "handed back to the flood rule" : ch.blocked ? "blocked" : "opened";
  const stuck = ch.no_open_road ? ` · ${ch.no_open_road} with no open road (plan kept, red alert)` : "";
  return `${ch.name} (${ch.road_id}) ${what} — ${ch.rerouted} route leg(s) re-planned${stuck}.`;
}

/** F1 — the run's road network: who closed what, how many active route legs
 * drive on each road, and Block / Open / Back-to-flood-rule controls. Every
 * value comes from sim.road_status / sim.road_log (engine.road_status()). */
const PAGE = 40;

function RoadControlPanel({ roads = [], log = [], onState }) {
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [query, setQuery] = useState("");
  const [all, setAll] = useState(false);

  // Real cities have hundreds of roads (F7): busiest / closed first, searchable.
  const q = query.trim().toLowerCase();
  const ranked = [...roads]
    .filter((r) => !q || `${r.road_id} ${r.name}`.toLowerCase().includes(q))
    .sort(
      (a, b) =>
        (b.operator ? 1 : 0) - (a.operator ? 1 : 0) ||
        b.active_legs - a.active_legs ||
        (b.blocked ? 1 : 0) - (a.blocked ? 1 : 0) ||
        (b.flood_exposure || 0) - (a.flood_exposure || 0)
    );
  const shown = all || q ? ranked : ranked.slice(0, PAGE);

  async function act(roadId, action) {
    setBusy(roadId);
    setNote("");
    try {
      const res = await roadAction(roadId, action);
      onState?.(res);
      setNote(roadChangeNote(res));
    } catch (e) {
      setNote(`Failed: ${e?.response?.data?.detail || e?.message || "error"}`);
    } finally {
      setBusy("");
    }
  }

  const closed = roads.filter((r) => r.blocked).length;
  return (
    <div className="panel road-panel">
      <div className="panel-head">
        <h3>⛔ Roads — block one and watch the units re-route</h3>
        <span className={`badge ${closed ? "warn" : "live"}`}>
          {closed}/{roads.length || 0} closed
        </span>
      </div>
      {!roads.length ? <p className="hint">Run a scenario to load the road network.</p> : null}
      {roads.length > PAGE ? (
        <div className="road-search">
          <input
            type="search"
            placeholder={`Search ${roads.length} roads by name or id…`}
            aria-label="Search roads"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {!q ? (
            <button type="button" className="link-btn" onClick={() => setAll((v) => !v)}>
              {all ? `Show the ${PAGE} busiest` : `Show all ${roads.length}`}
            </button>
          ) : (
            <span className="muted">{ranked.length} match(es)</span>
          )}
        </div>
      ) : null}
      <div className="road-grid">
        {shown.map((r) => (
          <div key={r.road_id} className={`road-card ${r.blocked ? "is-closed" : ""} ${r.operator ? "is-operator" : ""}`}>
            <div className="road-card-head">
              <b>{r.road_id}</b>
              <span className={`road-chip src-${r.blocked ? r.source : "open"}`}>
                {r.blocked ? "⛔ " : "✅ "}
                {r.operator ? `${r.blocked ? "Blocked" : "Opened"} by operator` : SOURCE_LABEL[r.source] || r.source}
              </span>
            </div>
            <div className="road-name">{r.name}</div>
            <div className="road-meta">
              <span>{r.active_legs} active leg(s)</span>
              <span>flood exposure {Math.round((r.flood_exposure || 0) * 100)}%</span>
            </div>
            {!r.blocked && r.closes_in_sim_min != null ? (
              <div className="road-chip src-flood" title="Forecast of the simulation's own closure rule (exposure ≥ 0.85 − blockage), not a hydraulic model">
                ⚠ floods in ~{r.closes_in_sim_min} min
              </div>
            ) : null}
            <div className="road-actions">
              {r.blocked ? (
                <button type="button" disabled={!!busy} onClick={() => act(r.road_id, "open")}>
                  ✅ Open
                </button>
              ) : (
                <button type="button" className="danger" disabled={!!busy} onClick={() => act(r.road_id, "block")}>
                  ⛔ Block
                </button>
              )}
              {r.operator ? (
                <button type="button" className="link-btn" disabled={!!busy} onClick={() => act(r.road_id, "clear")}>
                  Back to flood rule
                </button>
              ) : null}
              {busy === r.road_id ? <span className="muted">re-planning…</span> : null}
            </div>
          </div>
        ))}
      </div>
      {note ? <p className="hint control-note">{note}</p> : null}
      {log.length ? (
        <details className="road-log">
          <summary>Road changes this run ({log.length})</summary>
          <ul>
            {[...log].reverse().map((e, i) => (
              <li key={i}>
                <span className="muted">{formatTimeIST(e.at)}</span> · <b>{e.road_id}</b>{" "}
                {e.by === "flood" ? "closed by the flood rule" : e.cleared ? "handed back to the flood rule" : e.blocked ? "blocked by operator" : "opened by operator"}{" "}
                — {e.rerouted} leg(s) re-planned
                {e.no_open_road ? `, ${e.no_open_road} with no open road` : ""}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <p className="hint">
        A closed road is removed from the road graph. Every unit whose remaining route used it gets a new route at
        once (Yen candidates → simulated QAOA choice); a unit already driving continues from where it is. Opening a road
        re-plans any leg it makes at least 0.5 min faster. If no open road is left, the plan is kept and a red alert is
        raised — a straight line is never presented as a road.
      </p>
    </div>
  );
}

export default memo(RoadControlPanel);
