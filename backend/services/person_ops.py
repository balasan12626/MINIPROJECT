"""Per-person SOS ops — the canonical rescue stage machine.

    queued → assigned → en_route → to_shelter → rescued

Stage timing is driven by real travel time, not a fixed step:

* queued      — admin triage. The admin dispatches one SOS every
                DISPATCH_SECONDS in vulnerable-first order. An SOS that needs an
                ambulance stays queued while all AMBULANCE_POOL units are busy.
* assigned    — MOBILISE_SECONDS crew roll-out at the unit's base.
* en_route    — unit base → person along a flood-aware road route; duration is
                that route's travel time (weighted km / RESCUE_SPEED_KMH).
* to_shelter  — person → shelter, route recomputed at pickup against the road
                state at that moment (blockages since dispatch are honoured).
* rescued     — terminal.

Travel time is simulated minutes; the demo clock runs TIME_SCALE× faster than
the wall clock (1 wall second = 2 simulated minutes), so a 14-minute drive plays
out in 7 s. Every transition is stamped at the moment it was due (not at the
moment a poll happened to notice), so the timeline is exact regardless of
polling cadence. Each row carries `ops_stage_seconds` (wall seconds the current
stage lasts) so the frontend can interpolate a unit's position along the route.

Unit positions are NOT stored anywhere — the frontend derives them from
`ops_stage_at` + `ops_stage_seconds` + the route polyline.
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.services.priority import needs_ambulance, vulnerability_label
from backend.services.route_engine import RESCUE_SPEED_KMH, travel_minutes
from backend.utils.geo import haversine_km

# ---- clock ------------------------------------------------------------------
TIME_SCALE = 120.0  # simulated seconds per wall-clock second (1 wall s = 2 sim min)
DISPATCH_SECONDS = 3.0  # wall s between successive admin dispatches
MOBILISE_SECONDS = 2.0  # wall s crew roll-out once assigned
MIN_LEG_SECONDS = 2.0  # floor so a unit parked next to the person still visibly moves

STAGES = ["queued", "assigned", "en_route", "to_shelter", "rescued"]

STAGE_LABEL = {
    "queued": "In SOS queue — waiting for dispatch",
    "assigned": "Unit + shelter assigned (K-means team linked)",
    "en_route": "Unit en route to the person",
    "to_shelter": "Picked up — transporting to shelter",
    "rescued": "Completed — person at shelter (rescued)",
    "merged": "Merged — duplicate of another SOS (operator)",
}

AMBULANCE_POOL = [f"Ambulance Unit {i}" for i in range(1, 11)]

# F16: a what-if plays the stage machine in a worker thread while the live run
# keeps ticking. Its pool / route chooser live in context variables (copied
# into the thread by asyncio.to_thread), never in the module globals above.
_POOL_OVERRIDE: ContextVar[list[str] | None] = ContextVar("ops_pool", default=None)
_CHOOSER_OVERRIDE: ContextVar[str | None] = ContextVar("ops_chooser", default=None)


def ambulance_pool() -> list[str]:
    """The ambulances of the current context (live run = AMBULANCE_POOL)."""
    return _POOL_OVERRIDE.get() or AMBULANCE_POOL


def route_chooser() -> str:
    return _CHOOSER_OVERRIDE.get() or ROUTE_CHOOSER


@contextmanager
def isolated(pool: list[str] | None = None, chooser: str | None = None):
    """Run stage-machine calls with their own pool / route chooser (what-if)."""
    t1, t2 = _POOL_OVERRIDE.set(pool), _CHOOSER_OVERRIDE.set(chooser)
    try:
        yield
    finally:
        _POOL_OVERRIDE.reset(t1)
        _CHOOSER_OVERRIDE.reset(t2)

# Shelters person_ops may assign. Every name must resolve to coordinates via
# seed.SHELTERS or rescue_desk.SHELTERS (frontend mirror: data/rescueAssets.js).
SHELTER_POOL = [
    "Delhi University Sports Complex",
    "Talkatora Indoor Stadium",
    "Jawaharlal Nehru Stadium",
    "Commonwealth Games Village Hall",
    "Yamuna Sports Complex Shelter",
    "Thyagaraj Sports Complex",
    "Chhatrasal Stadium",
    "IIT Delhi Lecture Hall Complex",
    "Akshardham Community Shelter",
]

ACTIVE_STAGES = {"assigned", "en_route", "to_shelter"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: Any) -> datetime | None:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat()


def leg_seconds(sim_minutes: float) -> float:
    """Wall-clock seconds a leg of `sim_minutes` takes on the demo clock."""
    return max(MIN_LEG_SECONDS, float(sim_minutes) * 60.0 / TIME_SCALE)


def clock_info() -> dict[str, Any]:
    return {
        "time_scale": TIME_SCALE,
        "speed_kmh": RESCUE_SPEED_KMH,
        "dispatch_seconds": DISPATCH_SECONDS,
        "mobilise_seconds": MOBILISE_SECONDS,
        "note": f"Stage duration = route travel time; 1 wall second = {TIME_SCALE / 60:g} simulated minutes.",
    }


# ---- geography ----------------------------------------------------------------


def shelter_registry(overrides: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """name -> {lat, lon, capacity, occupancy, closed}. Seed wins; desk fills gaps.
    Operator `overrides` ({name: {closed, capacity}}) are applied last;
    `base_capacity` keeps the seeded number so a reset can restore it."""
    from backend.geo.cities import LEGACY, active_id
    from backend.services.rescue_desk import SHELTERS as DESK
    from backend.services.seed import SHELTERS as SEED

    # The rescue-desk shelters are Delhi demo places: only for the demo network.
    desk = list(DESK) if active_id() == LEGACY else []
    out: dict[str, dict[str, Any]] = {}
    for s in desk + list(SEED):
        cap = int(s.get("capacity") or 0)
        out[s["name"]] = {
            "name": s["name"],
            "lat": float(s["lat"]),
            "lon": float(s["lon"]),
            "capacity": cap,
            "base_capacity": cap,
            "occupancy": int(s.get("occupancy") or 0),
            "closed": False,
            # F27: how the seeded number was made (Sphere footprint or assumed by type).
            "capacity_source": s.get("capacity_source") or "seed data",
            "capacity_detail": {k: s[k] for k in ("area_m2", "floor_area_m2", "buildings", "levels_source", "usable_share",
                                                   "m2_per_person", "capacity_assumed_by_type") if k in s} or None,
        }
    for name, ov in (overrides or {}).items():
        if name in out:
            if ov.get("capacity") is not None:
                out[name]["capacity"] = max(0, int(ov["capacity"]))
            out[name]["closed"] = bool(ov.get("closed"))
    return out


def _team_base(row: dict[str, Any], teams: list[dict[str, Any]]) -> tuple[float, float] | None:
    from backend.services.seed import RESCUE_TEAMS

    name = row.get("assigned_team_name") or row.get("assigned_team")
    for t in list(teams or []) + list(RESCUE_TEAMS):
        if name and (t.get("name") == name or t.get("team_id") == name) and t.get("lat") is not None:
            return float(t["lat"]), float(t["lon"])
    return None


def _nearest_depot(lat: float, lon: float, teams: list[dict[str, Any]]) -> dict[str, Any] | None:
    from backend.services.seed import RESCUE_TEAMS

    pool = [t for t in (list(teams or []) or list(RESCUE_TEAMS)) if t.get("lat") is not None]
    if not pool:
        return None
    return min(pool, key=lambda t: haversine_km(lat, lon, float(t["lat"]), float(t["lon"])))


QAOA_CANDIDATES = 4  # Yen candidates per trip = qubits in the QAOA circuit
# "qaoa" (live app) or "dijkstra" (headless batch evaluation, F12: shortest
# weighted path only — no candidate generation, no QAOA, for speed).
ROUTE_CHOOSER = "qaoa"


MAX_ROUTE_POINTS = 160  # polylines are served every poll — keep them light


def _thin_poly(pts: list[list[float]], max_pts: int) -> list[list[float]]:
    """Drop near-collinear / duplicate vertices, then evenly down-sample; the
    ends are kept so a unit starts and arrives exactly where it should."""
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    if len(out) <= max_pts:
        return out
    step = (len(out) - 1) / (max_pts - 1)
    return [out[round(i * step)] for i in range(max_pts)]


def _km_of(points: list[list[float]]) -> float:
    return sum(haversine_km(p[0], p[1], q[0], q[1]) for p, q in zip(points, points[1:]))


def route_candidates(
    a: tuple[float, float], b: tuple[float, float], roads: list[dict[str, Any]] | None, k: int | None = None
) -> dict[str, Any]:
    """Up to `k` (default QAOA_CANDIDATES) Yen k-shortest candidate paths over
    the road graph with blocked roads removed; candidate 0 is the Dijkstra
    shortest path. Shared by road_route (live) and scripts/bench_routes.py, so
    the benchmark measures exactly what the live app does.

    Returns {"cands": [...], "no_open_road": bool}. An empty `cands` means no
    open path: `no_open_road` is True when the two ends are distinct junctions
    (every road between them closed), False when they share one junction."""
    from itertools import islice

    import networkx as nx

    from backend.services.route_engine import _nearest_node, build_graph
    from backend.services.seed import GRAPH_NODES, ROADS

    a = (float(a[0]), float(a[1]))
    b = (float(b[0]), float(b[1]))
    g = build_graph(list(roads or ROADS))
    src, dst = _nearest_node(*a), _nearest_node(*b)
    if src != dst and not (src in g and dst in g and nx.has_path(g, src, dst)):
        # The nearest junction can be cut off (e.g. a unit standing on the
        # road that was just closed). Try the next-nearest junctions at both
        # ends and take the closest pair that is still connected.
        def _near(pt: tuple[float, float]) -> list[str]:
            return sorted(GRAPH_NODES, key=lambda n: haversine_km(pt[0], pt[1], *GRAPH_NODES[n]))[:3]

        pairs = sorted(
            ((u, v) for u in _near(a) for v in _near(b) if u != v and nx.has_path(g, u, v)),
            key=lambda uv: haversine_km(a[0], a[1], *GRAPH_NODES[uv[0]]) + haversine_km(*GRAPH_NODES[uv[1]], b[0], b[1]),
        )
        if pairs:
            src, dst = pairs[0]

    from backend.services.route_engine import edge_points

    def _poly(nodes: list[str]) -> list[list[float]]:
        # Follows the real road shape between junctions when the city has it.
        pts = [[a[0], a[1]], list(GRAPH_NODES[nodes[0]])]
        for u, v in zip(nodes, nodes[1:]):
            pts.extend(edge_points(u, v)[1:])
        pts.append([b[0], b[1]])
        return _thin_poly(pts, MAX_ROUTE_POINTS)

    if not (src != dst and src in g and dst in g and nx.has_path(g, src, dst)):
        return {"cands": [], "no_open_road": src != dst}

    cands = []
    for nodes in islice(nx.shortest_simple_paths(g, src, dst, weight="weight"), k or QAOA_CANDIDATES):
        edges = list(zip(nodes, nodes[1:]))
        cost = haversine_km(a[0], a[1], *GRAPH_NODES[nodes[0]]) + haversine_km(*GRAPH_NODES[nodes[-1]], b[0], b[1])
        cost += sum(float(g.edges[u, v].get("weight") or 0) for u, v in edges)
        pts = _poly(nodes)
        cands.append(
            {
                "nodes": nodes,
                "road_ids": sorted({str(g.edges[u, v].get("road_id")) for u, v in edges if g.edges[u, v].get("road_id")}),
                "points": pts,
                "weighted_km": cost,
                # (road_id, weighted km) per edge, in driving order — for F10's
                # "will this road still be open when the unit gets there?"
                "lead_km": haversine_km(a[0], a[1], *GRAPH_NODES[nodes[0]]),
                "edge_seq": [(str(g.edges[u, v].get("road_id")), float(g.edges[u, v].get("weight") or 0)) for u, v in edges],
                # worst edge exposure — the QUBO hazard term (candidate_costs)
                "hazard": max((float(g.edges[u, v].get("flood_exposure") or 0) for u, v in edges), default=0.0),
                # exposure × length summed over the path — reported by the benchmark
                "hazard_km": sum(
                    float(g.edges[u, v].get("flood_exposure") or 0) * float(g.edges[u, v].get("distance_km") or 0)
                    for u, v in edges
                ),
                "km": _km_of(pts),
            }
        )
    return {"cands": cands, "no_open_road": False}


def first_closed_road(cand: dict[str, Any], closing: dict[str, float] | None, depart_min: float = 0.0) -> str | None:
    """F10: the first road on `cand` that the flood rule closes BEFORE the unit
    gets there (arrival = depart + travel time to the start of that road)."""
    if not closing:
        return None
    t = depart_min + travel_minutes(cand.get("lead_km") or 0.0)
    for rid, w in cand.get("edge_seq") or []:
        c = closing.get(rid)
        if c is not None and c <= t:
            return rid
        t += travel_minutes(w)
    return None


def road_route(
    a: tuple[float, float],
    b: tuple[float, float],
    roads: list[dict[str, Any]] | None,
    closing: dict[str, float] | None = None,
    depart_min: float = 0.0,
) -> dict[str, Any]:
    """Flood-aware route over the road graph (blocked roads removed).

    Up to QAOA_CANDIDATES candidate paths come from Yen's k-shortest paths
    (candidate 0 is the Dijkstra shortest path). A simulated QAOA circuit
    picks one by travel time + flood exposure (optimization/qaoa_route.py).
    Falls back to a direct segment when the graph has no open path.

    F10: with `closing` ({road_id: sim minutes until the flood rule closes it})
    a candidate that reaches a road after it closes is dropped; when every
    candidate does, those roads are removed and the candidates rebuilt."""
    from backend.optimization.qaoa_route import candidate_costs, qaoa_choose

    a = (float(a[0]), float(a[1]))
    b = (float(b[0]), float(b[1]))
    fast = route_chooser() == "dijkstra"
    found = route_candidates(a, b, roads, k=1 if fast else None)
    cands = found["cands"]
    forecast_note = None
    if closing and cands:
        hits = [first_closed_road(c, closing, depart_min) for c in cands]
        ok = [c for c, h in zip(cands, hits) if h is None]
        if ok:
            dropped = sorted({h for h in hits if h})
            cands = ok
        else:
            from backend.services.seed import ROADS

            horizon = depart_min + max(travel_minutes(c["weighted_km"]) for c in cands)
            soon = {rid for rid, m in closing.items() if m <= horizon}
            safer = [dict(r, blocked=True, accessible=False) if r["road_id"] in soon else r for r in (roads or ROADS)]
            again = route_candidates(a, b, safer)["cands"]
            dropped = sorted({h for h in hits if h})
            if again:
                cands = again
            else:
                forecast_note = {"risk": dropped, "note": "every open route crosses a road forecast to flood first - kept the best one"}
        if dropped and forecast_note is None:
            forecast_note = {"avoided": dropped, "note": "candidates crossing a road forecast to flood before arrival were dropped"}
    if not cands:
        points = [[a[0], a[1]], [b[0], b[1]]]
        return {
            "points": [[round(p[0], 6), round(p[1], 6)] for p in points],
            "km": round(_km_of(points), 3),
            "sim_minutes": round(travel_minutes(haversine_km(a[0], a[1], b[0], b[1])), 1),
            "method": "direct",
            "road_ids": [],
            # src != dst but every road between them is closed: the straight
            # line is NOT a drivable route (reroute() refuses to adopt it).
            "no_open_road": found["no_open_road"],
        }

    q = qaoa_choose(candidate_costs(cands)) if len(cands) > 1 and not fast else None
    pick = q["chosen"] if q else 0
    best = cands[pick]
    out = {
        "points": [[round(p[0], 6), round(p[1], 6)] for p in best["points"]],
        "km": round(best["km"], 3),
        "sim_minutes": round(travel_minutes(best["weighted_km"]), 1),
        "method": "qaoa-flood" if q else "dijkstra-flood",
        # Roads this route drives on — reroute() checks them against blockages.
        "road_ids": best["road_ids"],
    }
    if q:
        out["quantum"] = {
            **q,
            "dijkstra": 0,
            "agrees_with_dijkstra": pick == 0,
            "candidates": [
                {
                    "km": round(c["km"], 3),
                    "sim_minutes": round(travel_minutes(c["weighted_km"]), 1),
                    "hazard": round(c["hazard"], 3),
                    "qubo_cost": round(cost, 4),
                    # display only (served every poll): a light outline of the candidate
                    "points": [[round(p[0], 5), round(p[1], 5)] for p in _thin_poly(c["points"], 40)],
                }
                for c, cost in zip(cands, candidate_costs(cands))
            ],
        }
    if forecast_note:
        out["flood_forecast"] = forecast_note
        if out.get("quantum"):
            # candidate 0 is the shortest of the candidates that SURVIVED the forecast
            out["quantum"]["filtered_by_forecast"] = True
    return out


# ---- live reroute (road blocked / reopened mid-run) ---------------------------------

REROUTE_GAIN_MIN = 0.5  # a reopened road must save at least this many sim minutes


def position_on(points: list[list[float]], frac: float) -> list[float]:
    """Point at fraction `frac` of a polyline's length — the same linear
    interpolation the frontend uses to draw the moving unit."""
    pts = [[float(p[0]), float(p[1])] for p in points or []]
    if not pts:
        return []
    if len(pts) == 1 or frac <= 0:
        return pts[0]
    if frac >= 1:
        return pts[-1]
    seg = [haversine_km(p[0], p[1], q[0], q[1]) for p, q in zip(pts, pts[1:])]
    total = sum(seg)
    if total <= 0:
        return pts[0]
    goal = total * frac
    for (p, q), d in zip(zip(pts, pts[1:]), seg):
        if goal <= d and d > 0:
            t = goal / d
            return [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t]
        goal -= d
    return pts[-1]


def leg_progress(row: dict[str, Any], now: datetime) -> float:
    started = _parse(row.get("ops_stage_at")) or now
    secs = float(row.get("ops_stage_seconds") or 0)
    if secs <= 0:
        return 1.0
    return max(0.0, min(1.0, (now - started).total_seconds() / secs))


def blocked_road_ids(roads: list[dict[str, Any]] | None) -> set[str]:
    return {str(r.get("road_id")) for r in roads or [] if r.get("blocked") or not r.get("accessible", True)}


def route_hits(route: dict[str, Any] | None, blocked: set[str]) -> list[str]:
    """Blocked roads a stored route drives on. Routes built before `road_ids`
    existed are treated as hitting any blocked road (re-checked once)."""
    if not route or route.get("method") == "direct" or not blocked:
        return []
    if "road_ids" not in route:
        return sorted(blocked)
    return sorted(blocked & set(route.get("road_ids") or []))


def reroute(
    rows: list[dict[str, Any]],
    roads: list[dict[str, Any]] | None,
    reason: str,
    now: datetime | None = None,
    improve: bool = False,
    closing: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Recompute the remaining legs of active rows after the road state changed.

    * a leg that drives on a now-blocked road is always re-planned;
    * with `improve=True` (a road re-opened) any leg is re-planned when the new
      route saves at least REROUTE_GAIN_MIN of the remaining minutes.

    A unit already driving continues from where it is now (position_on the old
    polyline at its current progress) — it never jumps back to the depot. The
    leg clock restarts at `now` with the new route's travel time. Returns one
    change record per re-planned leg (also kept on the row as `reroutes`)."""
    now = now or _now()
    blocked = blocked_road_ids(roads)
    changes: list[dict[str, Any]] = []
    for row in rows or []:
        st = row.get("ops_status")
        if st not in ACTIVE_STAGES or row.get("lat") is None:
            continue
        person = (float(row["lat"]), float(row["lon"]))
        shelter = (float(row["shelter_lat"]), float(row["shelter_lon"])) if row.get("shelter_lat") is not None else None
        legs = []  # (key, start point, end point, moving now?)
        if st == "assigned" and row.get("unit_base"):
            legs.append(("route_to_person", tuple(row["unit_base"]), person, False))
        if st == "en_route":
            legs.append(("route_to_person", None, person, True))
        if st in ("assigned", "en_route") and shelter:
            legs.append(("route_to_shelter", person, shelter, False))
        if st == "to_shelter" and shelter:
            legs.append(("route_to_shelter", None, shelter, True))
        for key, start, end, moving in legs:
            old = row.get(key) or {}
            hits = route_hits(old, blocked)
            stuck = (row.get("route_alert") or {}).get("leg") == key
            if not hits and not improve and not stuck:
                continue
            frac = leg_progress(row, now) if moving else 0.0
            if moving:
                pos = position_on(old.get("points") or [], frac)
                if not pos:
                    continue
                start = (pos[0], pos[1])
            old_left = float(old.get("sim_minutes") or 0) * (1.0 - frac)
            new = road_route(start, end, roads, closing, 0.0 if moving else MOBILISE_SECONDS * TIME_SCALE / 60.0)
            new_min = float(new.get("sim_minutes") or 0)
            if new.get("no_open_road"):
                # Every road to the target is closed. Do NOT swap in a straight
                # line (it would look faster than the road). Keep the plan,
                # raise an alert; reopening a road re-plans this leg.
                if hits and (row.get("route_alert") or {}).get("roads") != hits:
                    row["route_alert"] = {"at": _iso(now), "leg": key, "roads": hits, "reason": reason}
                    _journey(row, now, "NO_OPEN_ROAD",
                             f"{reason} · no open road {'to the person' if key == 'route_to_person' else 'to the shelter'} - "
                             "keeping the current plan until a road reopens", "Route Agent", st)
                    changes.append({"citizen_name": row.get("citizen_name"), "unit_name": row.get("unit_name"), "leg": key,
                                    "stage": st, "reason": reason, "blocked_roads": hits, "no_open_road": True,
                                    "old_minutes_left": round(old_left, 1), "new_minutes": None, "delta_minutes": 0.0,
                                    "old_km": old.get("km"), "new_km": None, "method": None, "from_current_position": moving})
                continue
            if not hits and not stuck and new_min > old_left - REROUTE_GAIN_MIN:
                continue  # reopened road does not help this leg
            if stuck:
                row.pop("route_alert", None)
            row[key] = new
            if key == "route_to_person":
                row["eta_min"] = new["sim_minutes"]
            else:
                row["eta_to_shelter_min"] = new["sim_minutes"]
            if moving:
                row["ops_stage_at"] = _iso(now)
                row["ops_stage_seconds"] = leg_seconds(new_min)
            leg_name = "to the person" if key == "route_to_person" else "to the shelter"
            rec = {
                "at": _iso(now),
                "leg": key,
                "stage": st,
                "reason": reason,
                "blocked_roads": hits,
                "old_minutes_left": round(old_left, 1),
                "new_minutes": round(new_min, 1),
                "delta_minutes": round(new_min - old_left, 1),
                "old_km": old.get("km"),
                "new_km": new.get("km"),
                "method": new.get("method"),
                "from_current_position": moving,
            }
            row.setdefault("reroutes", []).append(rec)
            _journey(
                row,
                now,
                "REROUTED",
                f"{reason} · new route {leg_name}: {new.get('km')} km, {new.get('sim_minutes')} min "
                f"({'+' if rec['delta_minutes'] >= 0 else ''}{rec['delta_minutes']} min vs remaining old route)"
                + (" · continuing from the unit's current position" if moving else ""),
                "Route Agent",
                st,
            )
            changes.append({"citizen_name": row.get("citizen_name"), "unit_name": row.get("unit_name"), **rec})
    return changes


