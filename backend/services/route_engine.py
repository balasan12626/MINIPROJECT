from __future__ import annotations

from typing import Any

import networkx as nx

from backend.database import mongo
from backend.services.seed import GRAPH_EDGE_INFO, GRAPH_EDGES, GRAPH_NODES, ROADS
from backend.utils.geo import haversine_km


# Free-flow rescue vehicle speed on an open road. Edge weights already inflate
# distance for traffic + flood exposure, so travel time = weighted km / speed.
# (Was `cost / 0.35 * 6` = 17 min per km ≈ 3.5 km/h — a walking pace that
# produced ~536 min ETAs in the Path Contest.)
RESCUE_SPEED_KMH = 25.0


def travel_minutes(weighted_km: float) -> float:
    return float(weighted_km) / RESCUE_SPEED_KMH * 60.0


def _road_lookup(roads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["road_id"]: r for r in roads}


def edge_km(u: str, v: str) -> float:
    """Real road length when the city has it (OSM cities), else the straight line."""
    info = GRAPH_EDGE_INFO.get(f"{u}|{v}") or GRAPH_EDGE_INFO.get(f"{v}|{u}")
    if info and info.get("km") is not None:
        return float(info["km"])
    lat1, lon1 = GRAPH_NODES[u]
    lat2, lon2 = GRAPH_NODES[v]
    return haversine_km(lat1, lon1, lat2, lon2)


def edge_points(u: str, v: str) -> list[list[float]]:
    """Road shape from u to v (OSM cities keep it), else the two end points."""
    info = GRAPH_EDGE_INFO.get(f"{u}|{v}")
    if info and info.get("pts"):
        return [list(p) for p in info["pts"]]
    info = GRAPH_EDGE_INFO.get(f"{v}|{u}")
    if info and info.get("pts"):
        return [list(p) for p in reversed(info["pts"])]
    return [list(GRAPH_NODES[u]), list(GRAPH_NODES[v])]


def _edge_cost(u: str, v: str, road: dict[str, Any] | None, dest_lat: float, dest_lon: float) -> float | None:
    if road and (road.get("blocked") or not road.get("accessible", True)):
        return None
    dist = edge_km(u, v)
    traffic = float((road or {}).get("traffic") or 0.4)
    flood = float((road or {}).get("flood_exposure") or 0.2)
    travel = dist * (1.0 + 0.8 * traffic + 1.4 * flood)
    return travel


def _nearest_node(lat: float, lon: float) -> str:
    return min(GRAPH_NODES, key=lambda n: haversine_km(lat, lon, *GRAPH_NODES[n]))


# Graphs are rebuilt only when the road state actually changes. Callers treat
# the returned graph as READ-ONLY (it is shared).
_GRAPH_CACHE: dict[tuple, nx.Graph] = {}


def clear_graph_cache() -> None:
    _GRAPH_CACHE.clear()


def build_graph(roads: list[dict[str, Any]]) -> nx.Graph:
    lookup = _road_lookup(roads)
    key = (
        len(GRAPH_NODES),
        len(GRAPH_EDGES),
        next(iter(GRAPH_NODES), None),
        tuple(
            sorted(
                (rid, bool(r.get("blocked")), bool(r.get("accessible", True)), r.get("flood_exposure"), r.get("traffic"))
                for rid, r in lookup.items()
            )
        ),
    )
    hit = _GRAPH_CACHE.get(key)
    if hit is not None:
        return hit
    g = nx.Graph()
    for node, (lat, lon) in GRAPH_NODES.items():
        g.add_node(node, lat=lat, lon=lon)
    for u, v, rid in GRAPH_EDGES:
        road = lookup.get(rid)
        lat2, lon2 = GRAPH_NODES[v]
        cost = _edge_cost(u, v, road, lat2, lon2)
        if cost is None:
            continue
        # Two junctions joined by two roads: keep the cheaper one.
        if g.has_edge(u, v) and g.edges[u, v]["weight"] <= cost:
            continue
        g.add_edge(
            u,
            v,
            weight=cost,
            road_id=rid,
            distance_km=edge_km(u, v),
            flood_exposure=float((road or {}).get("flood_exposure") or 0.2),
        )
    if len(_GRAPH_CACHE) > 64:
        _GRAPH_CACHE.clear()
    _GRAPH_CACHE[key] = g
    return g


def path_payload(g: nx.Graph, nodes: list[str]) -> dict[str, Any]:
    coords = [{"node": n, "lat": GRAPH_NODES[n][0], "lon": GRAPH_NODES[n][1]} for n in nodes]
    dist = 0.0
    cost = 0.0
    roads = []
    for a, b in zip(nodes, nodes[1:]):
        data = g.edges[a, b]
        dist += float(data.get("distance_km") or 0)
        cost += float(data.get("weight") or 0)
        roads.append(data.get("road_id"))
    return {
        "nodes": nodes,
        "coordinates": coords,
        "distance_km": round(dist, 3),
        "cost": round(cost, 4),
        "travel_time_min": round(travel_minutes(cost), 2),
        "roads": roads,
    }


async def candidate_routes(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float, k: int = 3) -> list[dict[str, Any]]:
    stored = await mongo.find_many("roads", {}, limit=5000, sort_field="road_id", direction=1)
    roads = stored or ROADS
    g = build_graph(roads)
    src = _nearest_node(origin_lat, origin_lon)
    dst = _nearest_node(dest_lat, dest_lon)
    if src not in g or dst not in g or not nx.has_path(g, src, dst):
        return []
    routes = []
    try:
        gen = nx.shortest_simple_paths(g, src, dst, weight="weight")
        for i, nodes in enumerate(gen):
            payload = path_payload(g, nodes)
            payload["label"] = "Recommended Route" if i == 0 else f"Alternative Route {i}"
            payload["method"] = "yen-dijkstra"
            routes.append(payload)
            if len(routes) >= k:
                break
    except Exception:  # noqa: BLE001
        nodes = nx.shortest_path(g, src, dst, weight="weight")
        payload = path_payload(g, nodes)
        payload["label"] = "Recommended Route"
        payload["method"] = "dijkstra"
        routes.append(payload)
    return routes
