"""F21 — real hospitals per city from OpenStreetMap (`amenity=hospital`).

    python scripts/build_hospitals.py --city patna      (or --all)

Adds `hospitals` (≤ MAX_HOSPITALS, spread over the city like the shelters) to
backend/data/cities/<id>.json. Bed counts come ONLY from the OSM `beds` tag;
untagged → `beds: null` ("capacity unknown") — never invented. Raw Overpass
answers are cached in backend/data/cities/raw/<id>.hospitals.json.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CITY_DIR = ROOT / "backend" / "data" / "cities"
RAW_DIR = CITY_DIR / "raw"
MAX_HOSPITALS = 8

_spec = importlib.util.spec_from_file_location("bcd", ROOT / "scripts" / "build_city_data.py")
bcd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bcd)


def _beds(tags: dict[str, Any]) -> int | None:
    v = str(tags.get("beds") or "").strip()
    return int(v) if v.isdigit() and 0 < int(v) < 20000 else None


def hospitals_from(raw: dict[str, Any], bbox: list[float]) -> list[dict[str, Any]]:
    s, w, n, e = bbox
    seen: set[str] = set()
    items = []
    for el in raw.get("elements") or []:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        if not name or lat is None or not (s <= lat <= n and w <= lon <= e):
            continue
        key = name.lower()
        if key in seen:  # one entry per named hospital (OSM often has node + way)
            continue
        seen.add(key)
        beds = _beds(tags)
        items.append({
            "name": name,
            "lat": round(float(lat), 6),
            "lon": round(float(lon), 6),
            "osm": f"{el['type']}/{el['id']}",
            "beds": beds,
            "beds_source": "OSM beds tag" if beds is not None else None,
            "emergency": tags.get("emergency"),
            "operator_type": tags.get("operator:type"),
            "_rank": (tags.get("emergency") == "yes", beds or 0),
        })
    items.sort(key=lambda h: h["_rank"], reverse=True)
    picked = bcd.spread_pick(items, MAX_HOSPITALS)
    out = []
    for i, h in enumerate(picked, 1):
        h.pop("_rank", None)
        out.append({"hospital_id": f"H{i:02d}", **h})
    return out


def fill_city(cid: str, refresh: bool = False) -> dict[str, Any]:
    path = CITY_DIR / f"{cid}.json"
    city = json.loads(path.read_text(encoding="utf-8"))
    cache = RAW_DIR / f"{cid}.hospitals.json"
    if cache.exists() and not refresh:
        raw = json.loads(cache.read_text(encoding="utf-8"))
    else:
        s, w, n, e = city["bbox"]
        raw = bcd.overpass(f'[out:json][timeout:120];nwr["amenity"="hospital"]({s},{w},{n},{e});out tags center;')
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(raw), encoding="utf-8")
    city["hospitals"] = hospitals_from(raw, city["bbox"])
    city["hospitals_source"] = {"data": "OpenStreetMap amenity=hospital (ODbL)", "beds": "OSM beds tag only; null = unknown"}
    city.setdefault("counts", {})["hospitals"] = len(city["hospitals"])
    path.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    return city


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hospitals per city from OSM")
    ap.add_argument("--city")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)
    ids = sorted(p.stem for p in CITY_DIR.glob("*.json") if "." not in p.stem) if args.all else [args.city]
    if not ids or ids == [None]:
        ap.error("--city or --all")
    for cid in ids:
        try:
            c = fill_city(cid, args.refresh)
        except SystemExit as e:  # Overpass down: keep going, re-run later (cache is reused)
            print(f"[{cid}] skipped: {e}")
            continue
        beds = sum(1 for h in c["hospitals"] if h["beds"] is not None)
        print(f"[{cid}] {len(c['hospitals'])} hospitals ({beds} with an OSM beds tag)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
