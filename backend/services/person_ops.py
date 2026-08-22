"""Per-person SOS ops: queued → assigned → en_route → to_shelter → rescued (every ~12s)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

STAGE_SECONDS = 12.0

STAGES = ["queued", "assigned", "en_route", "to_shelter", "rescued"]

STAGE_LABEL = {
    "queued": "In SOS queue — waiting for ambulance & shelter",
    "assigned": "Ambulance + shelter assigned (K-means team linked)",
    "en_route": "Ambulance en route to patient",
    "to_shelter": "Picked up — dropping to shelter",
    "rescued": "Completed — person at shelter (rescued)",
}

AMBULANCE_POOL = [f"Ambulance Unit {i}" for i in range(1, 11)]

SHELTER_POOL = [
    "Delhi University Sports Complex",
    "Talkatora Indoor Stadium",
    "Jawaharlal Nehru Stadium",
    "Commonwealth Games Village Hall",
    "Yamuna Sports Complex Shelter",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: Any) -> datetime | None:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat()


def ensure_ops(row: dict[str, Any], index: int = 0) -> dict[str, Any]:
    """Attach ops fields if missing."""
    if row.get("ops_status"):
        return row
    row["ops_status"] = "queued"
    row["ops_stage_at"] = _iso()
    row["live_status"] = "queued"
    row["status"] = "queued"
    row["ambulance_name"] = row.get("ambulance_name")
    row["shelter_name"] = row.get("shelter_name")
    row["journey"] = list(row.get("journey") or [])
    if not row["journey"]:
        row["journey"].append(
            {
                "at": row["ops_stage_at"],
                "event": "QUEUED",
                "detail": STAGE_LABEL["queued"],
                "agent": "Administrator Agent",
                "status": "queued",
            }
        )
    row.setdefault("person_index", index)
    return row


def _assign_resources(row: dict[str, Any], index: int) -> None:
    if not row.get("ambulance_name"):
        row["ambulance_name"] = AMBULANCE_POOL[index % len(AMBULANCE_POOL)]
    if not row.get("shelter_name"):
        row["shelter_name"] = SHELTER_POOL[index % len(SHELTER_POOL)]
    row["assigned_team"] = row.get("assigned_team_name") or row.get("assigned_team") or row["ambulance_name"]
    row["assigned_team_name"] = row.get("assigned_team_name") or row["assigned_team"]


def advance_one(row: dict[str, Any], index: int = 0, force: bool = False) -> bool:
    """Advance one stage if STAGE_SECONDS elapsed (or force). Returns True if changed."""
    ensure_ops(row, index)
    st = row.get("ops_status") or "queued"
    if st == "rescued":
        row["rescued"] = "yes"
        row["live_status"] = "rescued"
        row["status"] = "rescued"
        return False
    started = _parse(row.get("ops_stage_at")) or _now()
    elapsed = (_now() - started).total_seconds()
    if not force and elapsed < STAGE_SECONDS:
        return False
    try:
        idx = STAGES.index(st)
    except ValueError:
        idx = 0
    if idx >= len(STAGES) - 1:
        return False
    nxt = STAGES[idx + 1]
    row["ops_status"] = nxt
    row["ops_stage_at"] = _iso()
    row["live_status"] = nxt
    row["status"] = nxt
    if nxt == "assigned":
        _assign_resources(row, index)
        agent = "Administrator Agent"
        detail = (
            f"{STAGE_LABEL[nxt]} · ambulance {row.get('ambulance_name')} · "
            f"shelter {row.get('shelter_name')} · cluster {row.get('cluster_id') or 'n/a'}"
        )
    elif nxt == "en_route":
        agent = "Ambulance Agent"
        detail = f"{STAGE_LABEL[nxt]} · {row.get('ambulance_name')}"
    elif nxt == "to_shelter":
        agent = "Ambulance Agent"
        detail = f"{STAGE_LABEL[nxt]} · heading to {row.get('shelter_name')}"
    else:  # rescued
        agent = "Shelter Agent"
        detail = f"{STAGE_LABEL[nxt]} · admitted at {row.get('shelter_name')}"
        row["rescued"] = "yes"
    row.setdefault("journey", []).append(
        {
            "at": row["ops_stage_at"],
            "event": nxt.upper(),
            "detail": detail,
            "agent": agent,
            "status": nxt,
            "ambulance_name": row.get("ambulance_name"),
            "shelter_name": row.get("shelter_name"),
            "cluster_id": row.get("cluster_id"),
        }
    )
    row.setdefault("timestamps", {})[nxt] = row["ops_stage_at"]
    return True


def advance_all(rows: list[dict[str, Any]]) -> int:
    changed = 0
    for i, row in enumerate(rows or []):
        ensure_ops(row, i + 1)
        if advance_one(row, i, force=False):
            changed += 1
    return changed


def sync_citizen_from_log(citizen: dict[str, Any], log: dict[str, Any]) -> None:
    for key in (
        "ops_status",
        "live_status",
        "status",
        "ambulance_name",
        "shelter_name",
        "journey",
        "rescued",
        "ops_stage_at",
        "timestamps",
        "cluster_id",
        "assigned_team",
        "assigned_team_name",
        "vulnerability",
        "rescue_order",
    ):
        if log.get(key) is not None:
            citizen[key] = log.get(key)
