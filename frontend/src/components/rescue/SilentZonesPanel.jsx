import { memo, useState } from "react";
import { postJson } from "../../services/api.js";

/** F29 — modelled silent areas: the flood reached the phone towers, so people
 * there may not be able to call. `view` is state.silent_zones (null = this city
 * has no towers file yet → the feature is off and we say why). */
function SilentZonesPanel({ view, onState }) {
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  if (view === undefined) return null;
  if (view === null) {
    return (
      <p className="hint silent-off">
        Silent areas (phone towers lost to the flood): off — no tower data for this city yet. Add <code>OPENCELLID_TOKEN</code> to
        .env and run <code>python scripts/build_towers.py --city &lt;id&gt;</code>.
      </p>
    );
  }
  const zones = view.zones || [];
  async function patrol(z) {
    setBusy(z.zone_id);
    setNote("");
    try {
      const res = await postJson("/api/simulation/patrol", { zone_id: z.zone_id });
      onState?.(res);
      const p = res?.patrol;
      setNote(p ? `${p.unit} sent to the silent area near ${p.zone} (${p.km} km, ${p.minutes} min).` : "Patrol sent.");
    } catch (e) {
      setNote(`Patrol failed: ${e?.response?.data?.detail || e?.message || "error"}`);
    } finally {
      setBusy("");
    }
  }
  return (
    <div className="panel silent-panel">
      <div className="panel-head">
        <h3>Silent areas — phone towers lost to the flood</h3>
        <span className="badge sim">modelled</span>
      </div>
      <p className="hint">
        {view.towers_flooded} of {view.towers} towers under the flood rule. {view.coverage_source}. {view.attribution}
      </p>
      {zones.length ? (
        <ul className="silent-list">
          {zones.map((z) => (
            <li key={z.zone_id}>
              <b>Near {z.name}</b> · ~{z.area_km2} km² without a working tower{" "}
              {onState ? (
                <button type="button" disabled={!!busy} onClick={() => patrol(z)}>
                  🚑 Send patrol
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="hint">No silent area right now.</p>
      )}
      {note ? <p className="hint control-note">{note}</p> : null}
    </div>
  );
}

export default memo(SilentZonesPanel);
