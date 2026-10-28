"""F28 — food, water (and basic medicine) supply runs to shelters.

Need per shelter = people DELIVERED there this run (the stage machine's own
`rescued` rows) × the Sphere minimum rates below. Stock (in person-days)
starts at an ASSUMED level and falls with simulated time; supply trucks — an
ASSUMED, labelled fleet, default OFF — drive from the city's depots to the
shelter with the fewest hours of stock left (nearest-need-first), on the SHARED
router (`person_ops.road_route`, F10-aware), timed like every unit leg
(`leg_seconds`), and are re-planned when a road on their route closes (F1).
Trucks are not SOS rows, so they never change SOS counters or fairness boards.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from backend.services import person_ops as po
from backend.utils.geo import haversine_km

# Sphere Handbook 2018 (4th ed.): Water supply standard 2.1 — at least 15 L per
# person per day for drinking and domestic hygiene; Food security and nutrition —
# 2,100 kcal per person per day.
WATER_L_PER_PERSON_DAY = 15.0
FOOD_KCAL_PER_PERSON_DAY = 2100.0
RATES_SOURCE = ("Sphere Handbook 2018: water ≥ 15 L / person / day (WASH water supply standard 2.1); "
                "food 2,100 kcal / person / day (food security and nutrition)")
DEFAULTS = {"trucks": 3, "load_person_days": 1500.0, "initial_stock_days": 1.0, "reorder_hours": 24.0}
ASSUMED = ("assumed fleet: trucks, load (person-days of water + food per trip), the starting stock "
           "(days of supplies for each shelter's capacity) and the reorder point (a truck is sent when a shelter "
           "has under 24 h of stock) are labelled parameters, not data")


def settings(params: dict[str, Any] | None) -> dict[str, float] | None:
    s = (params or {}).get("supply")
    if not s or not s.get("on"):
        return None
    return {k: float(s.get(k) or v) for k, v in DEFAULTS.items()}


class SupplyOps:
    def __init__(self, cfg: dict[str, float], teams: list[dict[str, Any]], shelters: dict[str, dict[str, Any]], now: datetime):
        self.cfg = cfg
        homes = [t for t in teams if t.get("lat") is not None] or [{"name": "depot", "lat": 0.0, "lon": 0.0}]
        self.trucks = [{"name": f"Supply Truck {i + 1}", "home": homes[i % len(homes)]["name"],
                        "lat": float(homes[i % len(homes)]["lat"]), "lon": float(homes[i % len(homes)]["lon"]),
                        "leg": None, "trips": 0} for i in range(int(cfg["trucks"]))]
        self.stock = {n: float(s.get("capacity") or 0) * cfg["initial_stock_days"] for n, s in shelters.items()}
        self.delivered_pd: dict[str, float] = {}
        self.last = now
        self.log: list[dict[str, Any]] = []

    # ---- helpers ---------------------------------------------------------------
    @staticmethod
    def people_at(rows: list[dict[str, Any]]) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in rows or []:
            if r.get("ops_status") == "rescued" and r.get("shelter_name") and r.get("destination_kind") != "hospital":
                out[r["shelter_name"]] = out.get(r["shelter_name"], 0) + int(r.get("people") or 1)
        return out

    def hours_left(self, name: str, people: int) -> float | None:
        if people <= 0:
            return None
        return round(self.stock.get(name, 0.0) / people * 24.0, 1)

    def _where(self, t: dict[str, Any], now: datetime) -> tuple[float, float]:
        leg = t.get("leg")
        if not leg:
            return t["lat"], t["lon"]
        secs = float(leg["seconds"]) or 1.0
        frac = max(0.0, min(1.0, (now - po._parse(leg["depart_at"])).total_seconds() / secs))
        p = po.position_on(leg["points"], frac)
        return (p[0], p[1]) if p else (t["lat"], t["lon"])

    def _plan(self, t: dict[str, Any], name: str, shelter: dict[str, Any], roads, now: datetime, closing=None) -> bool:
        origin = self._where(t, now)
        route = po.road_route(origin, (shelter["lat"], shelter["lon"]), roads, closing)
        if route.get("no_open_road") or route.get("method") == "direct" and route.get("km", 0) > 0.05:
            return False
        t["leg"] = {"to": name, "points": route["points"], "km": route["km"], "sim_minutes": route["sim_minutes"],
                    "road_ids": route.get("road_ids") or [], "depart_at": po._iso(now),
                    "seconds": po.leg_seconds(route["sim_minutes"]), "load": self.cfg["load_person_days"]}
        return True

    # ---- one step of simulated time ---------------------------------------------
    def step(self, rows, shelters: dict[str, dict[str, Any]], roads, now: datetime, closing=None) -> list[dict[str, Any]]:
        events = []
        people = self.people_at(rows)
        days = max(0.0, (now - self.last).total_seconds()) * po.TIME_SCALE / 86400.0
        for n, p in people.items():
            self.stock[n] = max(0.0, self.stock.get(n, 0.0) - p * days)
        self.last = now
        for t in self.trucks:  # arrivals
            leg = t.get("leg")
            if leg and now >= po._parse(leg["depart_at"]) + timedelta(seconds=float(leg["seconds"])):
                self.stock[leg["to"]] = self.stock.get(leg["to"], 0.0) + leg["load"]
                self.delivered_pd[leg["to"]] = self.delivered_pd.get(leg["to"], 0.0) + leg["load"]
                end = leg["points"][-1] if leg["points"] else [t["lat"], t["lon"]]
                t.update({"lat": float(end[0]), "lon": float(end[1]), "leg": None, "trips": t["trips"] + 1})
                events.append({"truck": t["name"], "shelter": leg["to"], "delivered_person_days": leg["load"], "at": po._iso(now)})
        targeted = {t["leg"]["to"] for t in self.trucks if t.get("leg")}
        need = sorted(
            ((self.hours_left(n, p), n) for n, p in people.items()
             if p > 0 and n not in targeted and n in shelters and not shelters[n].get("closed")
            and (self.hours_left(n, p) or 0.0) < self.cfg.get("reorder_hours", 24.0)),
            key=lambda x: x[0],
        )
        for _, n in need:  # nearest-need-first: the emptiest shelter gets the nearest idle truck
            idle = [t for t in self.trucks if not t.get("leg")]
            if not idle:
                break
            s = shelters[n]
            t = min(idle, key=lambda x: haversine_km(x["lat"], x["lon"], s["lat"], s["lon"]))
            if self._plan(t, n, s, roads, now, closing):
                events.append({"truck": t["name"], "dispatched_to": n, "km": t["leg"]["km"], "at": po._iso(now)})
        self.log += events
        return events

    def reroute(self, roads, shelters, now: datetime) -> list[dict[str, Any]]:
        """F1 hook: a truck whose route uses a road that just closed re-plans from where it is."""
        blocked = po.blocked_road_ids(roads)
        out = []
        for t in self.trucks:
            leg = t.get("leg")
            if leg and set(leg.get("road_ids") or []) & blocked:
                to = leg["to"]
                pos = self._where(t, now)
                t["lat"], t["lon"] = pos
                ok = self._plan(t, to, shelters[to], roads, now) if to in shelters else False
                if not ok:
                    t["leg"] = None  # no open road: the truck waits where it is
                out.append({"truck": t["name"], "to": to, "replanned": ok, "at": po._iso(now)})
        self.log += out
        return out

    def board(self, rows, now: datetime) -> dict[str, Any]:
        people = self.people_at(rows)
        names = sorted(set(people) | set(self.stock))
        return {
            "shelters": [
                {"name": n, "people": people.get(n, 0),
                 "need_water_l_per_day": round(people.get(n, 0) * WATER_L_PER_PERSON_DAY, 1),
                 "need_food_kcal_per_day": round(people.get(n, 0) * FOOD_KCAL_PER_PERSON_DAY),
                 "stock_person_days": round(self.stock.get(n, 0.0), 1),
                 "hours_of_stock_left": self.hours_left(n, people.get(n, 0)),
                 "delivered_person_days": round(self.delivered_pd.get(n, 0.0), 1),
                 "incoming": [t["name"] for t in self.trucks if (t.get("leg") or {}).get("to") == n]}
                for n in names if people.get(n, 0) > 0 or self.delivered_pd.get(n)
            ],
            "trucks": [{"name": t["name"], "home": t["home"], "trips": t["trips"],
                        "position": list(self._where(t, now)),
                        "leg": {k: t["leg"][k] for k in ("to", "km", "sim_minutes", "depart_at", "seconds", "points")} if t.get("leg") else None}
                       for t in self.trucks],
            "rates_source": RATES_SOURCE,
            "assumed": ASSUMED,
            "settings": self.cfg,
            "log": self.log[-20:],
        }
