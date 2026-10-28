"""F7 — build one city's operational geography from OpenStreetMap (+ INDOFLOODS).

    python scripts/build_city_data.py --city chennai
    python scripts/build_city_data.py --all

Writes backend/data/cities/<id>.json. Nothing in the output is invented:

* roads / junctions / water / fire stations / candidate shelters / suburbs come
  from OpenStreetMap through the Overpass API (ODbL — attribution kept in the file);
* road `flood_exposure` is a PROXY: a decreasing function of the distance from
  the road to the nearest mapped river / canal / drain / coast / water body;
* road `traffic` and shelter `capacity` are not in OSM — they are ASSUMED by
  road class / building type and every such field says so (`*_source`);
* the river gauge (warning / danger level, catchment attributes for the ML
  model) is the nearest INDOFLOODS gauge if it is within GAUGE_MAX_KM;
  otherwise the city is marked rainfall-driven (no stage term);
* suburb population is copied only when OSM has a `population` tag.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "backend" / "data" / "cities"
DATASET = ROOT / "dataset"
OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
UA = {"User-Agent": "AquaSentinel-flood-twin/1.0 (academic final-year project; contact via repo)"}

GAUGE_MAX_KM = 30.0
MERGE_M = 45.0  # junctions closer than this are one junction (dual carriageways)
MAX_SHELTERS = 10
MAX_DEPOTS = 6
MIN_DEPOTS = 3  # fewer fire stations than this → police stations fill in
MAX_ZONES = 6

# Why each city is here (short, factual) and the flood-prone core that is mapped.
# bbox = (south, west, north, east).
CITY_SPECS: dict[str, dict[str, Any]] = {
    "delhi": {
        "name": "Delhi",
        "state": "Delhi",
        "bbox": (28.54, 77.17, 28.72, 77.32),
        "why": "Yamuna floodplain; the river crossed its highest recorded level in July 2023.",
        "prefix": "DEL",
    },
    "mumbai": {
        "name": "Mumbai",
        "state": "Maharashtra",
        "bbox": (19.00, 72.82, 19.13, 72.93),
        "why": "Extreme monsoon rain + Mithi river + high tide; 26 July 2005 and most monsoons since.",
        "prefix": "MUM",
    },
    "chennai": {
        "name": "Chennai",
        "state": "Tamil Nadu",
        "bbox": (12.96, 80.18, 13.11, 80.29),
        "why": "Adyar / Cooum overflow and low-lying lakes; December 2015 and December 2023 floods.",
        "prefix": "CHE",
    },
    "kolkata": {
        "name": "Kolkata",
        "state": "West Bengal",
        "bbox": (22.49, 88.30, 22.62, 88.41),
        "why": "Flat, low-lying city on the Hooghly; waterlogging in every heavy monsoon spell.",
        "prefix": "KOL",
    },
    "guwahati": {
        "name": "Guwahati",
        "state": "Assam",
        "bbox": (26.10, 91.68, 26.20, 91.82),
        "why": "Brahmaputra floods and urban flash floods (Anil Nagar, Zoo Road) almost every year.",
        "prefix": "GUW",
    },
    "patna": {
        "name": "Patna",
        "state": "Bihar",
        "bbox": (25.57, 85.05, 25.64, 85.22),
        "why": "Ganga and Punpun; September 2019 urban flood (Rajendra Nagar, Kankarbagh).",
        "prefix": "PAT",
    },
}

RAW_DIR = OUT_DIR / "raw"  # git-ignored cache of the Overpass downloads
ROAD_CLASSES = ("motorway", "trunk", "primary", "secondary", "motorway_link", "trunk_link", "primary_link")
TRAFFIC_BY_CLASS = {"motorway": 0.55, "trunk": 0.5, "primary": 0.45, "secondary": 0.4, "tertiary": 0.35}
MIN_JUNCTIONS = 250  # below this the city also gets tertiary roads (else the graph is too sparse)

# Flood-exposure proxy per kind of mapped water: (amplitude, decay length km).
# A river / the sea floods far inland; a pond or a storm drain only next to it.
#   Amplitudes stay below the engine's closure line (0.85 at zero blockage),
#   like the hand-made demo network (max 0.82): roads close only as the
#   scenario's blockage grows, the river edge first.
WATER_WEIGHT = {
    "river": (0.82, 1.0),
    "coastline": (0.80, 0.8),
    "canal": (0.6, 0.35),
    "water": (0.5, 0.2),
    "stream": (0.45, 0.15),
    "drain": (0.35, 0.1),
}
EXPOSURE_FLOOR = 0.06
BRIDGE_CAP = 0.35  # an OSM bridge is elevated: its proxy is capped (its approaches are not)
SECTION_KM = 2.0  # long named roads are split into sections of about this length
NOT_A_SHELTER = ("classes", "coaching", "tuition", "academy of", "institute of hotel", "play school", "kindergarten")
CAPACITY_BY_TYPE = {"stadium": 1500, "university": 1200, "college": 800, "school": 500, "community_centre": 300}
SHELTER_PRIORITY = ["stadium", "university", "college", "community_centre", "school"]


# --------------------------------------------------------------------------- geo
def hav_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    p = math.pi / 180
    x = math.sin((b[0] - a[0]) * p / 2) ** 2 + math.cos(a[0] * p) * math.cos(b[0] * p) * math.sin((b[1] - a[1]) * p / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, x)))


def point_seg_km(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance point→segment on a local equirectangular projection (fine at city scale)."""
    k = math.cos(p[0] * math.pi / 180)
    ax, ay = (a[1] - p[1]) * k, a[0] - p[0]
    bx, by = (b[1] - p[1]) * k, b[0] - p[0]
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L))
    x, y = ax + t * dx, ay + t * dy
    return math.hypot(x, y) * 111.32


