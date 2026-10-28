"""Multi-agent coordination layer for a simulation run.

Ten rule-based agents read the run's authoritative state (the engine's
history, the person_ops stage machine, the fleet and shelter boards) and talk
to each other through a shared message board. Nothing here invents numbers:
every message quotes a value that is in the state it was given.

    Probability Agent ─┐
    Flood Agent ───────┼──► Manager Agent ──► Administrator Agent (P < 50 %)
    Dam Agent ─────────┘          │
                                  ├──► Ambulance / Rescue / Shelter Agents
                                  │      READY at P ≥ 50 %, FIELD at P ≥ 75 %
    Route Agent (QAOA) ◄──────────┤
    Notification Agent ◄──────────┘  every message → colour-coded notification

The Manager sets the response tier from the canonical flood probability
(thresholds.ESCALATION_READY / ESCALATION_FIELD) and watches for a SUDDEN RISE
(probability jump, rainfall jump or the Isolation-Forest card monitor). On a
tier change or a sudden rise every agent announces its action from the
operator-editable PLAYBOOK. The rescue stage machine in services/person_ops.py
keeps dispatching SOS calls as before; tiers drive coordination and
notifications.

Severity colours: green = normal / done, yellow = be ready / action needed,
red = critical / all on field / sudden rise.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from backend.thresholds import ESCALATION_FIELD, ESCALATION_READY

AGENTS = [
    ("manager", "Manager Agent", "Coordinates every agent and sets the response tier"),
    ("administrator", "Administrator Agent", "Human-in-the-loop desk: SOS queue, decisions below 50 %"),
    ("probability", "Probability Agent", "ML: reads the flood model's probability every tick"),
    ("flood", "Flood Agent", "Watches rainfall and the city's river gauge (if it has one)"),
    ("dam", "Dam Agent", "Watches the upstream barrage stage"),
    ("ambulance", "Ambulance Agent", "Runs the 10-unit ambulance pool"),
    ("rescue", "Rescue Agent", "Runs the K-means cluster rescue teams"),
    ("shelter", "Shelter Agent", "Allocates shelter seats and admits people"),
    ("route", "Route Agent (QAOA)", "Picks each route with a simulated QAOA circuit"),
    ("notify", "Notification Agent", "Turns every decision into a colour-coded notification"),
]
NAME = {k: n for k, n, _ in AGENTS}

TIERS = {
    "WAITING": "Waiting for the first flood probability",
    "ADMIN": f"Below {round(ESCALATION_READY * 100)} % — handed to the Administrator (human review)",
    "READY": f"CRITICAL ≥ {round(ESCALATION_READY * 100)} % — all units told to be ready",
    "FIELD": f"≥ {round(ESCALATION_FIELD * 100)} % — all units on the field",
}
TIER_SEVERITY = {"WAITING": "green", "ADMIN": "green", "READY": "yellow", "FIELD": "red"}

KIND_SEVERITY = {
    "info": "green",
    "ack": "green",
    "done": "green",
    "dispatch": "yellow",
    "handover": "yellow",
    "critical": "yellow",
    "alert": "red",
    "field": "red",
    "sudden": "red",
    "road": "yellow",
}

MAX_MESSAGES = 300

# ---- operator-editable playbook ----------------------------------------------
# What each agent does when the tier changes or the flood picture jumps
# suddenly. Edited from the Agents tab (PUT /api/simulation/playbook).
DEFAULT_PLAYBOOK: dict[str, Any] = {
    "sudden_rise_points": 15,  # probability jump (percentage points) between ticks
    "sudden_rain_mm": 30,  # or a rainfall jump of at least this many mm
    # F23: warn a zone when its first road is forecast (F10) to flood within this many sim minutes.
    "warning_lead_min": 30,
    "actions": {
        "SILENT_ZONE": {
            "manager": "Treat the silent area as possibly the worst hit: send a patrol without waiting for calls.",
            "administrator": "Do not read the quiet SOS queue there as 'safe'.",
            "probability": "Keep scoring; the silent area is modelled from the road flood proxy, not observed.",
            "flood": "Report which towers the flood reached.",
            "dam": "No action unless a release widens the silent area.",
            "ambulance": "Send the nearest free crew to the silent area's centre (patrol).",
            "rescue": "Send a team on foot / by road to look for people who cannot call.",
            "shelter": "Expect walk-in arrivals from the silent area.",
            "route": "Plan the patrol on roads that are still open.",
            "notify": "Send a yellow SILENT AREA alert to every unit near it.",
        },
        "ZONE_WARNING": {
            "manager": "Order an early evacuation warning for the zone before its roads flood.",
            "administrator": "Watch the zone's SOS queue; new calls from it come first while roads are still open.",
            "probability": "Keep scoring; the warning follows the road forecast, not a new probability.",
            "flood": "Report the forecast closure time of the zone's first road.",
            "dam": "Check whether an upstream release brings the closure forward.",
            "ambulance": "Pre-position one free crew at the zone's edge, on a road that stays open longest.",
            "rescue": "Send a team to help people leave on foot while roads are open.",
            "shelter": "Hold seats for people leaving the warned zone.",
            "route": "Prefer roads out of the zone that close last.",
            "notify": "Send a yellow EVACUATION WARNING for the zone to its shelters and units.",
        },
        "ADMIN": {
            "manager": "Hand the decision to the Administrator; keep field units at base.",
            "administrator": "Review the SOS queue by hand and approve each dispatch.",
            "probability": "Keep scoring every tick; report any move of 5 points or more.",
            "flood": "Report rainfall and river level each tick.",
            "dam": "Watch the barrage stage against the danger mark.",
            "ambulance": "Stay at base; serve only dispatched SOS calls.",
            "rescue": "Stay at depots; serve only dispatched SOS calls.",
            "shelter": "Normal intake.",
            "route": "Plan routes only for dispatched trips.",
            "notify": "Send green status updates.",
        },
        "READY": {
            "manager": "Declare CRITICAL and put every unit on standby.",
            "administrator": "Approve vulnerable-first dispatch without waiting.",
            "probability": "Re-score every tick and cross-check Random Forest vs XGBoost.",
            "flood": "Track rainfall trend and alert on any jump.",
            "dam": "Alert at 97 % of the barrage danger level.",
            "ambulance": "Crews on standby, engines running.",
            "rescue": "Teams on standby at their depots.",
            "shelter": "Open intake and hold seats for incoming groups.",
            "route": "Pre-compute routes avoiding flooded roads.",
            "notify": "Send yellow BE READY alerts to all ambulances and shelters.",
        },
        "FIELD": {
            "manager": "ALL UNITS ON THE FIELD.",
            "administrator": "Auto-dispatch every SOS immediately.",
            "probability": "Keep scoring; flag if the model and physics disagree.",
            "flood": "Report every tick.",
            "dam": "Report the barrage stage every tick.",
            "ambulance": "Deploy every free ambulance to the highest-priority SOS.",
            "rescue": "Deploy every cluster team to its K-means cluster.",
            "shelter": "Admit everyone; reroute groups when a shelter passes 90 %.",
            "route": "Re-route at every pickup against the latest road state.",
            "notify": "Send red ALL ON FIELD alerts to every unit and shelter.",
        },
        "SUDDEN": {
            "manager": "Sudden rise: re-assess the tier now, do not wait for the next tick.",
            "administrator": "Pause manual review; let dispatch run vulnerable-first.",
            "probability": "ML: re-score now, compare Random Forest vs XGBoost, ask the explainer which input caused the jump.",
            "flood": "Confirm the rainfall jump and report the river trend.",
            "dam": "Check the barrage stage for a matching rise.",
            "ambulance": "Move free crews to standby immediately.",
            "rescue": "Move teams to standby immediately.",
            "shelter": "Open extra intake now.",
            "route": "Re-check open roads; flooded roads drop out of the graph.",
            "notify": "Send a red SUDDEN RISE alert to every unit.",
        },
        "ROAD_BLOCKED": {
            "manager": "Confirm the closure and check no unit is left without an open route.",
            "administrator": "Hold new dispatches through the closed road until routes are re-planned.",
            "probability": "Keep scoring; road closures do not change the flood probability.",
            "flood": "Report whether the closure matches the flooded stretch.",
            "dam": "Check whether a barrage release explains the closure.",
            "ambulance": "Follow the new route from your current position; report if it is also cut.",
            "rescue": "Follow the new route from your current position.",
            "shelter": "Update arrival times for groups on re-planned routes.",
            "route": "Drop the closed road from the graph and re-plan every leg that used it (QAOA over fresh candidates).",
            "notify": "Send a yellow ROAD BLOCKED alert to every unit on an affected route.",
        },
        "SHELTER_CLOSED": {
            "manager": "Confirm the closure and check every group heading there has a new shelter.",
            "administrator": "Stop allocating new SOS groups to the closed shelter.",
            "probability": "Keep scoring; a shelter closure does not change the flood probability.",
            "flood": "Report whether flooding near the shelter caused the closure.",
            "dam": "No action unless a release threatens the remaining shelters.",
            "ambulance": "Take the group to the new shelter from your current position.",
            "rescue": "Take the group to the new shelter from your current position.",
            "shelter": "Move every incoming group to the nearest open shelter with free seats; report anyone left without a seat.",
            "route": "Re-plan the leg to the new shelter on the open roads.",
            "notify": "Send a yellow SHELTER CLOSED alert to every unit carrying a moved group.",
        },
    },
}
PLAYBOOK: dict[str, Any] = copy.deepcopy(DEFAULT_PLAYBOOK)


def get_playbook() -> dict[str, Any]:
    return copy.deepcopy(PLAYBOOK)


def set_playbook(body: dict[str, Any] | None) -> dict[str, Any]:
    """Merge an edited playbook over the current one (unknown keys ignored)."""
    global PLAYBOOK
    if not body:
        return get_playbook()
    if body.get("reset"):
        PLAYBOOK = copy.deepcopy(DEFAULT_PLAYBOOK)
        return get_playbook()
    nxt = copy.deepcopy(PLAYBOOK)
    limits = {"sudden_rise_points": 100.0, "sudden_rain_mm": 1000.0, "warning_lead_min": 240.0}
    for key, hi in limits.items():
        if body.get(key) is not None:
            nxt[key] = max(1.0, min(hi, float(body[key])))
    for trig, acts in (body.get("actions") or {}).items():
        if trig in nxt["actions"] and isinstance(acts, dict):
            for agent, text in acts.items():
                if agent in NAME:
                    nxt["actions"][trig][agent] = str(text or "").strip()[:240]
    PLAYBOOK = nxt
    return get_playbook()


def load_playbook(data: dict[str, Any] | None) -> dict[str, Any]:
    """Startup (F5): the stored playbook merged over the defaults, so triggers
    added after it was saved keep their default actions."""
    global PLAYBOOK
    PLAYBOOK = copy.deepcopy(DEFAULT_PLAYBOOK)
    return set_playbook({k: v for k, v in (data or {}).items() if k != "reset"})


def tier_for(p: float | None) -> str:
    if p is None:
        return "WAITING"
    if p >= ESCALATION_FIELD:
        return "FIELD"
    if p >= ESCALATION_READY:
        return "READY"
    return "ADMIN"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _river_name() -> str:
    """River of the active city's gauge (F7), e.g. "Yamuna"."""
    try:
        from backend.geo.cities import active

        g = active().get("gauge") or {}
        return str(g.get("river") or "River").split("/")[-1].strip() or "River"
    except Exception:  # noqa: BLE001
        return "River"


