"""F7 — the city the digital twin runs on.

Cities are DATA (backend/data/cities/<id>.json, built by
scripts/build_city_data.py from OpenStreetMap + INDOFLOODS). The original
hand-made Delhi network stays available as city "delhi_seed".

One engine runs one operation, so there is ONE active city per backend.
`activate()` swaps the CONTENTS of the seed containers in place
(seed.SHELTERS / ROADS / ZONES / RESCUE_TEAMS / GRAPH_NODES / GRAPH_EDGES /
GRAPH_EDGE_INFO and person_ops.SHELTER_POOL). Every module that imported those
names keeps a reference to the same object, so it sees the new city without
any per-call plumbing.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CITY_DIR = Path(__file__).resolve().parents[1] / "data" / "cities"
LEGACY = "delhi_seed"
DEFAULT_CITY = LEGACY  # API callers that send no city keep today's behaviour

_active = LEGACY
_legacy_snapshot: dict[str, Any] | None = None


def _legacy() -> dict[str, Any]:
    """The hand-made Delhi network, captured once before any swap."""
    global _legacy_snapshot
    if _legacy_snapshot is None:
        from backend.services import person_ops, seed

        _legacy_snapshot = copy.deepcopy(
            {
                "id": LEGACY,
                "name": "Delhi (demo network)",
                "state": "Delhi",
                "why": "Hand-made 17-junction Yamuna floodplain network (original demo; used by tests and route benchmark v1).",
                "center": [28.6139, 77.2090],
                "zoom": 11,
                "attribution": "Curated demo data",
                "gauge": {
                    "available": True,
                    "station": "Yamuna at ITO / Delhi",
                    "river": "Yamuna",
                    "lat": 28.6284,
                    "lon": 77.2410,
                    "danger_level_m": 205.8,
                    "warning_level_m": 204.5,
                    "source": "repo demo value (ITO); INDOFLOODS Delhi rly bridge danger level is 205.33 m",
                    "catchment": {},
                },
                "upstream_dam": {"station": "Hathnikund Barrage", "lat": 30.3139, "lon": 77.5886},
                "graph_nodes": {k: list(v) for k, v in seed.GRAPH_NODES.items()},
                "graph_edges": [list(e) for e in seed.GRAPH_EDGES],
                "edge_info": {},
                "roads": seed.ROADS,
                "shelters": seed.SHELTERS,
                "rescue_teams": seed.RESCUE_TEAMS,
                "zones": seed.ZONES,
                "hospitals": _delhi_hospitals(),
                "shelter_pool": list(person_ops.SHELTER_POOL),
                "water": [],
                "bbox": [28.54, 77.10, 28.72, 77.43],
                "counts": {
                    "junctions": len(seed.GRAPH_NODES),
                    "road_segments": len(seed.GRAPH_EDGES),
                    "named_roads": len(seed.ROADS),
                    "shelters": len(person_ops.SHELTER_POOL),
                    "depots": len(seed.RESCUE_TEAMS),
                    "zones": len(seed.ZONES),
                },
                "notes": ["Original curated demo network; capacities and exposures are project settings."],
            }
        )
    return _legacy_snapshot


def _delhi_hospitals() -> list[dict[str, Any]]:
    """F21: the demo network is in Delhi, so it uses the real Delhi OSM hospitals."""
    try:
        return list(_read("delhi").get("hospitals") or [])
    except Exception:  # noqa: BLE001
        return []


@lru_cache(maxsize=16)
def _read(city_id: str) -> dict[str, Any]:
    path = CITY_DIR / f"{city_id}.json"
    if not path.exists():
        raise KeyError(city_id)
    return json.loads(path.read_text(encoding="utf-8"))


def load_city(city_id: str) -> dict[str, Any]:
    if city_id == LEGACY:
        return _legacy()
    return _read(city_id)


def available_ids() -> list[str]:
    return [LEGACY] + sorted(p.stem for p in CITY_DIR.glob("*.json"))


def flood_driver(city: dict[str, Any]) -> str:
    return "river" if (city.get("gauge") or {}).get("available") else "rainfall"


def summary(city: dict[str, Any]) -> dict[str, Any]:
    """Small block served with every state poll (no geometry)."""
    gauge = {k: v for k, v in (city.get("gauge") or {}).items() if k != "catchment"}
    return {
        "id": city["id"],
        "name": city["name"],
        "state": city.get("state"),
        "why": city.get("why"),
        "center": city.get("center"),
        "zoom": city.get("zoom", 12),
        "bbox": city.get("bbox"),
        "attribution": city.get("attribution"),
        "flood_driver": flood_driver(city),
        "gauge": gauge,
        "has_upstream_dam": bool(city.get("upstream_dam")),
        "counts": city.get("counts"),
        "notes": city.get("notes") or [],
        "built_at": city.get("built_at"),
    }


def list_cities() -> list[dict[str, Any]]:
    out = []
    for cid in available_ids():
        try:
            out.append(summary(load_city(cid)))
        except Exception:  # noqa: BLE001 — a broken file must not hide the others
            continue
    return out


def road_geometry(city: dict[str, Any]) -> dict[str, list[list[list[float]]]]:
    """road_id -> list of polylines (each [[lat, lon], ...]) for the map."""
    nodes = city["graph_nodes"]
    info = city.get("edge_info") or {}
    out: dict[str, list] = {}
    for u, v, rid in city["graph_edges"]:
        pts = (info.get(f"{u}|{v}") or {}).get("pts") or [nodes[u], nodes[v]]
        out.setdefault(rid, []).append([[round(p[0], 5), round(p[1], 5)] for p in pts])
    return out


def view(city_id: str) -> dict[str, Any]:
    """Everything the map needs once per city (static geometry)."""
    city = load_city(city_id)
    return {
        **summary(city),
        "shelters": [
            {k: s.get(k) for k in ("shelter_id", "name", "lat", "lon", "capacity", "capacity_source", "kind", "flood_risk")}
            for s in city["shelters"]
        ],
        "rescue_teams": [{k: t.get(k) for k in ("team_id", "name", "lat", "lon", "scope")} for t in city["rescue_teams"]],
        "hospitals": city.get("hospitals") or [],
        "zones": city["zones"],
        "water": city.get("water") or [],
        "roads": [
            {k: r.get(k) for k in ("road_id", "name", "highway", "length_km", "flood_exposure", "flood_exposure_source")}
            for r in city["roads"]
        ],
        "road_geometry": road_geometry(city),
    }


def active_id() -> str:
    return _active


def active() -> dict[str, Any]:
    return load_city(_active)


def activate(city_id: str | None) -> dict[str, Any]:
    """Make `city_id` the city every service plans on. Idempotent."""
    global _active
    city_id = city_id or DEFAULT_CITY
    city = load_city(city_id)  # KeyError for an unknown city, before touching anything
    if city_id == _active and _active != LEGACY:
        return city
    from backend.services import person_ops, route_engine, seed

    _legacy()  # snapshot the hand-made network before the first swap
    seed.SHELTERS[:] = copy.deepcopy(city["shelters"])
    seed.ROADS[:] = copy.deepcopy(city["roads"])
    seed.ZONES[:] = copy.deepcopy(city["zones"])
    seed.RESCUE_TEAMS[:] = copy.deepcopy(city["rescue_teams"])
    seed.HOSPITALS[:] = copy.deepcopy(city.get("hospitals") or [])
    seed.GRAPH_NODES.clear()
    seed.GRAPH_NODES.update({k: (float(v[0]), float(v[1])) for k, v in city["graph_nodes"].items()})
    seed.GRAPH_EDGES[:] = [tuple(e) for e in city["graph_edges"]]
    seed.GRAPH_EDGE_INFO.clear()
    seed.GRAPH_EDGE_INFO.update(city.get("edge_info") or {})
    person_ops.SHELTER_POOL[:] = city.get("shelter_pool") or [s["name"] for s in city["shelters"]]
    route_engine.clear_graph_cache()
    _active = city_id
    return city


async def sync_db() -> None:
    """Mongo `shelters` / `roads` / `rescue_teams` hold ONLY the active city."""
    from backend.database import mongo
    from backend.services import seed

    for coll, items, key in (
        ("shelters", seed.SHELTERS, "shelter_id"),
        ("roads", seed.ROADS, "road_id"),
        ("rescue_teams", seed.RESCUE_TEAMS, "team_id"),
    ):
        await mongo.delete_many(coll, {key: {"$nin": [x[key] for x in items]}})
        for x in items:
            await mongo.upsert(coll, {key: x[key]}, {k: v for k, v in x.items() if k != "_id"})
