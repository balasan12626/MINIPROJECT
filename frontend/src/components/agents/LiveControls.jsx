import { memo, useState } from "react";
import { overrideSimulation, sosSurge } from "../../services/api.js";
import { roadAction, roadChangeNote } from "../rescue/RoadControlPanel.jsx";

/** Edit the running simulation on the fly: rainfall, river, barrage stage,
 * flood probability, plus a 50-SOS surge. Every button is a real backend
 * call (POST /api/simulation/override or /sos/surge); the agents and the
 * notification centre react to the new state. */
const FIELDS = [
  { key: "rainfall_mm", label: "Rainfall (24 h)", unit: "cm", toApi: (v) => v * 10, fromState: (v) => v / 10, step: 0.5 },
  { key: "river_m", label: "Yamuna river level", unit: "m", toApi: (v) => v, fromState: (v) => v, step: 0.1 },
  { key: "dam_m", label: "Barrage (dam) stage", unit: "m", toApi: (v) => v, fromState: (v) => v, step: 0.1 },
  { key: "flood_probability", label: "Flood probability", unit: "%", toApi: (v) => v, fromState: (v) => v * 100, step: 1 },
];

const r1 = (v) => (typeof v === "number" ? Math.round(v * 10) / 10 : null);

function LiveControls({ last, current, overrides = {}, roads = [], onState, compact = false, city = null }) {
  const [draft, setDraft] = useState({});
  // F7: a rainfall-driven city has no river gauge; only Delhi has the upstream barrage.
  const hasRiver = !city || city.flood_driver !== "rainfall";
  const hasDam = !city || Boolean(city.has_upstream_dam);
  const riverName = city?.gauge?.river ? String(city.gauge.river).split("/").pop().trim() : "Yamuna";
  const fields = FIELDS.filter((f) => (f.key !== "river_m" || hasRiver) && (f.key !== "dam_m" || hasDam)).map((f) =>
    f.key === "river_m" ? { ...f, label: `${riverName} river level` } : f
  );
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");

  const now = {
    rainfall_mm: last?.rainfall_mm,
    river_m: last?.river_m,
    dam_m: last?.dam_m,
    flood_probability: current?.flood_probability ?? last?.flood_probability,
  };

  async function run(label, fn) {
    setBusy(label);
    setNote("");
    try {
      const res = await fn();
      onState?.(res);
      const p = res?.current?.flood_probability ?? res?.history?.[res.history.length - 1]?.flood_probability;
      setNote(`${label} — done. Flood probability now ${p != null ? `${(p * 100).toFixed(1)}%` : "—"} · ${res?.multi_agent?.tier_label || ""}`);
    } catch (e) {
      setNote(`${label} failed: ${e?.message || "error"}`);
    } finally {
      setBusy("");
    }
  }

  // F1: the open road that the most active route legs drive on right now.
  const busiest = roads.filter((r) => !r.blocked && r.active_legs > 0).sort((a, b) => b.active_legs - a.active_legs)[0];
  async function blockBusiest() {
    if (!busiest) return;
    setBusy(`Block ${busiest.road_id}`);
    setNote("");
    try {
      const res = await roadAction(busiest.road_id, "block");
      onState?.(res);
      setNote(roadChangeNote(res));
    } catch (e) {
      setNote(`Block ${busiest.road_id} failed: ${e?.message || "error"}`);
    } finally {
      setBusy("");
    }
  }

  const apply = (f) => {
    const v = Number(draft[f.key]);
    if (!Number.isFinite(v)) return;
    run(`${f.label} → ${v} ${f.unit}`, () => overrideSimulation({ [f.key]: f.toApi(v) }));
  };
  const clear = (f) => run(`${f.label} back to scenario`, () => overrideSimulation({ clear: [f.key] }));
  const bump = (f, delta) => {
    const base = typeof now[f.key] === "number" ? f.fromState(now[f.key]) : 0;
    const v = Math.max(0, base + delta);
    run(`${f.label} ${delta > 0 ? "+" : ""}${delta} ${f.unit}`, () => overrideSimulation({ [f.key]: f.toApi(v) }));
  };

  return (
    <div className={`panel live-controls ${compact ? "is-compact" : ""}`}>
      <div className="panel-head">
        <h3>Live controls — edit the running scenario</h3>
        {busy ? <span className="badge warn">{busy}…</span> : null}
      </div>
      <div className="quick-row">
        <button type="button" className="danger" disabled={!!busy} onClick={() => run("50 SOS surge", () => sosSurge(50))}>
          🆘 Add 50 SOS at once
        </button>
        <button type="button" disabled={!!busy} onClick={() => bump(FIELDS[0], 50)}>
          🌧️ Rainfall +50 cm
        </button>
        <button type="button" disabled={!!busy} onClick={() => run("Rainfall → 1 cm", () => overrideSimulation({ rainfall_mm: 10 }))}>
          🌤️ Rainfall to 1 cm
        </button>
        {hasDam ? (
          <>
            <button type="button" disabled={!!busy} onClick={() => bump(FIELDS[2], 2)}>
              🏞️ Barrage +2 m
            </button>
            <button type="button" disabled={!!busy} onClick={() => bump(FIELDS[2], -2)}>
              🏞️ Barrage −2 m
            </button>
          </>
        ) : null}
        <button
          type="button"
          disabled={!!busy || !busiest}
          title={busiest ? `${busiest.name}: ${busiest.active_legs} active route leg(s)` : "No open road is in use right now"}
          onClick={blockBusiest}
        >
          ⛔ Block busiest road{busiest ? ` (${busiest.road_id})` : ""}
        </button>
      </div>
      {!compact ? (
        <div className="control-grid">
          {fields.map((f) => {
            const cur = typeof now[f.key] === "number" ? r1(f.fromState(now[f.key])) : null;
            const edited = overrides?.[f.key] != null;
            return (
              <div key={f.key} className={`control-card ${edited ? "is-edited" : ""}`}>
                <span className="control-label">
                  {f.label}
                  {edited ? <em className="badge warn">edited</em> : null}
                </span>
                <b className="control-now">
                  {cur ?? "—"} <small>{f.unit}</small>
                </b>
                <div className="control-edit">
                  <input
                    type="number"
                    step={f.step}
                    placeholder={cur ?? ""}
                    value={draft[f.key] ?? ""}
                    onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                    aria-label={`New ${f.label} in ${f.unit}`}
                  />
                  <button type="button" className="primary" disabled={!!busy || draft[f.key] === "" || draft[f.key] == null} onClick={() => apply(f)}>
                    Set
                  </button>
                </div>
                <button type="button" className="link-btn" disabled={!!busy || !edited} onClick={() => clear(f)}>
                  Back to scenario value
                </button>
              </div>
            );
          })}
        </div>
      ) : null}
      {note ? <p className="hint control-note">{note}</p> : null}
      <p className="hint">
        Each change re-runs the flood model on the new values. Watch the bell 🔔 for the agents&apos; notifications.
        {!hasRiver ? ` ${city?.name || "This city"} is rainfall-driven (no river gauge modelled), so there is no river control.` : ""}
      </p>
    </div>
  );
}

export default memo(LiveControls);
