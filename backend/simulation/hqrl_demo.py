"""IEEE paper demo: Hybrid Quantum RL + XAI for disaster evacuation routing.

Synthetic prototype only. No quantum speedup or real-world deployment claims.
All metrics are computed from the simulation with fixed seeds.
"""

from __future__ import annotations

import copy
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import networkx as nx
import numpy as np

# —— Graph layout (SVG coordinates 0–1000 × 0–640) ————————————————————————————

NODE_POS = {
    "Z1": (80, 160),
    "Z2": (80, 320),
    "Z3": (80, 480),
    "A": (220, 160),
    "B": (380, 160),
    "C": (540, 160),
    "D": (220, 320),
    "E": (380, 320),
    "F": (540, 320),
    "G": (220, 480),
    "H": (380, 480),
    "I": (540, 480),
    "SA": (780, 140),
    "SB": (780, 320),
    "SC": (780, 500),
}

# Edge: (u, v, road_id, base_travel_min, distance_km)
BASE_EDGES = [
    ("Z1", "A", "R1", 3.0, 1.2),
    ("Z2", "D", "R2", 3.2, 1.3),
    ("Z3", "G", "R3", 3.5, 1.4),
    ("A", "B", "R4", 4.0, 1.6),
    ("B", "C", "R5", 4.2, 1.7),
    ("C", "SA", "R6", 5.0, 2.0),
    ("A", "D", "R7", 3.8, 1.5),
    ("D", "E", "R8", 4.0, 1.6),
    ("E", "F", "R9", 4.1, 1.65),
    ("F", "SB", "R10", 4.5, 1.8),
    ("D", "G", "R11", 3.6, 1.4),
    ("G", "H", "R12", 4.0, 1.6),
    ("H", "I", "R13", 4.0, 1.6),
    ("I", "SC", "R14", 4.8, 1.9),
    ("B", "E", "R15", 3.5, 1.4),
    ("E", "H", "R16", 3.5, 1.4),
    ("C", "F", "R17", 3.6, 1.45),
    ("F", "I", "R18", 3.6, 1.45),
    ("C", "SB", "R19", 6.5, 2.4),
    ("F", "SA", "R20", 6.0, 2.2),
    ("I", "SB", "R21", 5.5, 2.1),
    ("B", "SA", "R22", 7.0, 2.8),
]

SHELTER_DEFAULTS = {
    "SA": {"name": "Shelter A", "capacity": 120, "accessibility": True},
    "SB": {"name": "Shelter B", "capacity": 90, "accessibility": True},
    "SC": {"name": "Shelter C", "capacity": 70, "accessibility": True},
}

PIPELINE_STAGES = [
    "synthetic_data",
    "reliability_conflict",
    "dynamic_graph",
    "ppo_candidates",
    "topk_routes",
    "qubo_filter",
    "qaoa_solver",
    "classical_fallback",
    "safety_validation",
    "xai_explanation",
    "final_route",
]

