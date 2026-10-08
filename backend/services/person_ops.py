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
}

AMBULANCE_POOL = [f"Ambulance Unit {i}" for i in range(1, 11)]

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


def shelter_registry() -> dict[str, dict[str, Any]]:
    """name -> {lat, lon, capacity, occupancy}. Seed wins; desk fills gaps."""
    from backend.services.rescue_desk import SHELTERS as DESK
    from backend.services.seed import SHELTERS as SEED

    out: dict[str, dict[str, Any]] = {}
    for s in list(DESK) + list(SEED):
        out[s["name"]] = {
            "name": s["name"],
            "lat": float(s["lat"]),
            "lon": float(s["lon"]),
            "capacity": int(s.get("capacity") or 0),
            "occupancy": int(s.get("occupancy") or 0),
        }
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


def road_route(a: tuple[float, float], b: tuple[float, float], roads: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Flood-aware Dijkstra over the road graph (blocked roads removed), with
    straight connectors to/from the nearest graph node. Falls back to a direct
    segment when the graph has no open path."""
    import networkx as nx

    from backend.services.route_engine import _nearest_node, build_graph
    from backend.services.seed import GRAPH_NODES, ROADS

    a = (float(a[0]), float(a[1]))
    b = (float(b[0]), float(b[1]))
    straight = haversine_km(a[0], a[1], b[0], b[1])
    g = build_graph(list(roads or ROADS))
    src, dst = _nearest_node(*a), _nearest_node(*b)
    points: list[list[float]] = [[a[0], a[1]]]
    method = "direct"
    cost = straight
    if src != dst and src in g and dst in g and nx.has_path(g, src, dst):
        nodes = nx.shortest_path(g, src, dst, weight="weight")
        cost = haversine_km(a[0], a[1], *GRAPH_NODES[nodes[0]])
        for u, v in zip(nodes, nodes[1:]):
            cost += float(g.edges[u, v].get("weight") or 0)
        cost += haversine_km(*GRAPH_NODES[nodes[-1]], b[0], b[1])
        points += [[GRAPH_NODES[n][0], GRAPH_NODES[n][1]] for n in nodes]
        method = "dijkstra-flood"
    points.append([b[0], b[1]])
    km = sum(haversine_km(p[0], p[1], q[0], q[1]) for p, q in zip(points, points[1:]))
    minutes = travel_minutes(cost)
    return {
        "points": [[round(p[0], 6), round(p[1], 6)] for p in points],
        "km": round(km, 3),
        "sim_minutes": round(minutes, 1),
        "method": method,
    }


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
    row["needs_ambulance"] = needs_ambulance(row)
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


def _pick_shelter(row: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    reg = shelter_registry()
    committed: dict[str, int] = {}
    for r in rows:
        if r is not row and r.get("shelter_name"):
            committed[r["shelter_name"]] = committed.get(r["shelter_name"], 0) + int(r.get("people") or 1)
    need = int(row.get("people") or 1)
    lat, lon = float(row.get("lat") or 0), float(row.get("lon") or 0)
    options = []
    for name in SHELTER_POOL:
        s = reg.get(name)
        if not s:
            continue
        left = s["capacity"] - s["occupancy"] - committed.get(name, 0)
        options.append((left >= need, haversine_km(lat, lon, s["lat"], s["lon"]), s, left))
    usable = [o for o in options if o[0]]
    if not usable:
        return None
    _, _, s, left = min(usable, key=lambda o: o[1])
    return {**s, "seats_left_before": left}


def _assign(row: dict[str, Any], rows: list[dict[str, Any]], ctx: dict[str, Any], at: datetime) -> str | None:
    """Pick unit + shelter + route. Returns a wait reason when it cannot."""
    person = (float(row.get("lat") or 0), float(row.get("lon") or 0))
    base = _team_base(row, ctx.get("teams") or [])
    if base is None:
        return "No rescue team resolved for this cluster"
    shelter = _pick_shelter(row, rows)
    if shelter is None:
        return "No shelter with free seats for this group"
    base_name = row.get("assigned_team_name") or row.get("assigned_team")
    if row.get("needs_ambulance"):
        busy = _busy_ambulances(rows)
        free = [a for a in AMBULANCE_POOL if a not in busy]
        if not free:
            return f"All {len(AMBULANCE_POOL)} ambulances busy"
        row["ambulance_name"] = free[0]
        row["unit_role"] = "ambulance"
        row["unit_name"] = free[0]
        # Ambulances are a city-wide pool with no depot of their own in this
        # repo; they are dispatched from the rescue depot nearest the person.
        depot = _nearest_depot(person[0], person[1], ctx.get("teams") or [])
        if depot:
            base = (float(depot["lat"]), float(depot["lon"]))
            base_name = depot.get("name")
    else:
        row["ambulance_name"] = None
        row["unit_role"] = "rescue"
        row["unit_name"] = row.get("assigned_team_name") or row.get("assigned_team")
    row["unit_base"] = [base[0], base[1]]
    row["unit_base_name"] = base_name
    row["shelter_name"] = shelter["name"]
    row["shelter_lat"] = shelter["lat"]
    row["shelter_lon"] = shelter["lon"]
    row["route_to_person"] = road_route(base, person, ctx.get("roads"))
    row["route_to_shelter"] = road_route(person, (shelter["lat"], shelter["lon"]), ctx.get("roads"))
    row["eta_min"] = row["route_to_person"]["sim_minutes"]
    row["eta_to_shelter_min"] = row["route_to_shelter"]["sim_minutes"]
    row["assigned_team"] = row.get("assigned_team_name") or row.get("assigned_team")
    row.pop("ops_wait_reason", None)
    return None


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
    elif nxt == "en_route":
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
            )
            row["eta_to_shelter_min"] = row["route_to_shelter"]["sim_minutes"]
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


def _due(row: dict[str, Any]) -> datetime:
    started = _parse(row.get("ops_stage_at")) or _now()
    return started + timedelta(seconds=float(row.get("ops_stage_seconds") or 0))


def advance_all(rows: list[dict[str, Any]], ctx: dict[str, Any] | None = None, now: datetime | None = None) -> int:
    """Event-driven catch-up: repeatedly fire the earliest due transition until
    nothing is due at `now`. Returns the number of transitions fired."""
    ctx = ctx or {}
    now = now or _now()
    for i, row in enumerate(rows or []):
        ensure_ops(row, i + 1)
    changed = 0
    blocked: set[int] = set()  # queued rows waiting on a resource this pass
    clock = None
    for _ in range(len(rows or []) * 6 + 5):
        due_rows = [
            (_due(r), i)
            for i, r in enumerate(rows)
            if r.get("ops_status") != "rescued" and i not in blocked and _due(r) <= now
        ]
        if not due_rows:
            break
        due, i = min(due_rows, key=lambda x: x[0])
        row = rows[i]
        # A row that waited on a resource transitions when the resource freed.
        at = max(due, clock) if clock and row.get("ops_wait_reason") else due
        st = row.get("ops_status") or "queued"
        if st == "queued":
            reason = _assign(row, rows, ctx, at)
            if reason:
                if row.get("ops_wait_reason") != reason:
                    row["ops_wait_reason"] = reason
                    _journey(row, due, "WAITING", f"Held in queue — {reason}", "Administrator Agent", "queued")
                blocked.add(i)
                continue
        nxt = STAGES[min(len(STAGES) - 1, STAGES.index(st) + 1 if st in STAGES else 1)]
        _transition(row, nxt, at, ctx)
        clock = at
        changed += 1
        if nxt == "rescued":
            blocked.clear()  # an ambulance / seats may have freed up
    return changed


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


SYNC_KEYS = (
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
