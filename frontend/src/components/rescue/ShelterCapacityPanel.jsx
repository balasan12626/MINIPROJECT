import { memo, useState } from "react";
import { setShelter } from "../../services/api.js";

const pct = (part, whole) => (whole > 0 ? Math.max(0, Math.min(100, (part / whole) * 100)) : 0);

/** Ask the backend to close / reopen / resize / reset a shelter (F2). */
/** F27: how a shelter's seeded capacity was made. */
export function capacitySourceText(s) {
  const d = s.capacity_detail;
  if (String(s.capacity_source).startsWith("Sphere") && d) {
    return `Capacity: ${Math.round(d.floor_area_m2).toLocaleString("en-IN")} m² floor (${d.buildings} OSM building(s); ${d.levels_source}) × ${d.usable_share} usable (assumed) ÷ ${d.m2_per_person} m² per person (Sphere 2018)`;
  }
  return `Capacity: ${s.capacity_source}`;
}

export async function shelterAction(name, action, capacity) {
  if (action === "clear") return setShelter({ name, clear: true });
  if (action === "capacity") return setShelter({ name, capacity: Number(capacity) });
  return setShelter({ name, closed: action === "close" });
}

export function shelterChangeNote(res) {
  const ch = res?.shelter_change;
  if (!ch) return "Done.";
  const none = ch.no_seats ? ` · ${ch.no_seats} group(s) have no shelter with free seats (red alert)` : "";
  return `${ch.name}: ${ch.cleared ? "reset to the seeded capacity" : ch.action} — ${ch.moved} group(s) moved${none}.`;
}

/** Live shelter seats, as the shelter allocator sees them.
 *
 * Source: sim.shelter_allocation (backend person_ops.shelter_allocation_board),
 * the same arithmetic the allocator uses to pick a shelter:
 *   seats left = capacity − baseline occupancy − people allocated this run.
 * The bar stacks baseline | delivered this run | still incoming | free; the
 * baseline (registry) and this run's numbers are never blended.
 * With `onState`, each shelter gets Close / Reopen / capacity / Reset controls. */