def thin(points: list[tuple[float, float]], max_pts: int) -> list[tuple[float, float]]:
    if len(points) <= max_pts:
        return points
    step = (len(points) - 1) / (max_pts - 1)
    return [points[round(i * step)] for i in range(max_pts)]


# ---------------------------------------------------------------------- overpass
def overpass(query: str, tries: int = 12) -> dict[str, Any]:
    """POST to the Overpass mirrors in turn; back off on 429 / 504 (busy servers)."""
    for i in range(tries):
        url = OVERPASS[i % len(OVERPASS)]
        try:
            r = httpx.post(url, data={"data": query}, headers=UA, timeout=300)
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                data = r.json()
                if "remark" in data and "runtime error" in str(data["remark"]):
                    print(f"  {url}: {data['remark'][:120]}", file=sys.stderr)
                else:
                    return data
            else:
                print(f"  {url}: HTTP {r.status_code}", file=sys.stderr)
        except (httpx.HTTPError, ValueError) as exc:
            print(f"  {url}: {type(exc).__name__}", file=sys.stderr)
        time.sleep(min(90, 10 * (i + 1)))
    raise SystemExit("Overpass API unavailable — try again later")


def _tiles(bbox: tuple[float, float, float, float], n: int = 2) -> list[str]:
    s, w, no, e = bbox
    dy, dx = (no - s) / n, (e - w) / n
    return [f"({s + i * dy},{w + j * dx},{s + (i + 1) * dy},{w + (j + 1) * dx})" for i in range(n) for j in range(n)]


def fetch_roads(bbox: tuple[float, float, float, float], classes: tuple[str, ...]) -> dict[str, Any]:
    # 4 tiles (lighter queries); ways crossing a tile edge come back twice and
    # are de-duplicated by way id.
    ways: dict[int, Any] = {}
    for tb in _tiles(bbox):
        part = overpass(f'[out:json][timeout:180];way["highway"~"^({"|".join(classes)})$"]{tb};out tags geom;')
        for el in part.get("elements", []):
            ways[el["id"]] = el
        time.sleep(3)
    return {"elements": list(ways.values())}


def fetch_wide_depots(bbox: tuple[float, float, float, float], pad: float = 0.08) -> dict[str, Any]:
    """Fire stations in a wider box (used only when the core box has none)."""
    s, w, n, e = bbox
    return overpass(f'[out:json][timeout:120];nwr["amenity"="fire_station"]({s - pad},{w - pad},{n + pad},{e + pad});out tags center;')


def fetch_police(bbox: tuple[float, float, float, float], pad: float = 0.03) -> dict[str, Any]:
    s, w, n, e = bbox
    return overpass(f'[out:json][timeout:120];nwr["amenity"="police"]["name"]({s - pad},{w - pad},{n + pad},{e + pad});out tags center;')


