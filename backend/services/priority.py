"""Vulnerable-first ordering after K-means (policy on top of clustering)."""

from __future__ import annotations

from typing import Any


def _age(c: dict[str, Any]) -> int | None:
    try:
        if c.get("age") is None or c.get("age") == "":
            return None
        return int(c.get("age"))
    except (TypeError, ValueError):
        return None


def water_tier(note: str | None) -> int:
    n = str(note or "").lower()
    if "chest" in n or "neck" in n or "shoulder" in n:
        return 2
    if "waist" in n:
        return 1
    return 0


def vulnerability_tier(c: dict[str, Any]) -> int:
    age = _age(c)
    if age is not None and (age < 18 or age >= 60):
        return 0
    if water_tier(c.get("water_level_note") or c.get("water_depth")) >= 2:
        return 1
    return 2


def vulnerability_label(c: dict[str, Any]) -> str:
    age = _age(c)
    if age is not None and age < 18:
        return "child"
    if age is not None and age >= 60:
        return "elderly"
    if water_tier(c.get("water_level_note")) >= 2:
        return "chest-deep"
    return "standard"


def sort_key(c: dict[str, Any]) -> tuple:
    age = _age(c) if _age(c) is not None else 40
    tier = vulnerability_tier(c)
    if tier == 0:
        if age < 18:
            return (0, age, -water_tier(c.get("water_level_note")))
        return (0, 100 + (100 - age), -water_tier(c.get("water_level_note")))
    if tier == 1:
        return (1, -water_tier(c.get("water_level_note")), age)
    return (2, -water_tier(c.get("water_level_note")), age)


def rank_citizens(citizens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(list(citizens or []), key=sort_key)
    out = []
    for i, c in enumerate(ordered, start=1):
        row = dict(c)
        row["rescue_order"] = i
        row["vulnerability"] = vulnerability_label(c)
        out.append(row)
    return out


def attach_cluster_queues(clusters: list[dict[str, Any]], citizens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(c.get("_id") or c.get("id") or ""): c for c in citizens}
    by_name = {str(c.get("citizen_name") or ""): c for c in citizens}
    updated = []
    for cl in clusters:
        members = []
        for eid in cl.get("emergency_ids") or []:
            if eid and eid in by_id:
                members.append(by_id[eid])
        if not members:
            members = [c for c in citizens if str(c.get("cluster_id") or "") == cl.get("cluster_id")]
        ranked = rank_citizens(members)
        row = dict(cl)
        row["priority_queue"] = [
            {
                "rescue_order": m.get("rescue_order"),
                "citizen_name": m.get("citizen_name"),
                "age": m.get("age"),
                "water_level_note": m.get("water_level_note"),
                "vulnerability": m.get("vulnerability"),
                "people": m.get("people"),
            }
            for m in ranked
        ]
        updated.append(row)
    return updated
