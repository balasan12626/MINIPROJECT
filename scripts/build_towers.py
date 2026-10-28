"""F29 — mobile-tower locations per city from OpenCelliD.

    $env:OPENCELLID_TOKEN = "..."   (or put OPENCELLID_TOKEN=... in .env)
    python scripts/build_towers.py --city patna          (or --all)

→ backend/data/cities/<id>.towers.json : {towers: [{lat, lon, radio, flood_exposure}], source, licence, ...}

* The token is read ONLY from the environment / .env — never asked for, never stored.
* OpenCelliD `cell/getInArea` limits one request to ~4 km², so the city bbox is
  tiled (TILE_KM) and the tiles are cached in raw/<id>.towers.raw.json.
* Each tower's `flood_exposure` uses the SAME distance-to-water proxy as the roads
  (build_city_data.exposure_at over the cached OSM water), so "tower flooded" and
  "road closed" follow one rule. Data © OpenCelliD contributors, CC BY-SA 4.0.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
import time
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CITY_DIR = ROOT / "backend" / "data" / "cities"
RAW_DIR = CITY_DIR / "raw"
API = "https://opencellid.org/cell/getInArea"
TILE_KM = 1.9  # 1.9 km × 1.9 km < 4 km² per request

_spec = importlib.util.spec_from_file_location("bcd", ROOT / "scripts" / "build_city_data.py")
bcd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bcd)


def token() -> str | None:
    tok = os.environ.get("OPENCELLID_TOKEN")
    if tok:
        return tok.strip()
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("OPENCELLID_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"') or None
    return None


def tiles(bbox: list[float]) -> list[tuple[float, float, float, float]]:
    s, w, n, e = bbox
    dlat = TILE_KM / 110.574
    dlon = TILE_KM / (111.320 * math.cos(math.radians((s + n) / 2)))
    out = []
    lat = s
    while lat < n:
        lon = w
        while lon < e:
            out.append((round(lat, 5), round(lon, 5), round(min(n, lat + dlat), 5), round(min(e, lon + dlon), 5)))
            lon += dlon
        lat += dlat
    return out


def fetch_city(cid: str, tok: str) -> list[dict]:
    city = json.loads((CITY_DIR / f"{cid}.json").read_text(encoding="utf-8"))
    cache_p = RAW_DIR / f"{cid}.towers.raw.json"
    cache = json.loads(cache_p.read_text(encoding="utf-8")) if cache_p.exists() else {}
    with httpx.Client(timeout=60) as c:
        for t in tiles(city["bbox"]):
            key = ",".join(map(str, t))
            if key in cache:
                continue
            r = c.get(API, params={"key": tok, "BBOX": key, "format": "json", "limit": 1000})
            if r.status_code != 200:
                raise SystemExit(f"OpenCelliD HTTP {r.status_code}: {r.text[:200]}")
            body = r.json()
            cache[key] = body.get("cells") or []
            cache_p.write_text(json.dumps(cache), encoding="utf-8")
            time.sleep(1.0)
    seen, out = set(), []
    for cells in cache.values():
        for x in cells:
            k = (round(float(x["lat"]), 4), round(float(x["lon"]), 4), x.get("radio"))
            if k in seen:
                continue
            seen.add(k)
            out.append({"lat": k[0], "lon": k[1], "radio": x.get("radio")})
    return out


def with_exposure(cid: str, towers: list[dict]) -> list[dict]:
    raw_p = RAW_DIR / f"{cid}.raw.json"
    if not raw_p.exists():
        raise SystemExit(f"[{cid}] no OSM raw cache — run build_city_data.py --city {cid} first")
    raw = json.loads(raw_p.read_text(encoding="utf-8"))
    lines = bcd.water_lines(raw["water"])
    for t in towers:
        t["flood_exposure"] = bcd.exposure_at((t["lat"], t["lon"]), lines)[0]
    return towers


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mobile towers per city (OpenCelliD)")
    ap.add_argument("--city")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args(argv)
    tok = token()
    if not tok:
        print("OPENCELLID_TOKEN is not set. Register at https://opencellid.org (free), then put "
              "OPENCELLID_TOKEN=<your token> in .env and re-run. Nothing was written.")
        return 2
    ids = sorted(p.stem for p in CITY_DIR.glob("*.json") if "." not in p.stem) if args.all else [args.city]
    for cid in ids:
        towers = with_exposure(cid, fetch_city(cid, tok))
        out = {
            "city": cid,
            "towers": towers,
            "source": "OpenCelliD cell/getInArea",
            "licence": "CC BY-SA 4.0",
            "attribution": "Cell tower data © OpenCelliD contributors (CC BY-SA 4.0)",
            "flood_exposure_source": "same distance-to-water proxy as the roads (OSM water, build_city_data.exposure_at)",
            "retrieved_at": date.today().isoformat(),
        }
        (CITY_DIR / f"{cid}.towers.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
        print(f"[{cid}] {len(towers)} towers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
