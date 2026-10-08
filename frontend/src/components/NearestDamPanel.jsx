import { useEffect, useMemo, useState } from "react";
import { fetchDams } from "../services/api.js";
import { nearestDam } from "../utils/geo.js";
import { useScenario } from "../state/ScenarioContext.jsx";

/** Nearest reservoir in the REAL dam registry (GET /api/dams) to the FLOOD
 * REGION the evacuation engine simulates (GET /api/dams -> evacuation_region,
 * derived from backend/services/seed.py ZONES). Real haversine distance over
 * real coordinates — no fabricated metric, and never relative to whatever dam
 * happens to be selected.
 *
 * `focusDam` is accepted for backwards compatibility and only used to say
 * whether the run's reservoir is that nearest dam. */
export default function NearestDamPanel({ focusDam = null, region: regionProp = null }) {
  const ctx = useScenario();
  const [fallback, setFallback] = useState(null);

  // Standalone use (outside the /simulation provider): read the registry once.
  useEffect(() => {
    if (ctx) return undefined;
    let alive = true;
    fetchDams()
      .then((res) => alive && setFallback(res || null))
      .catch(() => alive && setFallback({ dams: [], evacuation_region: null }));
    return () => {
      alive = false;
    };
  }, [ctx]);

  const registry = ctx ? ctx.dams : fallback?.dams || [];
  const region = regionProp || ctx?.currentRun?.run?.region || ctx?.evacuationRegion || fallback?.evacuation_region || null;

  const result = useMemo(() => {
    if (!region) return null;
    const list = (registry || []).map((d) => ({ ...d, latitude: Number(d.lat), longitude: Number(d.lon) }));
    return nearestDam({ lat: Number(region.lat), lon: Number(region.lon) }, list);
  }, [registry, region]);

  return (
    <div className="panel">
      <h2>NEAREST DAM TO FLOOD REGION</h2>
      {result ? (
        <>
          <div className="metric"><span>Flood region</span><b>{region.name}</b></div>
          <div className="metric"><span>Dam</span><b>{result.dam.name}</b></div>
          <div className="metric"><span>State</span><b>{result.dam.state}</b></div>
          <div className="metric"><span>River</span><b>{result.dam.river}</b></div>
          <div className="metric"><span>Distance</span><b>{result.distanceKm.toFixed(1)} km</b></div>
          <p className="hint">
            Registry of {registry.length} reservoirs; region centre {Number(region.lat).toFixed(4)}, {Number(region.lon).toFixed(4)}.
            {String(result.dam.river || "").toLowerCase() !== String(region.river || "").toLowerCase()
              ? ` No registry reservoir is on the ${region.river}; this dam's level (m MSL) is not the Yamuna barrage stage.`
              : ""}
            {focusDam?.id ? (focusDam.id === result.dam.id ? " This is the run's reservoir." : ` The run used ${focusDam.name}.`) : ""}
          </p>
        </>
      ) : (
        <p className="hint">Nearest-dam data unavailable (dam registry or flood region not loaded).</p>
      )}
    </div>
  );
}
