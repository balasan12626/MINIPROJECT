"""Rescue desk: Admin → Ambulance → Shelter, one SOS at a time."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from backend.utils.geo import jsonable, utcnow


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


AMBULANCES = [
    {"ambulance_id": f"AMB-{i:02d}", "name": f"Ambulance Unit {i}", "status": "free", "current_case_id": None}
    for i in range(1, 11)
]

# 5 shelters ~10k total capacity
SHELTERS = [
    {"shelter_id": "SH-01", "name": "Delhi University Sports Complex", "capacity": 2000, "occupancy": 110, "lat": 28.688, "lon": 77.209},
    {"shelter_id": "SH-02", "name": "Talkatora Indoor Stadium", "capacity": 1800, "occupancy": 40, "lat": 28.625, "lon": 77.195},
    {"shelter_id": "SH-03", "name": "Jawaharlal Nehru Stadium", "capacity": 3200, "occupancy": 640, "lat": 28.583, "lon": 77.234},
    {"shelter_id": "SH-04", "name": "Commonwealth Games Village Hall", "capacity": 1500, "occupancy": 200, "lat": 28.612, "lon": 77.275},
    {"shelter_id": "SH-05", "name": "Yamuna Sports Complex Shelter", "capacity": 1500, "occupancy": 90, "lat": 28.655, "lon": 77.305},
]

# pin colors for map / UI
STATUS_COLORS = {
    "sos": "#ff5d6c",
    "shared": "#f5c542",
    "assigned": "#4aa3ff",
    "en_route": "#f0a04a",
    "pickup": "#c084fc",
    "to_shelter": "#5ce1ff",
    "rescued": "#3ee0a0",
    "declined": "#8aa3b0",
    "waiting": "#ff8a5c",
}


class RescueDesk:
    def __init__(self) -> None:
        self.ambulances = [dict(a) for a in AMBULANCES]
        self.shelters = [dict(s) for s in SHELTERS]
        self.cases: list[dict[str, Any]] = []
        self.queue: list[str] = []  # case_ids waiting for free amb+shelter
        self.active_case_id: Optional[str] = None  # only one in-flight assignment
        self.messages: list[dict[str, Any]] = []
        self.message_counts = {"whatsapp": 0, "telegram": 0, "sms": 0, "web": 0}
        self.admin_log: list[dict[str, Any]] = []

    def _log_admin(self, text: str, extra: dict | None = None) -> None:
        self.admin_log.append({"at": _iso(_now()), "text": text, "extra": extra or {}})
        self.admin_log = self.admin_log[-80:]

    def _send_msg(self, channel: str, to: str, text: str, case_id: str | None = None) -> None:
        ch = channel.lower()
        if ch not in self.message_counts:
            ch = "web"
        self.message_counts[ch] = int(self.message_counts.get(ch) or 0) + 1
        self.messages.append(
            {
                "id": str(uuid.uuid4())[:8],
                "channel": ch,
                "to": to,
                "text": text,
                "case_id": case_id,
                "at": _iso(_now()),
            }
        )
        self.messages = self.messages[-120:]

    def _free_ambulances(self) -> list[dict]:
        return [a for a in self.ambulances if a.get("status") == "free"]

    def _shelter_rows(self) -> list[dict]:
        rows = []
        for s in self.shelters:
            cap = int(s.get("capacity") or 0)
            occ = int(s.get("occupancy") or 0)
            left = max(0, cap - occ)
            rows.append(
                {
                    **s,
                    "vacant": left,
                    "filled": occ,
                    "left": left,
                    "full": left <= 0,
                }
            )
        return rows

    def _total_vacant(self) -> int:
        return sum(r["vacant"] for r in self._shelter_rows())

    def _pick_shelter(self, people: int) -> dict | None:
        for s in sorted(self._shelter_rows(), key=lambda x: -x["vacant"]):
            if s["vacant"] >= max(1, people):
                return next(x for x in self.shelters if x["shelter_id"] == s["shelter_id"])
        return None

    def _case(self, case_id: str) -> dict | None:
        return next((c for c in self.cases if c.get("case_id") == case_id), None)

    def _append_journey(self, case: dict, event: str, detail: str, agent: str = "Administrator Agent") -> None:
        case.setdefault("journey", []).append(
            {
                "at": _iso(_now()),
                "event": event,
                "detail": detail,
                "agent": agent,
                "status": case.get("status"),
            }
        )

    def state(self) -> dict[str, Any]:
        free_amb = len(self._free_ambulances())
        vacant = self._total_vacant()
        active = self._case(self.active_case_id) if self.active_case_id else None
        return jsonable(
            {
                "ambulances": self.ambulances,
                "ambulances_total": len(self.ambulances),
                "ambulances_free": free_amb,
                "ambulances_busy": len(self.ambulances) - free_amb,
                "shelters": self._shelter_rows(),
                "shelters_total": len(self.shelters),
                "capacity_total": sum(int(s.get("capacity") or 0) for s in self.shelters),
                "vacant_total": vacant,
                "cases": self.cases,
                "queue": self.queue,
                "queue_len": len(self.queue),
                "active_case_id": self.active_case_id,
                "active_case": active,
                "messages": self.messages[-40:],
                "message_counts": self.message_counts,
                "admin_log": self.admin_log[-40:],
                "status_colors": STATUS_COLORS,
                "wait_reason": self._wait_reason(),
            }
        )

    def _wait_reason(self) -> str | None:
        if self.active_case_id:
            return None
        if not self.queue:
            return None
        if not self._free_ambulances():
            return "All 10 ambulances busy — please wait until one is free, then next SOS is sent."
        if self._total_vacant() <= 0:
            return "All shelters full — please wait until seats free, then next SOS is sent."
        return "Waiting to assign next SOS (one person at a time)."

    def ingest_sos(self, body: dict[str, Any]) -> dict[str, Any]:
        people = int(body.get("people") or 1)
        case_id = f"CASE-{str(uuid.uuid4())[:8].upper()}"
        case = {
            "case_id": case_id,
            "citizen_name": body.get("citizen_name") or "Unknown Citizen",
            "age": body.get("age"),
            "lat": body.get("lat"),
            "lon": body.get("lon"),
            "people": people,
            "water_level_note": body.get("water_level_note") or "flood water",
            "status": "sos",
            "pin_color": STATUS_COLORS["sos"],
            "created_at": _iso(_now()),
            "shared_at": None,
            "ambulance_id": None,
            "ambulance_name": None,
            "shelter_id": None,
            "shelter_name": None,
            "declined_by": [],
            "accepted_ambulance": None,
            "cluster_id": body.get("cluster_id"),
            "flood_probability": body.get("flood_probability"),
            "model_id": body.get("model_id") or "random_forest",
            "journey": [],
            "rescued": None,
            "timestamps": {"sos": _iso(_now())},
        }
        self._append_journey(case, "SOS_RECEIVED", f"SOS from {case['citizen_name']} · {people} people", "Citizen")
        self.cases.append(case)
        self.queue.append(case_id)
        self._send_msg("whatsapp", "Administrator Agent", f"New SOS: {case['citizen_name']} ({people} people)", case_id)
        self._send_msg("telegram", "Administrator Agent", f"SOS alert {case_id} — review & share", case_id)
        self._log_admin(f"New SOS {case_id} from {case['citizen_name']} queued.", {"case_id": case_id})
        self.try_dispatch_next()
        return self.state()

    def ingest_from_simulation(self, sim_state: dict[str, Any]) -> dict[str, Any]:
        """Pull new simulation citizens into rescue desk (dedupe by name+lat)."""
        existing = {(c.get("citizen_name"), c.get("lat"), c.get("lon")) for c in self.cases}
        pred = ((sim_state.get("pipeline") or {}).get("prediction") or {})
        clusters = ((sim_state.get("pipeline") or {}).get("clusters") or [])
        for c in sim_state.get("citizens") or []:
            key = (c.get("citizen_name"), c.get("lat"), c.get("lon"))
            if key in existing:
                continue
            cluster_id = None
            for cl in clusters:
                for p in cl.get("priority_queue") or []:
                    if p.get("citizen_name") == c.get("citizen_name"):
                        cluster_id = cl.get("cluster_id")
                        break
            self.ingest_sos(
                {
                    **c,
                    "cluster_id": cluster_id or c.get("cluster_id"),
                    "flood_probability": pred.get("flood_probability"),
                    "model_id": pred.get("model_id"),
                }
            )
        return self.state()

    def try_dispatch_next(self) -> None:
        """Only one active share at a time; wait if amb/shelter unavailable."""
        if self.active_case_id:
            return
        while self.queue:
            case_id = self.queue[0]
            case = self._case(case_id)
            if not case:
                self.queue.pop(0)
                continue
            free = self._free_ambulances()
            shelter = self._pick_shelter(int(case.get("people") or 1))
            if not free:
                case["status"] = "waiting"
                case["pin_color"] = STATUS_COLORS["waiting"]
                self._append_journey(case, "WAIT_AMBULANCE", "No free ambulance — please wait", "Administrator Agent")
                self._log_admin("SOS held: all ambulances busy.")
                return
            if not shelter:
                case["status"] = "waiting"
                case["pin_color"] = STATUS_COLORS["waiting"]
                self._append_journey(case, "WAIT_SHELTER", "No vacant shelter seats — please wait", "Administrator Agent")
                self._log_admin("SOS held: shelters full.")
                return
            # Share this one case only
            self.queue.pop(0)
            self.active_case_id = case_id
            case["status"] = "shared"
            case["pin_color"] = STATUS_COLORS["shared"]
            case["shared_at"] = _iso(_now())
            case["timestamps"]["shared"] = case["shared_at"]
            case["proposed_shelter_id"] = shelter["shelter_id"]
            case["proposed_shelter_name"] = shelter["name"]
            case["proposed_ambulance_ids"] = [a["ambulance_id"] for a in free[:3]]
            self._append_journey(
                case,
                "ADMIN_SHARED",
                f"Admin shared SOS to ambulance units + shelter {shelter['name']} (1 person request only)",
                "Administrator Agent",
            )
            self._send_msg("whatsapp", "Ambulance Agent", f"New patient: {case['citizen_name']} — Accept or Decline", case_id)
            self._send_msg("telegram", "Shelter Agent", f"Reserve seats at {shelter['name']} for {case['people']} people", case_id)
            self._send_msg("whatsapp", "Shelter Agent", f"Vacancy check: {shelter['name']}", case_id)
            self._log_admin(f"Shared {case_id} to ambulance & shelter agents (single request).")
            return

    def admin_share(self, case_id: str) -> dict[str, Any]:
        if case_id not in self.queue and self.active_case_id != case_id:
            # move to front of queue
            if any(c.get("case_id") == case_id for c in self.cases):
                self.queue = [case_id] + [q for q in self.queue if q != case_id]
        self.try_dispatch_next()
        return self.state()

    def ambulance_action(self, case_id: str, ambulance_id: str, action: str) -> dict[str, Any]:
        case = self._case(case_id)
        amb = next((a for a in self.ambulances if a["ambulance_id"] == ambulance_id), None)
        if not case or not amb:
            return self.state()
        action = action.lower()
        if action == "decline":
            case.setdefault("declined_by", []).append({"ambulance_id": ambulance_id, "at": _iso(_now())})
            self._append_journey(case, "AMBULANCE_DECLINED", f"{amb['name']} declined", "Ambulance Agent")
            self._send_msg("telegram", "Administrator Agent", f"{amb['name']} declined {case_id}", case_id)
            self._log_admin(f"{ambulance_id} declined {case_id}")
            return self.state()
        if action == "accept":
            if amb.get("status") != "free":
                self._append_journey(case, "AMBULANCE_BUSY", f"{amb['name']} not free", "Ambulance Agent")
                return self.state()
            amb["status"] = "busy"
            amb["current_case_id"] = case_id
            case["status"] = "assigned"
            case["pin_color"] = STATUS_COLORS["assigned"]
            case["ambulance_id"] = ambulance_id
            case["ambulance_name"] = amb["name"]
            case["accepted_ambulance"] = ambulance_id
            case["timestamps"]["assigned"] = _iso(_now())
            shelter = next((s for s in self.shelters if s["shelter_id"] == case.get("proposed_shelter_id")), None)
            if shelter:
                case["shelter_id"] = shelter["shelter_id"]
                case["shelter_name"] = shelter["name"]
            self._append_journey(case, "AMBULANCE_ACCEPTED", f"{amb['name']} accepted — assigned", "Ambulance Agent")
            self._send_msg("whatsapp", "Administrator Agent", f"{amb['name']} accepted {case['citizen_name']}", case_id)
            self._send_msg("telegram", case["citizen_name"], f"Ambulance {amb['name']} is assigned to you", case_id)
            return self.state()
        # flow steps
        steps = {
            "going": ("en_route", "GOING_TO_PATIENT", "En route to patient pickup place"),
            "pickup": ("pickup", "PICKUP", "Patient picked up"),
            "drop": ("to_shelter", "DROP_TO_SHELTER", "Dropping patient at shelter"),
            "completed": ("rescued", "COMPLETED", "Case completed — rescued at shelter"),
        }
        if action not in steps:
            return self.state()
        status, event, detail = steps[action]
        case["status"] = status
        case["pin_color"] = STATUS_COLORS.get(status, "#fff")
        case["timestamps"][action] = _iso(_now())
        self._append_journey(case, event, detail, "Ambulance Agent")
        if action == "drop":
            self._send_msg("whatsapp", "Shelter Agent", f"Arriving with {case['citizen_name']}", case_id)
        if action == "completed":
            case["rescued"] = True
            # occupy shelter seats
            shelter = next((s for s in self.shelters if s["shelter_id"] == case.get("shelter_id")), None)
            if shelter:
                need = int(case.get("people") or 1)
                shelter["occupancy"] = min(int(shelter.get("capacity") or 0), int(shelter.get("occupancy") or 0) + need)
                self._append_journey(
                    case,
                    "SHELTER_ADMITTED",
                    f"Admitted to {shelter['name']} · seats used {need}",
                    "Shelter Agent",
                )
                self._send_msg("telegram", "Administrator Agent", f"{case['citizen_name']} rescued at {shelter['name']}", case_id)
            # free ambulance
            amb["status"] = "free"
            amb["current_case_id"] = None
            if self.active_case_id == case_id:
                self.active_case_id = None
            self._send_msg("whatsapp", "Administrator Agent", f"Case {case_id} completed. Ambulance free.", case_id)
            self._log_admin(f"Completed {case_id}; ambulance freed; next SOS if queued.")
            self.try_dispatch_next()
        return self.state()

    def shelter_confirm(self, case_id: str, accept: bool = True) -> dict[str, Any]:
        case = self._case(case_id)
        if not case:
            return self.state()
        if not accept:
            case.setdefault("declined_by", []).append({"shelter": case.get("proposed_shelter_id"), "at": _iso(_now())})
            self._append_journey(case, "SHELTER_DECLINED", "Shelter agent declined / full", "Shelter Agent")
            # try another shelter
            alt = self._pick_shelter(int(case.get("people") or 1))
            if alt and alt["shelter_id"] != case.get("proposed_shelter_id"):
                case["proposed_shelter_id"] = alt["shelter_id"]
                case["proposed_shelter_name"] = alt["name"]
                self._append_journey(case, "SHELTER_REASSIGN", f"Reassigned to {alt['name']}", "Administrator Agent")
            else:
                case["status"] = "waiting"
                case["pin_color"] = STATUS_COLORS["waiting"]
                if self.active_case_id == case_id:
                    self.active_case_id = None
                    self.queue.insert(0, case_id)
            return self.state()
        shelter = next((s for s in self.shelters if s["shelter_id"] == case.get("proposed_shelter_id")), None)
        if shelter:
            case["shelter_id"] = shelter["shelter_id"]
            case["shelter_name"] = shelter["name"]
            self._append_journey(case, "SHELTER_RESERVED", f"Seats reserved at {shelter['name']}", "Shelter Agent")
            self._send_msg("whatsapp", "Ambulance Agent", f"Shelter ready: {shelter['name']}", case_id)
        return self.state()

    def confirm_rescued(self, case_id: str, rescued: bool) -> dict[str, Any]:
        case = self._case(case_id)
        if not case:
            return self.state()
        case["rescued"] = bool(rescued)
        if rescued:
            case["status"] = "rescued"
            case["pin_color"] = STATUS_COLORS["rescued"]
            self._append_journey(case, "RESCUED_YES", "Citizen confirmed rescued: YES", "Rescue Agent")
        else:
            self._append_journey(case, "RESCUED_NO", "Citizen said NOT rescued — ask again / escalate", "Rescue Agent")
            self._send_msg("telegram", "Administrator Agent", f"{case['citizen_name']} not rescued yet — re-ask", case_id)
        return self.state()

    def reset(self) -> dict[str, Any]:
        self.__init__()
        return self.state()

    def person_report(self, case_id: str) -> dict[str, Any]:
        case = self._case(case_id)
        if not case:
            return {"available": False, "message": "Case not found"}
        return {
            "available": True,
            "case": case,
            "message_counts": self.message_counts,
            "ambulances_free": len(self._free_ambulances()),
            "vacant_total": self._total_vacant(),
        }


desk = RescueDesk()