def _pct(p: float | None) -> str:
    return "n/a" if p is None else f"{p * 100:.1f}%"


class MultiAgentSystem:
    def __init__(self) -> None:
        self.run_id: str | None = None
        self.messages: list[dict[str, Any]] = []
        self.seen: set[str] = set()
        self.seq = 0
        self.tier = "WAITING"
        self.tier_since: str | None = None
        self.tier_history: list[dict[str, Any]] = []
        self.sudden: list[dict[str, Any]] = []
        self.last_p: float | None = None
        self.last_rain: float | None = None
        self.notified: list[dict[str, Any]] = []
        self.amb_full = False
        self.road_events = 0
        self.shelter_events = 0
        # New messages not yet saved for replay (F5); the engine drains this
        # once per tick / operator action, never inside the 1.2 s poll.
        self.outbox: list[dict[str, Any]] = []

    def drain_outbox(self) -> list[dict[str, Any]]:
        out, self.outbox = self.outbox, []
        return out

    # ---- message board -------------------------------------------------------
    def _say(
        self,
        frm: str,
        to: list[str] | str,
        text: str,
        kind: str = "info",
        at: str | None = None,
        key: str | None = None,
        title: str | None = None,
        severity: str | None = None,
    ) -> None:
        if key is not None:
            if key in self.seen:
                return
            self.seen.add(key)
        recipients = [to] if isinstance(to, str) else list(to)
        self.seq += 1
        self.messages.append(
            {
                "id": self.seq,
                "at": at or _now(),
                "from": frm,
                "from_name": NAME.get(frm, frm),
                "to": recipients,
                "to_names": [NAME.get(t, t) for t in recipients],
                "text": text,
                "kind": kind,
                "title": title or kind.capitalize(),
                "severity": severity or KIND_SEVERITY.get(kind, "green"),
            }
        )
        if len(self.messages) > MAX_MESSAGES:
            self.messages = self.messages[-MAX_MESSAGES:]
        self.outbox.append(self.messages[-1])
        if len(self.outbox) > 2000:  # nobody drained (no run loop): keep it bounded
            self.outbox = self.outbox[-2000:]

    def _playbook(self, trigger: str, severity: str, at: str | None = None) -> None:
        """Every agent announces its action for this trigger."""
        acts = (PLAYBOOK.get("actions") or {}).get(trigger) or {}
        label = {
            "ADMIN": "Below 50 %",
            "READY": "CRITICAL",
            "FIELD": "ALL ON FIELD",
            "SUDDEN": "SUDDEN RISE",
            "ROAD_BLOCKED": "ROAD BLOCKED",
            "SHELTER_CLOSED": "SHELTER CLOSED",
            "ZONE_WARNING": "EVACUATION WARNING",
            "SILENT_ZONE": "SILENT AREA",
        }[trigger]
        for k, _, _ in AGENTS:
            text = acts.get(k)
            if text:
                self._say(k, "manager", text, kind="playbook", at=at, title=f"{label} · action", severity=severity)

    # ---- one coordination pass -----------------------------------------------
    def update(
        self,
        *,
        run_id: str | None,
        status: str | None,
        probability: float | None,
        last: dict[str, Any] | None,
        rows: list[dict[str, Any]],
        fleet: dict[str, Any],
        shelters: list[dict[str, Any]],
        prediction: dict[str, Any] | None = None,
        prev: dict[str, Any] | None = None,
        card_monitor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if run_id != self.run_id:
            self.__init__()
            self.run_id = run_id
        last = last or {}
        prediction = prediction or {}
        rain = last.get("rainfall_mm")
        river = last.get("river_m")
        dam = last.get("dam_m")
        v2 = prediction.get("v2") or {}
        model = v2.get("stage1_model") or prediction.get("model_id") or "ML model"
        sev_now = TIER_SEVERITY[tier_for(probability)]

        # Flood Agent: rainfall moves by ≥ 15 % (and ≥ 5 mm) → tell Probability.
        if rain is not None and (
            self.last_rain is None
            or (abs(rain - self.last_rain) >= 5 and abs(rain - self.last_rain) >= 0.15 * max(self.last_rain, 1))
        ):
            trend = "first reading" if self.last_rain is None else ("rising" if rain > self.last_rain else "falling")
            self._say(
                "flood",
                "probability",
                f"Rainfall {trend}: {rain:.1f} mm/24 h ({rain / 10:.1f} cm) · "
                + (f"{_river_name()} {river} m" if river is not None else "rainfall-driven city (no river gauge)"),
                title="Rainfall update",
                severity=sev_now,
            )
            self.last_rain = rain

        # Probability Agent: report a move of ≥ 5 points to the Manager.
        if probability is not None and (self.last_p is None or abs(probability - self.last_p) >= 0.05):
            self._say(
                "probability",
                "manager",
                f"Flood probability {_pct(probability)} ({model}).",
                title="Flood probability",
                severity=sev_now,
            )
            self.last_p = probability

        # Manager: SUDDEN RISE between the last two ticks (or the card monitor).
        self._sudden(prev, last, card_monitor)

        # Dam Agent: barrage stage crossing 97 % / 100 % of the 205.8 m danger mark.
        if dam is not None:
            share = dam / 205.8
            for mark in (0.97, 1.0):
                if share >= mark:
                    self._say(
                        "dam",
                        "manager",
                        f"Barrage stage {dam:.2f} m is {share * 100:.1f}% of the 205.8 m danger level.",
                        kind="alert",
                        key=f"dam|{mark}",
                        title="Dam alert",
                    )

        # Manager Agent: response tier.
        tier = tier_for(probability)
        if tier != self.tier:
            prev_tier = self.tier
            self.tier = tier
            self.tier_since = _now()
            self.tier_history.append({"at": self.tier_since, "tier": tier, "probability": probability})
            self._on_tier(prev_tier, tier, probability, fleet, shelters)

        # Person events from the stage machine (timestamps are the backend's).
        for r in rows or []:
            self._on_person(r)

        # Fleet / shelter pressure.
        # Once per episode: alert when the pool runs out, all-clear when a unit frees up.
        if fleet.get("ambulances_total"):
            if fleet.get("ambulances_free") == 0 and not self.amb_full:
                self.amb_full = True
                waiting = len(fleet.get("waiting_for_ambulance") or [])
                self._say(
                    "ambulance",
                    "manager",
                    f"All {fleet['ambulances_total']} ambulances busy · {waiting} SOS waiting for a unit.",
                    kind="alert",
                    title="Ambulances all busy",
                )
            elif fleet.get("ambulances_free") and self.amb_full:
                self.amb_full = False
                self._say(
                    "ambulance",
                    "manager",
                    f"{fleet['ambulances_free']} of {fleet['ambulances_total']} ambulances free again.",
                    kind="done",
                    title="Ambulance available",
                )
        for s in shelters or []:
            if s.get("allocated_this_run") and (s.get("utilisation_pct") or 0) >= 90:
                self._say(
                    "shelter",
                    "manager",
                    f"{s['name']} is {s['utilisation_pct']}% full ({s['seats_left']} seats left) — routing new groups elsewhere.",
                    kind="alert",
                    key=f"shelter-full|{s['name']}",
                    title="Shelter almost full",
                    severity="yellow",
                )

        return self._view(status, probability, rain, river, dam, rows, fleet, shelters, model)

    def _sudden(self, prev: dict[str, Any] | None, last: dict[str, Any], monitor: dict[str, Any] | None) -> None:
        if not last:
            return
        tick = last.get("tick")
        pts = float(PLAYBOOK.get("sudden_rise_points") or 15) / 100.0
        rain_jump = float(PLAYBOOK.get("sudden_rain_mm") or 30)
        reasons = []
        p0, p1 = (prev or {}).get("flood_probability"), last.get("flood_probability")
        r0, r1 = (prev or {}).get("rainfall_mm"), last.get("rainfall_mm")
        if p0 is not None and p1 is not None and p1 - p0 >= pts:
            reasons.append(f"probability {_pct(p0)} → {_pct(p1)}")
        if r0 is not None and r1 is not None and r1 - r0 >= rain_jump:
            reasons.append(f"rainfall {r0:.0f} → {r1:.0f} mm")
        if (monitor or {}).get("sudden"):
            alerts = (monitor or {}).get("alerts") or []
            for a in alerts[:2]:
                if a.get("direction") == "up":
                    reasons.append(f"card monitor: {a.get('label')} {a.get('from_value')} → {a.get('to_value')}")
        if not reasons:
            return
        key = f"sudden|{tick}|{last.get('sim_time_sec')}"
        if key in self.seen:
            return
        at = _now()
        self._say(
            "manager",
            [k for k, _, _ in AGENTS if k != "manager"],
            "SUDDEN RISE — " + "; ".join(reasons) + ". Every agent: run the sudden-rise playbook.",
            kind="sudden",
            key=key,
            at=at,
            title="Sudden rise",
        )
        self.sudden.append({"at": at, "reasons": reasons, "tick": tick})
        self._playbook("SUDDEN", "red", at=at)

    def announce_surge(self, run_id: str | None, fresh: list[dict[str, Any]], total: int) -> None:
        """Called by the engine when many SOS calls arrive at once."""
        if run_id != self.run_id:
            self.__init__()
            self.run_id = run_id
        new = len(fresh)
        n = total
        amb = sum(1 for r in fresh if r.get("needs_ambulance"))
        ppl = sum(int(r.get("people") or 1) for r in fresh)
        at = _now()
        self._say(
            "administrator",
            [k for k, _, _ in AGENTS if k != "administrator"],
            f"SOS SURGE: {new} new SOS calls at once ({ppl} people, {amb} need an ambulance). Queue is now {n}.",
            kind="sudden",
            at=at,
            key=f"surge|{n}",
            title="SOS surge",
        )
        self.sudden.append({"at": at, "reasons": [f"SOS surge +{new} calls ({amb} need an ambulance)"], "tick": None})
        self._playbook("SUDDEN", "red", at=at)

    def announce_road(
        self,
        run_id: str | None,
        road_id: str,
        name: str,
        blocked: bool,
        by: str,
        changes: list[dict[str, Any]],
        changed_state: bool = True,
    ) -> None:
        """A road closed / reopened (operator or flood rule) and what the Route
        Agent re-planned because of it."""
        if run_id != self.run_id:
            self.__init__()
            self.run_id = run_id
        at = _now()
        self.road_events += 1
        stuck = [c for c in changes if c.get("no_open_road")]
        changes = [c for c in changes if not c.get("no_open_road")]
        units = sorted({str(c.get("unit_name")) for c in changes if c.get("unit_name")})
        who = "Operator" if by == "operator" else "Flood rule"
        if not changed_state:
            self._say("route", "manager", f"{name} ({road_id}) was already {'closed' if blocked else 'open'} - nothing re-planned.",
                      kind="info", at=at, key=f"road|{road_id}|{self.road_events}", title="Road unchanged", severity="green")
            return
        if blocked:
            text = (f"{who} closed {name} ({road_id}). Re-planned {len(changes)} route leg(s)"
                    + (f" for {', '.join(units[:6])}{' ...' if len(units) > 6 else ''}." if units else " - no active unit was using it."))
            to = ["manager", "administrator"] + (["ambulance"] if any("Ambulance" in u for u in units) else []) + (
                ["rescue"] if any("Ambulance" not in u for u in units) else [])
            self._say("route", to, text, kind="road", at=at, key=f"road|{road_id}|{self.road_events}",
                      title=f"Road blocked: {road_id}", severity="yellow")
            for c in changes[:12]:
                self._say("route", "ambulance" if "Ambulance" in str(c.get("unit_name")) else "rescue",
                          f"{c.get('unit_name')} ({c.get('citizen_name')}): new route "
                          f"{'to the person' if c['leg'] == 'route_to_person' else 'to the shelter'} "
                          f"{c.get('new_km')} km, {c.get('new_minutes')} min ({'+' if c['delta_minutes'] >= 0 else ''}{c['delta_minutes']} min)"
                          + (" from its current position." if c.get("from_current_position") else "."),
                          kind="dispatch", at=at, key=f"reroute|{road_id}|{self.road_events}|{c.get('citizen_name')}|{c['leg']}",
                          title="Rerouted", severity="yellow")
            for c in stuck[:12]:
                self._say("route", ["manager", "administrator"],
                          f"No open road for {c.get('unit_name')} ({c.get('citizen_name')}) "
                          f"{'to the person' if c['leg'] == 'route_to_person' else 'to the shelter'} - every road is closed. "
                          "Plan kept; reopen a road to re-plan.",
                          kind="alert", at=at, key=f"noroad|{road_id}|{self.road_events}|{c.get('citizen_name')}|{c['leg']}",
                          title="No open road", severity="red")
            self._playbook("ROAD_BLOCKED", "yellow", at=at)
        else:
            text = f"{who} reopened {name} ({road_id}). {len(changes)} route leg(s) switched to a faster route."
            self._say("route", ["manager", "ambulance", "rescue"], text, kind="done", at=at,
                      key=f"road|{road_id}|{self.road_events}", title=f"Road open: {road_id}", severity="green")

    def announce_zone_warnings(self, run_id: str | None, warnings: list[dict[str, Any]]) -> int:
        """F23: one EVACUATION WARNING per zone per run (stable key warn:{run}:{zone});
        the ZONE_WARNING playbook runs once, on the first warning of the run."""
        new = [w for w in warnings if f"warn:{run_id}:{w['zone_id']}" not in self.seen]
        if not new:
            return 0
        at = _now()
        first = not any(k.startswith(f"warn:{run_id}:") for k in self.seen)
        for w in new:
            when = "already flooding" if w["closes_in_min"] <= 0 else f"forecast to flood in ~{w['closes_in_min']:.0f} min"
            pop = f" ({w['population']:,} people, WorldPop)" if w.get("population") else ""
            self._say(
                "flood", ["manager", "notify", "shelter", "ambulance"],
                f"EVACUATION WARNING — {w['name']}{pop}: road {w['road_name']} {when}. Leave now while roads are open.",
                kind="alert", at=at, key=f"warn:{run_id}:{w['zone_id']}", title="EVACUATION WARNING", severity="yellow",
            )
        if first:
            self._playbook("ZONE_WARNING", "yellow", at=at)
        return len(new)

    def announce_silent_zones(self, run_id: str | None, view: dict[str, Any] | None) -> int:
        """F29: one SILENT AREA message per zone per run (key silent:{run}:{zone})."""
        zones = (view or {}).get("zones") or []
        new = [z for z in zones if f"silent:{run_id}:{z['zone_id']}" not in self.seen]
        if not new:
            return 0
        at = _now()
        first = not any(k.startswith(f"silent:{run_id}:") for k in self.seen)
        for z in new:
            self._say(
                "flood", ["manager", "ambulance", "rescue"],
                f"SILENT AREA near {z['name']} (~{z['area_km2']} km²): the modelled flood reached its phone towers - "
                "people there may not be able to send an SOS. Consider a patrol.",
                kind="alert", at=at, key=f"silent:{run_id}:{z['zone_id']}", title="SILENT AREA", severity="yellow",
            )
        if first:
            self._playbook("SILENT_ZONE", "yellow", at=at)
        return len(new)

    def announce_staging(self, run_id: str | None, moves: dict[str, dict[str, Any]]) -> None:
        """F9: idle ambulances sent to hotspot staging points."""
        if run_id != self.run_id:
            self.__init__()
            self.run_id = run_id
        at = _now()
        for name, mv in list(moves.items())[:10]:
            self._say(
                "ambulance",
                "manager",
                f"{name} idle → staging point {mv.get('label')} ({mv.get('km')} km, {mv.get('sim_minutes')} min) "
                "to be closer to the predicted hotspots.",
                kind="dispatch",
                at=at,
                key=f"stage|{name}|{mv.get('depart_at')}",
                title="Pre-positioned",
                severity="green",
            )

    def announce_shelter_change(
        self,
        run_id: str | None,
        name: str | None,
        closed: bool,
        action: str,
        changes: list[dict[str, Any]],
        changed: bool = True,
    ) -> None:
        """A shelter closed / reopened / resized (name given), or groups moved
        because a road closure cut their shelter off (name None)."""
        if run_id != self.run_id:
            self.__init__()
            self.run_id = run_id
        at = _now()
        self.shelter_events += 1
        ev = self.shelter_events
        moved = [c for c in changes if not c.get("no_seats")]
        stranded = [c for c in changes if c.get("no_seats")]
        if name and not changed:
            self._say("shelter", "manager", f"{name}: nothing changed.", kind="info", at=at,
                      key=f"shelter|{name}|{ev}", title="Shelter unchanged", severity="green")
            return
        units = sorted({str(c.get("unit_name")) for c in moved if c.get("unit_name")})
        if name:
            text = (f"{name} {action}. Moved {len(moved)} group(s) to other shelters"
                    + (f" ({', '.join(units[:6])}{' ...' if len(units) > 6 else ''})." if units else " - no active group was heading there."))
            to = ["manager", "administrator", "route"] + (["ambulance"] if any("Ambulance" in u for u in units) else []) + (
                ["rescue"] if any("Ambulance" not in u for u in units) else [])
            self._say("shelter", to, text, kind="road" if closed or moved else "done", at=at, key=f"shelter|{name}|{ev}",
                      title=f"Shelter {'closed' if closed else 'updated'}: {name}", severity="yellow" if closed or moved else "green")
        for c in moved[:12]:
            self._say("shelter", "ambulance" if "Ambulance" in str(c.get("unit_name")) else "rescue",
                      f"{c.get('unit_name')} ({c.get('citizen_name')}): shelter {c.get('old_shelter')} → {c.get('new_shelter')}, "
                      f"{c.get('new_km')} km, {c.get('new_minutes')} min"
                      + (" from its current position." if c.get("from_current_position") else "."),
                      kind="dispatch", at=at, key=f"shelter-move|{ev}|{c.get('citizen_name')}",
                      title="Shelter changed", severity="yellow")
        for c in stranded[:12]:
            self._say("shelter", ["manager", "administrator"],
                      f"No shelter with free seats for {c.get('citizen_name')} ({c.get('unit_name')}). "
                      "The unit keeps the group until a shelter is reopened or enlarged.",
                      kind="alert", at=at, key=f"shelter-none|{ev}|{c.get('citizen_name')}",
                      title="No shelter seats", severity="red")
        if name and closed:
            self._playbook("SHELTER_CLOSED", "red" if stranded else "yellow", at=at)

    def _on_tier(self, prev: str, tier: str, p: float | None, fleet: dict[str, Any], shelters: list[dict[str, Any]]) -> None:
        free = fleet.get("ambulances_free")
        total = fleet.get("ambulances_total")
        seats = sum(s.get("seats_left") or 0 for s in shelters or [])
        if tier == "ADMIN":
            self._say(
                "manager",
                "administrator",
                f"P {_pct(p)} is below {round(ESCALATION_READY * 100)}%. Handing the decision to you (human review); field units stay at base.",
                kind="handover",
                title="Handed to Administrator",
                severity="green",
            )
            self._say("administrator", "manager", "Acknowledged — reviewing the SOS queue manually.", kind="ack", title="Administrator in charge")
            self.notified = []
            self._playbook("ADMIN", "green")
        elif tier in ("READY", "FIELD"):
            ready = tier == "READY"
            text = (
                f"CRITICAL: P {_pct(p)} ≥ {round(ESCALATION_READY * 100)}%. Be ready — crews on standby, shelters open intake."
                if ready
                else f"P {_pct(p)} ≥ {round(ESCALATION_FIELD * 100)}%. ALL UNITS ON THE FIELD."
            )
            self._say(
                "manager",
                [k for k, _, _ in AGENTS if k != "manager"],
                text,
                kind="critical" if ready else "field",
                title="CRITICAL — be ready" if ready else "ALL ON FIELD",
            )
            self._say(
                "ambulance",
                "manager",
                f"{'Standby' if ready else 'Deploying'}: {free}/{total} ambulances free, the rest already on jobs.",
                kind="ack",
                title="Ambulances",
                severity=TIER_SEVERITY[tier],
            )
            self._say("rescue", "manager", f"{'Standby' if ready else 'Deploying'}: cluster rescue teams notified.", kind="ack", title="Rescue teams", severity=TIER_SEVERITY[tier])
            self._say("shelter", "manager", f"Intake open: {seats:,} seats free across {len(shelters or [])} shelters.", kind="ack", title="Shelters", severity=TIER_SEVERITY[tier])
            at = _now()
            self.notified = (
                [{"unit": a["name"], "type": "ambulance", "status": "on job" if a["status"] == "busy" else ("standby" if ready else "deployed"), "at": at} for a in fleet.get("ambulances") or []]
                + [{"unit": s["name"], "type": "shelter", "status": "intake open", "at": at} for s in shelters or []]
            )
            n_amb = sum(1 for n in self.notified if n["type"] == "ambulance")
            n_sh = len(self.notified) - n_amb
            self._say(
                "notify",
                ["ambulance", "shelter", "rescue"],
                f"{'BE READY' if ready else 'ALL ON FIELD'} alert sent to {n_amb} ambulances and {n_sh} shelters.",
                kind="critical" if ready else "field",
                title="Alert sent to units",
                at=at,
            )
            self._playbook(tier, TIER_SEVERITY[tier], at=at)

    def _on_person(self, r: dict[str, Any]) -> None:
        name = r.get("citizen_name")
        ts = r.get("timestamps") or {}
        unit = r.get("unit_name") or "unit"
        role = "ambulance" if r.get("unit_role") == "ambulance" else "rescue"
        shelter = r.get("shelter_name")
        if ts.get("queued"):
            vuln = r.get("vulnerability") or "standard"
            self._say(
                "administrator",
                "manager",
                f"New SOS{' via 📱 citizen app' if r.get('source') == 'citizen' else ''}: {name}, {r.get('people') or 1} people ({vuln}).",
                at=ts["queued"],
                key=f"{name}|queued",
                title="SOS received",
                severity="red" if vuln != "standard" else "yellow",
            )
        wait = str(r.get("ops_wait_reason") or "")
        if r.get("ops_status") == "queued" and wait:
            self._say(
                "ambulance" if "ambulance" in wait else "shelter" if "shelter" in wait else "administrator",
                "manager",
                f"No unit for {name} yet — {wait}. Held in the queue ({r.get('vulnerability') or 'standard'}).",
                kind="alert",
                key=f"{name}|wait|{wait}",
                title="Ambulance not available" if "ambulance" in wait else "Waiting for a unit",
            )
        if ts.get("assigned") and r.get("unit_name"):
            self._say(
                "manager",
                [role, "shelter"],
                f"Dispatch {unit} to {name}; reserve {r.get('people') or 1} seats at {shelter}.",
                kind="dispatch",
                at=ts["assigned"],
                # unit in the key: a job re-offered after a reject announces again
                key=f"{name}|assigned|{unit}",
                title="Unit dispatched",
            )
        # Driver rejected / did not answer (F3). No answer twice for the same
        # person is red — the job keeps bouncing.
        no_answer = 0
        for rej in r.get("rejections") or []:
            silent = rej.get("reason") == "no answer"
            no_answer += silent
            nxt = rej.get("next_unit")
            self._say(
                role,
                ["manager", "administrator"],
                f"{rej.get('unit_name')} {'did not answer' if silent else 'rejected'} the SOS for {name}"
                + (f" ({rej.get('reason')})" if not silent else "")
                + (f" → offered to {nxt}." if nxt else f" → held in queue: {rej.get('wait_reason') or 'no free unit'}."),
                kind="alert" if silent and no_answer >= 2 else "info",
                at=rej.get("at"),
                key=f"rej:{name}:{rej.get('unit_name')}:{rej.get('at')}",
                title="No answer → reassigned" if silent else "Driver rejected",
                severity="red" if silent and no_answer >= 2 else "yellow",
            )
            q = (r.get("route_to_person") or {}).get("quantum") or {}
            if q.get("candidates"):
                agree = "agrees with Dijkstra" if q.get("agrees_with_dijkstra") else "differs from Dijkstra"
                self._say(
                    "route",
                    "manager",
                    f"QAOA picked route {q.get('chosen', 0) + 1} of {len(q['candidates'])} for {name} "
                    f"({(r.get('route_to_person') or {}).get('km')} km, p={q.get('chosen_probability', 0):.2f}) — {agree}.",
                    at=ts["assigned"],
                    key=f"{name}|route",
                    title="Route chosen (QAOA)",
                )
        if ts.get("accepted"):
            who = "driver" if role == "ambulance" else "crew lead"
            self._say(role, "manager", f"{unit} {who} accepted {name}.", kind="ack", at=ts["accepted"], key=f"{name}|accepted", title="Driver accepted")
        if ts.get("to_shelter"):
            self._say(
                role,
                "shelter",
                f"{unit} picked up {name} — ETA {r.get('eta_to_shelter_min')} min to {shelter}.",
                at=ts["to_shelter"],
                key=f"{name}|to_shelter",
                title="Picked up",
                severity="yellow",
            )
        if ts.get("rescued"):
            self._say("shelter", "manager", f"{name} admitted at {shelter}. Safe.", kind="done", at=ts["rescued"], key=f"{name}|rescued", title="Safe at shelter")

    def _view(self, status, p, rain, river, dam, rows, fleet, shelters, model) -> dict[str, Any]:
        rows = rows or []
        stage = lambda s: sum(1 for r in rows if r.get("ops_status") == s)  # noqa: E731
        active = sum(1 for r in rows if r.get("ops_status") in ("assigned", "en_route", "to_shelter"))
        seats = sum(s.get("seats_left") or 0 for s in shelters or [])
        q_rows = [(r.get("route_to_person") or {}).get("quantum") for r in rows]
        q_rows = [q for q in q_rows if q and q.get("candidates")]
        agree = sum(1 for q in q_rows if q.get("agrees_with_dijkstra"))
        tier = self.tier
        hot = tier in ("READY", "FIELD")
        sev_count = {c: sum(1 for m in self.messages if m["severity"] == c) for c in ("green", "yellow", "red")}

        cards = {
            "manager": (tier, TIERS[tier]),
            "administrator": (
                "ACTIVE" if tier == "ADMIN" or stage("queued") else "WATCHING",
                f"{stage('queued')} SOS in queue · {'deciding (human review)' if tier == 'ADMIN' else 'dispatching vulnerable-first'}",
            ),
            "probability": ("ALERT" if hot else "WATCHING", f"P = {_pct(p)} · {model}"),
            "flood": (
                "ALERT" if hot else "WATCHING",
                f"Rain {rain:.1f} mm ({rain / 10:.1f} cm) · river {river} m" if rain is not None else "No reading yet",
            ),
            "dam": ("ALERT" if dam is not None and dam >= 0.97 * 205.8 else "WATCHING", f"Barrage {dam} m / 205.8 m danger" if dam is not None else "No reading yet"),
            "ambulance": (
                "ACTIVE" if fleet.get("ambulances_busy") else ("STANDBY" if hot else "IDLE"),
                f"{fleet.get('ambulances_free', '—')}/{fleet.get('ambulances_total', '—')} free · {fleet.get('ambulances_busy', 0)} on jobs",
            ),
            "rescue": (
                "ACTIVE" if fleet.get("rescue_units_active") else ("STANDBY" if hot else "IDLE"),
                f"{len(fleet.get('rescue_units_active') or [])} teams on jobs",
            ),
            "shelter": ("ACTIVE" if stage("to_shelter") or stage("rescued") else ("STANDBY" if hot else "IDLE"), f"{seats:,} seats free · {stage('rescued')} admitted"),
            "route": (
                "ACTIVE" if active else "IDLE",
                f"{len(q_rows)} QAOA route choices · {agree} agree with Dijkstra" if q_rows else "No routes yet",
            ),
            "notify": (
                "ALERT" if sev_count["red"] else ("ACTIVE" if self.messages else "IDLE"),
                f"{sev_count['red']} red · {sev_count['yellow']} yellow · {sev_count['green']} green",
            ),
        }
        actions = (PLAYBOOK.get("actions") or {}).get(tier) or {}
        agents = [
            {
                "key": k,
                "name": n,
                "role": role,
                "status": cards[k][0],
                "observation": cards[k][1],
                "action": actions.get(k),
                "messages_sent": sum(1 for m in self.messages if m["from"] == k),
            }
            for k, n, role in AGENTS
        ]
        return {
            "available": True,
            "run_status": status,
            "probability": p,
            "tier": tier,
            "tier_label": TIERS[tier],
            "tier_severity": TIER_SEVERITY[tier],
            "tier_since": self.tier_since,
            "tier_history": self.tier_history,
            "sudden_events": self.sudden,
            "thresholds": {"ready": ESCALATION_READY, "field": ESCALATION_FIELD},
            "agents": agents,
            "messages": list(reversed(self.messages[-200:])),
            "severity_counts": sev_count,
            "notified": self.notified,
            "playbook": get_playbook(),
            "note": "Rule-based agents over the live run state; every message quotes a value from that state.",
        }
