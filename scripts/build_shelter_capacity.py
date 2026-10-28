"""F27 — shelter capacity from building size (Sphere standard), not from type.

    python scripts/build_shelter_capacity.py --city patna     (or --all)

For each shelter (an OSM feature) the covered floor area is the sum of the
OSM building outlines that belong to it:
  * shelter is a way/relation (campus, stadium): every `building=*` way inside it;
  * shelter is a node: the `building=*` way(s) that contain the node.
floor area = Σ footprint_m2 × levels   (levels = `building:levels` when tagged, else 1 — `levels_source` says which)
capacity   = floor(floor_area × USABLE_SHARE / M2_PER_PERSON)

M2_PER_PERSON = 3.5 m² — Sphere Handbook 2018 (4th edition), Shelter and Settlement
Standard 3 "Living space", key indicator: at least 3.5 m² of living space per person
(excluding cooking, bathing and sanitation). USABLE_SHARE (how much of a floor can
be living space in a school / stadium / hall) is ASSUMED and labelled.
A shelter with no mapped outline keeps "assumed by building type".
Overpass answers are cached in backend/data/cities/raw/<city>.buildings.json.
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
RAW_DIR = CITY_DIR / "raw"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
M2_PER_PERSON = 3.5
USABLE_SHARE = 0.5
CITATION = {
    "standard": "Sphere Handbook 2018 (4th edition), Shelter and Settlement Standard 3: Living space",
    "figure": "at least 3.5 m2 of living space per person, excluding cooking, bathing and sanitation",
    "url": "https://spherestandards.org/handbook-2018/",
    "also": "https://spherestandards.org/wp-content/uploads/Sphere-in-Practice.pdf",
}


def polygon_area_m2(pts: list[tuple[float, float]]) -> float:
    """Shoelace on a local equirectangular projection (lat, lon in degrees)."""
    if len(pts) < 3:
        return 0.0
    lat0 = sum(p[0] for p in pts) / len(pts)
    kx = 111_320.0 * math.cos(math.radians(lat0))
    ky = 110_574.0
    xy = [(p[1] * kx, p[0] * ky) for p in pts]
    s = 0.0
    for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def levels_of(tags: dict) -> tuple[float, str]:
    v = str(tags.get("building:levels") or "").strip()
    try:
        n = float(v.split(";")[0])
        if 0 < n < 60:
            return n, "OSM building:levels"
    except ValueError:
        pass
    return 1.0, "assumed 1 level (building:levels not tagged)"


def capacity_from(buildings: list[dict]) -> dict | None:
    if not buildings:
        return None
    floor, footprint, tagged = 0.0, 0.0, 0
    for b in buildings:
        pts = [(g["lat"], g["lon"]) for g in b.get("geometry") or []]
        a = polygon_area_m2(pts)
        lv, src = levels_of(b.get("tags") or {})
        tagged += src.startswith("OSM")
        footprint += a
        floor += a * lv
    if floor <= 0:
        return None
    return {
        "capacity": int(math.floor(floor * USABLE_SHARE / M2_PER_PERSON)),
        "capacity_source": "Sphere standard from OSM footprint",
        "area_m2": round(footprint, 1),
        "floor_area_m2": round(floor, 1),
        "buildings": len(buildings),
        "levels_source": f"{tagged} of {len(buildings)} buildings tagged with building:levels, the rest assumed 1 level",
        "usable_share": USABLE_SHARE,
        "usable_share_source": "assumed (share of floor area usable as living space)",
        "m2_per_person": M2_PER_PERSON,
        "capacity_citation": CITATION,
    }


def query_for(osm: str) -> str:
    kind, oid = osm.split("/")
    if kind == "node":
        return f"[out:json][timeout:60];node({oid});is_in->.a;way(pivot.a)[building];out geom tags;"
    sel = "way" if kind == "way" else "rel"
    return f"[out:json][timeout:60];{sel}({oid});out geom tags;"


def inside(pt: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    """Ray casting; pt and poly as (lat, lon)."""
    y, x = pt
    hit = False
    for (y1, x1), (y2, x2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            hit = not hit
    return hit


def buildings_in_site(site: dict, client: "httpx.Client") -> list[dict]:
    """Every building way whose centroid lies inside the site outline (+ the site
    itself when it is tagged building)."""
    rings = []
    if site.get("type") == "way":
        rings = [[(g["lat"], g["lon"]) for g in site.get("geometry") or []]]
    else:  # relation: outer members
        rings = [[(g["lat"], g["lon"]) for g in m.get("geometry") or []]
                 for m in site.get("members") or [] if m.get("role") in ("outer", "") and m.get("geometry")]
    rings = [r for r in rings if len(r) >= 3]
    out = [site] if (site.get("tags") or {}).get("building") and site.get("type") == "way" else []
    if not rings:
        return out
    lats = [p[0] for r in rings for p in r]
    lons = [p[1] for r in rings for p in r]
    q = f"[out:json][timeout:60];way[building]({min(lats)},{min(lons)},{max(lats)},{max(lons)});out geom tags;"
    for b in fetch(q, client):
        pts = [(g["lat"], g["lon"]) for g in b.get("geometry") or []]
        if not pts or b.get("id") == site.get("id"):
            continue
        c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        if any(inside(c, r) for r in rings):
            out.append(b)
    return out


def fetch(q: str, client: httpx.Client) -> list[dict]:
    last = None
    for attempt in range(4):
        url = OVERPASS[attempt % len(OVERPASS)]
        try:
            r = client.post(url, data={"data": q})
            r.raise_for_status()
            return r.json().get("elements") or []
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 + 4 * attempt)
    raise RuntimeError(f"Overpass failed: {last}")


def fill_city(cid: str, client: httpx.Client, refresh: bool = False) -> dict:
    path = CITY_DIR / f"{cid}.json"
    city = json.loads(path.read_text(encoding="utf-8"))
    cache_p = RAW_DIR / f"{cid}.buildings.json"
    cache = {} if refresh or not cache_p.exists() else json.loads(cache_p.read_text(encoding="utf-8"))
    for s in city["shelters"]:
        osm = s.get("osm")
        if not osm:
            continue
        if osm not in cache:
            try:
                els = fetch(query_for(osm), client)
                if not osm.startswith("node/") and els:
                    els = buildings_in_site(els[0], client)
                cache[osm] = els
                time.sleep(1.0)
                cache_p.write_text(json.dumps(cache), encoding="utf-8")
            except Exception as e:  # noqa: BLE001 — leave the old label; say why
                s["capacity_note"] = f"building outline not fetched: {str(e)[:120]}"
                print(f"  [{cid}] {s['name']}: fetch failed, kept {s['capacity']} ({s['capacity_source']})", flush=True)
                continue
        els = [e for e in cache[osm] if e.get("type") == "way" and (e.get("tags") or {}).get("building")]
        cap = capacity_from(els)
        if cap:
            s.setdefault("capacity_assumed_by_type", s.get("capacity"))
            s.update(cap)
            s.pop("capacity_note", None)
        else:
            s["capacity_note"] = "no building outline mapped in OSM — capacity stays assumed by type"
        print(f"  [{cid}] {s['name']}: {s['capacity']} ({s['capacity_source']})", flush=True)
    path.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    return city


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Shelter capacity from OSM building size (Sphere standard)")
    ap.add_argument("--city")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)
    ids = sorted(p.stem for p in CITY_DIR.glob("*.json") if "." not in p.stem) if args.all else [args.city]
    if not ids or ids == [None]:
        ap.error("--city or --all")
    with httpx.Client(timeout=120, headers={"User-Agent": "AquaSentinel-build/1.0"}) as client:
        for cid in ids:
            c = fill_city(cid, client, args.refresh)
            n = sum(1 for s in c["shelters"] if s["capacity_source"].startswith("Sphere"))
            print(f"[{cid}] {n}/{len(c['shelters'])} shelters sized from building outlines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
