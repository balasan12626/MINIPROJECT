"""Headless operation simulator — ONE core, two callers.

* F12 stress test (`scripts/monte_carlo_ops.py`): `make_instance` + `play` on a
  SYNTHETIC seeded operation, every policy on the same instance.
* F16 what-if planner: `snapshot(engine)` copies the LIVE run and
  `play_whatif` plays the next N simulated minutes once per option.

Both drive the live stage machine (`person_ops`) on a virtual clock — there is
no second simulator. Nothing here mutates the engine: the what-if works on deep
copies and its ambulance pool / route chooser live in `person_ops.isolated()`.
"""

from __future__ import annotations

import copy
import math
import random
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.services import person_ops as po
from backend.services import seed
from backend.utils.geo import haversine_km

POLICIES = {
    # idealised: launches from the depot nearest the person wherever the ambulance
    # really is — reported, but NOT a fair baseline for the position-aware policies
    "nearest_depot": {"dispatch_policy": "nearest_depot", "preposition": False},
    "first_free": {"dispatch_policy": "first_free", "preposition": False},
    "greedy": {"dispatch_policy": "greedy", "preposition": False},
    "optimal": {"dispatch_policy": "optimal", "preposition": False},
    "optimal+prepos": {"dispatch_policy": "optimal", "preposition": True},
}
T0 = datetime(2026, 7, 1, 6, 0, 0, tzinfo=timezone.utc)
STEP_S = 2.0  # one engine tick of wall time
STEP_LATE_S = 6.0  # step once closures stop changing
PREPOS_EVERY = 3  # pre-positioning re-plans every 3 ticks
PREPOS_P = 0.7  # flood probability used for hotspot weights (fixed: no ML in the batch run)
TICKS = 36  # the default scenario length, then the operation runs on
HORIZON_S = 1500.0  # wall s on the demo clock (= 50 simulated hours): unserved after this = censored
SIM_MIN_PER_S = po.TIME_SCALE / 60.0
WATER = ["ankle-deep", "knee-deep", "waist-deep", "chest-deep"]


# ---- F23: zone warnings (shared by the live engine, the stress test and the what-if) ---

ZONE_ROAD_KM = 1.5  # a road "belongs" to a zone when its point is within this distance


def zone_road_ids(zones: list[dict[str, Any]] | None = None, roads: list[dict[str, Any]] | None = None) -> dict[str, list[str]]:
    zones = seed.ZONES if zones is None else zones
    roads = seed.ROADS if roads is None else roads
    out: dict[str, list[str]] = {}
    for z in zones:
        out[str(z["zone_id"])] = [r["road_id"] for r in roads if r.get("lat") is not None
                                  and haversine_km(float(z["lat"]), float(z["lon"]), float(r["lat"]), float(r["lon"])) <= ZONE_ROAD_KM]
    return out


def zone_warn_times(close_s: dict[str, float], lead_s: float, zone_roads: dict[str, list[str]]) -> dict[str, float]:
    """Warning time per zone = (first close time of its roads) − lead, never < 0."""
    out = {}
    for zid, rids in zone_roads.items():
        ts = [close_s[r] for r in rids if r in close_s]
        if ts:
            out[zid] = max(0.0, min(ts) - lead_s)
    return out


def warned_zone_near(lat: float, lon: float, at_s: float, warn_s: dict[str, float], zones: list[dict[str, Any]] | None = None) -> str | None:
    """A zone within ZONE_ROAD_KM of (lat, lon) whose warning was out by `at_s`."""
    for z in seed.ZONES if zones is None else zones:
        w = warn_s.get(str(z["zone_id"]))
        if w is not None and w <= at_s and haversine_km(lat, lon, float(z["lat"]), float(z["lon"])) <= ZONE_ROAD_KM:
            return str(z["zone_id"])
    return None


# ---- F12: synthetic instance ---------------------------------------------------------

