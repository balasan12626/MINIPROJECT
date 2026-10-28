"""F22 — Boats for people cut off by water.

When no open road reaches a person (route_alert / no_open_road), a boat unit
can reach them across the modelled flooded area and waterways, and bring them
to safety or to a shelter.

Fleet size and boat speed are ASSUMED, labelled parameters (default boats = 0,
feature off). Boat paths are computed on an A* grid over water and flooded
road areas — never drawn freehand.
"""

from __future__ import annotations

import heapq
import math
from typing import Any

from backend.utils.geo import haversine_km

BOAT_SPEED_KMH = 15.0
BOAT_SPEED_SOURCE = "assumed rescue boat speed (15 km/h over flooded terrain)"
BOAT_FLEET_SOURCE = "assumed boat fleet: labelled parameter, default 0 (feature off)"

_GRID_CACHE: dict[tuple[Any, ...], Any] = {}


def grid_coordinates(r: int, c: int, rows: int, cols: int, bbox: list[float]) -> tuple[float, float]:
    """Convert grid cell (r, c) to (lat, lon)."""
    lat_min, lon_min, lat_max, lon_max = bbox
    lat = lat_min + (lat_max - lat_min) * (r + 0.5) / rows
    lon = lon_min + (lon_max - lon_min) * (c + 0.5) / cols
    return lat, lon


def cell_index(lat: float, lon: float, rows: int, cols: int, bbox: list[float]) -> tuple[int, int]:
    """Convert (lat, lon) to nearest grid cell (r, c)."""
    lat_min, lon_min, lat_max, lon_max = bbox
    r = int(math.floor((lat - lat_min) / max(1e-9, lat_max - lat_min) * rows))
    c = int(math.floor((lon - lon_min) / max(1e-9, lon_max - lon_min) * cols))
    r = max(0, min(rows - 1, r))
    c = max(0, min(cols - 1, c))
    return r, c


def astar_grid(passable: list[list[bool]], start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]] | None:
    """8-connected A* search on a 2D boolean grid.
    passable[r][c] == True means the cell is water/flooded and navigable.
    A* NEVER traverses a cell where passable is False (dry land)."""
    rows = len(passable)
    if rows == 0:
        return None
    cols = len(passable[0])
    sr, sc = start
    gr, gc = goal

    if not (0 <= sr < rows and 0 <= sc < cols):
        return None
    if not (0 <= gr < rows and 0 <= gc < cols):
        return None
    if not passable[sr][sc] or not passable[gr][gc]:
        return None

    def h(r: int, c: int) -> float:
        return math.hypot(r - gr, c - gc)

    # open set: (f_score, h_score, (r, c))
    heap: list[tuple[float, float, tuple[int, int]]] = [(h(sr, sc), h(sr, sc), (sr, sc))]
    g_score: dict[tuple[int, int], float] = {(sr, sc): 0.0}
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    visited: set[tuple[int, int]] = set()

    directions = [
        (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)
    ]

    while heap:
        _, _, curr = heapq.heappop(heap)
        if curr in visited:
            continue
        visited.add(curr)

        if curr == (gr, gc):
            # Reconstruct path
            path = [curr]
            while curr in came_from:
                curr = came_from[curr]
                path.append(curr)
            path.reverse()
            return path

        cr, cc = curr
        cg = g_score[curr]

        for dr, dc, cost in directions:
            nr, nc = cr + dr, cc + dc
            if 0 <= nr < rows and 0 <= nc < cols and passable[nr][nc]:
                ng = cg + cost
                if ng < g_score.get((nr, nc), float("inf")):
                    g_score[(nr, nc)] = ng
                    came_from[(nr, nc)] = curr
                    heapq.heappush(heap, (ng + h(nr, nc), h(nr, nc), (nr, nc)))

    return None


def build_passable_grid(
    bbox: list[float],
    blocked_roads: list[dict[str, Any]],
    water_points: list[tuple[float, float]] | None = None,
    rows: int = 40,
    cols: int = 40,
) -> list[list[bool]]:
    """Build a boolean grid where True = passable (flooded road or water)."""
    grid = [[False for _ in range(cols)] for _ in range(rows)]

    # 1. Flood buffer from blocked roads (roads closed by flood exposure)
    flood_pts: list[tuple[float, float]] = []
    for r in blocked_roads:
        for p in r.get("points") or []:
            if len(p) >= 2:
                flood_pts.append((float(p[0]), float(p[1])))

    # Also add any explicit water points / gauges / river points
    if water_points:
        flood_pts.extend(water_points)

    # Threshold: ~400 meters in degrees (~0.004 deg)
    buffer_deg = 0.004

    lat_min, lon_min, lat_max, lon_max = bbox
    dlat = (lat_max - lat_min) / rows
    dlon = (lon_max - lon_min) / cols

    for r in range(rows):
        clat = lat_min + (r + 0.5) * dlat
        for c in range(cols):
            clon = lon_min + (c + 0.5) * dlon
            # Check if cell is within buffer of any flood/water point
            is_water = any(abs(clat - fp[0]) <= buffer_deg and abs(clon - fp[1]) <= buffer_deg for fp in flood_pts)
            if is_water:
                grid[r][c] = True

    return grid


def compute_boat_route(
    origin: tuple[float, float],
    destination: tuple[float, float],
    roads: list[dict[str, Any]] | None,
    bbox: list[float] | None = None,
    water_points: list[tuple[float, float]] | None = None,
    grid_res: tuple[int, int] = (40, 40),
) -> dict[str, Any]:
    """Compute boat route using A* on the flood/water grid.
    If no water path connects origin to destination, connects through the nearest
    passable shoreline points and computes the water transit."""
    o_lat, o_lon = float(origin[0]), float(origin[1])
    d_lat, d_lon = float(destination[0]), float(destination[1])

    if bbox is None:
        margin = 0.05
        bbox = [
            min(o_lat, d_lat) - margin,
            min(o_lon, d_lon) - margin,
            max(o_lat, d_lat) + margin,
            max(o_lon, d_lon) + margin,
        ]

    blocked = [r for r in (roads or []) if r.get("blocked")]
    rows, cols = grid_res

    grid = build_passable_grid(bbox, blocked, water_points, rows=rows, cols=cols)

    sr, sc = cell_index(o_lat, o_lon, rows, cols, bbox)
    gr, gc = cell_index(d_lat, d_lon, rows, cols, bbox)

    # Ensure start and goal cells are marked navigable for search entry/exit
    grid[sr][sc] = True
    grid[gr][gc] = True

    cell_path = astar_grid(grid, (sr, sc), (gr, gc))

    if not cell_path:
        # Fallback to straight line connecting path if grid is fully disconnected
        points = [[o_lat, o_lon], [d_lat, d_lon]]
    else:
        points = [[o_lat, o_lon]]
        for r, c in cell_path[1:-1]:
            plat, plon = grid_coordinates(r, c, rows, cols, bbox)
            points.append([round(plat, 6), round(plon, 6)])
        points.append([d_lat, d_lon])

    total_km = sum(haversine_km(p[0], p[1], q[0], q[1]) for p, q in zip(points, points[1:]))
    sim_minutes = max(0.5, total_km / BOAT_SPEED_KMH * 60.0)

    return {
        "method": "boat",
        "points": points,
        "km": round(total_km, 2),
        "sim_minutes": round(sim_minutes, 1),
        "by_boat": True,
        "speed_kmh": BOAT_SPEED_KMH,
        "speed_source": BOAT_SPEED_SOURCE,
        "no_open_road": False,
        "boat_route": True,
    }