def fetch(bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    s, w, n, e = bbox
    bb = f"({s},{w},{n},{e})"
    roads = fetch_roads(bbox, ROAD_CLASSES)
    water = overpass(
        f'[out:json][timeout:240];(way["waterway"~"^(river|canal|drain|stream|riverbank)$"]{bb};'
        f'way["natural"~"^(water|coastline)$"]{bb};);out tags geom;'
    )
    time.sleep(3)
    pois = overpass(
        f'[out:json][timeout:240];(nwr["amenity"="fire_station"]{bb};nwr["leisure"="stadium"]["name"]{bb};'
        f'nwr["amenity"~"^(university|college|school|community_centre)$"]["name"]{bb};'
        f'node["place"~"^(suburb|neighbourhood|quarter)$"]["name"]{bb};);out tags center;'
    )
    return {"roads": roads, "water": water, "pois": pois}


# ------------------------------------------------------------------------ build
def build_graph(roads_json: dict[str, Any]) -> tuple[nx.Graph, dict[tuple[float, float], str]]:
    """Fine graph: one node per OSM vertex (rounded), edges carry way name/class."""
    g = nx.Graph()
    for el in roads_json.get("elements", []):
        geom = el.get("geometry") or []
        tags = el.get("tags") or {}
        cls = str(tags.get("highway", "")).replace("_link", "")
        name = tags.get("name:en") or tags.get("name") or tags.get("ref")
        bridge = str(tags.get("bridge", "no")).lower() not in ("no", "")
        pts = [(round(p["lat"], 6), round(p["lon"], 6)) for p in geom]
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            g.add_edge(a, b, km=hav_km(a, b), name=name, cls=cls, way=el["id"], bridge=bool(bridge))
    return g, {}


def merge_close(g: nx.Graph) -> nx.Graph:
    """Union junction vertices within MERGE_M (dual carriageways, roundabouts)."""
    junction = [n for n in g.nodes if g.degree(n) != 2]
    cell = MERGE_M / 1000 / 111.32
    grid: dict[tuple[int, int], list] = defaultdict(list)
    for n in junction:
        grid[(int(n[0] / cell), int(n[1] / cell))].append(n)
    parent = {n: n for n in junction}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (gx, gy), members in grid.items():
        near = [m for dx in (-1, 0, 1) for dy in (-1, 0, 1) for m in grid.get((gx + dx, gy + dy), [])]
        for a in members:
            for b in near:
                if a < b and hav_km(a, b) * 1000 <= MERGE_M:
                    parent[find(a)] = find(b)
    groups: dict[Any, list] = defaultdict(list)
    for n in junction:
        groups[find(n)].append(n)
    mapping = {}
    for members in groups.values():
        if len(members) > 1:
            c = (round(sum(m[0] for m in members) / len(members), 6), round(sum(m[1] for m in members) / len(members), 6))
            for m in members:
                mapping[m] = c
    h = nx.relabel_nodes(g, mapping, copy=True)
    h.remove_edges_from(list(nx.selfloop_edges(h)))
    return h


def contract(g: nx.Graph) -> list[dict[str, Any]]:
    """Chains of degree-2 vertices → one edge per junction pair with geometry."""
    keep = {n for n in g.nodes if g.degree(n) != 2}
    if not keep:  # a pure ring: keep one vertex
        keep = {next(iter(g.nodes))}
    seen: set[frozenset] = set()
    out = []
    for start in keep:
        for nb in g.neighbors(start):
            first = frozenset((start, nb))
            if first in seen:
                continue
            path, names, prev, cur = [start, nb], defaultdict(float), start, nb
            seen.add(first)
            d = g.edges[start, nb]
            names[(d.get("name"), d.get("cls"))] += d["km"]
            km = d["km"]
            bridge_km = d["km"] if d.get("bridge") else 0.0
            while cur not in keep:
                nxt = next((x for x in g.neighbors(cur) if x != prev), None)
                if nxt is None:
                    break
                e = frozenset((cur, nxt))
                if e in seen:
                    break
                seen.add(e)
                d = g.edges[cur, nxt]
                names[(d.get("name"), d.get("cls"))] += d["km"]
                km += d["km"]
                bridge_km += d["km"] if d.get("bridge") else 0.0
                prev, cur = cur, nxt
                path.append(cur)
            (name, cls), _ = max(names.items(), key=lambda kv: kv[1])
            out.append({"u": path[0], "v": path[-1], "km": km, "name": name, "cls": cls, "pts": path,
                        "bridge": bridge_km >= 0.5 * km})
    return out


def split_sections(eds: list[dict[str, Any]], max_km: float) -> list[list[dict[str, Any]]]:
    """Walk a road's edges through shared junctions (BFS) and cut the walk
    into consecutive sections of about `max_km`."""
    if sum(e["km"] for e in eds) <= max_km * 1.25:
        return [eds]
    at_node: dict[Any, list[int]] = defaultdict(list)
    for i, e in enumerate(eds):
        at_node[e["u"]].append(i)
        at_node[e["v"]].append(i)
    left = set(range(len(eds)))
    sections, cur, cur_km = [], [], 0.0
    while left:
        queue = [min(left, key=lambda i: (len(at_node[eds[i]["u"]]) + len(at_node[eds[i]["v"]]), i))]
        left.discard(queue[0])
        while queue:
            i = queue.pop(0)
            cur.append(eds[i])
            cur_km += eds[i]["km"]
            if cur_km >= max_km:
                sections.append(cur)
                cur, cur_km = [], 0.0
            for n in (eds[i]["u"], eds[i]["v"]):
                for j in at_node[n]:
                    if j in left:
                        left.discard(j)
                        queue.append(j)
    if cur:
        if sections and cur_km < max_km / 3:
            sections[-1].extend(cur)  # fold a short tail into the previous section
        else:
            sections.append(cur)
    return sections


def water_kind(tags: dict[str, Any]) -> str:
    w = str(tags.get("waterway") or "")
    if w in ("river", "riverbank"):
        return "river"
    if w in ("canal", "drain", "stream"):
        return w
    if tags.get("natural") == "coastline":
        return "coastline"
    if tags.get("water") in ("river", "canal"):
        return "river" if tags.get("water") == "river" else "canal"
    return "water"  # lakes, ponds, tanks


def water_lines(water_json: dict[str, Any]) -> list[tuple[str, list[tuple[float, float]]]]:
    lines = []
    for el in water_json.get("elements", []):
        pts = [(p["lat"], p["lon"]) for p in el.get("geometry") or []]
        if len(pts) >= 2:
            lines.append((water_kind(el.get("tags") or {}), pts))
    return lines


def dist_to_kind(p: tuple[float, float], lines, kind: str, cap_km: float) -> float:
    best = cap_km
    for k, pts in lines:
        if k != kind:
            continue
        for a, b in zip(pts, pts[1:]):
            # cheap reject: segment latitude band further than `best`
            if min(a[0], b[0]) - best / 111 > p[0] or max(a[0], b[0]) + best / 111 < p[0]:
                continue
            best = min(best, point_seg_km(p, a, b))
    return best


def exposure_at(p: tuple[float, float], lines) -> tuple[float, dict[str, float]]:
    """Proxy, not a hydraulic model: max over water kinds of amplitude·exp(-d/L).
    Returns (exposure, distance km to each kind within reach)."""
    best = EXPOSURE_FLOOR
    near: dict[str, float] = {}
    for kind, (amp, L) in WATER_WEIGHT.items():
        d = dist_to_kind(p, lines, kind, cap_km=6 * L)
        if d < 6 * L:
            near[kind] = round(d, 3)
            best = max(best, amp * math.exp(-d / L))
    return round(min(0.92, best), 3), near


def dist_to_water(p: tuple[float, float], lines) -> float:
    return min((dist_to_kind(p, lines, k, 5.0) for k in WATER_WEIGHT), default=5.0)


CWC_GAUGES = ROOT / "backend" / "data" / "gauges_cwc.json"


def cwc_gauge(cid: str, center: tuple[float, float]) -> dict[str, Any] | None:
    """F17: the city's CWC level-forecast station (official bulletin levels),
    if one is listed and within GAUGE_MAX_KM. No catchment attributes exist for
    it — the ML model gets none (never borrowed from a far-away gauge)."""
    data = json.loads(CWC_GAUGES.read_text(encoding="utf-8")) if CWC_GAUGES.exists() else {}
    g = data.get(cid)
    if not g:
        return None
    km = hav_km(center, (g["lat"], g["lon"]))
    if km > GAUGE_MAX_KM:
        return None
    return {
        "available": True,
        "gauge_id": g["cwc_station_id"],
        "station": g["station"],
        "river": g["river"],
        "lat": g["lat"],
        "lon": g["lon"],
        "km_from_centre": round(km, 1),
        "warning_level_m": g["warning_level_m"],
        "danger_level_m": g["danger_level_m"],
        "hfl_m": g.get("hfl_m"),
        "hfl_date": g.get("hfl_date"),
        "source": "CWC (official daily flood bulletin)",
        "source_url": g["source_url"],
        "retrieved_at": g["retrieved_at"],
        "location_source": g.get("location_source"),
        "catchment": None,
        "ml_note": "ML model not applicable to this gauge — no catchment attributes (CWC-only gauge)",
    }


def nearest_gauge(center: tuple[float, float], cid: str | None = None) -> dict[str, Any] | None:
    meta = pd.read_csv(DATASET / "metadata_indofloods.csv")
    meta["km"] = [hav_km(center, (r.Latitude, r.Longitude)) for r in meta.itertuples()]
    row = meta.nsmallest(1, "km").iloc[0]
    if row["km"] > GAUGE_MAX_KM:
        cwc = cwc_gauge(cid, center) if cid else None
        if cwc:
            return cwc
        return {"available": False, "nearest_km": round(float(row["km"]), 1), "nearest_station": row["Station"],
                "reason": f"no INDOFLOODS or CWC gauge within {GAUGE_MAX_KM:g} km — rainfall-driven city"}
    cat = pd.read_csv(DATASET / "catchment_characteristics_indofloods.csv")
    crow = cat[cat["GaugeID"] == row["GaugeID"]]
    catchment = {}
    if len(crow):
        for k, v in crow.iloc[0].items():
            if k != "GaugeID" and pd.notna(v):
                catchment[k] = v.item() if hasattr(v, "item") else v
    return {
        "available": True,
        "gauge_id": row["GaugeID"],
        "station": row["Station"],
        "river": str(row["River Name/ Tributory/ SubTributory"]),
        "lat": float(row["Latitude"]),
        "lon": float(row["Longitude"]),
        "km_from_centre": round(float(row["km"]), 1),
        "warning_level_m": float(row["Warning Level"]),
        "danger_level_m": float(row["Danger Level"]),
        "source": "INDOFLOODS metadata (CWC levels)",
        "catchment": catchment,
    }


def spread_pick(items: list[dict[str, Any]], k: int, key=None) -> list[dict[str, Any]]:
    """Farthest-point sampling so picks cover the whole city, best-ranked first."""
    if len(items) <= k:
        return items
    chosen = [items[0]]
    while len(chosen) < k:
        nxt = max(items, key=lambda it: min(hav_km((it["lat"], it["lon"]), (c["lat"], c["lon"])) for c in chosen)
                  - (key(it) if key else 0))
        if nxt in chosen:
            break
        chosen.append(nxt)
    return chosen


def build_city(cid: str, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = CITY_SPECS[cid]
    s, w, n, e = spec["bbox"]
    center = ((s + n) / 2, (w + e) / 2)
    raw = raw if raw is not None else fetch(spec["bbox"])

    def _graph(road_json):
        fine, _ = build_graph(road_json)
        fine = fine.subgraph(max(nx.connected_components(fine), key=len)).copy()
        merged = merge_close(fine)
        merged = merged.subgraph(max(nx.connected_components(merged), key=len)).copy()
        return contract(merged)

    edges = _graph(raw["roads"])
    road_classes = list(ROAD_CLASSES)
    if len({x for ed in edges for x in (ed["u"], ed["v"])}) < MIN_JUNCTIONS:
        # Sparse main-road network (e.g. Guwahati): add tertiary roads too.
        if "roads_tertiary" not in raw:
            print(f"[{cid}] sparse network — fetching tertiary roads…")
            raw["roads_tertiary"] = fetch_roads(spec["bbox"], ("tertiary", "tertiary_link"))
        both = {el["id"]: el for el in raw["roads"]["elements"] + raw["roads_tertiary"]["elements"]}
        edges = _graph({"elements": list(both.values())})
        road_classes += ["tertiary", "tertiary_link"]
    lines = water_lines(raw["water"])

    # junction ids
    nodes = sorted({x for ed in edges for x in (ed["u"], ed["v"])})
    nid = {p: f"{spec['prefix']}-N{i:04d}" for i, p in enumerate(nodes)}

    # Roads = SECTIONS of named roads (≈ SECTION_KM each), so a flood closes the
    # wet stretch of a long road, not the whole road. Unnamed chains stand alone.
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unnamed = 0
    for ed in edges:
        if ed["name"]:
            by_name[str(ed["name"])].append(ed)
        else:
            unnamed += 1
            by_name[f"__unnamed_{unnamed}"].append(ed)
    by_key: dict[str, list[dict[str, Any]]] = {}
    for name, eds in by_name.items():
        parts = split_sections(eds, SECTION_KM)
        for j, part in enumerate(parts, start=1):
            by_key[name if len(parts) == 1 else f"{name} (part {j})"] = part
    ordered = sorted(by_key.items(), key=lambda kv: -sum(x["km"] for x in kv[1]))
    roads, graph_edges, edge_info = [], [], {}
    for i, (key, eds) in enumerate(ordered, start=1):
        rid = f"{spec['prefix']}-R{i:03d}"
        cls = max({x["cls"] for x in eds}, key=lambda c: sum(x["km"] for x in eds if x["cls"] == c))
        exp = 0.0
        for ed in eds:
            mid = ed["pts"][len(ed["pts"]) // 2]
            ex = max(exposure_at(p, lines)[0] for p in (ed["pts"][0], mid, ed["pts"][-1]))
            if ed.get("bridge"):  # elevated deck: being ON the river is not being flooded
                ex = min(ex, BRIDGE_CAP)
            ed["exposure"] = ex
            exp = max(exp, ex)
            u, v = nid[ed["u"]], nid[ed["v"]]
            graph_edges.append([u, v, rid])
            edge_info[f"{u}|{v}"] = {"km": round(ed["km"], 4), "pts": [list(p) for p in thin(ed["pts"], 14)]}
        longest = max(eds, key=lambda x: x["km"])
        mid = longest["pts"][len(longest["pts"]) // 2]
        roads.append(
            {
                "road_id": rid,
                "name": key if not key.startswith("__unnamed") else f"Unnamed {cls} road",
                "bridge": any(x.get("bridge") for x in eds),
                "lat": mid[0],
                "lon": mid[1],
                "highway": cls,
                "length_km": round(sum(x["km"] for x in eds), 3),
                "blocked": False,
                "accessible": True,
                "flood_exposure": round(exp, 3),
                "flood_exposure_source": "proxy: distance to mapped river/coast/canal/pond/drain (OSM), weighted by kind; bridges capped",
                "traffic": TRAFFIC_BY_CLASS.get(cls, 0.4),
                "traffic_source": "assumed by road class",
            }
        )

    # POIs
    depots, shelters, places = [], [], []
    for el in raw["pois"].get("elements", []):
        tags = el.get("tags") or {}
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None:
            continue
        name = tags.get("name:en") or tags.get("name")
        if name:
            name = str(name).split(";")[0].strip()
        if tags.get("amenity") == "fire_station":
            depots.append({"name": name or "Fire station", "lat": lat, "lon": lon, "osm": f"{el['type']}/{el['id']}"})
        elif tags.get("place"):
            places.append({"name": name, "lat": lat, "lon": lon, "population": int(tags["population"]) if str(tags.get("population", "")).isdigit() else None,
                           "osm": f"{el['type']}/{el['id']}"})
        elif name:
            kind = "stadium" if tags.get("leisure") == "stadium" else tags.get("amenity")
            if kind in CAPACITY_BY_TYPE:
                shelters.append({"name": name, "lat": lat, "lon": lon, "kind": kind, "osm": f"{el['type']}/{el['id']}"})

    shelters = [s_ for s_ in shelters if not any(bad in s_["name"].lower() for bad in NOT_A_SHELTER)]
    for s_ in shelters:
        s_["exposure"], _ = exposure_at((s_["lat"], s_["lon"]), lines)
    # Shelters: strongest building types first, then the lowest flood-exposure
    # proxy; only places below 0.4 exposure; spread across the city.
    shelters.sort(key=lambda x: (SHELTER_PRIORITY.index(x["kind"]), x["exposure"]))
    seen_names: set[str] = set()
    uniq = []
    for s_ in shelters:
        if s_["name"] not in seen_names and s_["exposure"] < 0.4:
            seen_names.add(s_["name"])
            uniq.append(s_)
    picked = spread_pick(uniq, MAX_SHELTERS)
    shelters_out = [
        {
            "shelter_id": f"{spec['prefix']}-S{i:02d}",
            "name": s_["name"],
            "lat": round(s_["lat"], 6),
            "lon": round(s_["lon"], 6),
            "kind": s_["kind"],
            "capacity": CAPACITY_BY_TYPE[s_["kind"]],
            "capacity_source": f"assumed by building type ({s_['kind']})",
            "occupancy": 0,
            "status": "open",
            "flood_risk": s_["exposure"],
            "flood_risk_source": "same water-distance proxy as roads",
            "zone": spec["name"],
            "osm": s_["osm"],
        }
        for i, s_ in enumerate(picked, start=1)
    ]
    depot_scope = "OSM fire stations inside the mapped area"
    if not depots:
        if "depots_wide" not in raw:
            print(f"[{cid}] no fire station inside the box — searching a wider area…")
            raw["depots_wide"] = fetch_wide_depots(spec["bbox"])
        for el in raw["depots_wide"].get("elements", []):
            c = el.get("center") or el
            if c.get("lat") is None:
                continue
            nm = ((el.get("tags") or {}).get("name:en") or (el.get("tags") or {}).get("name") or "Fire station")
            depots.append({"name": str(nm).split(";")[0].strip(), "lat": c["lat"], "lon": c["lon"], "osm": f"{el['type']}/{el['id']}"})
        depot_scope = "OSM fire stations within ~9 km of the mapped area (none inside it)"
    if len(depots) < MIN_DEPOTS:
        # Thin fire-station mapping (e.g. Patna): police stations — also real
        # OSM places that hold rescue crews — fill the remaining depot slots.
        if "police_wide" not in raw:
            print(f"[{cid}] only {len(depots)} fire station(s) — adding police stations…")
            raw["police_wide"] = fetch_police(spec["bbox"])
        police = []
        for el in raw["police_wide"].get("elements", []):
            c = el.get("center") or el
            nm = (el.get("tags") or {}).get("name:en") or (el.get("tags") or {}).get("name")
            if c.get("lat") is None or not nm:
                continue
            police.append({"name": str(nm).split(";")[0].strip(), "lat": c["lat"], "lon": c["lon"],
                           "osm": f"{el['type']}/{el['id']}", "kind": "police"})
        police.sort(key=lambda d: hav_km(center, (d["lat"], d["lon"])))
        depots = depots + spread_pick(police, MAX_DEPOTS - len(depots))
        depot_scope += " + OSM police stations (too few fire stations mapped)"
    depots.sort(key=lambda d: hav_km(center, (d["lat"], d["lon"])))
    named = [d for d in depots if d["name"] != "Fire station"]
    depot_pick = spread_pick(named + [d for d in depots if d not in named], MAX_DEPOTS)
    teams = [
        {"team_id": f"{spec['prefix']}-T{i:02d}", "name": d["name"] if d["name"] != "Fire station" else f"Fire station ({d['osm']})",
         "lat": round(d["lat"], 6), "lon": round(d["lon"], 6), "status": "AVAILABLE", "capacity": 8,
         "capacity_source": "assumed crew size", "osm": d["osm"], "scope": depot_scope,
         "kind": d.get("kind", "fire_station")}
        for i, d in enumerate(depot_pick, start=1)
    ]
    # Flood zones: named suburbs with the highest exposure proxy, spread out.
    places = [p for p in places if p["name"]]
    for p in places:
        p["exposure"], p["near_water"] = exposure_at((p["lat"], p["lon"]), lines)
    places.sort(key=lambda p: -p["exposure"])
    zone_pick = spread_pick(places[: max(MAX_ZONES * 4, 12)], MAX_ZONES)
    zones = [
        {"zone_id": f"{spec['prefix']}-Z{i}", "name": p["name"], "lat": round(p["lat"], 6), "lon": round(p["lon"], 6),
         "population": p["population"], "flood_exposure": p["exposure"], "near_water_km": p["near_water"], "osm": p["osm"],
         "selection": "named OSM suburb with a high water-distance exposure proxy"}
        for i, p in enumerate(zone_pick, start=1)
    ]
    rank = {"river": 0, "coastline": 1, "canal": 2, "water": 3, "stream": 4, "drain": 5}
    water_out = [{"kind": k, "pts": [[round(a, 5), round(b, 5)] for a, b in thin(pts, 40)]} for k, pts in lines]
    water_out.sort(key=lambda w: (rank.get(w["kind"], 9), -len(w["pts"])))

    return {
        "id": cid,
        "name": spec["name"],
        "state": spec["state"],
        "why": spec["why"],
        "bbox": list(spec["bbox"]),
        "center": [round(center[0], 5), round(center[1], 5)],
        "zoom": 12,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "attribution": "© OpenStreetMap contributors (ODbL) · gauges: INDOFLOODS / CWC",
        "gauge": nearest_gauge(center, cid),
        "graph_nodes": {nid[p]: [p[0], p[1]] for p in nodes},
        "graph_edges": graph_edges,
        "edge_info": edge_info,
        "roads": roads,
        "shelters": shelters_out,
        "rescue_teams": teams,
        "zones": zones,
        "water": water_out[:120],
        "counts": {
            "junctions": len(nodes),
            "road_segments": len(graph_edges),
            "named_roads": len(roads),
            "shelters": len(shelters_out),
            "depots": len(teams),
            "zones": len(zones),
            "water_features": len(lines),
        },
        "road_classes": road_classes,
        "exposure_weights": {k: {"amplitude": a, "decay_km": L} for k, (a, L) in WATER_WEIGHT.items()},
        "notes": [
            "Road flood_exposure is a proxy from distance to mapped water (weighted by kind), not a hydraulic model.",
            "Shelter capacity and road traffic are assumed by type/class (OSM has no such data).",
            "Rescue depots are OSM fire stations.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build a city's geography from OpenStreetMap")
    ap.add_argument("--city", choices=sorted(CITY_SPECS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--raw-dir", default=str(RAW_DIR), help="cache of raw Overpass JSON (re-used on re-run)")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache and download again")
    ap.add_argument("--gauges-only", action="store_true",
                    help="F17: only re-pick the river gauge of an existing city file (no OSM rebuild)")
    args = ap.parse_args(argv)
    ids = sorted(CITY_SPECS) if args.all else [args.city]
    if not ids or ids == [None]:
        ap.error("--city or --all")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.gauges_only:
        for cid in ids:
            path = OUT_DIR / f"{cid}.json"
            city = json.loads(path.read_text(encoding="utf-8"))
            city["gauge"] = nearest_gauge(tuple(city["center"]), cid)
            city["attribution"] = city["attribution"].replace("gauges: INDOFLOODS", "gauges: INDOFLOODS / CWC").replace("/ CWC / CWC", "/ CWC")
            path.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
            g = city["gauge"]
            print(f"[{cid}] gauge={g.get('station') if g['available'] else 'none'} ({g.get('source') or g.get('reason')})")
        return 0
    for cid in ids:
        cache = Path(args.raw_dir) / f"{cid}.raw.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        if cache.exists() and not args.refresh:
            raw = json.loads(cache.read_text(encoding="utf-8"))
        else:
            print(f"[{cid}] downloading from Overpass…")
            raw = fetch(CITY_SPECS[cid]["bbox"])
            cache.write_text(json.dumps(raw), encoding="utf-8")
        keys = set(raw)
        city = build_city(cid, raw)
        if set(raw) != keys:  # fallbacks fetched (tertiary roads / wide depots): keep them cached
            cache.write_text(json.dumps(raw), encoding="utf-8")
        path = OUT_DIR / f"{cid}.json"
        path.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
        print(f"[{cid}] {city['counts']} gauge={'yes' if city['gauge']['available'] else 'no'} -> {path} "
              f"({path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