def make_instance(rng: random.Random, n_sos: int, surge: int) -> dict[str, Any]:
    zones = seed.ZONES
    callers = []
    for i in range(n_sos + surge):
        z = rng.choice(zones)
        r = rng.random()
        age = rng.randint(3, 11) if r < 0.15 else rng.randint(66, 88) if r < 0.35 else rng.randint(18, 60)
        callers.append(
            {
                "citizen_name": f"Caller {i + 1:03d}",
                "age": age,
                "water_level_note": rng.choice(WATER),
                "people": rng.randint(1, 5),
                "lat": round(float(z["lat"]) + rng.gauss(0, 0.006), 6),
                "lon": round(float(z["lon"]) + rng.gauss(0, 0.006), 6),
                "arrive_s": 0.0 if i < n_sos else rng.uniform(60, 240),
            }
        )
    shelters = list(po.SHELTER_POOL)
    return {
        "callers": callers,
        "blockage0": round(rng.uniform(0.05, 0.25), 3),
        "shelter_closed": rng.choice(shelters) if shelters else None,
        "shelter_close_s": rng.uniform(40, 160),
    }


def blockage_at(b0: float, tick: int) -> float:
    growth = 1 - math.exp(-tick / 8.0)  # same curve as engine._evolve
    return min(0.95, b0 + 0.25 * growth)


def roads_at(b: float, closed: set[str], exposure_model: str = "distance") -> list[dict[str, Any]]:
    out = []
    for r in seed.ROADS:
        x = dict(r)
        expo = float(r.get("flood_exposure_v2") if exposure_model == "hand" else r.get("flood_exposure") or 0)
        x["blocked"] = r["road_id"] in closed or expo >= 0.85 - b
        x["accessible"] = not x["blocked"]
        out.append(x)
    return out


def _arrive(rows: list[dict[str, Any]], c: dict[str, Any], teams: list[dict[str, Any]], at: datetime) -> dict[str, Any]:
    """Queue one caller at `at` (cluster team = nearest depot), as the MC run does."""
    depot = min(teams, key=lambda d: haversine_km(c["lat"], c["lon"], d["lat"], d["lon"]))
    row = {k: v for k, v in c.items() if k != "arrive_s"}
    row.update({"assigned_team": depot["name"], "assigned_team_name": depot["name"], "cluster_id": depot["team_id"]})
    po.ensure_ops(row, len(rows) + 1, queue_position=1, at=at)
    row["person_index"] = len(rows) + 1
    rows.append(row)
    return row


def _outcomes(rows: list[dict[str, Any]], since: datetime | None = None) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        ts = r.get("timestamps") or {}
        q = po._parse(ts.get("queued"))
        pick = po._parse(ts.get("to_shelter"))
        safe = po._parse(ts.get("rescued"))
        rec = {
            "citizen_name": r.get("citizen_name"),
            "vulnerability": r.get("vulnerability"),
            "needs_ambulance": bool(r.get("needs_ambulance")),
            "pickup_min": round((pick - q).total_seconds() * SIM_MIN_PER_S, 2) if pick and q else None,
            "safe_min": round((safe - q).total_seconds() * SIM_MIN_PER_S, 2) if safe and q else None,
            "no_open_road": bool(r.get("route_alert")),
        }
        if since is not None:  # what-if: minutes from the snapshot until safe
            rec["safe_from_now_min"] = round(max(0.0, (safe - since).total_seconds()) * SIM_MIN_PER_S, 2) if safe else None
            rec["synthetic"] = bool(r.get("synthetic_arrival"))
        out.append(rec)
    return out


def road_close_times(b0: float, exposure_model: str = "distance") -> dict[str, float]:
    """Wall second at which the flood rule closes each road in a synthetic run."""
    out: dict[str, float] = {}
    for k in range(TICKS):
        b = blockage_at(b0, k)
        for r in seed.ROADS:
            expo = float(r.get("flood_exposure_v2") if exposure_model == "hand" else r.get("flood_exposure") or 0)
            if r["road_id"] not in out and expo >= 0.85 - b:
                out[r["road_id"]] = k * STEP_S
    return out


def avoided_by_warning(inst: dict[str, Any], compliance: float, lead_min: float) -> set[str]:
    """F23: late callers near a zone that was already warned leave early with
    probability `compliance` (an ASSUMED share, swept — never a finding).
    Separate seeded RNG: compliance 0 changes nothing at all."""
    if compliance <= 0:
        return set()
    warn = zone_warn_times(road_close_times(inst["blockage0"]), lead_min * 60.0 / po.TIME_SCALE, zone_road_ids())
    rng = random.Random(int(inst["blockage0"] * 1e6) + 7)
    out = set()
    for c in inst["callers"]:
        u = rng.random()
        if c["arrive_s"] > 0 and warned_zone_near(c["lat"], c["lon"], c["arrive_s"], warn) and u < compliance:
            out.add(c["citizen_name"])
    return out


