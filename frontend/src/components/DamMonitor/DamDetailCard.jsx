import { useEffect, useState } from "react";
import { useScenario } from "../../state/ScenarioContext.jsx";

const MCM_PER_TMC = 28.3168; // 1 TMC (thousand million cubic feet) in million m³
const M_PER_FT = 0.3048;

const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const fmt = (v, d = 2) => (isNum(v) ? v.toFixed(d) : "—");

/** Live-storage fill %, the backend's formula:
 * (level − dead storage) / (FRL − dead storage). Used only to preview an edit. */
function fillPct(level, frl, dead) {
  if (!isNum(level) || !isNum(frl)) return null;
  const d = isNum(dead) ? dead : 0;
  if (frl <= d) return null;
  return Math.max(0, Math.min(100, ((level - d) / (frl - d)) * 100));
}

/** Dams read on their own gauge (Mettur: feet, full = 120 ft) carry
 * gauge_unit / gauge_zero_m in the registry. m MSL ↔ gauge feet. */
function gaugeOf(d) {
  if (d?.gauge_unit !== "ft" || !isNum(d?.gauge_zero_m)) return null;
  return {
    full: d.gauge_full,
    toFt: (m) => (isNum(m) ? (m - d.gauge_zero_m) / M_PER_FT : null),
    toM: (ft) => d.gauge_zero_m + ft * M_PER_FT,
  };
}

function Spec({ label, value, unit, sub, hero = false }) {
  return (
    <div className={`dam-spec ${hero ? "is-hero" : ""}`}>
      <span className="dam-spec-label">{label}</span>
      <b className="dam-spec-value">
        {value}
        {unit && value !== "—" ? <small> {unit}</small> : null}
      </b>
      {sub ? <span className="dam-spec-sub">{sub}</span> : null}
    </div>
  );
}

/** The clicked dam: original registry figures (read-only) next to the two
 * values an operator may edit for the next run — reservoir level now and the
 * full reservoir level (sent as `capacity_override_m`). */