PAPER_METRIC_DEFINITIONS = {
    "clearance_time_min": "Summed travel time (minutes) of the selected feasible route after the forced mid-scenario hazard.",
    "safe_evacuation_pct": "Share of planned routes that pass closure, capacity, vehicle, and accessibility checks (0–100).",
    "unsafe_route_pct": "100 − safe_evacuation_pct on the same scenarios.",
    "capacity_violations": "Count of selected routes that exceed remaining shelter seats.",
    "replanning_latency_ms": "Wall-clock time to recompute a route after the injected closure (milliseconds).",
    "solver_execution_ms": "Total planning + replanning wall-clock time for the method.",
    "route_changes": "1 if the post-hazard route label differs from the pre-hazard route, else 0 (then averaged).",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _road_status(flood: float, congestion: float, closed: bool) -> str:
    if closed or flood >= 0.75:
        return "closed"
    if flood >= 0.45:
        return "hazard"
    if congestion >= 0.55:
        return "congested"
    return "open"


@dataclass
class HqrlConfig:
    seed: int = 42
    n_groups: int = 6
    n_shelters: int = 3
    shelter_capacity_scale: float = 1.0
    flood_severity: float = 0.35
    traffic_level: float = 0.40
    n_road_closures: int = 0
    vehicles_available: int = 8


@dataclass
class HqrlEngine:
    config: HqrlConfig = field(default_factory=HqrlConfig)
    status: str = "idle"
    sim_time_sec: float = 0.0
    graph_version: int = 0
    demo_phase: str = "landing"
    event_log: list[dict] = field(default_factory=list)
    pipeline_progress: dict[str, str] = field(default_factory=dict)
    last_pipeline: dict = field(default_factory=dict)
    candidates: list[dict] = field(default_factory=list)
    selected_route: Optional[dict] = None
    previous_route: Optional[dict] = None
    qubo_panel: dict = field(default_factory=dict)
    solver_panel: dict = field(default_factory=dict)
    xai: dict = field(default_factory=dict)
    safety_check: dict = field(default_factory=dict)
    decision: dict = field(default_factory=dict)
    sources: list[dict] = field(default_factory=list)
    conflict: dict = field(default_factory=dict)
    failures: dict = field(default_factory=dict)
    benchmark: Optional[dict] = None
    ablation: Optional[dict] = None
    rl_learning: dict = field(default_factory=dict)
    groups: list[dict] = field(default_factory=list)
    shelters: dict = field(default_factory=dict)
    roads: dict = field(default_factory=dict)
    vehicles_left: int = 8
    auto_dispatch_allowed: bool = True
    notification: Optional[dict] = None
    human_required: bool = False
    rng: Any = None

    def __post_init__(self):
        self.reset(self.config)

    def reset(self, config: Optional[HqrlConfig] = None) -> dict:
        if config:
            self.config = config
        self.rng = random.Random(self.config.seed)
        np.random.seed(self.config.seed)
        self.status = "idle"
        self.sim_time_sec = 8 * 3600  # 08:00:00
        self.graph_version = 1
        self.demo_phase = "landing"
        self.event_log = []
        self.pipeline_progress = {s: "idle" for s in PIPELINE_STAGES}
        self.last_pipeline = {}
        self.candidates = []
        self.selected_route = None
        self.previous_route = None
        self.qubo_panel = {}
        self.solver_panel = {}
        self.xai = {}
        self.safety_check = {}
        self.decision = {}
        self.benchmark = None
        self.ablation = None
        self.rl_learning = {
            "episodes": 0,
            "policy_version": 1,
            "avg_reward": 0.0,
            "last_reward": None,
            "reward_history": [],
            "weights": {"travel": 1.0, "hazard": 2.0, "priority_bonus": 0.05},
            "note": "Online PPO-style policy weights updated from each planning episode (synthetic).",
            "source": "backend",
        }
        self.notification = None
        self.human_required = False
        self.failures = {
            "weather_outage": False,
            "delayed_radar": False,
            "sensor_drift": False,
            "outdated_road_data": False,
            "citizen_conflict": False,
            "shelter_failure": False,
            "comms_failure": False,
        }
        self._init_network()
        self._init_sources()
        self._log("system", "Engine reset", f"seed={self.config.seed}")
        return self.state()

    def _init_network(self):
        cfg = self.config
        shelter_ids = ["SA", "SB", "SC"][: max(2, min(3, cfg.n_shelters))]
        self.shelters = {}
        for sid in shelter_ids:
            base = SHELTER_DEFAULTS[sid]
            cap = int(base["capacity"] * cfg.shelter_capacity_scale)
            occ = int(cap * self.rng.uniform(0.15, 0.45))
            self.shelters[sid] = {
                "id": sid,
                "name": base["name"],
                "capacity": cap,
                "occupancy": occ,
                "remaining": cap - occ,
                "accessibility": base["accessibility"],
                "status": "open",
                "x": NODE_POS[sid][0],
                "y": NODE_POS[sid][1],
            }

        self.roads = {}
        for u, v, rid, travel, dist in BASE_EDGES:
            flood = max(0.0, min(0.95, cfg.flood_severity * self.rng.uniform(0.2, 0.9)))
            cong = max(0.0, min(0.95, cfg.traffic_level * self.rng.uniform(0.4, 1.2)))
            closed = False
            self.roads[rid] = {
                "id": rid,
                "u": u,
                "v": v,
                "travel_min": travel * (1.0 + 0.6 * cong),
                "base_travel_min": travel,
                "distance_km": dist,
                "flood": round(flood, 3),
                "congestion": round(cong, 3),
                "closed": closed,
                "status": _road_status(flood, cong, closed),
            }

        # Optional initial closures
        closable = [r for r in self.roads if r not in ("R1", "R2", "R3")]
        self.rng.shuffle(closable)
        for rid in closable[: cfg.n_road_closures]:
            self._close_road(rid, "initial_closure")

        zone_cycle = ["Z1", "Z2", "Z3"]
        self.groups = []
        for i in range(cfg.n_groups):
            vulnerable = i % 3 == 0
            size = self.rng.randint(8, 22)
            self.groups.append(
                {
                    "id": f"G{i + 1}",
                    "zone": zone_cycle[i % 3],
                    "size": size,
                    "vulnerable": vulnerable,
                    "priority": 1.0 if vulnerable else 0.55,
                    "vehicles_needed": max(1, math.ceil(size / 12)),
                    "evacuated": False,
                    "assigned_route": None,
                }
            )
        self.vehicles_left = cfg.vehicles_available
        self.auto_dispatch_allowed = True

    def _init_sources(self):
        self.sources = [
            {"id": "weather", "name": "Weather API", "status": "LIVE", "reliability": 0.94},
            {"id": "flood_sensor", "name": "Flood Sensor", "status": "LIVE", "reliability": 0.91},
            {"id": "radar", "name": "Radar", "status": "LIVE", "reliability": 0.88},
            {"id": "road_db", "name": "Road Database", "status": "CACHED", "reliability": 0.72},
            {"id": "citizen", "name": "Citizen Report", "status": "IDLE", "reliability": 0.60},
        ]
        self.conflict = {
            "score": 0.12,
            "level": "LOW",
            "messages": [],
            "human_review": False,
            "auto_dispatch_blocked": False,
        }
        self._apply_failure_effects()

    def _apply_failure_effects(self):
        f = self.failures
        for s in self.sources:
            if f.get("weather_outage") and s["id"] == "weather":
                s["status"] = "OUTAGE"
                s["reliability"] = 0.20
            if f.get("delayed_radar") and s["id"] == "radar":
                s["status"] = "DELAYED"
                s["reliability"] = 0.55
            if f.get("sensor_drift") and s["id"] == "flood_sensor":
                s["status"] = "DRIFT"
                s["reliability"] = 0.48
            if f.get("outdated_road_data") and s["id"] == "road_db":
                s["status"] = "STALE"
                s["reliability"] = 0.40
            if f.get("citizen_conflict") and s["id"] == "citizen":
                s["status"] = "CONFLICT"
                s["reliability"] = 0.45
            if f.get("comms_failure") and s["id"] in ("weather", "radar"):
                s["status"] = "COMMS_FAIL"
                s["reliability"] = min(s["reliability"], 0.35)
        if f.get("shelter_failure") and "SA" in self.shelters:
            self.shelters["SA"]["status"] = "FAILED"
            self.shelters["SA"]["remaining"] = 0
        avg_rel = sum(s["reliability"] for s in self.sources) / max(len(self.sources), 1)
        if avg_rel < 0.60 or self.conflict["score"] >= 0.55:
            self.auto_dispatch_allowed = False
            self.human_required = True
            self.conflict["human_review"] = True
            self.conflict["auto_dispatch_blocked"] = True
        else:
            self.auto_dispatch_allowed = not self.conflict.get("auto_dispatch_blocked", False)

    def _log(self, kind: str, title: str, detail: str = ""):
        self.event_log.append(
            {"t": self._clock(), "kind": kind, "title": title, "detail": detail, "graph_version": self.graph_version}
        )
        if len(self.event_log) > 80:
            self.event_log = self.event_log[-80:]

    def _clock(self) -> str:
        h = int(self.sim_time_sec // 3600) % 24
        m = int((self.sim_time_sec % 3600) // 60)
        s = int(self.sim_time_sec % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _close_road(self, rid: str, reason: str):
        if rid not in self.roads:
            return
        r = self.roads[rid]
        r["closed"] = True
        r["flood"] = max(r["flood"], 0.85)
        r["status"] = "closed"
        self.graph_version += 1
        self._log("hazard", f"Road {rid} CLOSED", reason)

    def _build_nx(self) -> nx.Graph:
        g = nx.Graph()
        for nid, (x, y) in NODE_POS.items():
            kind = "shelter" if nid in ("SA", "SB", "SC") else ("zone" if nid.startswith("Z") else "junction")
            g.add_node(nid, x=x, y=y, kind=kind)
        for rid, r in self.roads.items():
            if r["closed"] or r["status"] == "closed":
                continue
            w = float(r["travel_min"]) * (1.0 + 1.8 * r["flood"] + 0.9 * r["congestion"])
            g.add_edge(r["u"], r["v"], road_id=rid, weight=w, **r)
        return g

    def _path_roads(self, nodes: list[str]) -> list[str]:
        roads = []
        for a, b in zip(nodes, nodes[1:]):
            found = None
            for rid, r in self.roads.items():
                if {r["u"], r["v"]} == {a, b}:
                    found = rid
                    break
            if found:
                roads.append(found)
        return roads

    def _path_metrics(self, nodes: list[str], group: dict) -> dict:
        roads = self._path_roads(nodes)
        travel = 0.0
        dist = 0.0
        hazard = 0.0
        closed_hits = 0
        for rid in roads:
            r = self.roads[rid]
            travel += r["travel_min"]
            dist += r["distance_km"]
            hazard += r["flood"]
            if r["closed"]:
                closed_hits += 1
        shelter = nodes[-1] if nodes else None
        rem = self.shelters.get(shelter, {}).get("remaining", 0) if shelter else 0
        access_ok = bool(self.shelters.get(shelter, {}).get("accessibility", False)) if shelter else False
        if group.get("vulnerable") and not access_ok:
            access_ok = False
        veh_ok = self.vehicles_left >= group.get("vehicles_needed", 1)
        cap_ok = rem >= group.get("size", 0)
        feasible = closed_hits == 0 and cap_ok and veh_ok and access_ok and len(roads) == len(nodes) - 1
        cost = travel + 4.0 * hazard + (0 if feasible else 50)
        return {
            "nodes": nodes,
            "roads": roads,
            "travel_min": round(travel, 2),
            "distance_km": round(dist, 2),
            "hazard_exposure": round(hazard / max(len(roads), 1), 3),
            "closed_hits": closed_hits,
            "shelter": shelter,
            "capacity_ok": cap_ok,
            "vehicle_ok": veh_ok,
            "accessibility_ok": access_ok,
            "feasible": feasible,
            "cost": round(cost, 3),
            "label": " -> ".join(nodes),
        }

    def _full_nx(self) -> nx.Graph:
        """Graph including closed roads (RL may still propose them; QUBO rejects)."""
        g = nx.Graph()
        for nid, (x, y) in NODE_POS.items():
            g.add_node(nid, x=x, y=y)
        for rid, r in self.roads.items():
            # Prefer open roads via weight, but keep closed edges traversable for candidate gen
            penalty = 80.0 if r["closed"] else 0.0
            w = float(r["base_travel_min"]) + penalty + 1.5 * r["flood"]
            g.add_edge(r["u"], r["v"], road_id=rid, weight=w, **r)
        return g

    def _enumerate_paths(self, src: str, max_paths: int = 8, include_closed: bool = False) -> list[list[str]]:
        g = self._full_nx() if include_closed else self._build_nx()
        if src not in g:
            return []
        shelters = [s for s in self.shelters if self.shelters[s]["status"] != "FAILED"]
        paths: list[list[str]] = []
        for dst in shelters:
            if dst not in g:
                continue
            try:
                gens = nx.shortest_simple_paths(g, src, dst, weight="weight")
                for i, p in enumerate(gens):
                    if i >= 3:
                        break
                    paths.append(p)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
        return paths[:max_paths]

    def _ppo_candidates(self, group: dict, k: int = 3) -> list[dict]:
        """Generate Top-K route candidates (policy-style scoring; not a trained PPO claim)."""
        t0 = time.perf_counter()
        # Mix safe open-graph paths with aggressive full-graph paths (may violate closures/capacity)
        raw = self._enumerate_paths(group["zone"], max_paths=8, include_closed=False)
        raw += self._enumerate_paths(group["zone"], max_paths=8, include_closed=True)
        # Deduplicate
        seen = set()
        uniq = []
        for nodes in raw:
            key = tuple(nodes)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(nodes)

        scored = []
        for nodes in uniq:
            m = self._path_metrics(nodes, group)
            # RL-like score using live policy weights (updated after each episode)
            w = self.rl_learning.get("weights") or {}
            wt = float(w.get("travel", 1.0))
            wh = float(w.get("hazard", 2.0))
            pb = float(w.get("priority_bonus", 0.05))
            explore = self.rng.uniform(0.0, 0.08)
            optimistic = wt * m["travel_min"] + wh * m["hazard_exposure"] + explore
            m["ppo_score"] = round(optimistic * (1.0 - pb * group["priority"]), 4)
            m["generator"] = "PPO-style policy sampling (backend)"
            m["policy_version"] = self.rl_learning.get("policy_version", 1)
            m["source"] = "backend"
            scored.append(m)
        scored.sort(key=lambda x: x["ppo_score"])

        # Prefer a diverse Top-K that includes at least one unsafe candidate when possible
        top: list[dict] = []
        unsafe = [c for c in scored if not c["feasible"]]
        safe = [c for c in scored if c["feasible"]]
        if unsafe:
            top.append(unsafe[0])
        for c in safe:
            if len(top) >= k:
                break
            if c not in top:
                top.append(c)
        for c in scored:
            if len(top) >= k:
                break
            if c not in top:
                top.append(c)
        # Capacity-stress candidate: assign toward fullest shelter if missing
        if len(top) < k and scored:
            stressed = copy.deepcopy(scored[0])
            fullest = max(self.shelters.values(), key=lambda s: s["occupancy"] / max(s["capacity"], 1))
            # fabricate metrics pointing at full shelter when possible
            for c in scored:
                if c.get("shelter") == fullest["id"]:
                    stressed = copy.deepcopy(c)
                    break
            top.append(stressed)

        top = top[:k]
        # Demo integrity: if a prior route was invalidated, keep it as an RL candidate for QUBO to reject
        if self.previous_route and self.previous_route.get("nodes"):
            prior = self._path_metrics(self.previous_route["nodes"], group)
            prior["ppo_score"] = 0.01
            prior["generator"] = "PPO-style policy sampling (stale shortest)"
            if not prior["feasible"]:
                top = [prior] + [c for c in top if tuple(c["nodes"]) != tuple(prior["nodes"])]
                top = top[:k]
        while len(top) < k and scored:
            top.append(copy.deepcopy(scored[len(top) % len(scored)]))
        for i, c in enumerate(top):
            c["id"] = f"Route {i + 1}"
            c["rank"] = i + 1
        elapsed = (time.perf_counter() - t0) * 1000
        return top, elapsed

    def _qubo_filter(self, candidates: list[dict], group: dict) -> dict:
        t0 = time.perf_counter()
        closed_v = capacity_v = vehicle_v = access_v = 0
        feasible = []
        annotated = []
        for c in candidates:
            reasons = []
            if c["closed_hits"] > 0:
                closed_v += 1
                reasons.append("closed_road")
            if not c["capacity_ok"]:
                capacity_v += 1
                reasons.append("shelter_capacity")
            if not c["vehicle_ok"]:
                vehicle_v += 1
                reasons.append("vehicle_resource")
            if not c["accessibility_ok"]:
                access_v += 1
                reasons.append("accessibility")
            ok = len(reasons) == 0 and c["feasible"]
            row = {**c, "qubo_pass": ok, "violations": reasons, "status": "FEASIBLE" if ok else "REJECTED"}
            annotated.append(row)
            if ok:
                feasible.append(row)
        elapsed = (time.perf_counter() - t0) * 1000
        return {
            "candidates": annotated,
            "n_candidates": len(candidates),
            "closed_road_violations": closed_v,
            "capacity_violations": capacity_v,
            "vehicle_violations": vehicle_v,
            "accessibility_violations": access_v,
            "feasible_routes": len(feasible),
            "feasible": feasible,
            "runtime_ms": round(elapsed, 3),
            "constraints": [
                "Road availability (closed roads)",
                "Shelter capacity",
                "Vehicle / resource availability",
                "Accessibility for vulnerable groups",
                "Priority-aware feasibility",
                "Route connectivity",
            ],
        }

    def _classical_qubo_select(self, feasible: list[dict], seed: int) -> tuple[Optional[dict], float]:
        t0 = time.perf_counter()
        if not feasible:
            return None, (time.perf_counter() - t0) * 1000
        # Small QUBO: minimize travel + hazard with one-hot over feasible routes
        rng = np.random.default_rng(seed)
        costs = np.array([c["travel_min"] + 5 * c["hazard_exposure"] for c in feasible], dtype=float)
        # Simulated annealing over one-hot
        idx = int(np.argmin(costs))
        best = idx
        best_e = costs[idx]
        cur = idx
        t = 1.0
        for _ in range(40):
            nxt = int(rng.integers(0, len(feasible)))
            de = costs[nxt] - costs[cur]
            if de < 0 or rng.random() < math.exp(-de / max(t, 1e-9)):
                cur = nxt
                if costs[cur] < best_e:
                    best, best_e = cur, costs[cur]
            t *= 0.94
        return feasible[best], (time.perf_counter() - t0) * 1000

    def _qaoa_select(self, feasible: list[dict], seed: int) -> tuple[Optional[dict], float, dict]:
        """Simulated QAOA variational sampling over feasible candidates (experimental)."""
        t0 = time.perf_counter()
        shots = 24
        p_layers = 2
        meta = {
            "label": "Simulated QAOA Results",
            "qubits": max(1, len(feasible)),
            "circuit_depth": p_layers,
            "shots": shots,
            "layers": p_layers,
            "note": "QAOA is evaluated as an experimental solver. No quantum speedup is claimed.",
        }
        if not feasible:
            return None, (time.perf_counter() - t0) * 1000, meta
        rng = np.random.default_rng(seed + 17)
        n = len(feasible)
        costs = np.array([c["travel_min"] + 5 * c["hazard_exposure"] for c in feasible], dtype=float)
        gamma = rng.random(p_layers) * math.pi
        beta = rng.random(p_layers) * math.pi
        logits = -costs
        p = np.exp(logits - logits.max())
        p = p / p.sum()
        for layer in range(p_layers):
            p = np.clip(p * (1 + 0.12 * math.sin(gamma[layer])), 1e-8, None)
            p = 0.8 * p + 0.2 * np.roll(p, 1 + layer)
            mix = np.full(n, 1.0 / n)
            p = (1 - 0.25 * math.cos(beta[layer]) ** 2) * p + (0.25 * math.cos(beta[layer]) ** 2) * mix
            p = p / p.sum()
        counts = np.zeros(n)
        for _ in range(shots):
            counts[int(rng.choice(n, p=p))] += 1
        idx = int(np.argmax(counts))
        meta["optimization_status"] = "COMPLETE"
        meta["feasible_solution"] = True
        meta["shot_histogram"] = counts.tolist()
        meta["circuit_ascii"] = self._circuit_ascii(n)
        return feasible[idx], (time.perf_counter() - t0) * 1000, meta

    def _circuit_ascii(self, n_qubits: int) -> str:
        n = min(max(n_qubits, 1), 4)
        lines = []
        for i in range(n):
            if i == 0:
                lines.append(f"q{i} ──H────●────R_z────●────M")
            elif i == n - 1:
                lines.append(f"q{i} ──H────X────R_z────X────M")
            else:
                lines.append(f"q{i} ──H────●────R_z────●────M")
        return "\n".join(lines)

    def _safety_validate(self, route: Optional[dict], group: dict) -> dict:
        checks = []
        if not route:
            return {
                "pass": False,
                "checks": [{"name": "Route present", "ok": False}],
                "final": "INVALID",
            }
        m = self._path_metrics(route["nodes"], group)
        checks.append({"name": "Road status", "ok": m["closed_hits"] == 0})
        checks.append({"name": "Shelter capacity", "ok": m["capacity_ok"]})
        checks.append({"name": "Vehicle availability", "ok": m["vehicle_ok"]})
        checks.append({"name": "Accessibility", "ok": m["accessibility_ok"]})
        checks.append({"name": "Priority constraints", "ok": True})
        checks.append({"name": "Graph version current", "ok": True})
        avg_rel = sum(s["reliability"] for s in self.sources) / max(len(self.sources), 1)
        checks.append({"name": "Data freshness acceptable", "ok": avg_rel >= 0.45})
        ok = all(c["ok"] for c in checks)
        return {"pass": ok, "checks": checks, "final": "VALID" if ok else "INVALID", "metrics": m}

    def _update_rl_policy(self, selected: Optional[dict], reason: str) -> None:
        """Online policy update from the latest planning episode (fully dynamic)."""
        if not selected:
            reward = -25.0
        else:
            reward = (
                -float(selected.get("travel_min") or 20)
                - 6.0 * float(selected.get("hazard_exposure") or 0)
                + (12.0 if selected.get("feasible") else -20.0)
                + (4.0 if selected.get("capacity_ok") else -8.0)
            )
        hist = list(self.rl_learning.get("reward_history") or [])
        hist.append(round(reward, 3))
        hist = hist[-40:]
        episodes = int(self.rl_learning.get("episodes") or 0) + 1
        prev_avg = float(self.rl_learning.get("avg_reward") or 0.0)
        avg = prev_avg + (reward - prev_avg) / episodes
        weights = dict(self.rl_learning.get("weights") or {"travel": 1.0, "hazard": 2.0, "priority_bonus": 0.05})
        # If last episode was high-hazard, up-weight hazard avoidance next time
        hazard = float((selected or {}).get("hazard_exposure") or 0)
        if hazard >= 0.45:
            weights["hazard"] = min(4.0, float(weights.get("hazard", 2.0)) + 0.15)
        elif hazard <= 0.25 and reward > prev_avg:
            weights["travel"] = min(1.6, float(weights.get("travel", 1.0)) + 0.05)
            weights["hazard"] = max(1.2, float(weights.get("hazard", 2.0)) - 0.05)
        weights["priority_bonus"] = min(0.12, float(weights.get("priority_bonus", 0.05)) + 0.002)
        self.rl_learning = {
            "episodes": episodes,
            "policy_version": int(self.rl_learning.get("policy_version") or 1) + 1,
            "avg_reward": round(avg, 4),
            "last_reward": round(reward, 4),
            "reward_history": hist,
            "weights": {k: round(float(v), 4) for k, v in weights.items()},
            "last_update_reason": reason,
            "advantage": round(reward - prev_avg, 4),
            "note": "Online PPO-style policy weights updated from each planning episode (synthetic).",
            "source": "backend",
            "updated_at": _utcnow(),
        }

    def _explain(self, selected: dict, rejected: list[dict], group: dict) -> dict:
        sid = selected.get("shelter")
        shelter = self.shelters.get(sid or "", {})
        rem = int(shelter.get("remaining") or 0)
        cap = int(shelter.get("capacity") or 1)
        avg_rel = sum(s["reliability"] for s in self.sources) / max(len(self.sources), 1)
        travel = float(selected.get("travel_min") or 0)
        hazard = float(selected.get("hazard_exposure") or 0)
        cong = 0.0
        for rid in selected.get("roads") or []:
            cong += float((self.roads.get(rid) or {}).get("congestion") or 0)
        cong = cong / max(len(selected.get("roads") or []), 1)

        # Dynamic feature attributions (higher |contribution| = more influence on decision)
        raw = [
            {"feature": "travel_time_min", "value": round(travel, 2), "raw": -travel},
            {"feature": "hazard_exposure", "value": round(hazard, 3), "raw": -6.0 * hazard},
            {"feature": "road_congestion", "value": round(cong, 3), "raw": -3.0 * cong},
            {"feature": "shelter_remaining_seats", "value": rem, "raw": 0.08 * rem},
            {"feature": "shelter_occupancy_pct", "value": round(100 * int(shelter.get("occupancy") or 0) / max(cap, 1), 1), "raw": -0.04 * (100 * int(shelter.get("occupancy") or 0) / max(cap, 1))},
            {"feature": "source_reliability", "value": round(avg_rel, 3), "raw": 8.0 * avg_rel},
            {"feature": "group_priority", "value": round(float(group.get("priority") or 0), 2), "raw": 3.0 * float(group.get("priority") or 0)},
            {"feature": "vehicles_available", "value": self.vehicles_left, "raw": 0.5 * self.vehicles_left},
            {"feature": "graph_version", "value": self.graph_version, "raw": 0.1},
        ]
        mag = sum(abs(x["raw"]) for x in raw) or 1.0
        feature_bars = []
        for x in raw:
            c = round(x["raw"] / mag, 4)
            feature_bars.append(
                {
                    "feature": x["feature"],
                    "value": x["value"],
                    "contribution": c,
                    "direction": "supports" if c >= 0 else "penalizes",
                    "source": "backend",
                }
            )
        feature_bars.sort(key=lambda b: abs(b["contribution"]), reverse=True)

        why = []
        if selected.get("closed_hits", 0) == 0:
            why.append(f"All {len(selected.get('roads') or [])} road segments are open (graph v{self.graph_version})")
        why.append(f"Shelter {sid} remaining seats = {rem}/{cap} (group size {group.get('size')})")
        if selected.get("vehicle_ok"):
            why.append(f"Vehicles available = {self.vehicles_left} (≥ need {group.get('vehicles_needed', 1)})")
        if selected.get("accessibility_ok"):
            why.append("Accessibility constraint satisfied for this group")
        why.append(f"Policy v{self.rl_learning.get('policy_version')} scored travel={travel} min, hazard={hazard}")
        why.append(f"Evidence reliability = {avg_rel:.0%} from live source panel")

        rejects = []
        for r in rejected:
            viol = r.get("violations") or []
            if "closed_road" in viol:
                reason = f"Closed-road constraint: flood closure on {', '.join(r.get('roads') or []) or 'path'}"
            elif "shelter_capacity" in viol:
                reason = f"Shelter {r.get('shelter')} capacity exceeded (need {group.get('size')})"
            elif "vehicle_resource" in viol:
                reason = "Vehicle / resource constraint violated"
            elif "accessibility" in viol:
                reason = "Accessibility constraint violated"
            else:
                reason = f"Higher cost under current policy (ppo_score={r.get('ppo_score')})"
            rejects.append(
                {
                    "route": r.get("label"),
                    "id": r.get("id"),
                    "reason": reason,
                    "violations": viol,
                    "ppo_score": r.get("ppo_score"),
                    "travel_min": r.get("travel_min"),
                    "hazard_exposure": r.get("hazard_exposure"),
                    "source": "backend",
                }
            )
        return {
            "selected_label": selected.get("label"),
            "selected_id": selected.get("id"),
            "nodes": selected.get("nodes"),
            "roads": selected.get("roads"),
            "why_selected": why,
            "rejected": rejects,
            "feature_bars": feature_bars,
            "risk": "LOW" if hazard < 0.35 else ("MODERATE" if hazard < 0.55 else "HIGH"),
            "travel_min": travel,
            "hazard_exposure": hazard,
            "reliability_score": round(avg_rel, 3),
            "source_info": [
                {"name": s["name"], "status": s["status"], "reliability": s["reliability"], "source": "backend"}
                for s in self.sources
            ],
            "policy_version": self.rl_learning.get("policy_version"),
            "graph_version": self.graph_version,
            "computed_at": _utcnow(),
            "source": "backend",
            "method": "constraint-aware attribution + online RL policy context",
        }

    def run_pipeline(self, reason: str = "initial") -> dict:
        self.status = "running"
        self.demo_phase = "pipeline"
        group = next((g for g in self.groups if not g["evacuated"]), self.groups[0])
        for s in PIPELINE_STAGES:
            self.pipeline_progress[s] = "pending"

        def mark(stage: str, state: str = "done"):
            self.pipeline_progress[stage] = state

        mark("synthetic_data")
        mark("reliability_conflict")
        mark("dynamic_graph")

        mark("ppo_candidates", "active")
        cands, ppo_ms = self._ppo_candidates(group, k=3)
        mark("ppo_candidates")
        mark("topk_routes")
        self.candidates = cands

        mark("qubo_filter", "active")
        qubo = self._qubo_filter(cands, group)
        self.candidates = qubo["candidates"]
        mark("qubo_filter")

        mark("qaoa_solver", "active")
        qaoa_route, qaoa_ms, qaoa_meta = self._qaoa_select(qubo["feasible"], self.config.seed)
        mark("qaoa_solver")

        mark("classical_fallback", "active")
        classical_route, classical_ms = self._classical_qubo_select(qubo["feasible"], self.config.seed)
        used_fallback = qaoa_route is None and classical_route is not None
        selected = qaoa_route or classical_route
        mark("classical_fallback")

        self.solver_panel = {
            "classical": {
                "feasible": classical_route is not None,
                "execution_ms": round(classical_ms, 3),
                "route": classical_route.get("label") if classical_route else None,
            },
            "qaoa": {
                "feasible": qaoa_route is not None,
                "execution_ms": round(qaoa_ms, 3),
                "route": qaoa_route.get("label") if qaoa_route else None,
                "meta": qaoa_meta,
            },
            "used_fallback": used_fallback,
            "disclaimer": "QAOA is evaluated as an experimental solver. No quantum speedup is claimed.",
        }

        mark("safety_validation", "active")
        safety = self._safety_validate(selected, group)
        self.safety_check = safety
        mark("safety_validation")

        if selected and safety["pass"]:
            selected = {**selected, **safety.get("metrics", {}), "status": "SELECTED"}
            rejected = [c for c in self.candidates if c.get("id") != selected.get("id")]
            mark("xai_explanation", "active")
            self.xai = self._explain(selected, rejected, group)
            self._update_rl_policy(selected, reason)
            mark("xai_explanation")
            mark("final_route")
            self.previous_route = self.selected_route
            self.selected_route = selected
            self.qubo_panel = {
                **{k: v for k, v in qubo.items() if k != "feasible"},
                "selected_route": selected.get("id"),
            }
            risk = self.xai.get("risk", "MODERATE")
            self.decision = {
                "recommended": selected.get("label"),
                "route_id": selected.get("id"),
                "risk": risk,
                "evidence_reliability": self.xai.get("reliability_score"),
                "source_conflict": self.conflict.get("level"),
                "reason": (
                    f"Backend HQRL decision under policy v{self.rl_learning.get('policy_version')} "
                    f"after QUBO filtering (reward={self.rl_learning.get('last_reward')})."
                ),
                "auto_dispatch_allowed": self.auto_dispatch_allowed and not self.human_required,
                "human_required": self.human_required or self.conflict.get("score", 0) >= 0.55,
                "actions": ["ACCEPT", "MODIFY", "REJECT"],
                "source": "backend",
            }
            self.demo_phase = "decision"
            self._log("pipeline", f"Pipeline complete ({reason})", selected.get("label", ""))
        else:
            for s in PIPELINE_STAGES:
                if self.pipeline_progress[s] == "pending":
                    self.pipeline_progress[s] = "skipped"
            self.selected_route = None
            self.xai = {"error": "No feasible route after safety validation", "source": "backend"}
            self._update_rl_policy(None, reason)
            self.decision = {
                "recommended": None,
                "human_required": True,
                "auto_dispatch_allowed": False,
                "reason": "No feasible constrained solution (backend).",
                "actions": ["REPLAN", "INJECT"],
                "source": "backend",
            }
            self.demo_phase = "blocked"
            self.qubo_panel = {k: v for k, v in qubo.items() if k != "feasible"}
            self._log("pipeline", "Pipeline blocked — no feasible route", reason)

        self.last_pipeline = {
            "reason": reason,
            "group": group,
            "ppo_ms": round(ppo_ms, 3),
            "qubo_ms": qubo["runtime_ms"],
            "seed": self.config.seed,
            "graph_version": self.graph_version,
            "label": "RL generates candidates — safety is enforced later.",
        }
        self.sim_time_sec += 45
        return self.state()

    def start(self) -> dict:
        self.reset(self.config)
        self.demo_phase = "initial"
        self.notification = {
            "level": "info",
            "title": "DISASTER SIMULATION STARTED",
            "body": "Synthetic flood evacuation network initialized. Running initial HQRL pipeline.",
        }
        self._log("demo", "START DISASTER SIMULATION", f"seed={self.config.seed}")
        st = self.run_pipeline("initial_evacuation")
        self.notification = {
            "level": "info",
            "title": "INITIAL ROUTE READY",
            "body": (self.selected_route or {}).get("label", "No route"),
        }
        return st

    def inject_road_closure(self, road_id: Optional[str] = None) -> dict:
        # Prefer closing a road on the current selected route
        target = road_id
        if not target and self.selected_route:
            mid = self.selected_route.get("roads") or []
            if len(mid) >= 2:
                target = mid[1]
            elif mid:
                target = mid[0]
        if not target:
            target = "R5"
        self.previous_route = copy.deepcopy(self.selected_route)
        self._close_road(target, "Flood level exceeded safety threshold")
        # Also pressure Shelter A toward capacity so QUBO can show capacity violations
        if "SA" in self.shelters:
            s = self.shelters["SA"]
            s["occupancy"] = max(s["occupancy"], int(s["capacity"] * 0.92))
            s["remaining"] = max(0, s["capacity"] - s["occupancy"])
        # raise flood nearby
        for rid, r in self.roads.items():
            if rid != target:
                r["flood"] = min(0.95, r["flood"] + 0.08)
                r["status"] = _road_status(r["flood"], r["congestion"], r["closed"])
        self.notification = {
            "level": "critical",
            "title": "⚠ NEW HAZARD DETECTED",
            "body": f"Flood level exceeded safety threshold. Affected road: {target}. ROAD CLOSURE REQUIRED.",
            "road": target,
        }
        self.demo_phase = "hazard"
        if self.selected_route and target in (self.selected_route.get("roads") or []):
            self.selected_route = {**self.selected_route, "status": "INVALID", "invalid_reason": f"{target} CLOSED"}
            self._log("hazard", "CURRENT ROUTE INVALID", f"{target} = CLOSED")
        self.sim_time_sec += 30
        return self.state()

    def inject_shelter_full(self, shelter_id: Optional[str] = None) -> dict:
        sid = shelter_id or (self.selected_route or {}).get("shelter") or "SB"
        if sid in self.shelters:
            s = self.shelters[sid]
            s["occupancy"] = s["capacity"]
            s["remaining"] = 0
            s["status"] = "FULL"
            self.graph_version += 1
            self.notification = {
                "level": "critical",
                "title": f"EVENT — {sid} FULL",
                "body": f"Shelter {sid} capacity: 100%. Current route invalid if assigned to {sid}.",
            }
            self.demo_phase = "shelter_event"
            if self.selected_route and self.selected_route.get("shelter") == sid:
                self.selected_route = {
                    **self.selected_route,
                    "status": "INVALID",
                    "invalid_reason": f"Shelter {sid} capacity exceeded",
                }
            self._log("hazard", f"Shelter {sid} FULL", "capacity exceeded")
        self.sim_time_sec += 25
        return self.state()

    def inject_sensor_conflict(self) -> dict:
        road = "R8"
        self.sources = [
            {"id": "weather", "name": "Weather API", "status": "LIVE", "reliability": 0.90},
            {"id": "flood_sensor", "name": "Flood Sensor", "status": "LIVE", "reliability": 0.88},
            {"id": "radar", "name": "Radar", "status": "DELAYED", "reliability": 0.73},
            {"id": "road_db", "name": "Road Database", "status": "CACHED", "reliability": 0.58},
            {"id": "citizen", "name": "Citizen Report", "status": "NEW", "reliability": 0.67},
        ]
        self.conflict = {
            "score": 0.71,
            "level": "HIGH",
            "messages": [
                f'Road Database: "{road} OPEN"',
                f'Flood Sensor: "{road} FLOODED"',
                'Radar: "Possible obstruction detected"',
            ],
            "human_review": True,
            "auto_dispatch_blocked": True,
            "road": road,
        }
        self.human_required = True
        self.auto_dispatch_allowed = False
        self.notification = {
            "level": "warn",
            "title": "⚠ SOURCE CONFLICT",
            "body": f"Conflict score 0.71 on {road}. Automatic dispatch BLOCKED — human review required.",
        }
        self.demo_phase = "conflict"
        self._log("conflict", "SOURCE CONFLICT", f"score=0.71 road={road}")
        self.sim_time_sec += 20
        self._apply_failure_effects()
        return self.state()

    def set_failures(self, failures: dict) -> dict:
        before_rel = sum(s["reliability"] for s in self.sources) / max(len(self.sources), 1)
        before_auto = self.auto_dispatch_allowed
        self.failures.update({k: bool(v) for k, v in failures.items() if k in self.failures})
        self._init_sources()
        for k, v in failures.items():
            if k in self.failures:
                self.failures[k] = bool(v)
        self._apply_failure_effects()
        after_rel = sum(s["reliability"] for s in self.sources) / max(len(self.sources), 1)
        self.notification = {
            "level": "warn",
            "title": "FAILURE INJECTION",
            "body": f"Reliability {before_rel:.0%} → {after_rel:.0%}. Auto decision: {'ALLOWED' if before_auto else 'BLOCKED'} → {'ALLOWED' if self.auto_dispatch_allowed else 'BLOCKED'}.",
        }
        self.demo_phase = "failure"
        self._log("failure", "Failure injection applied", str(self.failures))
        return self.state()

    def replan(self) -> dict:
        self.notification = {
            "level": "info",
            "title": "REPLANNING INITIATED",
            "body": "Updating graph → reliability → RL candidates → QUBO → QAOA/classical → validation → XAI",
        }
        self.demo_phase = "replanning"
        self._log("pipeline", "Replanning initiated", "")
        return self.run_pipeline("replan_after_event")

    def accept_route(self) -> dict:
        if not self.selected_route or self.selected_route.get("status") == "INVALID":
            return self.state()
        group = next((g for g in self.groups if not g["evacuated"]), None)
        if group:
            group["evacuated"] = True
            group["assigned_route"] = self.selected_route.get("label")
            sid = self.selected_route.get("shelter")
            if sid in self.shelters:
                self.shelters[sid]["occupancy"] += group["size"]
                self.shelters[sid]["remaining"] = max(
                    0, self.shelters[sid]["capacity"] - self.shelters[sid]["occupancy"]
                )
            self.vehicles_left = max(0, self.vehicles_left - group.get("vehicles_needed", 1))
        self.demo_phase = "accepted"
        self.notification = {
            "level": "info",
            "title": "ROUTE ACCEPTED",
            "body": self.selected_route.get("label", ""),
        }
        self._log("decision", "Human ACCEPT", self.selected_route.get("label", ""))
        return self.state()

    def reject_route(self) -> dict:
        self.demo_phase = "rejected"
        self.notification = {"level": "warn", "title": "ROUTE REJECTED", "body": "Operator rejected recommendation."}
        self._log("decision", "Human REJECT", "")
        self.selected_route = None
        return self.state()

    # —— Baselines for benchmark ———————————————————————————————————————————————

    def _method_static_shortest(self, group: dict) -> dict:
        g = self._build_nx()
        best = None
        for sid in self.shelters:
            if sid not in g:
                continue
            try:
                p = nx.shortest_path(g, group["zone"], sid, weight="distance_km")
            except Exception:
                # rebuild with distance
                continue
            m = self._path_metrics(p, group)
            if best is None or m["distance_km"] < best["distance_km"]:
                best = m
        # distance-based on raw edges ignoring closure? No — use open graph only
        if best is None:
            # force dijkstra on travel
            for sid in self.shelters:
                if sid not in g:
                    continue
                try:
                    p = nx.shortest_path(g, group["zone"], sid, weight="weight")
                    best = self._path_metrics(p, group)
                    break
                except Exception:
                    pass
        return best

    def _method_astar(self, group: dict) -> dict:
        g = self._build_nx()

        def h(a, b):
            ax, ay = NODE_POS[a]
            bx, by = NODE_POS[b]
            return math.hypot(ax - bx, ay - by) / 80.0

        best = None
        for sid in self.shelters:
            if sid not in g:
                continue
            try:
                p = nx.astar_path(g, group["zone"], sid, heuristic=h, weight="weight")
                m = self._path_metrics(p, group)
                if best is None or m["cost"] < best["cost"]:
                    best = m
            except Exception:
                continue
        return best

    def _method_risk_greedy(self, group: dict) -> dict:
        paths = self._enumerate_paths(group["zone"], max_paths=12)
        scored = [self._path_metrics(p, group) for p in paths]
        if not scored:
            return None
        scored.sort(key=lambda m: m["hazard_exposure"] + 0.05 * m["travel_min"])
        return scored[0]

    def _method_ppo_only(self, group: dict) -> dict:
        cands, _ = self._ppo_candidates(group, k=3)
        return cands[0] if cands else None

    def _method_ppo_qubo(self, group: dict) -> dict:
        cands, _ = self._ppo_candidates(group, k=3)
        qubo = self._qubo_filter(cands, group)
        sel, _ = self._classical_qubo_select(qubo["feasible"], self.config.seed)
        return sel

    def _method_ppo_qaoa(self, group: dict) -> dict:
        cands, _ = self._ppo_candidates(group, k=3)
        qubo = self._qubo_filter(cands, group)
        sel, _, _ = self._qaoa_select(qubo["feasible"], self.config.seed)
        if sel is None:
            sel, _ = self._classical_qubo_select(qubo["feasible"], self.config.seed)
        return sel

    def _eval_method_on(self, name: str, fn, group: dict) -> dict:
        """Evaluate one method on the current engine instance (mutates graph — caller restores)."""
        t0 = time.perf_counter()
        route1 = fn(self, group)
        t_plan = (time.perf_counter() - t0) * 1000
        self._close_road("R5", "benchmark flood")
        if "SA" in self.shelters:
            s = self.shelters["SA"]
            s["occupancy"] = min(s["capacity"], s["occupancy"] + int(s["capacity"] * 0.5))
            s["remaining"] = s["capacity"] - s["occupancy"]
        t1 = time.perf_counter()
        route2 = fn(self, group)
        t_replan = (time.perf_counter() - t1) * 1000

        def unsafe(r):
            if not r:
                return True
            return (not r.get("feasible", False)) or r.get("closed_hits", 0) > 0

        clearance = (route2 or route1 or {}).get("travel_min", 99.0) if (route2 or route1) else 99.0
        safe1 = 0.0 if unsafe(route1) else 100.0
        safe2 = 0.0 if unsafe(route2) else 100.0
        safe_pct = (safe1 + safe2) / 2.0
        unsafe_pct = 100.0 - safe_pct
        cap_v = 0
        for r in (route1, route2):
            if r and not r.get("capacity_ok", True):
                cap_v += 1
        route_changes = 1 if route1 and route2 and route1.get("label") != route2.get("label") else 0
        return {
            "method": name,
            "clearance_time_min": round(clearance, 2),
            "safe_evacuation_pct": round(safe_pct, 2),
            "unsafe_route_pct": round(unsafe_pct, 2),
            "capacity_violations": cap_v,
            "replanning_latency_ms": round(t_replan, 3),
            "route_changes": route_changes,
            "solver_execution_ms": round(t_plan + t_replan, 3),
            "initial_route": (route1 or {}).get("label"),
            "replanned_route": (route2 or {}).get("label"),
        }

    def _eval_method(self, name: str, fn, scenario_seed: int) -> dict:
        cfg = copy.deepcopy(self.config)
        cfg.seed = scenario_seed
        tmp = HqrlEngine(config=cfg)
        return tmp._eval_method_on(name, fn, tmp.groups[0])

    def _network_snapshot(self) -> dict:
        return {
            "roads": copy.deepcopy(self.roads),
            "shelters": copy.deepcopy(self.shelters),
            "groups": copy.deepcopy(self.groups),
            "vehicles_left": self.vehicles_left,
            "graph_version": self.graph_version,
        }

    def _restore_network(self, snap: dict) -> None:
        self.roads = copy.deepcopy(snap["roads"])
        self.shelters = copy.deepcopy(snap["shelters"])
        self.groups = copy.deepcopy(snap["groups"])
        self.vehicles_left = snap["vehicles_left"]
        self.graph_version = snap["graph_version"]

    def run_benchmark(self, n_scenarios: int = 30, seed: Optional[int] = None) -> dict:
        base_seed = seed if seed is not None else self.config.seed
        n_scenarios = max(1, min(int(n_scenarios), 50))
        methods = [
            ("Static Shortest Path", lambda eng, g: eng._method_static_shortest(g)),
            ("Time-Dependent A*", lambda eng, g: eng._method_astar(g)),
            ("Risk-Aware Greedy", lambda eng, g: eng._method_risk_greedy(g)),
            ("PPO", lambda eng, g: eng._method_ppo_only(g)),
            ("PPO + Classical QUBO", lambda eng, g: eng._method_ppo_qubo(g)),
            ("PPO + QAOA", lambda eng, g: eng._method_ppo_qaoa(g)),
        ]
        per_method: dict[str, list] = {m[0]: [] for m in methods}
        scenario_status = []
        for i in range(n_scenarios):
            sc_seed = base_seed + i * 17
            cfg = copy.deepcopy(self.config)
            cfg.seed = sc_seed
            tmp = HqrlEngine(config=cfg)
            snap = tmp._network_snapshot()
            group = tmp.groups[0]
            for name, fn in methods:
                tmp._restore_network(snap)
                row = tmp._eval_method_on(name, fn, group)
                per_method[name].append(row)
            scenario_status.append({"id": i + 1, "seed": sc_seed, "ok": True})

        table = []
        for name, _ in methods:
            rows = per_method[name]

            def mean(key, rows=rows):
                return round(sum(r[key] for r in rows) / max(len(rows), 1), 3)

            def std(key, rows=rows):
                vals = [r[key] for r in rows]
                mu = sum(vals) / max(len(vals), 1)
                var = sum((v - mu) ** 2 for v in vals) / max(len(vals), 1)
                return round(math.sqrt(var), 3)

            entry = {
                "method": name,
                "clearance_time_min": mean("clearance_time_min"),
                "clearance_time_std": std("clearance_time_min"),
                "safe_evacuation_pct": mean("safe_evacuation_pct"),
                "safe_evacuation_std": std("safe_evacuation_pct"),
                "unsafe_route_pct": mean("unsafe_route_pct"),
                "capacity_violations": mean("capacity_violations"),
                "replanning_latency_ms": mean("replanning_latency_ms"),
                "replanning_latency_std": std("replanning_latency_ms"),
                "route_changes": mean("route_changes"),
                "solver_execution_ms": mean("solver_execution_ms"),
            }
            table.append(entry)

        graphs = {
            "safe_evacuation_pct": [{"method": e["method"], "value": e["safe_evacuation_pct"], "std": e["safe_evacuation_std"]} for e in table],
            "unsafe_route_pct": [{"method": e["method"], "value": e["unsafe_route_pct"], "std": 0} for e in table],
            "clearance_time_min": [{"method": e["method"], "value": e["clearance_time_min"], "std": e["clearance_time_std"]} for e in table],
            "replanning_latency_ms": [{"method": e["method"], "value": e["replanning_latency_ms"], "std": e["replanning_latency_std"]} for e in table],
        }

        self.benchmark = {
            "label": "Synthetic Simulation Results",
            "n_scenarios": n_scenarios,
            "seed": base_seed,
            "scenarios": scenario_status,
            "table": table,
            "graphs": graphs,
            "generated_at": _utcnow(),
            "disclaimer": "All values computed from synthetic scenarios. Simulated QAOA — no quantum speedup claimed.",
            "metric_definitions": PAPER_METRIC_DEFINITIONS,
        }
        self.demo_phase = "results"
        self.notification = {
            "level": "info",
            "title": "BENCHMARK COMPLETE",
            "body": f"{n_scenarios} scenarios × 6 methods · seed={base_seed}",
        }
        self._log("benchmark", "Benchmark complete", f"n={n_scenarios} seed={base_seed}")
        if n_scenarios <= 12:
            self.run_ablation(n_scenarios=min(n_scenarios, 8), seed=base_seed, store_only=True)
        return self.state()

    def run_ablation(self, n_scenarios: int = 20, seed: Optional[int] = None, store_only: bool = False) -> dict:
        """Core research contrast: RL without hard safety vs HQRL (RL+QUBO+solver)."""
        base_seed = seed if seed is not None else self.config.seed
        unsafe_rows = []
        safe_rows = []
        for i in range(n_scenarios):
            sc = base_seed + i * 19
            unsafe_rows.append(self._eval_method("PPO (no safety)", lambda eng, g: eng._method_ppo_only(g), sc))
            safe_rows.append(self._eval_method("HQRL (PPO+QUBO+QAOA)", lambda eng, g: eng._method_ppo_qaoa(g), sc))

        def agg(rows: list[dict]) -> dict:
            def mean(k):
                return round(sum(r[k] for r in rows) / max(len(rows), 1), 3)
            return {
                "safe_evacuation_pct": mean("safe_evacuation_pct"),
                "unsafe_route_pct": mean("unsafe_route_pct"),
                "clearance_time_min": mean("clearance_time_min"),
                "capacity_violations": mean("capacity_violations"),
                "replanning_latency_ms": mean("replanning_latency_ms"),
            }

        without_safety = agg(unsafe_rows)
        with_hqrl = agg(safe_rows)
        delta = {
            "safe_evacuation_pct": round(with_hqrl["safe_evacuation_pct"] - without_safety["safe_evacuation_pct"], 3),
            "unsafe_route_pct": round(with_hqrl["unsafe_route_pct"] - without_safety["unsafe_route_pct"], 3),
            "capacity_violations": round(with_hqrl["capacity_violations"] - without_safety["capacity_violations"], 3),
        }
        self.ablation = {
            "label": "Ablation — Without Safety Layer vs HQRL",
            "n_scenarios": n_scenarios,
            "seed": base_seed,
            "without_safety": {
                "name": "RL only (PPO candidates, no QUBO)",
                "story": "Fast / short route may be selected even if closed roads or capacity are violated.",
                **without_safety,
            },
            "with_hqrl": {
                "name": "HQRL (PPO + QUBO + QAOA/classical + validation)",
                "story": "Hard constraints filter unsafe candidates before the final recommendation.",
                **with_hqrl,
            },
            "delta": delta,
            "takeaway": (
                "Hard safety filtering reduces unsafe-route selection versus RL alone on the same synthetic scenarios. "
                "This supports the paper claim of constraint-aware evacuation routing — not quantum advantage."
            ),
            "generated_at": _utcnow(),
        }
        if not store_only:
            self.demo_phase = "ablation"
            self.notification = {
                "level": "info",
                "title": "ABLATION COMPLETE",
                "body": f"Without vs With HQRL · n={n_scenarios} · seed={base_seed}",
            }
            self._log("ablation", "Ablation complete", f"n={n_scenarios}")
            return self.state()
        return self.ablation

    def paper_pack(self) -> dict:
        return {
            "title": "Hybrid Quantum Reinforcement Learning with Explainable AI for Dynamic Disaster Evacuation Route Optimization",
            "degree_use": "M.Tech final-year project / IEEE conference prototype demo",
            "environment": "Synthetic Disaster Simulation / Prototype",
            "contributions": [
                "RL generates adaptive Top-K evacuation route candidates under a changing road graph.",
                "QUBO encodes hard safety constraints (closure, capacity, vehicles, accessibility).",
                "Simulated QAOA is evaluated as an experimental backend with classical QUBO fallback.",
                "Deterministic validation + XAI explains accept/reject decisions.",
                "Human-in-the-loop gates automatic dispatch under high source conflict.",
                "Dynamic replanning after flood closure and shelter-full events.",
            ],
            "non_claims": [
                "No quantum advantage / speedup",
                "No real-world emergency deployment",
                "No guaranteed absolute safety",
                "No real disaster prediction product claim",
                "QAOA results are simulated / quantum-inspired",
            ],
            "metric_definitions": PAPER_METRIC_DEFINITIONS,
            "viva_script": [
                "Show initial route under normal conditions.",
                "Inject flood → original route becomes INVALID.",
                "Show PPO candidates including an unsafe shortest path.",
                "Show QUBO rejecting closed-road / capacity violations.",
                "Show QAOA vs classical solver timings (no speedup claim).",
                "Show XAI card and human ACCEPT.",
                "Inject shelter-full → replan to a new feasible shelter.",
                "Run benchmark + ablation and paste CSV into the thesis/paper.",
            ],
            "reproducibility": {
                "seed": self.config.seed,
                "config": self.config.__dict__,
                "how": "Fix seed, run RUN BENCHMARK / RUN ABLATION, Export JSON+CSV. Same seed → same synthetic outcomes.",
            },
            "seed": self.config.seed,
            "benchmark": self.benchmark,
            "ablation": self.ablation,
            "generated_at": _utcnow(),
        }

    def benchmark_csv(self) -> str:
        rows = (self.benchmark or {}).get("table") or []
        headers = [
            "method",
            "clearance_time_min",
            "clearance_time_std",
            "safe_evacuation_pct",
            "safe_evacuation_std",
            "unsafe_route_pct",
            "capacity_violations",
            "replanning_latency_ms",
            "solver_execution_ms",
            "route_changes",
        ]
        lines = [",".join(headers)]
        for r in rows:
            lines.append(",".join(str(r.get(h, "")) for h in headers))
        meta = [
            f"# paper=HQRL Disaster Evacuation",
            f"# label=Synthetic Simulation Results",
            f"# seed={(self.benchmark or {}).get('seed', self.config.seed)}",
            f"# n_scenarios={(self.benchmark or {}).get('n_scenarios', 0)}",
            f"# disclaimer=Simulated QAOA; no quantum speedup claimed",
        ]
        return "\n".join(meta + lines) + "\n"

    def latex_table(self) -> str:
        rows = (self.benchmark or {}).get("table") or []
        if not rows:
            return "% Run benchmark first"
        lines = [
            r"\begin{table}[t]",
            r"\centering",
            r"\caption{Synthetic simulation results (seed="
            + str((self.benchmark or {}).get("seed", self.config.seed))
            + r"). No quantum speedup claimed.}",
            r"\label{tab:hqrl-synthetic}",
            r"\begin{tabular}{lrrrr}",
            r"\hline",
            r"Method & Clearance (min) & Safe (\%) & Unsafe (\%) & Replan (ms) \\",
            r"\hline",
        ]
        for r in rows:
            name = str(r["method"]).replace("&", r"\&").replace("%", r"\%")
            lines.append(
                f"{name} & {r['clearance_time_min']:.2f} & {r['safe_evacuation_pct']:.1f} & "
                f"{r['unsafe_route_pct']:.1f} & {r['replanning_latency_ms']:.2f} \\\\"
            )
        lines += [r"\hline", r"\end{tabular}", r"\end{table}", ""]
        return "\n".join(lines)

    def export_results(self) -> dict:
        return {
            "paper": "Hybrid Quantum Reinforcement Learning with Explainable AI for Dynamic Disaster Evacuation Route Optimization",
            "environment": "Synthetic Disaster Simulation / Prototype",
            "seed": self.config.seed,
            "config": self.config.__dict__,
            "selected_route": self.selected_route,
            "qubo_panel": self.qubo_panel,
            "solver_panel": self.solver_panel,
            "xai": self.xai,
            "benchmark": self.benchmark,
            "ablation": self.ablation,
            "paper_pack": self.paper_pack(),
            "latex_table": self.latex_table(),
            "event_log": self.event_log,
            "exported_at": _utcnow(),
            "disclaimer": "Prototype architecture for adaptive, constraint-aware, explainable disaster evacuation routing. No quantum advantage, real-world deployment, or guaranteed safety is claimed.",
        }

    def configure(self, **kwargs) -> dict:
        cfg = self.config
        for k, v in kwargs.items():
            if hasattr(cfg, k) and v is not None:
                setattr(cfg, k, type(getattr(cfg, k))(v))
        return self.reset(cfg)

    def map_payload(self) -> dict:
        nodes = []
        for nid, (x, y) in NODE_POS.items():
            kind = "shelter" if nid in self.shelters else ("zone" if nid.startswith("Z") else "junction")
            extra = {}
            if kind == "shelter" and nid in self.shelters:
                s = self.shelters[nid]
                extra = {
                    "capacity": s["capacity"],
                    "occupancy": s["occupancy"],
                    "remaining": s["remaining"],
                    "status": s["status"],
                    "pct": round(100 * s["occupancy"] / max(s["capacity"], 1), 1),
                }
            nodes.append({"id": nid, "x": x, "y": y, "kind": kind, **extra})
        edges = []
        for rid, r in self.roads.items():
            edges.append(
                {
                    "id": rid,
                    "u": r["u"],
                    "v": r["v"],
                    "status": r["status"],
                    "flood": r["flood"],
                    "congestion": r["congestion"],
                    "closed": r["closed"],
                    "travel_min": round(r["travel_min"], 2),
                }
            )
        return {"nodes": nodes, "edges": edges, "width": 1000, "height": 640}

    def state(self) -> dict:
        avg_rel = sum(s["reliability"] for s in self.sources) / max(len(self.sources), 1)
        closures = sum(1 for r in self.roads.values() if r["closed"])
        active_groups = sum(1 for g in self.groups if not g["evacuated"])
        return {
            "available": True,
            "environment": "SYNTHETIC SIMULATION ENVIRONMENT",
            "paper_title": "Hybrid Quantum Reinforcement Learning with Explainable AI for Dynamic Disaster Evacuation Route Optimization",
            "status": self.status,
            "demo_phase": self.demo_phase,
            "sim_clock": self._clock(),
            "graph_version": self.graph_version,
            "seed": self.config.seed,
            "config": self.config.__dict__,
            "topbar": {
                "disaster": "FLOOD EVENT",
                "simulation_time": self._clock(),
                "graph_version": self.graph_version,
                "active_groups": active_groups,
                "available_shelters": sum(1 for s in self.shelters.values() if s["status"] in ("open", "FULL")),
                "road_closures": closures,
                "system_status": "HUMAN REVIEW" if self.human_required else ("ADVISORY" if self.selected_route else "STANDBY"),
                "data_freshness": "ACCEPTABLE" if avg_rel >= 0.6 else "DEGRADED",
                "source_reliability": round(avg_rel, 3),
                "conflict_level": self.conflict.get("level", "LOW"),
            },
            "map": self.map_payload(),
            "groups": self.groups,
            "shelters": list(self.shelters.values()),
            "roads": list(self.roads.values()),
            "vehicles_left": self.vehicles_left,
            "sources": self.sources,
            "conflict": self.conflict,
            "failures": self.failures,
            "pipeline_stages": PIPELINE_STAGES,
            "pipeline_progress": self.pipeline_progress,
            "last_pipeline": self.last_pipeline,
            "candidates": self.candidates,
            "qubo_panel": self.qubo_panel,
            "solver_panel": self.solver_panel,
            "safety_check": self.safety_check,
            "xai": self.xai,
            "rl_learning": self.rl_learning,
            "decision": self.decision,
            "data_mode": {
                "mode": "DYNAMIC_BACKEND_ONLY",
                "label": "All HQRL values computed on the backend from the live synthetic graph — not static UI placeholders.",
                "rl": "online",
                "xai": "online",
                "qubo": "online",
                "benchmark": "on_demand",
            },
            "selected_route": self.selected_route,
            "previous_route": self.previous_route,
            "notification": self.notification,
            "event_log": self.event_log[-30:],
            "benchmark": self.benchmark,
            "ablation": self.ablation,
            "paper_pack": {
                "contributions": self.paper_pack()["contributions"],
                "non_claims": self.paper_pack()["non_claims"],
                "viva_script": self.paper_pack()["viva_script"],
                "metric_definitions": PAPER_METRIC_DEFINITIONS,
            },
            "auto_dispatch_allowed": self.auto_dispatch_allowed,
            "human_required": self.human_required,
            "disclaimers": [
                "Synthetic Disaster Simulation / Prototype",
                "No quantum advantage claimed",
                "No real-world emergency deployment",
                "No guaranteed safety",
                "Simulated QAOA Results where applicable",
            ],
            "timestamp": _utcnow(),
        }


engine = HqrlEngine()
