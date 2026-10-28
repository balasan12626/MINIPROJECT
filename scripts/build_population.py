"""F19 — fill each OSM city zone's `population` from WorldPop.

    python scripts/build_population.py --city patna      (or --all)

Zones are OSM points (named suburbs), not polygons, so the people counted for a
zone are the WorldPop 2020 population summed over a circle of ZONE_RADIUS_KM
around the point — stated in `population_method`. Source: WorldPop Global
Project Population (unconstrained 100 m grid, 2020) via the WorldPop stats API
(api.worldpop.org/v1/services/stats, dataset `wpgppop`). Nothing is guessed: a
zone whose request fails keeps `population: null` and says why.
No new dependency (httpx is already used by the backend).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CITY_DIR = ROOT / "backend" / "data" / "cities"
API = "https://api.worldpop.org/v1/services/stats"
DATASET, YEAR = "wpgppop", 2020
ZONE_RADIUS_KM = 1.0
SOURCE = {
    "dataset": "WorldPop Global Project Population, unconstrained 100 m (wpgppop)",
    "year": YEAR,
    "url": "https://www.worldpop.org/project/categories?id=3",
    "api": API,
    "licence": "CC BY 4.0 (WorldPop, www.worldpop.org)",
}
METHOD = f"sum of the WorldPop {YEAR} grid over a {ZONE_RADIUS_KM:g} km circle around the zone's OSM point (zones have no polygon)"


def circle(lat: float, lon: float, r_km: float, n: int = 32) -> dict:
    pts = []
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        pts.append([round(lon + r_km / (111.32 * math.cos(math.radians(lat))) * math.cos(a), 6),
                    round(lat + r_km / 110.574 * math.sin(a), 6)])
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [pts]}}]}


def zone_population(lat: float, lon: float, client: httpx.Client) -> float:
    params = {"dataset": DATASET, "year": YEAR, "geojson": json.dumps(circle(lat, lon, ZONE_RADIUS_KM)), "runasync": "false"}
    last = None
    for attempt in range(3):
        try:
            r = client.get(API, params=params)
            r.raise_for_status()
            body = r.json()
            if body.get("error"):
                raise RuntimeError(body.get("error_message") or "WorldPop error")
            return float(body["data"]["total_population"])
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"WorldPop stats failed: {last}")


def fill_city(cid: str, client: httpx.Client) -> dict:
    path = CITY_DIR / f"{cid}.json"
    city = json.loads(path.read_text(encoding="utf-8"))
    for z in city["zones"]:
        try:
            z["population"] = int(round(zone_population(float(z["lat"]), float(z["lon"]), client)))
            z["population_source"] = SOURCE
            z["population_method"] = METHOD
            z.pop("population_missing_reason", None)
        except Exception as e:  # noqa: BLE001 — unknown stays null, with the reason
            z["population"] = None
            z["population_missing_reason"] = str(e)[:200]
        print(f"  [{cid}] {z['name']}: {z['population']}", flush=True)
    path.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    return city


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--city")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args(argv)
    ids = sorted(p.stem for p in CITY_DIR.glob("*.json") if "." not in p.stem) if args.all else [args.city]
    if not ids or ids == [None]:
        ap.error("--city or --all")
    with httpx.Client(timeout=90) as client:
        for cid in ids:
            c = fill_city(cid, client)
            filled = [z["population"] for z in c["zones"] if z["population"] is not None]
            print(f"[{cid}] {len(filled)}/{len(c['zones'])} zones filled, sum {sum(filled)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