# ---- live shelter reallocation (shelter closed / shrunk mid-run, F2) ---------------

NO_SEATS_REASON = "No shelter with free seats"


def _move_to_shelter(
    row: dict[str, Any],
    shelter: dict[str, Any],
    route: dict[str, Any],
    origin_moving: bool,
    now: datetime,
) -> None:
    row["shelter_name"] = shelter["name"]
    row["shelter_lat"] = shelter["lat"]
    row["shelter_lon"] = shelter["lon"]
    row["route_to_shelter"] = route
    row["eta_to_shelter_min"] = route["sim_minutes"]
    if isinstance(row.get("dispatch_request"), dict):
        row["dispatch_request"]["shelter_name"] = shelter["name"]
    if origin_moving:  # the unit is carrying the group: new leg starts here, now
        row["ops_stage_at"] = _iso(now)
        row["ops_stage_seconds"] = leg_seconds(route["sim_minutes"])
    if route.get("no_open_road"):
        row["route_alert"] = {"at": _iso(now), "leg": "route_to_shelter", "roads": [],
                              "reason": "No open road to the new shelter - straight-line estimate until a road reopens"}
    elif (row.get("route_alert") or {}).get("leg") == "route_to_shelter":
        row.pop("route_alert", None)
    row.pop("shelter_wait", None)
    if row.get("ops_wait_reason") == NO_SEATS_REASON:
        row.pop("ops_wait_reason", None)