def make_long_instance(rng: random.Random, hours: float, per_hour: float) -> dict[str, Any]:
    """F25: a LONG synthetic operation — SOS arrive all through `hours`
    (Poisson, `per_hour`), placed and aged like make_instance. Synthetic."""
    zones = seed.ZONES
    callers, t, i = [], 0.0, 0
    end_s = hours * 3600.0 / po.TIME_SCALE  # wall seconds on the demo clock
    rate = per_hour / (3600.0 / po.TIME_SCALE)  # per wall second
    while True:
        t += rng.expovariate(rate)
        if t > end_s:
            break
        z = rng.choice(zones)
        r = rng.random()
        age = rng.randint(3, 11) if r < 0.15 else rng.randint(66, 88) if r < 0.35 else rng.randint(18, 60)
        i += 1
        callers.append({"citizen_name": f"Caller {i:04d}", "age": age, "water_level_note": rng.choice(WATER),
                        "people": rng.randint(1, 5), "lat": round(float(z["lat"]) + rng.gauss(0, 0.006), 6),
                        "lon": round(float(z["lon"]) + rng.gauss(0, 0.006), 6), "arrive_s": t})
    return {"callers": callers, "blockage0": round(rng.uniform(0.05, 0.25), 3), "shelter_closed": None,
            "shelter_close_s": 0.0}


def play(inst: dict[str, Any], policy: dict[str, Any], compliance: float = 0.0, lead_min: float = 30.0,
         crew: dict[str, Any] | None = None, horizon_s: float = HORIZON_S, keep_rows: bool = False) -> dict[str, Any]:
    """One operation under one policy; returns per-person outcome rows."""
    teams = list(seed.RESCUE_TEAMS)
    closed: set[str] = set()
    ctx: dict[str, Any] = {"teams": teams, "shelter_overrides": {}, "staging": {},
                           "dispatch_policy": policy["dispatch_policy"]}
    if policy.get("fair_lambda") is not None:  # F32
        ctx["fair_lambda"] = policy["fair_lambda"]
    if crew:
        ctx["crew_rules"] = crew
    rows: list[dict[str, Any]] = []
    gone = avoided_by_warning(inst, compliance, lead_min)
    pending = sorted((c for c in inst["callers"] if c["citizen_name"] not in gone), key=lambda c: c["arrive_s"])
    shelter_done = False
    t = 0.0
    tick = 0
    while t <= horizon_s:
        now = T0 + timedelta(seconds=t)
        # arrivals (queued at their arrival time; cluster team = nearest depot)
        while pending and pending[0]["arrive_s"] <= t:
            c = pending.pop(0)
            _arrive(rows, c, teams, T0 + timedelta(seconds=c["arrive_s"]))
        # F34: a stored run replays ITS closures and shelter changes, not the synthetic rule
        if inst.get("closure_schedule") is not None:
            sched = inst["closure_schedule"]
            newly = {rid for s, ids in sched if s <= t for rid in ids} - closed
            if newly or "roads" not in ctx:
                closed |= newly
                ctx["roads"] = roads_at(-1.0, closed)  # b = -1: only the replayed closures
                if newly:
                    po.reroute(rows, ctx["roads"], "flood closure (replayed)", now=now)
                    po.reallocate(rows, ctx["shelter_overrides"], ctx["roads"], "flood closure (replayed)", now=now)
            ov = [o for s, o in inst.get("shelter_schedule") or [] if s <= t]
            if ov and ov[-1] != ctx["shelter_overrides"]:
                ctx["shelter_overrides"] = copy.deepcopy(ov[-1])
                po.reallocate(rows, ctx["shelter_overrides"], ctx["roads"], "shelter change (replayed)", now=now)
        # flood rule closes roads (grow-only) → live re-route of affected legs
        elif tick < TICKS:
            b = blockage_at(inst["blockage0"], tick)
            newly = {r["road_id"] for r in seed.ROADS if float(r.get("flood_exposure") or 0) >= 0.85 - b} - closed
            if newly:
                closed |= newly
                ctx["roads"] = roads_at(b, closed)
                po.reroute(rows, ctx["roads"], "flood closure", now=now)
                po.reallocate(rows, ctx["shelter_overrides"], ctx["roads"], "flood closure", now=now)
            ctx.setdefault("roads", roads_at(b, closed))
        if not shelter_done and inst["shelter_closed"] and t >= inst["shelter_close_s"]:
            shelter_done = True
            ctx["shelter_overrides"] = {inst["shelter_closed"]: {"closed": True}}
            po.reallocate(rows, ctx["shelter_overrides"], ctx["roads"], "shelter closed", now=now)
        po.advance_all(rows, ctx, now=now)
        if policy["preposition"] and tick % PREPOS_EVERY == 0:
            moves = po.plan_staging(rows, ctx, PREPOS_P, now=now)
            ctx["staging"].update(moves)
        if not pending and rows and all(r.get("ops_status") == "rescued" for r in rows):
            break
        # Transitions are stamped when DUE (event-driven), so a coarser step
        # after the flood stops growing changes no timestamp — only speed.
        t += STEP_S if tick < TICKS else STEP_LATE_S
        tick += 1
    out = {"people": _outcomes(rows), "roads_closed": len(closed), "end_s": t}
    if compliance > 0:
        out["sos_avoided"] = len(gone)
    if keep_rows:
        out["rows"] = rows
    return out


