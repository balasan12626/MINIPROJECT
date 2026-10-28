"""F20 — Validate road closures against satellite / crowdsourced flood maps.

Ground truth (in order of preference):
  1. UNOSAT FL20151123IND S1_20151124_Flood.shp — Sentinel-1 satellite, 24 Nov 2015
     (unosat-maps.web.cern.ch/unosat-maps/IN/FL20151123IND/FL20151123IND_shp.zip,
      Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported)
  2. OSM-India crowdsourced flooded-streets GeoJSON, December 2015
     (github.com/osm-in/flood-map, CC0)

The script uses whichever source is available on disk.

For each road centroid the classification is:
  observed_flooded  = centroid falls inside any UNOSAT flood polygon
                      (Jordan curve theorem ray-cast, pure Python, no GIS dependency)
                      OR within SNAP_KM of any crowdsourced flooded-street point
  predicted_closed  = flood_exposure >= 0.85 − blockage
                      (same rule as backend/services/ops_sim.roads_at)

Outputs:
  models/closure_validation_v1_chennai.json — metrics, per-class breakdown,
                                               threshold sweep, metadata

Usage:
    python scripts/validate_closures.py
    python scripts/validate_closures.py --city chennai --blockage 0.35
    python scripts/validate_closures.py --source osm   # force OSM fallback
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CITIES_DIR = ROOT / "backend" / "data" / "cities"
MODELS_DIR = ROOT / "models"
DATA_DIR = ROOT / "dataset"

UNOSAT_DIR = DATA_DIR / "unosat_fl20151123ind"
UNOSAT_SHP = UNOSAT_DIR / "S1_20151124_Flood.shp"

OSM_GEOJSON = DATA_DIR / "chennai-flooded-streets-Dec2.geojson"

# Snap radius for OSM-point fallback
SNAP_KM = 0.35

CITATION_UNOSAT = {
    "source": "UNOSAT FL20151123IND — Sentinel-1 satellite flood extent, 24 November 2015",
    "dataset": "Geodata of Flood Waters Over Chennai Area, Tamil Nadu State, India",
    "repository": "https://unosat-maps.web.cern.ch/unosat-maps/IN/FL20151123IND/",
    "hdx": "https://data.humdata.org/dataset/geodata-of-flood-waters-over-chennai-area-tamil-nadu-state-india-december-04-2015",
    "file": "S1_20151124_Flood.shp",
    "licence": "Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported",
    "event": "Chennai 2015 floods (November–December 2015)",
    "note": (
        "Preliminary satellite assessment; urban areas and vegetation may mask flood "
        "signature causing underestimation. Point-in-polygon with Jordan curve theorem."
    ),
}

CITATION_OSM = {
    "source": "OSM-India crowdsourced flooded-streets layer — Chennai, December 2015",
    "repository": "https://github.com/osm-in/flood-map",
    "file": "data/chennai-flooded-streets-Dec2.geojson",
    "licence": "CC0 / OpenStreetMap contributors",
    "event": "Chennai 2015 floods (November–December 2015)",
    "note": (
        "Crowdsourced map of streets reported flooded by volunteers during the event. "
        f"Roads within {SNAP_KM} km of a flooded-street coordinate = observed flooded."
    ),
}


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def point_in_polygon(px: float, py: float, ring: list[tuple[float, float]]) -> bool:
    """Jordan curve theorem ray-casting for (lon, lat) = (x, y) ring."""
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-15) + xi):
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------------------
# UNOSAT shapefile reader (pure-Python, no external GIS dependency)
# ---------------------------------------------------------------------------

def _read_ring(data: bytes, off: int, n: int) -> list[tuple[float, float]]:
    """Read n (x, y) doubles from data starting at off."""
    pts = struct.unpack_from(f"<{2*n}d", data, off)
    return [(pts[2 * i], pts[2 * i + 1]) for i in range(n)]


def read_unosat_polygons(shp_path: Path) -> list[list[list[tuple[float, float]]]]:
    """
    Parse the ESRI Shapefile (type 5 = Polygon) without external libraries.
    Returns a list of polygons; each polygon is a list of rings (outer + holes).
    All coordinates are (lon, lat) = (x, y) in WGS-84 decimal degrees.
    """
    polygons: list[list[list[tuple[float, float]]]] = []
    with open(shp_path, "rb") as f:
        f.read(100)  # skip file header
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            content_len = struct.unpack(">i", hdr[4:])[0]  # 16-bit words
            data = f.read(content_len * 2)
            if len(data) < content_len * 2:
                break
            shp_type = struct.unpack_from("<i", data, 0)[0]
            if shp_type != 5:  # not Polygon
                continue
            # 4-byte type + 32-byte bbox + 4 num_parts + 4 num_points
            num_parts = struct.unpack_from("<i", data, 36)[0]
            num_points = struct.unpack_from("<i", data, 40)[0]
            parts_off = 44
            pts_off = parts_off + 4 * num_parts
            part_starts = list(struct.unpack_from(f"<{num_parts}i", data, parts_off))
            part_starts.append(num_points)

            rings: list[list[tuple[float, float]]] = []
            for k in range(num_parts):
                start = part_starts[k]
                end = part_starts[k + 1]
                ring = _read_ring(data, pts_off + 16 * start, end - start)
                rings.append(ring)
            polygons.append(rings)
    return polygons


class PolygonIndex:
    """Grid-partitioned bounding-box index over UNOSAT flood polygons.

    For each query point we only check polygons whose bounding box covers
    the cell(s) the point falls in — typically a tiny fraction of all 88k polygons.
    """

    def __init__(
        self,
        polygons: list[list[list[tuple[float, float]]]],
        cell_deg: float = 0.05,
    ) -> None:
        self.cell = cell_deg
        # Store (minx, miny, maxx, maxy, poly) tuples
        self._entries: list[tuple[float, float, float, float, list]] = []
        # Grid: cell → list of entry indices
        self._grid: dict[tuple[int, int], list[int]] = {}

        for poly in polygons:
            if not poly:
                continue
            outer = poly[0]
            xs = [p[0] for p in outer]
            ys = [p[1] for p in outer]
            minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
            idx = len(self._entries)
            self._entries.append((minx, miny, maxx, maxy, poly))

            # Register in every grid cell the bbox overlaps
            ci0 = int(miny // cell_deg)
            ci1 = int(maxy // cell_deg)
            cj0 = int(minx // cell_deg)
            cj1 = int(maxx // cell_deg)
            for ci in range(ci0, ci1 + 1):
                for cj in range(cj0, cj1 + 1):
                    self._grid.setdefault((ci, cj), []).append(idx)

    def contains(self, lon: float, lat: float) -> bool:
        """Return True if (lon, lat) is inside any flood polygon."""
        ci = int(lat // self.cell)
        cj = int(lon // self.cell)
        candidates = self._grid.get((ci, cj))
        if not candidates:
            return False
        for idx in candidates:
            minx, miny, maxx, maxy, poly = self._entries[idx]
            if lon < minx or lon > maxx or lat < miny or lat > maxy:
                continue
            outer = poly[0]
            if point_in_polygon(lon, lat, outer):
                in_hole = False
                for ring in poly[1:]:
                    if point_in_polygon(lon, lat, ring):
                        in_hole = True
                        break
                if not in_hole:
                    return True
        return False



# ---------------------------------------------------------------------------
# OSM GeoJSON fallback: bucket grid
# ---------------------------------------------------------------------------

def load_flooded_points(geojson_path: Path) -> list[tuple[float, float]]:
    with open(geojson_path, "r", encoding="utf-8") as f:
        fc = json.load(f)
    points: list[tuple[float, float]] = []
    for feat in fc.get("features", []):
        geom = feat.get("geometry") or {}
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])
        if gtype == "LineString":
            for c in coords:
                if len(c) >= 2:
                    points.append((c[1], c[0]))  # (lat, lon)
        elif gtype == "MultiLineString":
            for line in coords:
                for c in line:
                    if len(c) >= 2:
                        points.append((c[1], c[0]))
    return points


class BucketGrid:
    def __init__(self, points: list[tuple[float, float]], cell_deg: float = 0.01) -> None:
        self.cell = cell_deg
        self.grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
        for p in points:
            key = self._key(p[0], p[1])
            self.grid.setdefault(key, []).append(p)

    def _key(self, lat: float, lon: float) -> tuple[int, int]:
        return (int(lat // self.cell), int(lon // self.cell))

    def nearest_km(self, lat: float, lon: float, radius_deg: float = 0.05) -> float:
        c = self.cell
        n_cells = max(1, math.ceil(radius_deg / c))
        ki, kj = int(lat // c), int(lon // c)
        best = float("inf")
        for di in range(-n_cells, n_cells + 1):
            for dj in range(-n_cells, n_cells + 1):
                bucket = self.grid.get((ki + di, kj + dj))
                if not bucket:
                    continue
                for p in bucket:
                    d = haversine_km(lat, lon, p[0], p[1])
                    if d < best:
                        best = d
        return best


# ---------------------------------------------------------------------------
# Classification & metrics
# ---------------------------------------------------------------------------

def classify_roads(
    roads: list[dict[str, Any]],
    index: PolygonIndex | None,
    grid: BucketGrid | None,
    snap_km: float,
    blockage: float,
) -> list[dict[str, Any]]:
    results = []
    for r in roads:
        lat, lon = float(r["lat"]), float(r["lon"])
        expo = float(r.get("flood_exposure") or 0.0)
        hw = r.get("highway") or "unknown"
        road_id = r.get("road_id", "")

        if index is not None:
            observed = index.contains(lon, lat)
        elif grid is not None:
            observed = grid.nearest_km(lat, lon, radius_deg=0.06) <= snap_km
        else:
            observed = False

        predicted = expo >= (0.85 - blockage)

        results.append({
            "road_id": road_id,
            "highway": hw,
            "lat": lat,
            "lon": lon,
            "flood_exposure": expo,
            "observed_flooded": observed,
            "predicted_closed": predicted,
        })
    return results


def compute_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(1 for r in results if r["observed_flooded"] and r["predicted_closed"])
    fp = sum(1 for r in results if not r["observed_flooded"] and r["predicted_closed"])
    fn = sum(1 for r in results if r["observed_flooded"] and not r["predicted_closed"])
    tn = sum(1 for r in results if not r["observed_flooded"] and not r["predicted_closed"])

    precision = tp / (tp + fp) if (tp + fp) > 0 else None
    recall = tp / (tp + fn) if (tp + fn) > 0 else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision is not None and recall is not None and (precision + recall) > 0
          else None)

    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "observed_flooded": tp + fn,
        "predicted_closed": tp + fp,
        "total_roads": len(results),
    }


def metrics_by_class(results: list[dict[str, Any]]) -> dict[str, Any]:
    classes: dict[str, list] = {}
    for r in results:
        hw = r.get("highway", "unknown")
        classes.setdefault(hw, []).append(r)
    out = {}
    for hw, recs in sorted(classes.items()):
        m = compute_metrics(recs)
        out[hw] = {
            "count": m["total_roads"],
            "observed_flooded": m["observed_flooded"],
            "precision": m["precision"],
            "recall": m["recall"],
            "f1": m["f1"],
        }
    return out


def threshold_sweep(
    roads: list[dict[str, Any]],
    index: PolygonIndex | None,
    grid: BucketGrid | None,
    snap_km: float,
) -> list[dict[str, Any]]:
    sweep = []
    for b_int in range(0, 75, 5):
        b = b_int / 100.0
        results = classify_roads(roads, index, grid, snap_km, b)
        m = compute_metrics(results)
        sweep.append({
            "blockage": round(b, 2),
            "precision": m["precision"],
            "recall": m["recall"],
            "f1": m["f1"],
            "predicted_closed": m["predicted_closed"],
            "observed_flooded": m["observed_flooded"],
        })
    return sweep


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def validate_city(
    city: str,
    blockage: float,
    snap_km: float,
    source: str = "auto",
) -> dict[str, Any]:
    city_path = CITIES_DIR / f"{city}.json"
    if not city_path.exists():
        raise FileNotFoundError(f"City file not found: {city_path}")

    with open(city_path, "r", encoding="utf-8") as f:
        city_data = json.load(f)
    roads = city_data.get("roads", [])
    print(f"Loaded {len(roads)} roads from {city_path.name}")

    index: PolygonIndex | None = None
    grid: BucketGrid | None = None
    citation: dict[str, Any]
    used_source: str

    use_unosat = (source == "auto" and UNOSAT_SHP.exists()) or source == "unosat"

    if use_unosat and UNOSAT_SHP.exists():
        print(f"Reading UNOSAT satellite polygons from {UNOSAT_SHP.name} …")
        polygons = read_unosat_polygons(UNOSAT_SHP)
        print(f"  {len(polygons)} flood polygons loaded")
        print("  Building spatial index …")
        index = PolygonIndex(polygons)
        citation = CITATION_UNOSAT
        used_source = "unosat_satellite"
    elif OSM_GEOJSON.exists():
        print(f"Loading OSM crowdsourced ground truth from {OSM_GEOJSON.name} …")
        flooded_pts = load_flooded_points(OSM_GEOJSON)
        print(f"  {len(flooded_pts)} flooded-street coordinate points")
        grid = BucketGrid(flooded_pts)
        citation = CITATION_OSM
        used_source = "osm_crowdsource"
    else:
        raise FileNotFoundError(
            "No ground-truth data found.\n"
            f"  Expected: {UNOSAT_SHP}\n"
            f"  Or:       {OSM_GEOJSON}\n"
            "Download OSM data first (it is fetched automatically on first run)."
        )

    print(f"Classifying roads at blockage={blockage} …")
    results = classify_roads(roads, index, grid, snap_km, blockage)
    metrics = compute_metrics(results)
    by_class = metrics_by_class(results)
    print("Sweeping thresholds …")
    sweep = threshold_sweep(roads, index, grid, snap_km)
    best_row = max(sweep, key=lambda r: r["f1"] or 0)

    output: dict[str, Any] = {
        "city": city,
        "event": "Chennai 2015 floods (November–December 2015)",
        "ground_truth_source": used_source,
        "ground_truth": citation,
        "snap_km": snap_km if used_source == "osm_crowdsource" else None,
        "default_blockage": blockage,
        "metrics_at_default_blockage": metrics,
        "metrics_by_road_class": by_class,
        "threshold_sweep": sweep,
        "best_f1": {
            "blockage": best_row["blockage"],
            "f1": best_row["f1"],
            "precision": best_row["precision"],
            "recall": best_row["recall"],
        },
        "notes": [
            f"Ground truth: {used_source}.",
            f"Closure rule: flood_exposure >= 0.85 - blockage (same as live engine in ops_sim.roads_at).",
            f"Threshold sweep is reported, not tuned — precision/recall measured at each blockage.",
            f"Total roads in {city} network: {len(roads)}. Observed-flooded: {metrics['observed_flooded']}.",
            f"Best measured F1={best_row['f1']} at blockage={best_row['blockage']} "
            f"(Precision={best_row['precision']}, Recall={best_row['recall']}).",
        ],
    }

    out_path = MODELS_DIR / f"closure_validation_v1_{city}.json"
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved → {out_path}")
    print(f"  Default blockage {blockage:.2f}: "
          f"Precision={metrics['precision']}, Recall={metrics['recall']}, F1={metrics['f1']}")
    print(f"  Best F1 {best_row['f1']} at blockage {best_row['blockage']}")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F20 — validate road closures against flood map")
    parser.add_argument("--city", default="chennai", help="City id (default: chennai)")
    parser.add_argument("--blockage", type=float, default=0.35,
                        help="Rainfall blockage level 0–0.7 for default metrics (default 0.35)")
    parser.add_argument("--snap_km", type=float, default=SNAP_KM,
                        help=f"Snap radius in km for OSM fallback (default {SNAP_KM})")
    parser.add_argument("--source", choices=["auto", "unosat", "osm"], default="auto",
                        help="Which ground truth to use (default: auto = UNOSAT if available)")
    args = parser.parse_args()
    validate_city(args.city, args.blockage, args.snap_km, args.source)