def reallocate(
    rows: list[dict[str, Any]],
    overrides: dict[str, dict[str, Any]] | None,
    roads: list[dict[str, Any]] | None,
    reason: str,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Move active groups off shelters they can no longer use.

    Targets, in this order (vulnerable-first inside each):
    * shelter closed by the operator;
    * shelter over its (edited) capacity — the newest allocations are released
      first until it fits again;
    * shelter cut off: the leg to it has no open road (`route_alert`), moved
      only when another shelter IS reachable;
    * groups already waiting for seats (`shelter_wait`).

    `rescued` rows are delivered — never moved. A unit carrying the group
    continues from its current position. With no shelter left, the row keeps
    its plan, gets `ops_wait_reason = NO_SEATS_REASON` and `shelter_wait`; a
    `to_shelter` row then holds at the end of its leg (advance_all) until a
    shelter frees up. Returns one change record per row touched."""
    now = now or _now()
    reg = shelter_registry(overrides)
    active = [r for r in rows or [] if r.get("ops_status") in ACTIVE_STAGES and r.get("lat") is not None]
    order = lambda r: (r.get("person_index") or 0)  # noqa: E731
    targets: list[tuple[dict[str, Any], str]] = []
    seen: set[int] = set()

    def _add(r: dict[str, Any], why: str) -> None:
        if id(r) not in seen:
            seen.add(id(r))
            targets.append((r, why))

    hosp_rows = [r for r in active if r.get("destination_kind") == "hospital"]
    active = [r for r in active if r.get("destination_kind") != "hospital"]
    for r in sorted(active, key=order):
        s = reg.get(r.get("shelter_name") or "")
        if s and s["closed"]:
            _add(r, "closed")
    for name, s in reg.items():
        if s["closed"]:
            continue
        mine = [r for r in rows or [] if r.get("shelter_name") == name]
        excess = s["occupancy"] + sum(int(r.get("people") or 1) for r in mine) - s["capacity"]
        if excess <= 0:
            continue
        newest = sorted(
            (r for r in mine if r.get("ops_status") in ACTIVE_STAGES and id(r) not in seen),
            key=lambda r: str((r.get("timestamps") or {}).get("assigned") or ""),
            reverse=True,
        )
        for r in newest:
            if excess <= 0:
                break
            _add(r, "over capacity")
            excess -= int(r.get("people") or 1)
    for r in sorted(active, key=order):
        if (r.get("route_alert") or {}).get("leg") == "route_to_shelter":
            _add(r, "unreachable")
        elif r.get("shelter_wait"):
            _add(r, "waiting")

    changes: list[dict[str, Any]] = []
    for row in sorted(hosp_rows, key=order):  # F21: a cut-off hospital leg → another reachable hospital
        if (row.get("route_alert") or {}).get("leg") != "route_to_shelter":
            continue
        moving = row["ops_status"] == "to_shelter"
        pos = position_on((row.get("route_to_shelter") or {}).get("points") or [], leg_progress(row, now)) if moving else None
        origin = (pos[0], pos[1]) if pos else (float(row["lat"]), float(row["lon"]))
        old = row.get("shelter_name")
        hosp, route, _ = _reachable_hospital(origin, roads, exclude={old} if old else set())
        if hosp is None:
            continue  # keep the plan + its red route alert
        _move_to_shelter(row, {"name": hosp["name"], "lat": float(hosp["lat"]), "lon": float(hosp["lon"])}, route, moving, now)
        change = {"citizen_name": row.get("citizen_name"), "unit_name": row.get("unit_name"), "stage": row["ops_status"],
                  "old_shelter": old, "new_shelter": hosp["name"], "reason": reason, "why": "unreachable", "at": _iso(now),
                  "new_minutes": route["sim_minutes"], "new_km": route["km"], "no_open_road": False,
                  "from_current_position": moving, "no_seats": False, "destination_kind": "hospital"}
        row.setdefault("shelter_changes", []).append({k: v for k, v in change.items() if k not in ("citizen_name", "unit_name")})
        _journey(row, now, "HOSPITAL_CHANGED", f"{reason} · {old} → {hosp['name']} (no open road to it) · "
                 f"{route['km']} km, {route['sim_minutes']} min", "Shelter Agent", row["ops_status"])
        changes.append(change)
    for row, why in targets:
        st = row["ops_status"]
        old = row.get("shelter_name")
        moving = st == "to_shelter"
        if moving:
            frac = leg_progress(row, now)
            pos = position_on((row.get("route_to_shelter") or {}).get("points") or [], frac)
            origin = (pos[0], pos[1]) if pos else (float(row["lat"]), float(row["lon"]))
        else:
            origin = (float(row["lat"]), float(row["lon"]))
        # A closed / shrunk shelter is never a candidate for its own groups.
        exclude = {old} if why in ("closed", "over capacity", "unreachable") and old else set()
        shelter, route = _reachable_shelter(row, rows, origin, roads, overrides, exclude)
        rec = {"citizen_name": row.get("citizen_name"), "unit_name": row.get("unit_name"), "stage": st,
               "old_shelter": old, "reason": reason, "why": why, "at": _iso(now)}
        if why == "unreachable" and (shelter is None or route.get("no_open_road")):
            continue  # nothing better reachable: keep the plan + its route alert
        if why == "waiting" and shelter is None:
            continue  # still no seats anywhere; already flagged
        if shelter is None:
            if not row.get("shelter_wait"):
                row["shelter_wait"] = True
                row["ops_wait_reason"] = NO_SEATS_REASON
                _journey(row, now, "SHELTER_WAIT",
                         f"{reason} · {NO_SEATS_REASON} - keeping the group with {row.get('unit_name') or 'the unit'} "
                         "until a shelter frees up", "Shelter Agent", st)
            changes.append({**rec, "new_shelter": None, "no_seats": True})
            continue
        _move_to_shelter(row, shelter, route, moving, now)
        change = {**rec, "new_shelter": shelter["name"], "new_minutes": route["sim_minutes"], "new_km": route["km"],
                  "no_open_road": bool(route.get("no_open_road")), "from_current_position": moving, "no_seats": False}
        row.setdefault("shelter_changes", []).append({k: v for k, v in change.items() if k not in ("citizen_name", "unit_name")})
        why_text = {"closed": "closed", "over capacity": "over its new capacity", "unreachable": "no open road to it",
                    "waiting": "seats free again"}[why]
        _journey(row, now, "SHELTER_CHANGED",
                 f"{reason} · {old or 'no shelter'} → {shelter['name']} ({why_text}) · "
                 f"{route['km']} km, {route['sim_minutes']} min"
                 + (" from the unit's current position" if moving else ""),
                 "Shelter Agent", st)
        changes.append(change)
    return changes


# ---- row lifecycle ---------------------------------------------------------------


def _journey(row: dict[str, Any], at: datetime, event: str, detail: str, agent: str, status: str) -> None:
    row.setdefault("journey", []).append(
        {
            "at": _iso(at),
            "event": event,
            "detail": detail,
            "agent": agent,
            "status": status,
            "ambulance_name": row.get("ambulance_name"),
            "unit_name": row.get("unit_name"),
            "shelter_name": row.get("shelter_name"),
            "cluster_id": row.get("cluster_id"),
        }
    )


def ensure_ops(row: dict[str, Any], index: int = 0, queue_position: int | None = None, at: datetime | None = None) -> dict[str, Any]:
    """Attach ops fields if missing. `queue_position` (1-based) staggers the
    admin's dispatch in vulnerable-first order."""
    if row.get("ops_status"):
        return row
    at = at or _now()
    pos = max(1, int(queue_position or 1))
    row["ops_status"] = "queued"
    row["ops_stage_at"] = _iso(at)
    row["ops_stage_seconds"] = DISPATCH_SECONDS * pos
    row["live_status"] = "queued"
    row["status"] = "queued"
    row.setdefault("ambulance_name", None)
    row.setdefault("shelter_name", None)
    row["vulnerability"] = row.get("vulnerability") or vulnerability_label(row)
    row["needs_ambulance"] = needs_ambulance(row) or medical_of(row) != "none"
    row["journey"] = list(row.get("journey") or [])
    row.setdefault("timestamps", {})["queued"] = row["ops_stage_at"]
    if not row["journey"]:
        _journey(row, at, "QUEUED", STAGE_LABEL["queued"], "Administrator Agent", "queued")
    row.setdefault("person_index", index)
    return row


def _busy_ambulances(rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(r.get("ambulance_name"))
        for r in rows
        if r.get("ambulance_name") and r.get("ops_status") in ACTIVE_STAGES
    }


def boat_pool(ctx: dict[str, Any] | None = None) -> list[str]:
    """Assumed fleet of rescue boats (F22: default 0 = off)."""
    n = int((ctx or {}).get("boats") or 0)
    return [f"Rescue Boat {i}" for i in range(1, n + 1)]


def _busy_boats(rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(r.get("unit_name"))
        for r in rows
        if r.get("unit_role") == "boat" and r.get("ops_status") in ACTIVE_STAGES
    }


def _shelter_options(
    row: dict[str, Any],
    rows: list[dict[str, Any]],
    overrides: dict[str, dict[str, Any]] | None = None,
    exclude: set[str] | frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Open shelters with enough free seats for this group, nearest first."""
    reg = shelter_registry(overrides)
    committed: dict[str, int] = {}
    for r in rows:
        if r is not row and r.get("shelter_name"):
            committed[r["shelter_name"]] = committed.get(r["shelter_name"], 0) + int(r.get("people") or 1)
    need = int(row.get("people") or 1)
    lat, lon = float(row.get("lat") or 0), float(row.get("lon") or 0)
    options = []
    for name in SHELTER_POOL:
        s = reg.get(name)
        if not s or s["closed"] or name in exclude:
            continue
        left = s["capacity"] - s["occupancy"] - committed.get(name, 0)
        if left >= need:
            options.append((haversine_km(lat, lon, s["lat"], s["lon"]), {**s, "seats_left_before": left}))
    return [s for _, s in sorted(options, key=lambda o: o[0])]


def _pick_shelter(
    row: dict[str, Any],
    rows: list[dict[str, Any]],
    overrides: dict[str, dict[str, Any]] | None = None,
    exclude: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any] | None:
    opts = _shelter_options(row, rows, overrides, exclude)
    return opts[0] if opts else None


def _reachable_shelter(
    row: dict[str, Any],
    rows: list[dict[str, Any]],
    origin: tuple[float, float],
    roads: list[dict[str, Any]] | None,
    overrides: dict[str, dict[str, Any]] | None = None,
    exclude: set[str] | frozenset[str] = frozenset(),
    closing: dict[str, float] | None = None,
    depart_min: float = 0.0,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Nearest open shelter with seats that has an open road from `origin`.
    Returns (shelter, route). When every shelter with seats is cut off, the
    nearest one comes back with its `no_open_road` route; (None, None) when no
    open shelter has seats at all."""
    opts = _shelter_options(row, rows, overrides, exclude)
    first = None
    for s in opts:
        route = road_route(origin, (s["lat"], s["lon"]), roads, closing, depart_min)
        if not route.get("no_open_road"):
            return s, route
        first = first or (s, route)
    return first or (None, None)


# ---- ambulance positions + dispatch policy (F8) -----------------------------------

# nearest_depot = original rule (first free ambulance, launched from the depot
#   nearest the person — IDEALISED: it ignores where the ambulance really is);
# first_free = same choice, but from the ambulance's tracked position (the fair
#   baseline); greedy = nearest free by road; optimal = joint assignment.
DISPATCH_POLICIES = ("nearest_depot", "first_free", "greedy", "optimal", "fair")
FAIR_LAMBDA_DEFAULT = 1.0  # F32: minutes of road time traded per minute of group wait
VULN_WEIGHT = {"child": 1.6, "elderly": 1.6, "chest-deep": 1.3, "standard": 1.0}

# ---- F21: medical triage + hospitals ----------------------------------------------
MEDICAL_LEVELS = ("none", "injured", "critical")
# Triage is a labelled PARAMETER (assumed, not from a clinical source): critical
# first in the queue, then injured, then everyone else (rank 2 = today's order).
TRIAGE_RANK = {"critical": 0, "injured": 1}
MEDICAL_WEIGHT = {"critical": 2.0, "injured": 1.4}
MEDICAL_WEIGHT_SOURCE = "assumed triage weights (labelled parameter, swept in sensitivity analysis)"


def medical_of(row: dict[str, Any]) -> str:
    m = str(row.get("medical") or "none").lower()
    return m if m in MEDICAL_LEVELS else "none"


def triage_rank(row: dict[str, Any]) -> int:
    return TRIAGE_RANK.get(medical_of(row), 2)


def dispatch_weight(row: dict[str, Any]) -> float:
    """Assignment weight = max(vulnerability weight, medical weight)."""
    return max(VULN_WEIGHT.get(str(row.get("vulnerability") or "standard"), 1.0), MEDICAL_WEIGHT.get(medical_of(row), 1.0))


def _reachable_hospital(
    origin: tuple[float, float],
    roads: list[dict[str, Any]] | None,
    exclude: set[str] | frozenset[str] = frozenset(),
    closing: dict[str, float] | None = None,
    depart_min: float = 0.0,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    """Nearest OSM hospital (straight-line order, up to 4 tried) with an open
    road. Beds are unknown for most hospitals, so no seat check is made.
    Returns (hospital, route, considered)."""
    from backend.services.seed import HOSPITALS

    opts = sorted((h for h in HOSPITALS if h["name"] not in exclude),
                  key=lambda h: haversine_km(origin[0], origin[1], float(h["lat"]), float(h["lon"])))[:4]
    considered = []
    for h in opts:
        route = road_route(origin, (float(h["lat"]), float(h["lon"])), roads, closing, depart_min)
        considered.append({"name": h["name"], "km": route.get("km"), "minutes": route.get("sim_minutes"),
                           "open_road": not route.get("no_open_road"), "beds": h.get("beds")})
        if not route.get("no_open_road"):
            return h, route, considered
    return None, None, considered


# ---- F25: crew shifts + fuel over a long operation (assumed rules, default OFF) -------
CREW_DEFAULTS = {"shift_max_min": 720.0, "rest_min": 480.0, "range_km": 400.0, "refuel_min": 20.0}
CREW_SOURCE = ("assumed crew rules: after 12 h of driving a crew rests 8 h at its home depot; after 400 km the "
               "ambulance refuels for 20 min - labelled parameters, swept in the long stress test")


def crew_rules(ctx: dict[str, Any] | None) -> dict[str, float] | None:
    r = (ctx or {}).get("crew_rules")
    if not r or not r.get("on"):
        return None
    return {k: float(r.get(k) or v) for k, v in CREW_DEFAULTS.items()}


def crew_state(name: str, rows: list[dict[str, Any]], rules: dict[str, float] | None, now: datetime) -> dict[str, Any]:
    """DERIVED from the unit's own completed legs (never stored): driving
    minutes and km since the last rest / refuel; resting / refuelling until."""
    if not rules:
        return {"state": "ok"}
    wall = lambda m: timedelta(seconds=m * 60.0 / TIME_SCALE)  # noqa: E731
    jobs = sorted(
        ((t, r) for r in rows or [] if r.get("ambulance_name") == name and r.get("ops_status") == "rescued"
         for t in [_parse((r.get("timestamps") or {}).get("rescued"))] if t),
        key=lambda x: x[0],
    )
    active = km = 0.0
    state, until = "ok", None
    for t, r in jobs:
        legs = [r.get("route_to_person") or {}, r.get("route_to_shelter") or {}]
        active += sum(float(x.get("sim_minutes") or 0) for x in legs)
        km += sum(float(x.get("km") or 0) for x in legs)
        if active >= rules["shift_max_min"]:
            state, until, active, km = "resting", t + wall(rules["rest_min"]), 0.0, 0.0  # refuelled during the rest
        elif km >= rules["range_km"]:
            state, until, km = "refuelling", t + wall(rules["refuel_min"]), 0.0
    if until is not None and now < until:
        return {"state": state, "until": _iso(until), "left_min": round((until - now).total_seconds() * TIME_SCALE / 60.0, 1),
                "active_min": round(active, 1), "km_since_fuel": round(km, 1)}
    return {"state": "ok", "active_min": round(active, 1), "km_since_fuel": round(km, 1)}


def unavailable_units(rows: list[dict[str, Any]], ctx: dict[str, Any] | None, now: datetime) -> dict[str, dict[str, Any]]:
    rules = crew_rules(ctx)
    if not rules:
        return {}
    out = {}
    for a in ambulance_pool():
        s = crew_state(a, rows, rules, now)
        if s["state"] != "ok":
            out[a] = s
    return out


def ambulance_home(name: str, teams: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Home depot of an ambulance: the pool is spread round-robin over the
    city's rescue depots (no ambulance depot list exists in the data)."""
    from backend.services.seed import RESCUE_TEAMS

    pool = [t for t in (list(teams or []) or list(RESCUE_TEAMS)) if t.get("lat") is not None]
    amb = ambulance_pool()
    if not pool or name not in amb:
        return None
    t = pool[amb.index(name) % len(pool)]
    return {"lat": float(t["lat"]), "lon": float(t["lon"]), "place": t.get("name"), "kind": "depot"}


def ambulance_positions(
    rows: list[dict[str, Any]], ctx: dict[str, Any] | None = None, now: datetime | None = None
) -> dict[str, dict[str, Any]]:
    """Where each ambulance is — DERIVED from the stage machine, never stored:
    busy → on its job; free → the shelter of its last drop-off, else its home
    depot; a staging move (F9, ctx["staging"]) → along that road route."""
    ctx = ctx or {}
    now = now or _now()
    out: dict[str, dict[str, Any]] = {}
    last_drop: dict[str, tuple[datetime, dict[str, Any]]] = {}
    busy: set[str] = set()
    for r in rows or []:
        a = r.get("ambulance_name")
        if not a:
            continue
        if r.get("ops_status") in ACTIVE_STAGES:
            busy.add(a)
        elif r.get("ops_status") == "rescued" and r.get("shelter_lat") is not None:
            t = _parse((r.get("timestamps") or {}).get("rescued")) or now
            if a not in last_drop or t > last_drop[a][0]:
                last_drop[a] = (t, {"lat": float(r["shelter_lat"]), "lon": float(r["shelter_lon"]),
                                    "place": f"after drop-off at {r.get('shelter_name')}", "kind": "shelter", "since": _iso(t)})
    staging = ctx.get("staging") or {}
    off = unavailable_units(rows, ctx, now)  # F25 (empty unless crew rules are on)
    for name in ambulance_pool():
        if name in busy:
            out[name] = {"status": "busy"}
            continue
        if name in off:
            home = ambulance_home(name, ctx.get("teams")) or {}
            where = home if off[name]["state"] == "resting" else ((last_drop.get(name) or (None, None))[1] or home)
            out[name] = {**where, "status": off[name]["state"], "until": off[name]["until"], "left_min": off[name]["left_min"]}
            continue
        pos = (last_drop.get(name) or (None, None))[1] or ambulance_home(name, ctx.get("teams"))
        mv = staging.get(name)
        if mv and pos is not None:
            started = _parse(mv.get("depart_at")) or now
            dropped = _parse(pos.get("since")) if pos.get("kind") == "shelter" else None
            if dropped is None or started >= dropped:  # the move is newer than the last drop-off
                secs = float(mv.get("seconds") or 0)
                frac = 1.0 if secs <= 0 else max(0.0, min(1.0, (now - started).total_seconds() / secs))
                p = position_on(mv.get("points") or [], frac)
                if p:
                    pos = {"lat": p[0], "lon": p[1], "kind": "staging" if frac >= 1 else "repositioning",
                           "place": f"{'at' if frac >= 1 else 'moving to'} staging point {mv.get('label') or ''}".strip(),
                           "staging_to": mv.get("to"), "progress": round(frac, 3)}
                    if frac < 1:  # the frontend animates the move like any unit leg
                        pos.update({"route": mv.get("points"), "depart_at": mv.get("depart_at"), "seconds": secs})
        out[name] = {"status": "free", **(pos or {})}
    return out


def _road_minutes(origins: list[tuple[float, float]], targets: list[tuple[float, float]], roads) -> list[list[float]]:
    """Shortest weighted road time origin_i → target_j (Dijkstra, one run per
    origin). Unreachable → inf. Used to COMPARE units; the chosen unit's real
    route is still planned by road_route (Yen candidates → QAOA)."""
    import networkx as nx

    from backend.services.route_engine import _nearest_node, build_graph
    from backend.services.seed import GRAPH_NODES, ROADS

    g = build_graph(list(roads or ROADS))
    tnodes = [_nearest_node(*t) for t in targets]
    tsnap = [haversine_km(t[0], t[1], *GRAPH_NODES[n]) for t, n in zip(targets, tnodes)]
    out = []
    for o in origins:
        src = _nearest_node(*o)
        snap = haversine_km(o[0], o[1], *GRAPH_NODES[src])
        dist = nx.single_source_dijkstra_path_length(g, src, weight="weight") if src in g else {}
        out.append(
            [
                travel_minutes(snap + dist[n] + s) if n in dist else float("inf")
                for n, s in zip(tnodes, tsnap)
            ]
        )
    return out


def _free_ambulances(rows: list[dict[str, Any]], rejected: set[str]) -> list[str]:
    busy = _busy_ambulances(rows)
    return [a for a in ambulance_pool() if a not in busy and a not in rejected]


def _pick_ambulance(row: dict[str, Any], rows: list[dict[str, Any]], ctx: dict[str, Any], at: datetime, free: list[str]):
    """Which free ambulance serves `row`, from where. Returns
    (name, (lat, lon), place, decision-dict)."""
    policy = ctx.get("dispatch_policy") or "nearest_depot"
    person = (float(row.get("lat") or 0), float(row.get("lon") or 0))
    if policy == "nearest_depot" or not free:
        depot = _nearest_depot(person[0], person[1], ctx.get("teams") or [])
        base = (float(depot["lat"]), float(depot["lon"])) if depot else person
        return free[0], base, (depot or {}).get("name"), {"policy": policy, "rule": "first free ambulance, from the depot nearest the person"}
    pos = ambulance_positions(rows, ctx, at)
    cands = [a for a in free if pos.get(a, {}).get("lat") is not None]
    if not cands:
        depot = _nearest_depot(person[0], person[1], ctx.get("teams") or [])
        base = (float(depot["lat"]), float(depot["lon"])) if depot else person
        return free[0], base, (depot or {}).get("name"), {"policy": policy, "rule": "no ambulance position known"}
    origins = [(pos[a]["lat"], pos[a]["lon"]) for a in cands]
    if policy == "first_free":
        chosen = cands[0]
        info = {"policy": "first_free", "rule": "first free ambulance in the list, from where it really is"}
    elif policy == "optimal" or (policy == "fair" and _fair_lambda(ctx) <= 0):
        chosen, info = _optimal_choice(row, rows, ctx, at, cands, origins)  # F32: λ = 0 is exactly "optimal"
    elif policy == "fair":
        plan = _fair_plan(row, rows, ctx, at, cands, origins)
        chosen = plan["plan"].get(id(row), (cands[0], None))[0]
        info = {"policy": "fair", "lambda": plan["lambda"], "rule": plan["rule"], "group_wait_min": plan["group_wait"]}
    else:
        mins = [m[0] for m in _road_minutes(origins, [person], ctx.get("roads"))]
        k = min(range(len(cands)), key=lambda i: (mins[i], i))
        chosen = cands[k]
        info = {"policy": "greedy", "rule": "nearest free ambulance by road time from where it is",
                "considered": [{"unit": a, "minutes": round(m, 1) if math.isfinite(m) else None} for a, m in zip(cands, mins)]}
    p = pos[chosen]
    return chosen, (p["lat"], p["lon"]), p.get("place"), info


def _fair_lambda(ctx: dict[str, Any]) -> float:
    v = ctx.get("fair_lambda")
    return float(FAIR_LAMBDA_DEFAULT if v is None else v)


def _waiting_amb_rows(rows, at):
    return sorted((r for r in rows if r.get("ops_status") == "queued" and r.get("needs_ambulance") and _due(r) <= at),
                  key=lambda r: (triage_rank(r), r.get("person_index") or 0))


def _fair_plan(row, rows, ctx, at, cands, origins) -> dict[str, Any]:
    """F32 — fairness knob λ: one joint assignment over the WHOLE waiting
    queue (up to 4× the free ambulances, triage / queue order), cost =
    weight × road minutes − λ × (current mean wait of the person's group,
    groups = vulnerability classes as on the F14 board). λ = 0 is never used
    here (it is exactly `optimal`). A row the plan leaves out waits."""
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    lam = _fair_lambda(ctx)
    waiting = _waiting_amb_rows(rows, at)
    if row not in waiting:
        waiting = [row] + waiting
    batch = waiting[: max(len(cands), 4 * len(cands))]
    if row not in batch:
        batch[-1] = row
    key = ("fair", _iso(at), lam, tuple(cands), tuple(id(r) for r in batch))
    cache = ctx.setdefault("_plan_cache", {})
    if len(cache) > 256:
        cache.clear()
    if key not in cache:
        scale = TIME_SCALE / 60.0
        waits: dict[str, list[float]] = {}
        for r in waiting:
            q = _parse((r.get("timestamps") or {}).get("queued"))
            waits.setdefault(str(r.get("vulnerability") or "standard"), []).append((at - q).total_seconds() * scale if q else 0.0)
        gw = {g: sum(v) / len(v) for g, v in waits.items()}
        targets = [(float(r.get("lat") or 0), float(r.get("lon") or 0)) for r in batch]
        mins = np.array(_road_minutes(origins, targets, ctx.get("roads")))
        w = np.array([dispatch_weight(r) for r in batch])
        bonus = np.array([gw.get(str(r.get("vulnerability") or "standard"), 0.0) for r in batch])
        cost = np.where(np.isfinite(mins), mins * w[None, :] - lam * bonus[None, :], 1e6)
        ai, rj = linear_sum_assignment(cost)
        # Unreachable pairs stay in the plan (as in `optimal`), so nobody is held back by a closed road.
        cache[key] = {"plan": {id(batch[j]): (cands[i], float(mins[i, j]) if np.isfinite(mins[i, j]) else None)
                               for i, j in zip(ai, rj)},
                      "lambda": lam, "group_wait": {g: round(v, 1) for g, v in gw.items()},
                      "rule": f"joint assignment over the waiting queue: weight × road minutes − λ({lam:g}) × group's mean wait"}
    return cache[key]


def _optimal_choice(row, rows, ctx, at, cands, origins):
    """Assignment over the WAITING queue: the next len(free) ambulance-needing
    SOS in queue order (admin triage is kept) × every free ambulance, solved
    once with the Hungarian method (min Σ vulnerability weight × road minutes).
    The plan is cached for this instant so each row in the batch gets the
    ambulance the joint solution gave it."""
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    waiting = sorted(
        (r for r in rows if r.get("ops_status") == "queued" and r.get("needs_ambulance") and _due(r) <= at),
        key=lambda r: (r.get("person_index") or 0),
    )
    if row not in waiting:
        waiting = [row] + waiting
    batch = waiting[: len(cands)]
    if row not in batch:
        batch[-1] = row
    key = (_iso(at), tuple(cands), tuple(id(r) for r in batch))
    cache = ctx.setdefault("_plan_cache", {})
    if len(cache) > 256:  # long-lived ctx (Monte-Carlo): plans are only needed for one instant
        cache.clear()
    if key not in cache:
        targets = [(float(r.get("lat") or 0), float(r.get("lon") or 0)) for r in batch]
        mins = np.array(_road_minutes(origins, targets, ctx.get("roads")))  # ambulances × rows
        big = 1e6
        w = np.array([dispatch_weight(r) for r in batch])
        cost = np.where(np.isfinite(mins), mins * w[None, :], big)
        ai, rj = linear_sum_assignment(cost)
        plan = {id(batch[j]): (cands[i], float(mins[i, j])) for i, j in zip(ai, rj)}
        cache[key] = {"plan": plan, "total": float(sum(mins[i, j] * w[j] for i, j in zip(ai, rj) if np.isfinite(mins[i, j]))),
                      "batch": len(batch), "free": len(cands)}
    got = cache[key]
    chosen, minutes = got["plan"].get(id(row), (cands[0], float("nan")))
    return chosen, {
        "policy": "optimal",
        "rule": "joint assignment of the waiting queue to every free ambulance (Hungarian, min Σ weight × road minutes)",
        "batch_size": got["batch"],
        "free_ambulances": got["free"],
        "batch_weighted_minutes": round(got["total"], 1),
        "minutes_for_this_person": round(minutes, 1) if math.isfinite(minutes) else None,  # inf = no open road
    }


# ---- pre-positioning idle ambulances (F9) -----------------------------------------

STAGING_MAX_POINTS = 6
STAGING_NEAR_KM = 1.5  # SOS within this distance count as demand at a junction
STAGING_KEEP_KM = 0.6  # an ambulance already this close to a planned point stays


def junction_demand(rows: list[dict[str, Any]], roads: list[dict[str, Any]] | None, probability: float | None) -> dict[str, float]:
    """Hotspot weight per road junction = flood-exposure proxy of the roads
    meeting there × current flood probability × (1 + SOS calls within 1.5 km).
    Every factor is live state or city data — nothing is invented."""
    import numpy as np

    from backend.services.seed import GRAPH_EDGES, GRAPH_NODES, ROADS

    expo = {r["road_id"]: float(r.get("flood_exposure") or 0) for r in (roads or ROADS)}
    node_exp: dict[str, float] = {}
    for u, v, rid in GRAPH_EDGES:
        e = expo.get(rid, 0.0)
        node_exp[u] = max(node_exp.get(u, 0.0), e)
        node_exp[v] = max(node_exp.get(v, 0.0), e)
    p = float(probability if probability is not None else 0.5)
    names = list(GRAPH_NODES)
    xy = np.array([GRAPH_NODES[n] for n in names], dtype=float)
    sos = np.array([(float(r["lat"]), float(r["lon"])) for r in rows or [] if r.get("lat") is not None], dtype=float)
    near = np.zeros(len(names))
    if len(sos):
        near = (_km_matrix(xy, sos) <= STAGING_NEAR_KM).sum(axis=1)
    return {n: node_exp.get(n, 0.0) * p * (1 + float(near[i])) for i, n in enumerate(names)}


def _km_matrix(a, b):
    """Pairwise distance (km) between two (n, 2) lat/lon arrays — equirectangular,
    accurate to well under 1 % at city scale; vectorised for the planners."""
    import numpy as np

    lat0 = np.radians(np.mean(a[:, 0]))
    dy = (a[:, None, 0] - b[None, :, 0]) * 111.32
    dx = (a[:, None, 1] - b[None, :, 1]) * 111.32 * np.cos(lat0)
    return np.hypot(dx, dy)


def staging_points(demand: dict[str, float], k: int) -> list[str]:
    """Greedy weighted k-median over junctions: repeatedly add the junction
    that most reduces Σ weight × distance-to-nearest-staging-point."""
    import numpy as np

    from backend.services.seed import GRAPH_NODES

    nodes = [n for n, w in demand.items() if w > 0]
    if not nodes or k <= 0:
        return []
    # Candidate set: the highest-demand junctions (keeps it O(k·C·N) small).
    cand = sorted(nodes, key=lambda n: -demand[n])[:120]
    w = np.array([demand[n] for n in nodes])
    d = _km_matrix(np.array([GRAPH_NODES[c] for c in cand]), np.array([GRAPH_NODES[n] for n in nodes]))  # C × N
    best = np.full(len(nodes), 50.0)
    chosen: list[int] = []
    for _ in range(min(k, len(cand))):
        gain = (w[None, :] * np.maximum(0.0, best[None, :] - d)).sum(axis=1)
        if chosen:
            gain[chosen] = -1.0
        c = int(np.argmax(gain))
        if gain[c] <= 0:
            break
        chosen.append(c)
        best = np.minimum(best, d[c])
    return [cand[c] for c in chosen]


def plan_staging(
    rows: list[dict[str, Any]], ctx: dict[str, Any], probability: float | None, now: datetime | None = None
) -> dict[str, dict[str, Any]]:
    """New staging moves for idle ambulances (returns {name: move}). Ambulances
    already at / heading to a planned point are left alone; each remaining idle
    ambulance gets the uncovered point nearest by road (Hungarian)."""
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    from backend.services.seed import GRAPH_NODES, ZONES

    now = now or _now()
    pos = ambulance_positions(rows, ctx, now)
    idle = [a for a, p in pos.items() if p.get("status") == "free" and p.get("lat") is not None]
    if not idle:
        return {}
    points = staging_points(junction_demand(rows, ctx.get("roads"), probability), min(STAGING_MAX_POINTS, len(idle)))
    if not points:
        return {}
    pts = {n: GRAPH_NODES[n] for n in points}
    covered, movers = set(), []
    for a in idle:
        p = pos[a]
        target = p.get("staging_to")
        here = target if target else (p["lat"], p["lon"])
        hit = next((n for n, c in pts.items() if haversine_km(here[0], here[1], c[0], c[1]) <= STAGING_KEEP_KM), None)
        if hit and hit not in covered:
            covered.add(hit)
        else:
            movers.append(a)
    free_pts = [n for n in points if n not in covered]
    if not movers or not free_pts:
        return {}
    mins = np.array(_road_minutes([(pos[a]["lat"], pos[a]["lon"]) for a in movers], [pts[n] for n in free_pts], ctx.get("roads")))
    cost = np.where(np.isfinite(mins), mins, 1e6)
    ai, pj = linear_sum_assignment(cost)
    moves = {}
    for i, j in zip(ai, pj):
        if not np.isfinite(mins[i, j]):
            continue
        a, n = movers[i], free_pts[j]
        start = (pos[a]["lat"], pos[a]["lon"])
        route = road_route(start, pts[n], ctx.get("roads"))
        if route.get("no_open_road") or route.get("method") == "direct" and route.get("km", 0) > 0.05:
            continue
        zone = min(ZONES, key=lambda z: haversine_km(pts[n][0], pts[n][1], z["lat"], z["lon"]), default=None) if ZONES else None
        moves[a] = {
            "points": route["points"],
            "km": route["km"],
            "sim_minutes": route["sim_minutes"],
            "depart_at": _iso(now),
            "seconds": leg_seconds(route["sim_minutes"]),
            "to": [pts[n][0], pts[n][1]],
            "node": n,
            "label": f"near {zone['name']}" if zone else n,
        }
    return moves


def _assign(row: dict[str, Any], rows: list[dict[str, Any]], ctx: dict[str, Any], at: datetime) -> str | None:
    """Pick unit + shelter + route. Returns a wait reason when it cannot."""
    person = (float(row.get("lat") or 0), float(row.get("lon") or 0))
    base = _team_base(row, ctx.get("teams") or [])
    if base is None:
        return "No rescue team resolved for this cluster"
    overrides = ctx.get("shelter_overrides")
    from backend.services.seed import HOSPITALS

    to_hospital = medical_of(row) != "none" and bool(HOSPITALS)
    if not to_hospital and _pick_shelter(row, rows, overrides) is None:
        return "No shelter with free seats for this group"
    base_name = row.get("assigned_team_name") or row.get("assigned_team")
    # Units that already rejected (or did not answer) this job are skipped (F3).
    rejected = set(row.get("rejected_units") or [])
    free: list[str] = []
    team_name = base_name
    if row.get("needs_ambulance"):
        busy = _busy_ambulances(rows)
        amb = ambulance_pool()
        off = unavailable_units(rows, ctx, at)  # F25: resting / refuelling crews are not dispatched
        free = [a for a in amb if a not in busy and a not in rejected and a not in off]
        if not free:
            if any(a not in busy and a not in off for a in amb):
                return "Every free ambulance rejected this SOS - waiting for another ambulance"
            if off:
                first = min(off.values(), key=lambda s: s["until"])
                return f"All {len(amb)} ambulances busy or off duty ({len(off)} resting / refuelling; next back at {first['until'][11:16]} UTC)"
            return f"All {len(amb)} ambulances busy"
    elif team_name in rejected:
        # The cluster's own team said no: fall back to the nearest other depot.
        from backend.services.seed import RESCUE_TEAMS

        pool = [t for t in (list(ctx.get("teams") or []) or list(RESCUE_TEAMS))
                if t.get("lat") is not None and t.get("name") not in rejected]
        if not pool:
            return "Every rescue team rejected this SOS"
        alt = min(pool, key=lambda t: haversine_km(person[0], person[1], float(t["lat"]), float(t["lon"])))
        base, base_name, team_name = (float(alt["lat"]), float(alt["lon"])), alt.get("name"), alt.get("name")
    closing = ctx.get("closing") or None
    mobilise_min = MOBILISE_SECONDS * TIME_SCALE / 60.0
    if row.get("needs_ambulance") and ctx.get("dispatch_policy") == "fair" and _fair_lambda(ctx) > 0:
        pos = ambulance_positions(rows, ctx, at)
        cands = [a for a in free if pos.get(a, {}).get("lat") is not None]
        if cands:
            plan = _fair_plan(row, rows, ctx, at, cands, [(pos[a]["lat"], pos[a]["lon"]) for a in cands])
            if id(row) not in plan["plan"]:
                return f"Fair dispatch (λ={plan['lambda']:g}) serves a longer-waiting group first"
    if row.get("needs_ambulance"):
        # F8: which free ambulance, from where, by the run's dispatch policy
        # ("nearest_depot" keeps the original rule: first free, nearest depot).
        amb, base, base_name, why = _pick_ambulance(row, rows, ctx, at, free)
        row["ambulance_name"] = amb
        row["unit_role"] = "ambulance"
        row["unit_name"] = amb
        row["dispatch_choice"] = why
    else:
        row["ambulance_name"] = None
        row["unit_role"] = "rescue"
        row["unit_name"] = team_name
    row["unit_base"] = [base[0], base[1]]
    row["unit_base_name"] = base_name
    # F10: the unit leaves after roll-out; it reaches the person `eta` later,
    # so the shelter leg is checked against closures at THAT time.
    row["route_to_person"] = road_route(base, person, ctx.get("roads"), closing, mobilise_min)
    shelter_depart = mobilise_min + float(row["route_to_person"].get("sim_minutes") or 0)
    shelter = None
    row.pop("hospital_alert", None)
    if to_hospital:
        # F21: injured / critical → nearest OSM hospital with an open road.
        hosp, to_hosp, considered = _reachable_hospital(person, ctx.get("roads"), closing=closing, depart_min=shelter_depart)
        row["hospitals_considered"] = considered
        if hosp is not None:
            shelter, to_shelter = {"name": hosp["name"], "lat": float(hosp["lat"]), "lon": float(hosp["lon"])}, to_hosp
            row["destination_kind"] = "hospital"
        else:
            row["hospital_alert"] = {"at": _iso(at), "reason": "No hospital reachable by an open road - taking the group to a shelter"}
    if shelter is None:
        if _pick_shelter(row, rows, overrides) is None:
            return "No shelter with free seats for this group"
        row["destination_kind"] = "shelter"
        # Nearest open shelter with seats that an open road still reaches.
        shelter, to_shelter = _reachable_shelter(row, rows, person, ctx.get("roads"), overrides,
                                                 closing=closing, depart_min=shelter_depart)
    row["shelter_name"] = shelter["name"]
    row["shelter_lat"] = shelter["lat"]
    row["shelter_lon"] = shelter["lon"]
    row["route_to_shelter"] = to_shelter
    row["eta_min"] = row["route_to_person"]["sim_minutes"]
    row["eta_to_shelter_min"] = row["route_to_shelter"]["sim_minutes"]
    cut = [k for k in ("route_to_person", "route_to_shelter") if row[k].get("no_open_road")]
    if cut:
        boats = boat_pool(ctx)
        busy_b = _busy_boats(rows)
        free_boats = [b for b in boats if b not in busy_b]
        if free_boats:
            from backend.services.boat_route import compute_boat_route

            b_unit = free_boats[0]
            row["unit_name"] = b_unit
            row["unit_role"] = "boat"
            row["by_boat"] = True
            row["ambulance_name"] = None
            row["route_to_person"] = compute_boat_route(base, person, ctx.get("roads"))
            row["route_to_shelter"] = compute_boat_route(person, (shelter["lat"], shelter["lon"]), ctx.get("roads"))
            row["eta_min"] = row["route_to_person"]["sim_minutes"]
            row["eta_to_shelter_min"] = row["route_to_shelter"]["sim_minutes"]
            row.pop("route_alert", None)
            row["boat_dispatch"] = {"boat": b_unit, "rule": "person cut off by flood water — rescued by boat (F22)"}
        else:
            # straight-line ESTIMATE: every road between the points is closed
            row["route_alert"] = {
                "at": _iso(at),
                "leg": cut[0],
                "roads": sorted(blocked_road_ids(ctx.get("roads"))),
                "reason": "No open road at allocation - straight-line estimate until a road reopens",
            }
    else:
        row.pop("route_alert", None)
    row["assigned_team"] = row.get("assigned_team_name") or row.get("assigned_team")
    row.pop("ops_wait_reason", None)
    row["decision"] = _decision(row, rows, ctx, at, overrides)
    return None


def _decision(row: dict[str, Any], rows: list[dict[str, Any]], ctx: dict[str, Any], at: datetime, overrides) -> dict[str, Any]:
    """F13 — why this person got this queue position, unit, shelter and route.
    Only what the allocator actually compared; nothing re-scored after the fact."""
    queued = _parse((row.get("timestamps") or {}).get("queued"))
    vuln = row.get("vulnerability") or "standard"
    ahead = sum(1 for r in rows if r is not row and (r.get("person_index") or 0) < (row.get("person_index") or 0))
    reg = shelter_registry(overrides)
    person = (float(row.get("lat") or 0), float(row.get("lon") or 0))
    opts = _shelter_options(row, rows, overrides, exclude=frozenset({row.get("shelter_name")}))[:3]
    closed = sorted(n for n in SHELTER_POOL if (reg.get(n) or {}).get("closed"))
    route = row.get("route_to_person") or {}
    q = route.get("quantum") or {}
    unit = {
        "name": row.get("unit_name"),
        "role": row.get("unit_role"),
        "from": row.get("unit_base_name"),
        "eta_min": row.get("eta_min"),
        "rejected_before": list(row.get("rejected_units") or []),
    }
    if row.get("unit_role") == "boat":
        unit["why"] = "cut off by flood water — assigned rescue boat across the flooded area (F22)"
    elif row.get("unit_role") == "ambulance":
        unit["why"] = (
            f"needs an ambulance ({vuln})" if vuln != "standard" else "needs an ambulance (water depth)"
        )
        unit["choice"] = row.get("dispatch_choice")
    else:
        unit["why"] = (
            "K-means cluster's own rescue team" if row.get("unit_name") == row.get("assigned_team_name")
            else "nearest other depot (the cluster team rejected the job)"
        )
    return {
        "at": _iso(at),
        "queue": {
            "rank": row.get("person_index"),
            "people_ahead": ahead,
            "vulnerability": vuln,
            "rule": "critical, then injured (F21 triage, assumed), then vulnerable-first: children, elderly and chest-deep callers",
            "medical": medical_of(row),
            "waited_min": round((at - queued).total_seconds() * TIME_SCALE / 60.0, 1) if queued else None,
        },
        "unit": unit,
        "shelter": {
            "chosen": row.get("shelter_name"),
            "km_straight": round(haversine_km(person[0], person[1], float(row.get("shelter_lat") or 0), float(row.get("shelter_lon") or 0)), 2)
            if row.get("shelter_lat") is not None else None,
            "rule": "nearest open shelter with seats for the whole group and an open road",
            "next_options": [
                {"name": s["name"], "km_straight": round(haversine_km(person[0], person[1], s["lat"], s["lon"]), 2),
                 "seats_left": s.get("seats_left_before")}
                for s in opts
            ],
            "closed": closed,
            "destination_kind": row.get("destination_kind") or "shelter",
            "medical": medical_of(row),
            "hospitals_considered": row.get("hospitals_considered") or [],
            "hospital_alert": row.get("hospital_alert"),
        },
        "route": {
            "method": route.get("method"),
            "km": route.get("km"),
            "minutes": route.get("sim_minutes"),
            "candidates": len(q.get("candidates") or []) or 1,
            "qaoa_matches_exhaustive": q.get("matches_exhaustive"),
            "agrees_with_dijkstra": q.get("agrees_with_dijkstra"),
            "flood_forecast": route.get("flood_forecast"),
            "no_open_road": bool(route.get("no_open_road")),
        },
    }


def _transition(row: dict[str, Any], nxt: str, at: datetime, ctx: dict[str, Any]) -> None:
    row["ops_status"] = nxt
    row["ops_stage_at"] = _iso(at)
    row["live_status"] = nxt
    row["status"] = nxt
    unit = row.get("unit_name") or "unit"
    if nxt == "assigned":
        row["ops_stage_seconds"] = MOBILISE_SECONDS
        vehicle = f"ambulance {row.get('ambulance_name')}" if row.get("unit_role") == "ambulance" else f"rescue team {unit}"
        detail = (
            f"{vehicle} · shelter {row.get('shelter_name')} · cluster {row.get('cluster_id') or 'n/a'} · "
            f"ETA {row.get('eta_min')} min ({row['route_to_person']['km']} km)"
        )
        agent = "Administrator Agent"
        # The SOS details that go to the unit's driver / crew lead.
        row["dispatch_request"] = {
            "sent_at": _iso(at),
            "to": unit,
            "role": row.get("unit_role") or "rescue",
            "citizen_name": row.get("citizen_name"),
            "age": row.get("age"),
            "people": row.get("people") or 1,
            "lat": row.get("lat"),
            "lon": row.get("lon"),
            "water_level_note": row.get("water_level_note"),
            "vulnerability": row.get("vulnerability"),
            "shelter_name": row.get("shelter_name"),
            "eta_min": row.get("eta_min"),
            "km": row["route_to_person"]["km"],
        }
        row["driver_accepted"] = False
        row["accepted_at"] = None
    elif nxt == "en_route":
        # The crew acknowledges the request when roll-out ends (simulated
        # driver agent — accepted at the moment the unit starts driving).
        row["driver_accepted"] = True
        row["accepted_at"] = _iso(at)
        # "driver app" = a person tapped Accept (F3); "auto" = simulated crew.
        row["accepted_via"] = ctx.get("accepted_via") or "auto"
        row.setdefault("timestamps", {})["accepted"] = row["accepted_at"]
        role = "Ambulance driver" if row.get("unit_role") == "ambulance" else "Rescue crew lead"
        _journey(
            row,
            at,
            "ACCEPTED",
            f"{role} of {unit} accepted the SOS request for {row.get('citizen_name')} · heading out"
            + (" (tapped Accept in the driver app)" if row["accepted_via"] == "driver app" else " (auto-accept)"),
            role,
            "assigned",
        )
        row["ops_stage_seconds"] = leg_seconds(row["route_to_person"]["sim_minutes"])
        detail = f"{unit} driving to the person · {row['route_to_person']['km']} km · {row['route_to_person']['sim_minutes']} min"
        agent = "Ambulance Agent" if row.get("unit_role") == "ambulance" else "Rescue Agent"
    elif nxt == "to_shelter":
        # Re-route against the road state at pickup time.
        if row.get("shelter_lat") is not None:
            row["route_to_shelter"] = road_route(
                (float(row["lat"]), float(row["lon"])),
                (float(row["shelter_lat"]), float(row["shelter_lon"])),
                ctx.get("roads"),
                ctx.get("closing") or None,  # F10: departs now
            )
            row["eta_to_shelter_min"] = row["route_to_shelter"]["sim_minutes"]
            if row["route_to_shelter"].get("no_open_road"):
                # Straight-line ESTIMATE only — every road to the shelter is closed.
                row["route_alert"] = {"at": _iso(at), "leg": "route_to_shelter", "roads": sorted(blocked_road_ids(ctx.get("roads"))),
                                      "reason": "No open road to the shelter at pickup - straight-line estimate"}
            elif (row.get("route_alert") or {}).get("leg") in ("route_to_shelter", "route_to_person"):
                row.pop("route_alert", None)
        row["ops_stage_seconds"] = leg_seconds(row["route_to_shelter"]["sim_minutes"])
        detail = (
            f"Picked up by {unit} — heading to {row.get('shelter_name')} · "
            f"{row['route_to_shelter']['km']} km · {row['route_to_shelter']['sim_minutes']} min"
        )
        agent = "Ambulance Agent" if row.get("unit_role") == "ambulance" else "Rescue Agent"
    else:  # rescued
        row["ops_stage_seconds"] = 0.0
        row["rescued"] = "yes"
        detail = f"Admitted at {row.get('shelter_name')} · {row.get('people') or 1} people"
        agent = "Shelter Agent"
    row.setdefault("timestamps", {})[nxt] = row["ops_stage_at"]
    _journey(row, at, nxt.upper(), f"{STAGE_LABEL[nxt]} · {detail}", agent, nxt)
    if nxt == "assigned":
        req = row["dispatch_request"]
        _journey(
            row,
            at,
            "REQUEST_SENT",
            f"SOS details sent to {unit}: {req['citizen_name']}, {req['people']} people, "
            f"GPS {req['lat']},{req['lon']}, {req.get('water_level_note') or 'flood water'} · drop at {req['shelter_name']}",
            "Administrator Agent",
            "assigned",
        )


def _due(row: dict[str, Any], manual: bool = False) -> datetime:
    started = _parse(row.get("ops_stage_at")) or _now()
    if manual and row.get("ops_status") == "assigned":
        # Drivers decide (F3): the request waits for Accept / Reject; when
        # nobody answers in time it is treated as a reject ("no answer").
        return started + timedelta(seconds=ACCEPT_TIMEOUT_SECONDS)
    return started + timedelta(seconds=float(row.get("ops_stage_seconds") or 0))


# ---- driver accept / reject (F3) ------------------------------------------------

ACCEPT_MODES = ("auto", "manual")
ACCEPT_TIMEOUT_SECONDS = 20.0  # wall s a driver has to answer in "manual" mode
NO_ANSWER = "no answer"


def accept(row: dict[str, Any], ctx: dict[str, Any] | None = None, at: datetime | None = None) -> None:
    """The driver / crew lead tapped Accept: the one existing en_route
    transition runs (same code path as auto-accept)."""
    if row.get("ops_status") != "assigned":
        raise ValueError("job is no longer waiting for this unit")
    _transition(row, "en_route", at or _now(), {**(ctx or {}), "accepted_via": "driver app"})


def reject(
    row: dict[str, Any],
    rows: list[dict[str, Any]],
    ctx: dict[str, Any] | None,
    at: datetime | None = None,
    reason: str = "rejected by driver",
) -> dict[str, Any]:
    """The unit said no (or did not answer). It is remembered on the row and
    excluded; the job goes straight to the next free unit. Returns the record."""
    if row.get("ops_status") != "assigned":
        raise ValueError("job is no longer waiting for this unit")
    ctx = ctx or {}
    at = at or _now()
    unit = row.get("unit_name") or "unit"
    role = "Ambulance driver" if row.get("unit_role") == "ambulance" else "Rescue crew lead"
    row.setdefault("rejected_units", []).append(unit)
    rec = {"at": _iso(at), "unit_name": unit, "reason": reason}
    row.setdefault("timestamps", {})["rejected"] = rec["at"]
    _journey(
        row,
        at,
        "REJECTED",
        (f"{unit} did not answer within {ACCEPT_TIMEOUT_SECONDS:g} s" if reason == NO_ANSWER else f"{role} of {unit} rejected the SOS request ({reason})")
        + " - offering the job to the next unit",
        role if reason != NO_ANSWER else "Administrator Agent",
        "assigned",
    )
    for key in ("ambulance_name", "unit_name", "dispatch_request", "accepted_at", "shelter_name", "shelter_lat", "shelter_lon"):
        row[key] = None
    row["driver_accepted"] = False
    row["ops_status"] = row["live_status"] = row["status"] = "queued"
    wait = _assign(row, rows, ctx, at)
    if wait is None:
        _transition(row, "assigned", at, ctx)
        rec["next_unit"] = row.get("unit_name")
    else:
        row["ops_stage_at"] = _iso(at)
        row["ops_stage_seconds"] = DISPATCH_SECONDS
        row["ops_wait_reason"] = wait
        _journey(row, at, "WAITING", f"Held in queue — {wait}", "Administrator Agent", "queued")
        rec["next_unit"] = None
        rec["wait_reason"] = wait
    row.setdefault("rejections", []).append(rec)
    return rec


def find_job(rows: list[dict[str, Any]], unit_name: str, stages: tuple[str, ...] = ("assigned",)) -> dict[str, Any] | None:
    """The row this unit is serving in one of `stages` (oldest request first)."""
    mine = [r for r in rows or [] if r.get("unit_name") == unit_name and r.get("ops_status") in stages]
    return min(mine, key=lambda r: str(r.get("ops_stage_at") or "")) if mine else None


def known_units(rows: list[dict[str, Any]], teams: list[dict[str, Any]] | None = None) -> list[str]:
    from backend.services.seed import RESCUE_TEAMS

    names = list(ambulance_pool()) + [str(t.get("name")) for t in (list(teams or []) or list(RESCUE_TEAMS)) if t.get("name")]
    names += [str(r["unit_name"]) for r in rows or [] if r.get("unit_name")]
    return list(dict.fromkeys(names))


def unit_view(
    rows: list[dict[str, Any]], unit_name: str, accept_mode: str = "auto", now: datetime | None = None
) -> dict[str, Any]:
    """What the driver app shows for one unit: the request waiting for an
    answer, else the job it is driving, else free. Read-only."""
    now = now or _now()
    row = find_job(rows, unit_name, ("assigned",)) or find_job(rows, unit_name, ("en_route", "to_shelter"))
    out: dict[str, Any] = {
        "unit": unit_name,
        "role": "ambulance" if unit_name in ambulance_pool() else "rescue",
        "accept_mode": accept_mode,
        "timeout_seconds": ACCEPT_TIMEOUT_SECONDS,
        "status": "free",
        "job": None,
        "trips_completed": sum(1 for r in rows or [] if r.get("unit_name") == unit_name and r.get("ops_status") == "rescued"),
    }
    if not row:
        return out
    st = row["ops_status"]
    out["status"] = "request" if st == "assigned" else "busy"
    req = row.get("dispatch_request") or {}
    started = _parse(row.get("ops_stage_at")) or now
    left = None
    if st == "assigned":
        limit = ACCEPT_TIMEOUT_SECONDS if accept_mode == "manual" else float(row.get("ops_stage_seconds") or MOBILISE_SECONDS)
        left = max(0.0, limit - (now - started).total_seconds())
    out["job"] = {
        "citizen_name": row.get("citizen_name"),
        "age": row.get("age"),
        "people": row.get("people") or 1,
        "vulnerability": row.get("vulnerability"),
        "water": row.get("water_level_note"),
        "lat": row.get("lat"),
        "lon": row.get("lon"),
        "stage": st,
        "stage_label": STAGE_LABEL.get(st),
        "shelter_name": row.get("shelter_name"),
        "shelter_lat": row.get("shelter_lat"),
        "shelter_lon": row.get("shelter_lon"),
        "unit_base": row.get("unit_base"),
        "unit_base_name": row.get("unit_base_name"),
        "route_to_person": row.get("route_to_person"),
        "route_to_shelter": row.get("route_to_shelter"),
        "eta_min": row.get("eta_min"),
        "eta_to_shelter_min": row.get("eta_to_shelter_min"),
        "requested_at": req.get("sent_at") or row.get("ops_stage_at"),
        "seconds_left": None if left is None else round(left, 1),
        "rejected_by": list(row.get("rejected_units") or []),
        "accepted_at": row.get("accepted_at"),
    }
    return out


def advance_all(rows: list[dict[str, Any]], ctx: dict[str, Any] | None = None, now: datetime | None = None) -> int:
    """Event-driven catch-up: repeatedly fire the earliest due transition until
    nothing is due at `now`. Returns the number of transitions fired."""
    ctx = ctx or {}
    now = now or _now()
    manual = ctx.get("accept_mode") == "manual"
    for i, row in enumerate(rows or []):
        ensure_ops(row, i + 1)
    changed = 0
    blocked: set[int] = set()  # queued rows waiting on a resource this pass
    clock = None
    for _ in range(len(rows or []) * 6 + 5):
        due_rows = [
            (_due(r, manual), i)
            for i, r in enumerate(rows)
            if r.get("ops_status") not in ("rescued", "merged") and i not in blocked and _due(r, manual) <= now
            # No shelter has seats (F2): the unit holds the group, no delivery.
            and not (r.get("ops_status") == "to_shelter" and r.get("shelter_wait"))
        ]
        if not due_rows:
            break
        due, i = min(due_rows, key=lambda x: (triage_rank(rows[x[1]]) if rows[x[1]].get("ops_status") == "queued" else 2, x[0], x[1]))
        row = rows[i]
        # A row that waited on a resource transitions when the resource freed.
        at = max(due, clock) if clock and row.get("ops_wait_reason") else due
        st = row.get("ops_status") or "queued"
        if st == "queued":
            reason = _assign(row, rows, ctx, at)
            # F25: a crew back from rest / refuel is a resource event too — retry at
            # the moment it is back (if that is already past), never before.
            for _ in range(len(ambulance_pool())):
                if not reason or not crew_rules(ctx) or not row.get("needs_ambulance"):
                    break
                back = sorted(_parse(s["until"]) for s in unavailable_units(rows, ctx, at).values())
                back = [b for b in back if b and at < b <= now]
                if not back:
                    break
                at = back[0]
                reason = _assign(row, rows, ctx, at)
            if reason:
                if row.get("ops_wait_reason") != reason:
                    row["ops_wait_reason"] = reason
                    _journey(row, due, "WAITING", f"Held in queue — {reason}", "Administrator Agent", "queued")
                blocked.add(i)
                continue
        if st == "assigned" and manual:
            reject(row, rows, ctx, due, NO_ANSWER)  # nobody tapped Accept in time
            clock = due
            changed += 1
            continue
        nxt = STAGES[min(len(STAGES) - 1, STAGES.index(st) + 1 if st in STAGES else 1)]
        _transition(row, nxt, at, ctx)
        clock = at
        changed += 1
        if nxt == "rescued":
            blocked.clear()  # an ambulance / seats may have freed up
    return changed


# ---- F30: duplicate SOS — suggest only, the operator decides ------------------------

DUP_RADIUS_M = 75.0
DUP_WINDOW_SIM_MIN = 20.0
DUP_NAME_SIMILARITY = 0.8


def _norm_name(s: Any) -> str:
    import re

    return " ".join(re.sub(r"[^a-z ]+", " ", str(s or "").lower()).split())


def name_similarity(a: Any, b: Any) -> float:
    """1 − normalised Levenshtein distance of the normalised names."""
    a, b = _norm_name(a), _norm_name(b)
    if not a or not b:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return round(1.0 - prev[-1] / max(len(a), len(b)), 3)


def dup_key(a: str, b: str) -> str:
    return "|".join(sorted([str(a), str(b)]))


def duplicate_candidates(rows: list[dict[str, Any]], dismissed: set[str] | None = None) -> list[dict[str, Any]]:
    """Pairs of open SOS within DUP_RADIUS_M and DUP_WINDOW_SIM_MIN of each other
    whose names are similar or that came from the same device. Never merged here."""
    dismissed = dismissed or set()
    open_rows = [r for r in rows or [] if r.get("ops_status") not in ("rescued", "merged") and r.get("lat") is not None]
    dlat = DUP_RADIUS_M / 110_574.0
    out = []
    for i, a in enumerate(open_rows):
        for b in open_rows[i + 1:]:
            if abs(float(a["lat"]) - float(b["lat"])) > dlat:
                continue
            d_m = haversine_km(float(a["lat"]), float(a["lon"]), float(b["lat"]), float(b["lon"])) * 1000.0
            if d_m > DUP_RADIUS_M:
                continue
            qa = _parse((a.get("timestamps") or {}).get("queued"))
            qb = _parse((b.get("timestamps") or {}).get("queued"))
            minutes = abs((qa - qb).total_seconds()) * TIME_SCALE / 60.0 if qa and qb else 0.0
            if minutes > DUP_WINDOW_SIM_MIN:
                continue
            key = dup_key(a.get("citizen_name"), b.get("citizen_name"))
            if key in dismissed:
                continue
            sim = name_similarity(a.get("citizen_name"), b.get("citizen_name"))
            same_dev = bool(a.get("device_key")) and a.get("device_key") == b.get("device_key")
            if sim < DUP_NAME_SIMILARITY and not same_dev:
                continue
            reasons = [f"{d_m:.0f} m apart", f"{minutes:.0f} sim min apart"]
            if sim >= DUP_NAME_SIMILARITY:
                reasons.append(f"names {round(sim * 100)}% alike")
            if same_dev:
                reasons.append("sent from the same phone")
            out.append({"key": key, "a": a.get("citizen_name"), "b": b.get("citizen_name"),
                        "distance_m": round(d_m, 1), "minutes_apart": round(minutes, 1), "name_similarity": sim,
                        "same_device": same_dev, "score": round(max(sim, 1.0 if same_dev else 0.0), 3),
                        "reasons": reasons})
    return sorted(out, key=lambda x: -x["score"])


def merge_rows(rows: list[dict[str, Any]], keep: str, drop: str, at: datetime | None = None) -> dict[str, Any]:
    """Operator-confirmed merge: `drop` leaves the queue (status "merged",
    `merged_into` = keep) — kept in the roster with its whole journey, never
    deleted. Its unit is freed (it is no longer in an active stage). The kept
    row takes the larger head count of the two."""
    at = at or _now()
    by = {str(r.get("citizen_name")): r for r in rows or []}
    k, d = by.get(keep), by.get(drop)
    if k is None or d is None or keep == drop:
        raise KeyError("unknown SOS row")
    if d.get("ops_status") in ("rescued", "merged") or k.get("ops_status") == "merged":
        raise ValueError("only open SOS can be merged")
    freed = d.get("unit_name") if d.get("ops_status") in ACTIVE_STAGES else None
    prev = d.get("ops_status")
    d["merged_into"] = keep
    d["merged_from_status"] = prev
    d["shelter_name_before_merge"] = d.get("shelter_name")
    d["shelter_name"] = None  # its seats go back to the pool
    d["ops_status"] = d["live_status"] = d["status"] = "merged"
    d["ops_stage_at"] = _iso(at)
    d.setdefault("timestamps", {})["merged"] = _iso(at)
    _journey(d, at, "MERGED", f"Duplicate of {keep} — merged by the operator (was {prev})", "Operator", "merged")
    people_before = int(k.get("people") or 1)
    k["people"] = max(people_before, int(d.get("people") or 1))
    k.setdefault("merged_from", []).append(drop)
    _journey(k, at, "MERGED", f"{drop} merged into this SOS by the operator (people {people_before} → {k['people']})",
             "Operator", k.get("ops_status") or "queued")
    return {"keep": keep, "drop": drop, "freed_unit": freed, "dropped_was": prev, "people": k["people"]}


def advance_one(row: dict[str, Any], index: int = 0, force: bool = False) -> bool:
    """Back-compat single-row advance (used by tests / tools)."""
    ensure_ops(row, index)
    if force:
        row["ops_stage_at"] = _iso(_now() - timedelta(seconds=float(row.get("ops_stage_seconds") or 0) + 0.001))
    return advance_all([row]) > 0


# ---- views for the state payload ------------------------------------------------


def unit_paths(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The leg each assigned unit is on. Static from/to + route polyline; the
    position along it is derived client-side from ops_stage_at/seconds."""
    out = []
    for r in rows or []:
        st = r.get("ops_status")
        if st not in ACTIVE_STAGES or not r.get("unit_base"):
            continue
        leg = r.get("route_to_shelter") if st == "to_shelter" else r.get("route_to_person")
        pts = (leg or {}).get("points") or []
        out.append(
            {
                "team_id": r.get("unit_name"),
                "team_name": r.get("unit_name"),
                "role": r.get("unit_role") or "rescue",
                "stage": st,
                "from": pts[0] if pts else r.get("unit_base"),
                "to": pts[-1] if pts else [r.get("lat"), r.get("lon")],
                "route": pts,
                "citizen_name": r.get("citizen_name"),
            }
        )
    return out


def eta_board(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from backend.services.demo_extras import medical_triage

    out = [
        {
            "citizen_name": r.get("citizen_name"),
            "rescue_order": r.get("person_index"),
            "eta_min": r.get("eta_min"),
            "eta_to_shelter_min": r.get("eta_to_shelter_min"),
            "assigned_team": r.get("unit_name") or r.get("assigned_team_name") or r.get("assigned_team"),
            "triage": medical_triage(r),
        }
        for r in rows or []
    ]
    out.sort(key=lambda r: r.get("rescue_order") or 99)
    return out


def delivered_by_shelter(rows: list[dict[str, Any]]) -> dict[str, int]:
    """People actually delivered this run — reported separately from the
    backend's growth-curve occupancy."""
    out: dict[str, int] = {}
    for r in rows or []:
        if r.get("ops_status") == "rescued" and r.get("shelter_name"):
            out[r["shelter_name"]] = out.get(r["shelter_name"], 0) + int(r.get("people") or 1)
    return out


def fleet_board(rows: list[dict[str, Any]], ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """Live ambulance pool + active rescue units, from the stage machine.
    With `ctx`, each FREE ambulance also carries its derived position (F8/F9)."""
    active = [r for r in rows or [] if r.get("ops_status") in ACTIVE_STAGES]
    positions = ambulance_positions(rows, ctx) if ctx is not None else {}
    busy = {str(r["ambulance_name"]): r for r in active if r.get("unit_role") == "ambulance" and r.get("ambulance_name")}
    trips: dict[str, int] = {}
    for r in rows or []:
        if r.get("ops_status") == "rescued" and r.get("unit_name"):
            trips[str(r["unit_name"])] = trips.get(str(r["unit_name"]), 0) + 1

    def _job(r: dict[str, Any] | None) -> dict[str, Any] | None:
        if not r:
            return None
        return {
            "citizen_name": r.get("citizen_name"),
            "people": r.get("people") or 1,
            "stage": r.get("ops_status"),
            "shelter_name": r.get("shelter_name"),
            "accepted": bool(r.get("driver_accepted")),
            "accepted_at": r.get("accepted_at"),
            "requested_at": (r.get("dispatch_request") or {}).get("sent_at"),
            "rejected_by": list(r.get("rejected_units") or []),
            "eta_min": r.get("eta_min"),
            "eta_to_shelter_min": r.get("eta_to_shelter_min"),
        }

    off = unavailable_units(rows, ctx, _now()) if ctx is not None else {}  # F25

    ambulances = [
        {
            "name": name,
            "status": "busy" if name in busy else (off[name]["state"] if name in off else "free"),
            "crew": off.get(name),
            "job": _job(busy.get(name)),
            "trips_completed": trips.get(name, 0),
            "position": None if name in busy else {k: v for k, v in (positions.get(name) or {}).items() if k != "status"} or None,
        }
        for name in ambulance_pool()
    ]
    rescue_units = [
        {"name": r.get("unit_name"), "base": r.get("unit_base_name"), "job": _job(r)}
        for r in active
        if r.get("unit_role") != "ambulance"
    ]
    waiting = [
        r.get("citizen_name")
        for r in rows or []
        if r.get("ops_status") == "queued" and "ambulances busy" in str(r.get("ops_wait_reason") or "")
    ]
    boats_cfg = boat_pool(ctx)
    busy_b = {str(r["unit_name"]): r for r in active if r.get("unit_role") == "boat" and r.get("unit_name")}
    boats_list = [
        {
            "name": name,
            "status": "busy" if name in busy_b else "free",
            "job": _job(busy_b.get(name)),
            "trips_completed": trips.get(name, 0),
        }
        for name in boats_cfg
    ]
    return {
        "ambulances": ambulances,
        "ambulances_total": len(ambulance_pool()),
        "ambulances_busy": len(busy),
        "ambulances_free": len(ambulance_pool()) - len(busy) - len([a for a in off if a not in busy]),
        "ambulances_off_duty": len(off),
        "crew_rules": crew_rules(ctx) if ctx is not None else None,
        "crew_rules_source": CREW_SOURCE if ctx is not None and crew_rules(ctx) else None,
        "rescue_units_active": rescue_units,
        "waiting_for_ambulance": waiting,
        "boats": boats_list,
        "boats_total": len(boats_cfg),
        "boats_busy": len(busy_b),
        "boats_free": len(boats_cfg) - len(busy_b),
    }


EQUITY_FLAG_RATIO = 1.5  # a group whose median is ≥ 1.5× the overall median is flagged
EQUITY_MIN_N = 3  # …but only with at least this many served people


def _q(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(round(p * (len(s) - 1))))], 1)


def equity_board(rows: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    """F14 — who waits longer? Time to pickup / to safety (simulated minutes
    from the SOS) by vulnerability class and by K-means cluster, from the
    stage machine's own timestamps. Still-waiting people are counted with how
    long they have waited so far (never folded into the served medians)."""
    now = now or _now()
    scale = TIME_SCALE / 60.0

    def mins(a, b):
        return (b - a).total_seconds() * scale if a and b else None

    recs = []
    for r in rows or []:
        if r.get("ops_status") == "merged":  # F30: the same people as the kept SOS
            continue
        ts = r.get("timestamps") or {}
        q = _parse(ts.get("queued"))
        recs.append(
            {
                "vulnerability": r.get("vulnerability") or "standard",
                "medical": medical_of(r),
                "cluster": r.get("cluster_id") or "—",
                "pickup": mins(q, _parse(ts.get("to_shelter"))),
                "safe": mins(q, _parse(ts.get("rescued"))) if r.get("ops_status") == "rescued" else None,
                "waiting": mins(q, now) if r.get("ops_status") != "rescued" else None,
            }
        )
    overall = [x["safe"] for x in recs if x["safe"] is not None]
    base = _q(overall, 0.5)

    def group(key: str) -> list[dict[str, Any]]:
        out = []
        for g in sorted({x[key] for x in recs}):
            m = [x for x in recs if x[key] == g]
            safe = [x["safe"] for x in m if x["safe"] is not None]
            pick = [x["pickup"] for x in m if x["pickup"] is not None]
            wait = [x["waiting"] for x in m if x["waiting"] is not None]
            med = _q(safe, 0.5)
            out.append(
                {
                    "group": g,
                    "people": len(m),
                    "served": len(safe),
                    "still_waiting": len(wait),
                    "longest_wait_min": round(max(wait), 1) if wait else None,
                    "pickup_p50": _q(pick, 0.5),
                    "pickup_p90": _q(pick, 0.9),
                    "safe_p50": med,
                    "safe_p90": _q(safe, 0.9),
                    "flag": bool(base and med is not None and len(safe) >= EQUITY_MIN_N and med >= EQUITY_FLAG_RATIO * base),
                }
            )
        return out

    by_v = group("vulnerability")
    by_c = group("cluster")
    by_m = group("medical")  # F21
    flagged = [f"{g['group']} ({k})" for k, rows_ in (("vulnerability", by_v), ("cluster", by_c), ("medical", by_m))
               for g in rows_ if g["flag"]]
    return {
        "overall": {"served": len(overall), "people": len(recs), "safe_p50": base, "safe_p90": _q(overall, 0.9)},
        "by_vulnerability": by_v,
        "by_cluster": by_c,
        "by_medical": by_m,
        "flagged": flagged,
        "rule": f"flag = median time to safety ≥ {EQUITY_FLAG_RATIO}× the overall median, with ≥ {EQUITY_MIN_N} served",
        "units": "simulated minutes from the SOS",
    }


def shelter_allocation_board(
    rows: list[dict[str, Any]], overrides: dict[str, dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Seats per allocatable shelter — the same arithmetic _pick_shelter uses
    (capacity - registry occupancy - people already allocated this run).
    A closed shelter has 0 seats left; delivered groups stay counted there."""
    reg = shelter_registry(overrides)
    out = []
    for name in SHELTER_POOL:
        s = reg.get(name)
        if not s:
            continue
        mine = [r for r in rows or [] if r.get("shelter_name") == name]
        ppl = lambda rs: sum(int(r.get("people") or 1) for r in rs)  # noqa: E731
        allocated = ppl(mine)
        cap = int(s["capacity"])
        base = int(s["occupancy"])
        out.append(
            {
                "name": name,
                "lat": s["lat"],
                "lon": s["lon"],
                "capacity": cap,
                "baseline_occupancy": base,
                "allocated_this_run": allocated,
                "incoming": ppl([r for r in mine if r.get("ops_status") in ACTIVE_STAGES]),
                "delivered_this_run": ppl([r for r in mine if r.get("ops_status") == "rescued"]),
                "seats_left": 0 if s["closed"] else max(0, cap - base - allocated),
                "closed": s["closed"],
                "base_capacity": int(s["base_capacity"]),
                "capacity_source": s.get("capacity_source"),
                "capacity_detail": s.get("capacity_detail"),
                "operator": name in (overrides or {}),
                "moved_away": sum(1 for r in rows or [] for c in (r.get("shelter_changes") or []) if c.get("old_shelter") == name),
                "utilisation_pct": round((base + allocated) / cap * 100.0, 1) if cap else None,
            }
        )
    return out


SYNC_KEYS = (
    "medical",
    "destination_kind",
    "hospital_alert",
    "hospitals_considered",
    "merged_into",
    "merged_from",
    "people",
    "reroutes",
    "shelter_changes",
    "shelter_wait",
    "rejected_units",
    "rejections",
    "accepted_via",
    "dispatch_choice",
    "decision",
    "ticket",
    "photo_url",
    "source",
    "accuracy_m",
    "route_alert",
    "driver_accepted",
    "accepted_at",
    "dispatch_request",
    "ops_status",
    "live_status",
    "status",
    "ambulance_name",
    "shelter_name",
    "shelter_lat",
    "shelter_lon",
    "journey",
    "rescued",
    "ops_stage_at",
    "ops_stage_seconds",
    "ops_wait_reason",
    "timestamps",
    "cluster_id",
    "assigned_team",
    "assigned_team_name",
    "vulnerability",
    "rescue_order",
    "needs_ambulance",
    "unit_role",
    "unit_name",
    "unit_base",
    "unit_base_name",
    "route_to_person",
    "route_to_shelter",
    "eta_min",
    "eta_to_shelter_min",
    "called_at",
    "answered",
)


def sync_citizen_from_log(citizen: dict[str, Any], log: dict[str, Any]) -> None:
    for key in SYNC_KEYS:
        if key in log:
            citizen[key] = log.get(key)
    if log.get("person_index") is not None:
        citizen["rescue_order"] = log.get("person_index")
    # A cleared wait reason must clear on the citizen too.
    if "ops_wait_reason" not in log:
        citizen.pop("ops_wait_reason", None)
    if "route_alert" not in log:
        citizen.pop("route_alert", None)
    if "shelter_wait" not in log:
        citizen.pop("shelter_wait", None)