function ShelterCapacityPanel({ allocation = [], onState = null }) {
  const [editing, setEditing] = useState("");
  const [capDraft, setCapDraft] = useState("");
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");

  async function act(name, action) {
    setBusy(name);
    setNote("");
    try {
      const res = await shelterAction(name, action, capDraft);
      onState?.(res);
      setNote(shelterChangeNote(res));
      if (action !== "capacity") setEditing("");
    } catch (e) {
      setNote(`Failed: ${e?.response?.data?.detail || e?.message || "error"}`);
    } finally {
      setBusy("");
    }
  }

  const totals = allocation.reduce(
    (t, s) => ({
      capacity: t.capacity + s.capacity,
      left: t.left + s.seats_left,
      allocated: t.allocated + s.allocated_this_run,
      delivered: t.delivered + s.delivered_this_run,
      closed: t.closed + (s.closed ? 1 : 0),
    }),
    { capacity: 0, left: 0, allocated: 0, delivered: 0, closed: 0 }
  );
  const sorted = [...allocation].sort((a, b) => b.allocated_this_run - a.allocated_this_run || a.name.localeCompare(b.name));

  return (
    <div className="panel shelter-cap-panel">
      <div className="panel-head">
        <h3>Shelter capacity — live</h3>
        <span className="fleet-summary">
          <span className="badge live">{totals.left.toLocaleString("en-IN")} seats free</span>
          <span className="badge sim">{totals.allocated} allocated this run</span>
          <span className="badge">{totals.delivered} delivered</span>
          {totals.closed ? <span className="badge warn">🚫 {totals.closed} closed</span> : null}
        </span>
      </div>
      {!allocation.length ? (
        <p className="hint">Shelter seats appear once the run starts.</p>
      ) : (
        <>
          <div className="shelter-cap-list">
            {sorted.map((s) => {
              const incoming = Math.max(0, s.allocated_this_run - s.delivered_this_run);
              return (
                <div
                  key={s.name}
                  className={`shelter-cap-row ${s.allocated_this_run ? "is-used" : ""} ${s.closed ? "is-closed" : ""}`}
                >
                  <div className="shelter-cap-head">
                    <b>
                      {s.name}
                      {s.closed ? <span className="road-chip src-operator"> 🚫 Closed</span> : null}
                    </b>
                    <span className="muted">
                      {s.closed ? "0 free" : `${s.seats_left.toLocaleString("en-IN")} free`} /{" "}
                      {s.capacity.toLocaleString("en-IN")}
                      {s.capacity !== s.base_capacity && s.base_capacity != null ? ` (was ${s.base_capacity})` : ""}
                    </span>
                  </div>
                  {s.capacity_source ? <p className="hint shelter-cap-source">{capacitySourceText(s)}</p> : null}
                  <div className="stack-bar" role="img" aria-label={`${s.name}: ${s.utilisation_pct}% used`}>
                    <i className="seg-base" style={{ width: `${pct(s.baseline_occupancy, s.capacity)}%` }} />
                    <i className="seg-done" style={{ width: `${pct(s.delivered_this_run, s.capacity)}%` }} />
                    <i className="seg-run" style={{ width: `${pct(incoming, s.capacity)}%` }} />
                  </div>
                  <div className="shelter-cap-meta">
                    <span>{s.utilisation_pct ?? "—"}% used</span>
                    {s.allocated_this_run || s.moved_away ? (
                      <span>
                        +{s.allocated_this_run} this run · {s.incoming} incoming · {s.delivered_this_run}{" "}
                        {s.closed ? "arrived before closing" : "arrived"}
                        {s.moved_away ? ` · ${s.moved_away} moved away` : ""}
                      </span>
                    ) : (
                      <span className="muted">not used this run</span>
                    )}
                  </div>
                  {onState ? (
                    <div className="road-actions">
                      {editing === s.name ? (
                        <>
                          {s.closed ? (
                            <button type="button" disabled={!!busy} onClick={() => act(s.name, "open")}>
                              ✅ Reopen
                            </button>
                          ) : (
                            <button type="button" className="danger" disabled={!!busy} onClick={() => act(s.name, "close")}>
                              🚫 Close
                            </button>
                          )}
                          <input
                            type="number"
                            min="0"
                            aria-label={`${s.name} capacity`}
                            className="shelter-cap-input"
                            value={capDraft}
                            onChange={(e) => setCapDraft(e.target.value)}
                          />
                          <button
                            type="button"
                            disabled={!!busy || capDraft === "" || Number(capDraft) < 0}
                            onClick={() => act(s.name, "capacity")}
                          >
                            Set capacity
                          </button>
                          {s.operator ? (
                            <button type="button" className="link-btn" disabled={!!busy} onClick={() => act(s.name, "clear")}>
                              Reset
                            </button>
                          ) : null}
                          <button type="button" className="link-btn" onClick={() => setEditing("")}>
                            Done
                          </button>
                          {busy === s.name ? <span className="muted">re-allocating…</span> : null}
                        </>
                      ) : (
                        <button
                          type="button"
                          className="link-btn"
                          onClick={() => {
                            setEditing(s.name);
                            setCapDraft(String(s.capacity));
                          }}
                        >
                          ✏️ Edit
                        </button>
                      )}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
          {note ? <p className="hint control-note">{note}</p> : null}
          <div className="stack-legend">
            <span>
              <i className="seg-base" /> Already in shelter (registry)
            </span>
            <span>
              <i className="seg-done" /> Delivered this run
            </span>
            <span>
              <i className="seg-run" /> Allocated, still incoming
            </span>
            <span>
              <i className="seg-free" /> Free seats
            </span>
          </div>
          <p className="hint">
            Each SOS is allocated to the nearest open shelter that has seats for the whole group and an open road. Closing a
            shelter (or cutting its capacity, newest allocations first) moves every group still heading there; a unit
            already carrying a group turns from where it is. Groups already delivered stay counted where they arrived.
          </p>
        </>
      )}
    </div>
  );
}

export default memo(ShelterCapacityPanel);