# ---- F34: hindsight replay of a stored run -------------------------------------------

def from_frames(frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Rebuild a run's arrivals, road closures and shelter changes from its
    stored replay frames (F5) as an instance `play` can replay."""
    frames = sorted(frames, key=lambda f: f.get("seq") or 0)
    if not frames:
        raise ValueError("no frames")
    first_seen: dict[str, dict[str, Any]] = {}
    recorded: dict[str, float | None] = {}
    for f in frames:
        for c in f.get("citizens") or []:
            n = c.get("citizen_name")
            if n and n not in first_seen:
                first_seen[n] = c
            ts = c.get("timestamps") or {}
            q, s = po._parse(ts.get("queued")), po._parse(ts.get("rescued"))
            if n and q and s:
                recorded[n] = round((s - q).total_seconds() * SIM_MIN_PER_S, 2)
    queued = {n: po._parse((c.get("timestamps") or {}).get("queued")) for n, c in first_seen.items()}
    t0 = min(t for t in queued.values() if t) if any(queued.values()) else po._parse(frames[0]["at"])
    callers = []
    for n, c in first_seen.items():
        if c.get("merged_into") or c.get("ops_status") == "merged":
            continue
        q = queued.get(n) or t0
        callers.append({"citizen_name": n, "age": c.get("age"), "water_level_note": c.get("water_level_note") or "",
                        "people": c.get("people") or 1, "lat": c.get("lat"), "lon": c.get("lon"),
                        "medical": c.get("medical") or "none", "arrive_s": max(0.0, (q - t0).total_seconds())})
    closures, seen = [], set()
    shelters, last_ov = [], None
    for f in frames:
        s = max(0.0, (po._parse(f["at"]) - t0).total_seconds())
        new = sorted(set(f.get("roads_closed") or []) - seen)
        if new:
            closures.append((s, new))
            seen |= set(new)
        ov = f.get("shelter_overrides") or {}
        if ov != last_ov:
            shelters.append((s, copy.deepcopy(ov)))
            last_ov = ov
    head = frames[-1]
    return {"callers": callers, "closure_schedule": closures, "shelter_schedule": shelters,
            "blockage0": 0.0, "shelter_closed": None, "shelter_close_s": 0.0,
            "recorded_safe_min": recorded, "run_id": head.get("run_id"), "city": head.get("city"),
            "policy": {"dispatch_policy": head.get("dispatch_policy"), "fair_lambda": head.get("fair_lambda"),
                       "preposition": bool(head.get("preposition"))} if head.get("dispatch_policy") else None}


def hindsight_bound(inst: dict[str, Any]) -> dict[str, float | None]:
    """A per-person LOWER BOUND on time to safety, knowing every arrival in
    advance (labelled "hindsight bound, not achievable live"): the first
    dispatch slot + roll-out + the STRAIGHT-LINE distance from the nearest
    possible unit start (any depot or shelter) to the person + the straight-line
    distance to the nearest shelter, at rescue speed, each leg at least the
    stage machine's floor. No road path, re-route or queue can be shorter, so
    no policy can beat it (a straight line is the shortest any leg can be,
    including the planner's own "direct" estimates)."""
    from backend.services.route_engine import travel_minutes

    reg = po.shelter_registry()
    starts = [(float(t["lat"]), float(t["lon"])) for t in seed.RESCUE_TEAMS] + [(s["lat"], s["lon"]) for s in reg.values()]
    shelters = [(s["lat"], s["lon"]) for n, s in reg.items() if n in po.SHELTER_POOL] or [(s["lat"], s["lon"]) for s in reg.values()]
    floor_min = po.MIN_LEG_SECONDS * SIM_MIN_PER_S
    fixed = (po.DISPATCH_SECONDS + po.MOBILISE_SECONDS) * SIM_MIN_PER_S
    out: dict[str, float | None] = {}
    for c in inst["callers"]:
        p = (float(c["lat"]), float(c["lon"]))
        to_p = min(haversine_km(p[0], p[1], a, b) for a, b in starts)
        to_s = min(haversine_km(p[0], p[1], a, b) for a, b in shelters) if shelters else None
        out[c["citizen_name"]] = None if to_s is None else round(
            fixed + max(floor_min, travel_minutes(to_p)) + max(floor_min, travel_minutes(to_s)), 2)
    return out


def stats(xs: list[float]) -> dict[str, Any]:
    if not xs:
        return {"n": 0, "mean": None, "p50": None, "p90": None}
    s = sorted(xs)
    return {
        "n": len(s),
        "mean": round(statistics.fmean(s), 2),
        "p50": round(statistics.median(s), 2),
        "p90": round(s[min(len(s) - 1, int(round(0.9 * (len(s) - 1))))], 2),
    }


def summarise(per_policy: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, runs in per_policy.items():
        people = [p for run in runs for p in run["people"]]
        served = [p for p in people if p["safe_min"] is not None]
        groups = sorted({p["vulnerability"] or "standard" for p in people})
        out[name] = {
            "people": len(people),
            "served": len(served),
            "censored": len(people) - len(served),
            "time_to_pickup_min": stats([p["pickup_min"] for p in people if p["pickup_min"] is not None]),
            "time_to_safety_min": stats([p["safe_min"] for p in served]),
            "ambulance_cases_time_to_safety_min": stats([p["safe_min"] for p in served if p["needs_ambulance"]]),
            "by_vulnerability": {
                g: stats([p["safe_min"] for p in served if (p["vulnerability"] or "standard") == g]) for g in groups
            },
        }
    return out


def paired(per_policy: dict[str, list[dict[str, Any]]], base: str = "nearest_depot", key: str = "safe_min") -> dict[str, Any]:
    """Per-run mean time-to-safety difference vs `base` (same instance)."""
    def run_mean(run):
        xs = [p[key] for p in run["people"] if p.get(key) is not None]
        return statistics.fmean(xs) if xs else None

    base_means = [run_mean(r) for r in per_policy[base]]
    out = {}
    for name, runs in per_policy.items():
        if name in (base, "nearest_depot"):  # the idealised rule is not a fair pair
            continue
        d = [run_mean(r) - b for r, b in zip(runs, base_means) if run_mean(r) is not None and b is not None]
        if not d:
            continue
        sd = statistics.pstdev(d) if len(d) > 1 else 0.0
        out[name] = {
            "runs": len(d),
            "mean_diff_min": round(statistics.fmean(d), 2),
            "ci95_min": [round(statistics.fmean(d) - 1.96 * sd / math.sqrt(len(d)), 2),
                         round(statistics.fmean(d) + 1.96 * sd / math.sqrt(len(d)), 2)],
            "faster_in_pct_of_runs": round(100.0 * sum(x < 0 for x in d) / len(d), 1),
        }
    return out


# ---- F16: what-if from the live run ----------------------------------------------------

OPTION_KINDS = ("baseline", "add_ambulances", "close_shelter", "set_capacity", "block_road", "open_road",
                "dispatch_policy", "preposition")
MAX_EXTRA_AMBULANCES = 10


def snapshot(engine, now: datetime | None = None) -> dict[str, Any]:
    """Deep copy of everything the stage machine needs from the LIVE run.
    The engine is only read. Future flood closures come from the engine's own
    rule run forward (the F10 forecast); operator-controlled roads are kept."""
    now = now or datetime.now(timezone.utc)
    if engine.contact_log:
        po.advance_all(engine.contact_log, engine.ops_ctx(), now=now)  # same catch-up state() does
    ctx = engine.ops_ctx()
    rows = copy.deepcopy(engine.contact_log)
    params = engine.params or {}
    delay = float(params.get("tick_seconds") or 2.0)
    closures: list[tuple[float, list[str]]] = []
    for rid, f in engine.road_forecast().items():
        closures.append((float(f["closes_in_ticks"]) * delay, [rid]))
    closures.sort()
    # Observed SOS arrival rate of THIS run (rows queued after the first batch).
    qs = sorted(t for t in (po._parse((r.get("timestamps") or {}).get("queued")) for r in rows) if t)
    later = [t for t in qs if qs and (t - qs[0]).total_seconds() > 5]
    elapsed = (now - qs[0]).total_seconds() if qs else 0.0
    rate = len(later) / elapsed if elapsed > 30 else 0.0
    view = engine.current_view() if hasattr(engine, "current_view") else {}
    # F23: when each zone is (or will be) warned, in wall s from the snapshot.
    from backend.agents.mas import PLAYBOOK

    lead_s = float(PLAYBOOK.get("warning_lead_min") or 30) * 60.0 / po.TIME_SCALE
    close_s = {r["road_id"]: 0.0 for r in ctx["roads"] if r.get("blocked") and r.get("source") == "flood"}
    for rid, f in engine.road_forecast().items():
        close_s.setdefault(rid, float(f["closes_in_sim_min"]) * 60.0 / po.TIME_SCALE)
    return {
        "taken_at": now,
        "run_id": engine.run_id,
        "tick": int(engine.tick or 0),
        "city": (params.get("city") or None),
        "rows": rows,
        "teams": copy.deepcopy(ctx.get("teams") or list(seed.RESCUE_TEAMS)),
        "roads": copy.deepcopy(ctx["roads"]),
        "shelter_overrides": copy.deepcopy(ctx.get("shelter_overrides") or {}),
        "staging": copy.deepcopy(ctx.get("staging") or {}),
        "closing": dict(ctx.get("closing") or {}),
        "dispatch_policy": ctx.get("dispatch_policy") or "nearest_depot",
        "fair_lambda": ctx.get("fair_lambda"),
        "crew_rules": copy.deepcopy(ctx.get("crew_rules")),
        "preposition": bool(params.get("preposition")),
        "flood_probability": (view or {}).get("flood_probability"),
        "accept_mode": ctx.get("accept_mode") or "auto",
        "future_closures": closures,
        "arrival_rate_per_wall_s": rate,
        "zone_warn_s": zone_warn_times(close_s, lead_s, zone_road_ids()),
        "warning_compliance": float(params.get("warning_compliance") or 0.0),
    }


def validate_option(opt: dict[str, Any]) -> str | None:
    """Reason the option is invalid for the current city, or None."""
    kind = opt.get("kind")
    if kind not in OPTION_KINDS:
        return f"unknown option {kind}"
    if kind == "add_ambulances" and not (1 <= int(opt.get("n") or 0) <= MAX_EXTRA_AMBULANCES):
        return f"add_ambulances needs 1..{MAX_EXTRA_AMBULANCES}"
    if kind in ("close_shelter", "set_capacity") and opt.get("name") not in po.shelter_registry():
        return f"unknown shelter {opt.get('name')}"
    if kind == "set_capacity" and (opt.get("capacity") is None or int(opt["capacity"]) < 0):
        return "set_capacity needs capacity >= 0"
    if kind in ("block_road", "open_road") and opt.get("road_id") not in {r["road_id"] for r in seed.ROADS}:
        return f"unknown road {opt.get('road_id')}"
    if kind == "dispatch_policy" and opt.get("policy") not in po.DISPATCH_POLICIES:
        return f"unknown policy {opt.get('policy')}"
    return None


def option_label(opt: dict[str, Any]) -> str:
    k = opt.get("kind")
    return {
        "baseline": "No change",
        "add_ambulances": f"+{opt.get('n')} ambulances",
        "close_shelter": f"Close {opt.get('name')}",
        "set_capacity": f"{opt.get('name')} capacity {opt.get('capacity')}",
        "block_road": f"Block road {opt.get('road_id')}",
        "open_road": f"Open road {opt.get('road_id')}",
        "dispatch_policy": f"Dispatch: {opt.get('policy')}",
        "preposition": f"Pre-positioning {'on' if opt.get('on') else 'off'}",
    }.get(k, str(k))


def _apply_option(opt: dict[str, Any], rows, ctx, state: dict[str, Any], now: datetime) -> list[str]:
    """Apply one option to the COPIED state at t=0. Returns the extra pool."""
    kind = opt.get("kind")
    extra: list[str] = []
    if kind == "add_ambulances":
        extra = [f"Extra Unit {i}" for i in range(1, int(opt["n"]) + 1)]
    elif kind in ("close_shelter", "set_capacity"):
        ov = ctx["shelter_overrides"].setdefault(opt["name"], {})
        if kind == "close_shelter":
            ov["closed"] = True
        else:
            ov["capacity"] = int(opt["capacity"])
        po.reallocate(rows, ctx["shelter_overrides"], ctx["roads"], f"what-if: {option_label(opt)}", now=now)
    elif kind in ("block_road", "open_road"):
        blocked = kind == "block_road"
        for r in ctx["roads"]:
            if r["road_id"] == opt["road_id"]:
                r["blocked"], r["accessible"], r["source"] = blocked, not blocked, "operator"
        state["operator_roads"].add(opt["road_id"])
        po.reroute(rows, ctx["roads"], f"what-if: {option_label(opt)}", improve=not blocked, now=now)
        po.reallocate(rows, ctx["shelter_overrides"], ctx["roads"], f"what-if: {option_label(opt)}", now=now)
    elif kind == "dispatch_policy":
        ctx["dispatch_policy"] = opt["policy"]
    elif kind == "preposition":
        state["preposition"] = bool(opt.get("on"))
    return extra


def play_whatif(snap: dict[str, Any], opt: dict[str, Any], horizon_min: float, rng: random.Random,
                arrivals: bool = True, keep_rows: bool = False) -> dict[str, Any]:
    """Play `horizon_min` simulated minutes from the snapshot under one option."""
    rows = copy.deepcopy(snap["rows"])
    ctx: dict[str, Any] = {
        "teams": copy.deepcopy(snap["teams"]),
        "roads": copy.deepcopy(snap["roads"]),
        "shelter_overrides": copy.deepcopy(snap["shelter_overrides"]),
        "staging": copy.deepcopy(snap["staging"]),
        "closing": dict(snap["closing"]),
        "dispatch_policy": snap["dispatch_policy"],
        # Simulated crews accept: a what-if cannot know a real driver's answer.
        "accept_mode": "auto",
        "crew_rules": copy.deepcopy(snap.get("crew_rules")),
        "fair_lambda": snap.get("fair_lambda"),
    }
    start: datetime = snap["taken_at"]
    state = {"preposition": snap["preposition"], "operator_roads": set()}
    extra = _apply_option(opt, rows, ctx, state, start)
    pool = list(po.AMBULANCE_POOL) + extra
    horizon_s = float(horizon_min) * 60.0 / po.TIME_SCALE
    # Synthetic future SOS at the run's own observed rate (Poisson), each one a
    # resample of a real caller of this run, jittered ~400 m. Labelled synthetic.
    pending: list[dict[str, Any]] = []
    rate = snap["arrival_rate_per_wall_s"] if arrivals else 0.0
    if rate > 0 and snap["rows"]:
        t = rng.expovariate(rate)
        k = 0
        while t <= horizon_s:
            src = rng.choice(snap["rows"])
            k += 1
            pending.append({
                "citizen_name": f"What-if arrival {k:03d}",
                "age": src.get("age"), "water_level_note": src.get("water_level_note"),
                "people": src.get("people") or 1,
                "lat": round(float(src.get("lat") or 0) + rng.gauss(0, 0.004), 6),
                "lon": round(float(src.get("lon") or 0) + rng.gauss(0, 0.004), 6),
                "arrive_s": t,
            })
            t += rng.expovariate(rate)
    # F23: arrivals near an already-warned zone leave early with the ASSUMED
    # compliance (separate RNG, so compliance 0 changes nothing).
    avoided = 0
    comp = float(snap.get("warning_compliance") or 0.0)
    if comp > 0 and pending:
        rng2 = random.Random(rng.random())
        keep = []
        for c in pending:
            if warned_zone_near(c["lat"], c["lon"], c["arrive_s"], snap.get("zone_warn_s") or {}) and rng2.random() < comp:
                avoided += 1
            else:
                keep.append(c)
        pending = keep
    closures = list(snap["future_closures"])
    teams = ctx["teams"] or list(seed.RESCUE_TEAMS)
    n_before = len(rows)
    t = 0.0
    tick = 0
    with po.isolated(pool=pool, chooser="dijkstra"):
        while t <= horizon_s:
            now = start + timedelta(seconds=t)
            while pending and pending[0]["arrive_s"] <= t:
                c = pending.pop(0)
                row = _arrive(rows, c, teams, start + timedelta(seconds=c["arrive_s"]))
                row["synthetic_arrival"] = True
            newly = []
            while closures and closures[0][0] <= t:
                newly += [rid for rid in closures.pop(0)[1] if rid not in state["operator_roads"]]
            if newly:
                for r in ctx["roads"]:
                    if r["road_id"] in newly:
                        r["blocked"], r["accessible"], r["source"] = True, False, "flood"
                po.reroute(rows, ctx["roads"], "flood closure (forecast)", now=now)
                po.reallocate(rows, ctx["shelter_overrides"], ctx["roads"], "flood closure (forecast)", now=now)
            po.advance_all(rows, ctx, now=now)
            if state["preposition"] and tick % PREPOS_EVERY == 0:
                ctx["staging"].update(po.plan_staging(rows, ctx, snap.get("flood_probability") or PREPOS_P, now=now))
            if not pending and all(r.get("ops_status") == "rescued" for r in rows):
                break
            t += STEP_S
            tick += 1
    # Only people not yet safe at the snapshot count (rescued ones cannot change).
    open_names = {r.get("citizen_name") for r in snap["rows"] if r.get("ops_status") != "rescued"}
    people = [p for p, r in zip(_outcomes(rows, since=start), rows)
              if r.get("citizen_name") in open_names or r.get("synthetic_arrival")]
    for p in people:  # unserved at the horizon count as the horizon (a lower bound)
        p["safe_or_horizon_min"] = p["safe_from_now_min"] if p["safe_from_now_min"] is not None else float(horizon_min)
    out = {"people": people, "added_rows": len(rows) - n_before, "sos_avoided_by_warning": avoided}
    if keep_rows:
        out["rows"] = rows
    return out


def whatif_summary(per_option: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    base = per_option.get("baseline") or []
    for name, runs in per_option.items():
        people = [p for run in runs for p in run["people"]]
        served = [p["safe_from_now_min"] for p in people if p["safe_from_now_min"] is not None]
        n_runs = max(1, len(runs))
        out[name] = {
            "people_per_run": round(len(people) / n_runs, 1),
            "served_per_run": round(len(served) / n_runs, 1),
            "still_waiting_per_run": round((len(people) - len(served)) / n_runs, 1),
            "synthetic_arrivals_per_run": round(sum(1 for p in people if p.get("synthetic")) / n_runs, 1),
            "sos_avoided_by_warning_per_run": round(sum(r.get("sos_avoided_by_warning", 0) for r in runs) / n_runs, 1),
            "time_to_safe_from_now_min": stats(served),
            # Fair across options that serve different numbers of people:
            # anyone still waiting at the horizon counts as the horizon.
            "time_to_safe_censored_min": stats([p["safe_or_horizon_min"] for p in people]),
        }
        if name != "baseline" and base:
            out[name]["vs_baseline"] = paired({"baseline": base, name: runs}, "baseline", key="safe_or_horizon_min").get(name)
    return out
