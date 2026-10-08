/** Mirrors backend/utils/geo.py::haversine_km exactly — same formula, real
 * math on real coordinates, no fabricated distances. */
export function haversineKm(lat1, lon1, lat2, lon2) {
  const r = 6371.0;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

/** Nearest entry in `dams` (each with latitude/longitude) to `point` {lat, lon}. */
export function nearestDam(point, dams = []) {
  if (!point || !Number.isFinite(point.lat) || !Number.isFinite(point.lon)) return null;
  let best = null;
  let bestDistanceKm = Infinity;
  for (const dam of dams) {
    if (!Number.isFinite(dam.latitude) || !Number.isFinite(dam.longitude)) continue;
    const distanceKm = haversineKm(point.lat, point.lon, dam.latitude, dam.longitude);
    if (distanceKm < bestDistanceKm) {
      bestDistanceKm = distanceKm;
      best = dam;
    }
  }
  return best ? { dam: best, distanceKm: bestDistanceKm } : null;
}
