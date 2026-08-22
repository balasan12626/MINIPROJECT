from __future__ import annotations

from typing import Any

import networkx as nx

from backend.database import mongo
from backend.services.seed import GRAPH_EDGES, GRAPH_NODES, ROADS
from backend.utils.geo import haversine_km


def _road_lookup(roads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["road_id"]: r for r in roads}


def _edge_cost(u: str, v: str, road: dict[str, Any] | None, dest_lat: float, dest_lon: float) -> float | None:
    if road and (road.get("blocked") or not road.get("accessible", True)):
        return None
    lat1, lon1 = GRAPH_NODES[u]
    lat2, lon2 = GRAPH_NODES[v]
    dist = haversine_km(lat1, lon1, lat2, lon2)
    traffic = float((road or {}).get("traffic") or 0.4)
    flood = float((road or {}).get("flood_exposure") or 0.2)
    travel = dist * (1.0 + 0.8 * traffic + 1.4 * flood)
    return travel


def _nearest_node(lat: float, lon: float) -> str:
    return min(GRAPH_NODES, key=lambda n: haversine_km(lat, lon, *GRAPH_NODES[n]))


def build_graph(roads: list[dict[str, Any]]) -> nx.Graph:
    lookup = _road_lookup(roads)
    g = nx.Graph()
    for node, (lat, lon) in GRAPH_NODES.items():
        g.add_node(node, lat=lat, lon=lon)
    for u, v, rid in GRAPH_EDGES:
        road = lookup.get(rid)
        lat1, lon1 = GRAPH_NODES[u]
        lat2, lon2 = GRAPH_NODES[v]
        cost = _edge_cost(u, v, road, lat2, lon2)
        if cost is None:
            continue
        g.add_edge(u, v, weight=cost, road_id=rid, distance_km=haversine_km(lat1, lon1, lat2, lon2))
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
        "travel_time_min": round(cost / 0.35 * 6, 2),
        "roads": roads,
    }


async def candidate_routes(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float, k: int = 3) -> list[dict[str, Any]]:
    stored = await mongo.find_many("roads", {}, limit=50, sort_field="road_id", direction=1)
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
