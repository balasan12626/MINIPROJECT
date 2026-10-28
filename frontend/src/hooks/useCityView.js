import { useEffect, useState } from "react";
import { fetchCityView } from "../services/api.js";

// Static per-city map data (GET /api/cities/{id}) — fetched once per city and
// shared by every map on the page; never part of the 1.2 s poll.
const cache = new Map();

export function useCityView(cityId) {
  const [view, setView] = useState(() => (cityId ? cache.get(cityId) || null : null));
  useEffect(() => {
    if (!cityId) {
      setView(null);
      return undefined;
    }
    if (cache.has(cityId)) {
      setView(cache.get(cityId));
      return undefined;
    }
    let alive = true;
    Promise.resolve()
      .then(() => fetchCityView(cityId))
      .then((v) => {
        cache.set(cityId, v);
        if (alive) setView(v);
      })
      .catch(() => alive && setView(null));
    return () => {
      alive = false;
    };
  }, [cityId]);
  return view;
}

const MAIN_ROADS = new Set(["motorway", "trunk", "primary"]);

/** Join live road status (per poll) with static geometry (per city). Real OSM
 * cities have hundreds of roads, so the MAP shows main roads plus any road that
 * is closed, operator-controlled or carrying an active route leg. */
export function roadsForMap(roadStatus, cityView) {
  const geo = cityView?.road_geometry || {};
  return (roadStatus || [])
    .filter(
      (r) =>
        !r.highway ||
        MAIN_ROADS.has(r.highway) ||
        r.blocked ||
        r.operator ||
        r.active_legs > 0 ||
        (r.closes_in_sim_min != null && r.closes_in_sim_min <= 30)
    )
    .map((r) => ({ ...r, segments: geo[r.road_id] || r.segments || [] }));
}