export default function DamDetailCard() {
  const ctx = useScenario();
  const d = ctx?.selectedDam || null;
  const gauge = gaugeOf(d);
  const [unit, setUnit] = useState(gauge ? "ft" : "m");
  useEffect(() => setUnit(gauge ? "ft" : "m"), [d?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!ctx) return null;
  const { dams, damId, setDamId, damLevel, damFrlOverride, patchInputs, running, isOutdated } = ctx;

  const origFrl = d?.full_reservoir_level_m;
  const dead = d?.dead_storage_level_m;
  const live = d?.live_capacity_mcm;
  const levelEdited = d && isNum(damLevel) && damLevel !== d.current_level_m;
  const frlEdited = damFrlOverride != null && damFrlOverride !== origFrl;
  const frlNow = frlEdited ? damFrlOverride : origFrl;
  const previewPct = fillPct(Number(damLevel), frlNow, dead);
  const edited = levelEdited || frlEdited;
  const ft = unit === "ft" && gauge;

  // Show / accept values in the chosen unit; always store m MSL.
  const shown = (m) => (ft ? gauge.toFt(m) : m);
  const setField = (field) => (e) => {
    const raw = e.target.value;
    if (raw === "") return patchInputs({ [field]: undefined });
    const n = Number(raw);
    patchInputs({ [field]: ft ? Math.round(gauge.toM(n) * 1000) / 1000 : n });
  };
  const inputVal = (m) => (isNum(m) ? Math.round(shown(m) * 100) / 100 : "");

  return (
    <section className="panel dam-detail" aria-label="Dam details">
      <div className="panel-head">
        <h3>Dam details</h3>
        {d?.figures_are_approximate ? <span className="badge sim">Public reference figures</span> : null}
      </div>

      <div className="dam-chip-row" role="listbox" aria-label="Choose a dam">
        {(dams || []).map((x) => (
          <button
            key={x.id}
            type="button"
            role="option"
            aria-selected={x.id === damId}
            className={`dam-chip ${x.id === damId ? "is-active" : ""}`}
            disabled={running}
            onClick={() => setDamId(x.id)}
          >
            {x.name}
            <small>{x.state}</small>
          </button>
        ))}
      </div>

      {!d ? (
        <p className="hint">Loading the dam registry…</p>
      ) : (
        <div className="dam-detail-grid">
          <div className="dam-detail-orig">
            <h4 className="dam-detail-title">
              {d.name} <span className="muted">· {d.river} · {d.state}</span>
            </h4>
            <p className="dam-detail-sub">Original values (dam registry)</p>
            <div className="dam-spec-grid">
              {gauge ? (
                <Spec
                  hero
                  label="Full capacity (dam gauge)"
                  value={fmt(gauge.full, 0)}
                  unit="ft"
                  sub={`FRL ${fmt(origFrl)} m MSL`}
                />
              ) : (
                <Spec
                  hero
                  label="Full reservoir level (FRL)"
                  value={fmt(origFrl)}
                  unit="m MSL"
                  sub={isNum(origFrl) ? `${fmt(origFrl / M_PER_FT, 0)} ft MSL` : undefined}
                />
              )}
              <Spec
                label="Total live capacity"
                value={fmt(live, 1)}
                unit="MCM"
                sub={isNum(live) ? `${fmt(live / MCM_PER_TMC, 2)} TMC` : undefined}
              />
              <Spec
                label="Level now"
                value={gauge ? fmt(gauge.toFt(d.current_level_m), 1) : fmt(d.current_level_m)}
                unit={gauge ? "ft" : "m MSL"}
                sub={gauge ? `${fmt(d.current_level_m)} m MSL` : `${fmt(d.current_level_m / M_PER_FT, 0)} ft MSL`}
              />
              <Spec
                label="Filled now"
                value={fmt(d.fill_percentage, 1)}
                unit="%"
                sub={
                  isNum(live) && isNum(d.fill_percentage)
                    ? `≈ ${fmt((d.fill_percentage / 100) * live, 0)} MCM stored`
                    : d.status
                }
              />
              <Spec
                label="Dead storage (MDDL)"
                value={gauge ? fmt(gauge.toFt(dead), 1) : fmt(dead)}
                unit={gauge ? "ft" : "m MSL"}
                sub={gauge ? `${fmt(dead)} m MSL` : undefined}
              />
              <Spec
                label="Normal level (historical)"
                value={gauge ? fmt(gauge.toFt(d.historical_normal_level_m), 1) : fmt(d.historical_normal_level_m)}
                unit={gauge ? "ft" : "m MSL"}
                sub={gauge ? `${fmt(d.historical_normal_level_m)} m MSL` : undefined}
              />
            </div>
            {d.capacity_note ? <p className="hint">{d.capacity_note}</p> : null}
            {gauge ? (
              <p className="hint">
                Gauge feet are converted with the dam&apos;s own anchor: 120 ft on the gauge = 240.79 m MSL.
              </p>
            ) : null}
            {d.downstream_region ? (
              <p className="hint">
                Downstream: <b>{d.downstream_region}</b>
              </p>
            ) : null}
          </div>

          <div className="dam-detail-edit">
            <div className="dam-edit-head">
              <p className="dam-detail-sub">Edit for the next run</p>
              {gauge ? (
                <div className="seg-control seg-small" role="radiogroup" aria-label="Units">
                  {[
                    ["ft", "ft (gauge)"],
                    ["m", "m MSL"],
                  ].map(([id, label]) => (
                    <button
                      key={id}
                      type="button"
                      role="radio"
                      aria-checked={unit === id}
                      className={unit === id ? "is-active" : ""}
                      onClick={() => setUnit(id)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
            <label className={levelEdited ? "field-changed" : ""}>
              <span>Reservoir level now ({ft ? "ft on gauge" : "m MSL"})</span>
              <input
                type="number"
                step="0.1"
                value={inputVal(damLevel)}
                disabled={running}
                onChange={setField("current_level_m")}
              />
            </label>
            <label className={frlEdited ? "field-changed" : ""}>
              <span>Full capacity level ({ft ? "ft on gauge" : "m MSL"})</span>
              <input
                type="number"
                step="0.1"
                min="0"
                value={inputVal(damFrlOverride ?? origFrl)}
                disabled={running}
                onChange={setField("capacity_override_m")}
              />
            </label>
            <div className="dam-fill-preview">
              <div className="dam-fill-bar" aria-hidden>
                <i style={{ width: `${previewPct ?? 0}%` }} />
              </div>
              <span>
                {previewPct == null ? "—" : `${previewPct.toFixed(1)}% filled`}
                <small className="muted"> preview · (level − MDDL) / (FRL − MDDL)</small>
              </span>
            </div>
            <div className="actions">
              <button
                type="button"
                disabled={running || !edited}
                onClick={() => patchInputs({ current_level_m: undefined, capacity_override_m: undefined })}
              >
                Reset to original
              </button>
            </div>
            <p className="hint">
              {edited
                ? isOutdated
                  ? "Edited. Click Re-run to apply these values."
                  : "Edited. These values are sent with the next run."
                : "Unchanged: the run uses the registry values."}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
