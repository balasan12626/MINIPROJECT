import { memo } from "react";
import { useScenario } from "../../state/ScenarioContext.jsx";

const DISPATCH = [
  ["optimal", "Best overall (assignment)", "The waiting queue (in triage order) is matched to every free ambulance at once — Hungarian method, minimising vulnerability-weighted road minutes."],
  ["greedy", "Nearest free ambulance", "Each SOS gets the free ambulance with the shortest road time from where it is now."],
  ["first_free", "First free ambulance", "First free ambulance in the list, driving from where it really is (the fair baseline)."],
  ["nearest_depot", "Original rule (idealised)", "First free ambulance, launched from the depot nearest the person — ignores where the ambulance really is."],
  ["fair", "Fair vs fast (λ)", "Joint assignment over the whole waiting queue that trades road minutes for the waiting time of the longest-waiting group (λ = 0 is exactly Best overall). Measured trade-off: Algorithms tab."],
];

/** F7 — which city's real road network the run plans on. The list and every
 * number on a card come from GET /api/cities (backend/data/cities/*.json). */
function CityPicker() {
  const ctx = useScenario();
  if (!ctx) return null;
  const { cities = [], cityId, setCityId, running, dispatchPolicy, setDispatchPolicy, preposition, setPreposition, rainSource, setRainSource, warningCompliance, setWarningCompliance, crewRules, setCrewRules, fairLambda, setFairLambda, supplyOn, setSupplyOn, boatsCount, setBoatsCount, exposureModel, setExposureModel } = ctx;
  if (!cities.length) return null;
  const chosen = cities.find((c) => c.id === cityId);
  return (
    <section className="panel city-picker" aria-label="Choose city">
      <div className="panel-head">
        <h3>Choose city</h3>
        <span className="hint">Real OpenStreetMap road networks · {cities.length} cities</span>
      </div>
      <div className="city-grid">
        {cities.map((c) => (
          <button
            key={c.id}
            type="button"
            aria-pressed={c.id === cityId}
            disabled={running}
            className={`city-card ${c.id === cityId ? "active" : ""}`}
            onClick={() => setCityId(c.id)}
          >
            <strong>{c.name}</strong>
            <span className="muted">{c.state}</span>
            <span className={`badge ${c.flood_driver === "river" ? "live" : "sim"}`}>
              {c.flood_driver === "river"
                ? `River gauge: ${c.gauge?.station || "—"}${String(c.gauge?.source || "").startsWith("CWC") ? " (CWC)" : ""}`
                : "Rainfall-driven"}
            </span>
            <span className="city-counts">
              {c.counts?.junctions ?? "—"} junctions · {c.counts?.shelters ?? "—"} shelters · {c.counts?.depots ?? "—"} depots
            </span>
          </button>
        ))}
      </div>
      {chosen ? (
        <div className="hint city-why">
          <b>{chosen.name}:</b> {chosen.why}{" "}
          {chosen.flood_driver === "river"
            ? `Gauge ${chosen.gauge?.station} (${chosen.gauge?.river}) — warning ${chosen.gauge?.warning_level_m} m, danger ${chosen.gauge?.danger_level_m} m (${chosen.gauge?.source}${chosen.gauge?.retrieved_at ? `, retrieved ${chosen.gauge.retrieved_at}` : ""}).${chosen.gauge?.ml_note ? ` ${chosen.gauge.ml_note}.` : ""}`
            : `${chosen.gauge?.reason || "No river gauge modelled"} — the flood probability uses rainfall only (no river-stage term).`}{" "}
          <span className="muted">{chosen.attribution}</span>
        </div>
      ) : null}
      {setDispatchPolicy ? (
        <div className="ops-settings">
          <label>
            Ambulance dispatch
            <select value={dispatchPolicy} disabled={running} onChange={(e) => setDispatchPolicy(e.target.value)}>
              {DISPATCH.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="ops-check">
            <input type="checkbox" checked={Boolean(preposition)} disabled={running} onChange={(e) => setPreposition(e.target.checked)} />
            Pre-position idle ambulances near predicted hotspots
          </label>
          {setRainSource ? (
            <label className="ops-check">
              <input
                type="checkbox"
                checked={rainSource === "forecast"}
                disabled={running}
                onChange={(e) => setRainSource(e.target.checked ? "forecast" : "scenario")}
              />
              Use live rainfall forecast for {chosen?.name || "this city"} (Open-Meteo, next 48 h) instead of the scenario&apos;s rainfall
            </label>
          ) : null}
          {dispatchPolicy === "fair" && setFairLambda ? (
            <label>
              Fairness λ (road minutes per minute of group wait)
              <input type="number" min="0" max="20" step="0.5" value={fairLambda} disabled={running} onChange={(e) => setFairLambda(Number(e.target.value))} />
            </label>
          ) : null}
          {setCrewRules ? (
            <label className="ops-check">
              <input type="checkbox" checked={Boolean(crewRules)} disabled={running} onChange={(e) => setCrewRules(e.target.checked)} />
              Crew rules (assumed): 12 h driving → 8 h rest at the depot; 400 km → 20 min refuel
            </label>
          ) : null}
          {setSupplyOn ? (
            <label className="ops-check">
              <input type="checkbox" checked={Boolean(supplyOn)} disabled={running} onChange={(e) => setSupplyOn(e.target.checked)} />
              Food &amp; water supply runs (assumed fleet: 3 trucks from the depots; need at Sphere rates 15 L + 2,100 kcal / person / day)
            </label>
          ) : null}
          {setBoatsCount ? (
            <label className="ops-check">
              Rescue boats for cut-off people (assumed fleet): {boatsCount || 0} {boatsCount ? "boats" : "(off)"}
              <input
                type="range"
                min="0"
                max="6"
                step="1"
                value={boatsCount || 0}
                disabled={running}
                onChange={(e) => setBoatsCount(Number(e.target.value))}
                aria-label="Rescue boats (assumed)"
              />
            </label>
          ) : null}
          {setWarningCompliance ? (
            <label className="ops-check">
              Early-warning compliance (assumed, not measured): {Math.round((warningCompliance || 0) * 100)}%
              <input
                type="range"
                min="0"
                max="0.8"
                step="0.1"
                value={warningCompliance || 0}
                disabled={running}
                onChange={(e) => setWarningCompliance(Number(e.target.value))}
                aria-label="Early-warning compliance (assumed)"
              />
            </label>
          ) : null}
          {setExposureModel ? (
            <div className="ops-check" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span>Road flood risk model (F26):</span>
              <div className="ask-chips" style={{ marginTop: 2, display: "flex", gap: 8 }}>
                <label className={`radio-pill ${exposureModel === "distance" ? "active" : ""}`}>
                  <input
                    type="radio"
                    name="exposure-model"
                    checked={exposureModel === "distance"}
                    disabled={running}
                    onChange={() => setExposureModel("distance")}
                  />
                  v1 (distance to water)
                </label>
                <label className={`radio-pill ${exposureModel === "hand" ? "active" : ""}`}>
                  <input
                    type="radio"
                    name="exposure-model"
                    checked={exposureModel === "hand"}
                    disabled={running}
                    onChange={() => setExposureModel("hand")}
                  />
                  v2 (HAND: height above drainage)
                </label>
              </div>
            </div>
          ) : null}
          <p className="hint">{DISPATCH.find(([id]) => id === dispatchPolicy)?.[2]}</p>
        </div>
      ) : null}
    </section>
  );
}

export default memo(CityPicker);
