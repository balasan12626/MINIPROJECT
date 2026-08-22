"""Demo extras for simulation builder/run (status board, ETA, ask-agent, summary)."""

from __future__ import annotations

from typing import Any

from backend.utils.geo import haversine_km


STATUS_FLOW = ["contacted", "trapped", "moving", "rescued"]


def medical_triage(citizen: dict[str, Any]) -> str:
    vuln = str(citizen.get("vulnerability") or "")
    age = citizen.get("age")
    try:
        age_i = int(age) if age is not None else None
    except (TypeError, ValueError):
        age_i = None
    water = str(citizen.get("water_level_note") or "").lower()
    if age_i is not None and age_i < 18:
        return "child"
    if age_i is not None and age_i >= 60:
        return "elderly"
    if "chest" in water or "injured" in water:
        return "injured"
    if vuln in {"child", "elderly", "chest-deep"}:
        return "priority"
    return "standard"


def eta_minutes(citizen: dict[str, Any], teams: list[dict[str, Any]]) -> float | None:
    lat, lon = citizen.get("lat"), citizen.get("lon")
    if lat is None or lon is None or not teams:
        return None
    best = None
    for t in teams:
        if t.get("lat") is None or t.get("lon") is None:
            continue
        km = haversine_km(float(lat), float(lon), float(t["lat"]), float(t["lon"]))
        # ~25 km/h flood response average
        mins = round(max(2.0, (km / 25.0) * 60.0), 1)
        if best is None or mins < best:
            best = mins
    return best


def build_status_board(contact_log: list[dict[str, Any]], tick: int = 0) -> list[dict[str, Any]]:
    board = []
    for row in contact_log or []:
        idx = int(row.get("person_index") or 0)
        # Prefer live ops pipeline (queued → assigned → en_route → to_shelter → rescued)
        ops = str(row.get("ops_status") or row.get("live_status") or "").lower()
        if ops:
            status = ops
        elif row.get("rescued") in ("yes", True):
            status = "rescued"
        elif row.get("rescued") in ("no", False):
            status = "trapped"
        else:
            stage = min(len(STATUS_FLOW) - 1, max(0, (tick // 3) - (idx // 3)))
            status = STATUS_FLOW[stage] if tick > 0 else (row.get("status") or "contacted")
        board.append(
            {
                "person_index": idx,
                "citizen_name": row.get("citizen_name"),
                "age": row.get("age"),
                "status": status,
                "water_level_note": row.get("water_level_note"),
                "assigned_team": row.get("assigned_team") or row.get("ambulance_name"),
                "ambulance_name": row.get("ambulance_name"),
                "shelter_name": row.get("shelter_name"),
                "cluster_id": row.get("cluster_id"),
                "vulnerability": row.get("vulnerability"),
                "triage": medical_triage(row),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "people": row.get("people"),
                "ops_status": row.get("ops_status"),
                "pdf_ready": True,
            }
        )
    board.sort(key=lambda r: r.get("person_index") or 99)
    return board


def build_eta_board(citizens: list[dict[str, Any]], teams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in citizens or []:
        out.append(
            {
                "citizen_name": c.get("citizen_name"),
                "rescue_order": c.get("rescue_order"),
                "eta_min": eta_minutes(c, teams),
                "assigned_team": c.get("assigned_team_name") or c.get("assigned_team"),
                "triage": medical_triage(c),
            }
        )
    out.sort(key=lambda r: r.get("rescue_order") or 99)
    return out


def team_paths(citizens: list[dict[str, Any]], teams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paths = []
    unused = list(teams or [])
    for c in sorted(citizens or [], key=lambda x: x.get("rescue_order") or 99)[:8]:
        if not unused or c.get("lat") is None:
            continue
        team = min(
            unused,
            key=lambda t: haversine_km(float(c["lat"]), float(c["lon"]), float(t.get("lat") or 0), float(t.get("lon") or 0)),
        )
        unused = [t for t in unused if t.get("team_id") != team.get("team_id")] or unused[1:]
        paths.append(
            {
                "team_id": team.get("team_id"),
                "team_name": team.get("name"),
                "role": team.get("role") or "rescue",
                "from": [float(team["lat"]), float(team["lon"])],
                "to": [float(c["lat"]), float(c["lon"])],
                "citizen_name": c.get("citizen_name"),
            }
        )
    return paths


def disagreement_debate(dual: dict[str, Any] | None) -> list[dict[str, str]]:
    dual = dual or {}
    rf = dual.get("random_forest")
    xgb = dual.get("xgboost")
    rf_s = "n/a" if rf is None else f"{rf * 100:.1f}%"
    xgb_s = "n/a" if xgb is None else f"{xgb * 100:.1f}%"
    if not dual.get("disagree"):
        return [
            {"from": "Flood Risk Agent", "to": "Administrator Agent", "text": f"Models agree enough. RF {rf_s}, XGBoost {xgb_s}."},
            {"from": "Administrator Agent", "to": "Flood Risk Agent", "text": "Copy. Policy may proceed without hold."},
        ]
    return [
        {"from": "Flood Risk Agent", "to": "Administrator Agent", "text": f"Random Forest reads {rf_s}. I recommend following the forest for ops consistency."},
        {"from": "Administrator Agent", "to": "Flood Risk Agent", "text": f"Hold. XGBoost is {xgb_s}. Gap is too wide to auto-dispatch."},
        {"from": "Flood Risk Agent", "to": "Administrator Agent", "text": "Then we stage teams only. No street entry until override."},
        {"from": "Administrator Agent", "to": "Rescue Agent", "text": "Rescue, edge only. Operator must clear the disagreement before full call."},
    ]


def confidence_band(dual: dict[str, Any] | None, blended: float | None) -> dict[str, Any]:
    dual = dual or {}
    vals = [v for v in [dual.get("random_forest"), dual.get("xgboost"), blended] if v is not None]
    if not vals:
        return {"available": False}
    lo, hi = min(vals), max(vals)
    mid = sum(vals) / len(vals)
    return {
        "available": True,
        "low": round(lo, 4),
        "mid": round(mid, 4),
        "high": round(hi, 4),
        "spread_pts": round((hi - lo) * 100, 1),
        "message": f"Confidence band {(lo * 100):.1f}% – {(hi * 100):.1f}% (spread {(hi - lo) * 100:.1f} pts)",
    }


def after_action_bullets(state: dict[str, Any]) -> list[str]:
    history = state.get("history") or []
    citizens = state.get("citizens") or []
    log = state.get("contact_log") or []
    after = state.get("after") or {}
    dual = ((state.get("pipeline") or {}).get("prediction") or {}).get("dual") or {}
    shelters = state.get("shelter_board") or []
    board = state.get("status_board") or build_status_board(log, int(state.get("tick") or 0))
    peaks = [h.get("flood_probability") for h in history if h.get("flood_probability") is not None]
    peak = max(peaks) if peaks else after.get("flood_probability")
    rescued = sum(1 for r in board if str(r.get("status") or "").lower() == "rescued")
    missing = sum(1 for r in board if str(r.get("status") or "").lower() in {"missing", "trapped"})
    vacant = sum(int(s.get("seats_left") or 0) for s in shelters)
    full = sum(1 for s in shelters if s.get("full"))
    first = next((c for c in sorted(citizens, key=lambda x: x.get("rescue_order") or 99)), None)
    bullets = [
        f"Peak flood probability reached {round((peak or 0) * 100, 1)}% during the run.",
        f"{len(citizens)} SOS citizens queued · rescued {rescued} · missing/trapped {missing}.",
        f"Shelters tracked: {len(shelters)} · vacant seats {vacant} · full shelters {full}.",
        f"Vulnerable-first lead: {(first or {}).get('citizen_name') or 'n/a'} (order 1).",
        (
            f"Model honesty: RF {None if dual.get('random_forest') is None else round(dual['random_forest']*100,1)}% vs "
            f"XGBoost {None if dual.get('xgboost') is None else round(dual['xgboost']*100,1)}%"
            + (" — disagreement held auto-dispatch." if dual.get("disagree") else " — models aligned.")
        ),
    ]
    fa = state.get("false_alarm") or {}
    if fa.get("active"):
        bullets.append(f"False-alarm / mistake drill: {fa.get('message')}")
    return bullets[:6]


def _ops_stats(state: dict[str, Any]) -> dict[str, Any]:
    citizens = list(state.get("citizens") or [])
    log = list(state.get("contact_log") or [])
    board = state.get("status_board") or build_status_board(log, int(state.get("tick") or 0))
    shelters = list(state.get("shelter_board") or [])
    pipeline = state.get("pipeline") or {}
    if not shelters:
        raw = pipeline.get("shelters") or pipeline.get("all_shelters") or []
        for s in raw[:12]:
            cap = int(s.get("capacity") or 0)
            occ = int(s.get("occupancy") or 0)
            shelters.append(
                {
                    "shelter_id": s.get("shelter_id"),
                    "name": s.get("name"),
                    "capacity": cap,
                    "occupancy": occ,
                    "seats_left": max(0, cap - occ),
                    "full": cap > 0 and occ >= cap,
                }
            )

    status_counts: dict[str, int] = {}
    for b in board:
        key = str(b.get("status") or "unknown").lower()
        status_counts[key] = status_counts.get(key, 0) + 1

    rescued = status_counts.get("rescued", 0)
    missing = status_counts.get("missing", 0) + status_counts.get("trapped", 0)
    contacted = status_counts.get("contacted", 0)
    moving = status_counts.get("moving", 0)
    pending = max(0, len(citizens) - rescued - missing - contacted - moving)
    vacant = sum(int(s.get("seats_left") or 0) for s in shelters)
    capacity = sum(int(s.get("capacity") or 0) for s in shelters)
    occupancy = sum(int(s.get("occupancy") or 0) for s in shelters)
    full_shelters = sum(1 for s in shelters if s.get("full") or int(s.get("seats_left") or 0) <= 0)
    people_total = sum(int(c.get("people") or 1) for c in citizens)

    mistakes: list[str] = []
    fa = state.get("false_alarm") or {}
    if fa.get("active"):
        mistakes.append(str(fa.get("message") or "False-alarm drill active — stand down full rescue."))
    dual = ((pipeline.get("prediction") or {}).get("dual") or {})
    if dual.get("disagree"):
        mistakes.append(dual.get("message") or "RF and XGBoost disagree — auto-dispatch held.")
    # People marked rescued=no while still listed → operational mismatch
    for row in log:
        if row.get("rescued") in ("no", False) and str(row.get("status") or "").lower() == "rescued":
            mistakes.append(f"Status conflict: {row.get('citizen_name')} — log says not rescued but status is rescued.")
    # Over-capacity vs SOS people
    if people_total > vacant and vacant >= 0 and shelters:
        mistakes.append(
            f"Capacity pressure: {people_total} people in SOS vs only {vacant} vacant shelter seats."
        )

    names_by_status: dict[str, list[str]] = {}
    for b in board:
        st = str(b.get("status") or "unknown").lower()
        names_by_status.setdefault(st, []).append(str(b.get("citizen_name") or "?"))

    return {
        "citizens": len(citizens),
        "people_total": people_total,
        "rescued": rescued,
        "missing": missing,
        "trapped": status_counts.get("trapped", 0),
        "contacted": contacted,
        "moving": moving,
        "pending": pending,
        "status_counts": status_counts,
        "names_by_status": names_by_status,
        "shelters": len(shelters),
        "shelter_capacity": capacity,
        "shelter_occupancy": occupancy,
        "vacant_seats": vacant,
        "full_shelters": full_shelters,
        "shelter_rows": shelters[:8],
        "mistakes": mistakes,
        "scenario": state.get("scenario"),
        "run_status": state.get("status"),
        "flood_probability": ((pipeline.get("prediction") or {}).get("flood_probability")),
    }


def _format_ops_brief(stats: dict[str, Any], focus: str = "all") -> str:
    lines: list[str] = []
    if focus in {"all", "status", "citizen", "citizens", "people", "sos"}:
        lines.append(
            f"Citizens (SOS): {stats['citizens']} · total people in those SOS: {stats['people_total']}."
        )
        lines.append(
            f"Status — rescued: {stats['rescued']}, missing/trapped: {stats['missing']}, "
            f"moving: {stats['moving']}, contacted: {stats['contacted']}."
        )
        for st, names in (stats.get("names_by_status") or {}).items():
            if names and st in {"rescued", "trapped", "missing", "moving", "contacted"}:
                sample = ", ".join(names[:5])
                more = f" (+{len(names) - 5} more)" if len(names) > 5 else ""
                lines.append(f"  · {st}: {sample}{more}")
    if focus in {"all", "shelter", "shelters", "vacant", "seat", "seats", "capacity"}:
        lines.append(
            f"Shelters: {stats['shelters']} · capacity {stats['shelter_capacity']} · "
            f"occupied {stats['shelter_occupancy']} · vacant seats {stats['vacant_seats']} · "
            f"full shelters {stats['full_shelters']}."
        )
        for s in stats.get("shelter_rows") or []:
            lines.append(
                f"  · {s.get('name') or s.get('shelter_id')}: "
                f"{s.get('occupancy')}/{s.get('capacity')} occupied, {s.get('seats_left')} vacant"
                + (" (FULL)" if s.get("full") else "")
            )
    if focus in {"all", "missing", "mistake", "mistakes", "wrong", "error", "false"}:
        if stats.get("mistakes"):
            lines.append("Mistakes / alerts:")
            for m in stats["mistakes"]:
                lines.append(f"  · {m}")
        else:
            lines.append("No status mistakes flagged right now (no false-alarm / capacity conflict).")
        if focus == "missing":
            names = (stats.get("names_by_status") or {}).get("trapped", []) + (
                stats.get("names_by_status") or {}
            ).get("missing", [])
            if names:
                lines.append(f"Missing/trapped names: {', '.join(names)}.")
            else:
                lines.append("No citizens currently marked missing/trapped.")
    if focus == "all":
        p = stats.get("flood_probability")
        if p is not None:
            lines.append(f"Current flood probability: {round(float(p) * 100, 1)}% · run status: {stats.get('run_status')}.")
    return "\n".join(lines)


def _normalize_q(q: str) -> str:
    q = (q or "").lower().strip()
    # common typos / shorthand
    repl = {
        "sheletr": "shelter",
        "sheltr": "shelter",
        "sheler": "shelter",
        "ishaving": " is having ",
        "havuing": "having",
        "vacney": "vacancy",
        "vacncy": "vacancy",
        "ambu": "ambulance",
        "ambulence": "ambulance",
        "citzen": "citizen",
        "cuctzen": "citizen",
        "resued": "rescued",
        "rescued": "rescued",
        "decliane": "declined",
        "declien": "declined",
    }
    for a, b in repl.items():
        q = q.replace(a, b)
    return " ".join(q.split())


def _has_any(q: str, words: tuple[str, ...]) -> bool:
    return any(w in q for w in words)


def answer_ask_agent(question: str, state: dict[str, Any]) -> dict[str, Any]:
    q = _normalize_q(question)
    stats = _ops_stats(state)
    citizens = sorted(state.get("citizens") or [], key=lambda c: c.get("rescue_order") or 99)
    dual = ((state.get("pipeline") or {}).get("prediction") or {}).get("dual") or {}
    first = citizens[0] if citizens else None

    # Merge rescue-desk live facts when available
    desk_bits = ""
    try:
        from backend.services.rescue_desk import desk

        rd = desk.state()
        stats["rescue_ambulances_free"] = rd.get("ambulances_free")
        stats["rescue_ambulances_total"] = rd.get("ambulances_total")
        stats["rescue_vacant"] = rd.get("vacant_total")
        stats["rescue_shelters"] = rd.get("shelters_total")
        declined = []
        accepted = []
        not_rescued = []
        for c in rd.get("cases") or []:
            for d in c.get("declined_by") or []:
                declined.append(f"{c.get('citizen_name')} ← {d.get('ambulance_id') or d.get('shelter') or 'unit'}")
            if c.get("accepted_ambulance"):
                accepted.append(f"{c.get('accepted_ambulance')} accepted {c.get('citizen_name')}")
            if c.get("rescued") is False or str(c.get("status") or "") not in {"rescued", "completed"}:
                if c.get("status") not in {None, "rescued"}:
                    not_rescued.append(f"{c.get('citizen_name')} ({c.get('status')})")
        stats["declined_list"] = declined
        stats["accepted_ambulances"] = accepted
        stats["not_rescued_list"] = [n for n in not_rescued if "rescued" not in n.lower()]
        desk_bits = (
            f"\nRescue desk: {rd.get('ambulances_free')}/{rd.get('ambulances_total')} ambulances free · "
            f"{rd.get('vacant_total')} shelter seats vacant · queue {rd.get('queue_len')}."
        )
    except Exception:  # noqa: BLE001
        pass

    if not q:
        return {
            "available": False,
            "answer": "Ask: How many shelters? Who declined? Which ambulance accepted? Who not rescued yet?",
            "stats": stats,
        }

    if _has_any(q, ("declined", "decline", "who declined", "rejected")):
        lines = stats.get("declined_list") or []
        ans = "Declines:\n" + ("\n".join(f"  · {x}" for x in lines) if lines else "  · Nobody declined yet.")
        return {"available": True, "answer": ans + desk_bits, "stats": stats}

    if _has_any(q, ("which ambulance", "ambulance accepted", "who accepted", "accepted ambulance")):
        lines = stats.get("accepted_ambulances") or []
        ans = "Ambulance accepts:\n" + ("\n".join(f"  · {x}" for x in lines) if lines else "  · No ambulance has accepted yet.")
        return {"available": True, "answer": ans + desk_bits, "stats": stats}

    if _has_any(q, ("not rescued", "who not rescued", "still missing", "not yet rescued")):
        names = stats.get("not_rescued_list") or []
        board_missing = (stats.get("names_by_status") or {}).get("trapped", []) + (
            stats.get("names_by_status") or {}
        ).get("missing", [])
        merged = list(dict.fromkeys(names + board_missing))
        ans = "Not rescued yet:\n" + ("\n".join(f"  · {x}" for x in merged) if merged else "  · All tracked citizens are rescued (or none in queue).")
        return {"available": True, "answer": ans + desk_bits, "stats": stats}

    if ("shelter" in q and _has_any(q, ("how many", "count", "having", "number", "vacant", "vacancy"))) or (
        "how many" in q and "shelter" in q
    ):
        return {
            "available": True,
            "answer": _format_ops_brief(stats, "shelters") + desk_bits,
            "stats": stats,
        }

    if any(w in q for w in ("how many citizen", "how many sos", "citizen count", "number of citizen", "people count")) or (
        "how many" in q and "citizen" in q
    ):
        return {
            "available": True,
            "answer": _format_ops_brief(stats, "citizens") + desk_bits,
            "stats": stats,
        }

    if any(w in q for w in ("vacant", "empty seat", "seats left", "capacity left", "available seat", "vacancy")):
        return {
            "available": True,
            "answer": _format_ops_brief(stats, "vacant") + desk_bits,
            "stats": stats,
        }

    if any(w in q for w in ("missing", "trapped", "still out")):
        return {
            "available": True,
            "answer": _format_ops_brief(stats, "missing") + desk_bits,
            "stats": stats,
        }

    if any(w in q for w in ("mistake", "wrong", "error", "false alarm", "conflict", "incorrect")):
        return {
            "available": True,
            "answer": _format_ops_brief(stats, "mistakes") + desk_bits,
            "stats": stats,
        }

    if "status" in q or "ops" in q or "brief" in q or "summary" in q:
        return {
            "available": True,
            "answer": _format_ops_brief(stats, "all") + desk_bits,
            "stats": stats,
        }

    if "first" in q or "priority" in q or ("who" in q and ("1" in q or "first" in q)):
        if first:
            return {
                "available": True,
                "answer": (
                    f"{first.get('citizen_name')} is Person 1 — age {first.get('age')}, "
                    f"{first.get('vulnerability') or 'standard'}, water {first.get('water_level_note')}.\n"
                    + _format_ops_brief(stats, "citizens")
                    + desk_bits
                ),
                "stats": stats,
            }
        return {"available": True, "answer": "No SOS queue loaded yet. Run a scenario first.", "stats": stats}

    if "disagree" in q or "xgboost" in q or "random forest" in q or ("model" in q and "agree" in q):
        return {
            "available": True,
            "answer": (dual.get("message") or f"RF={dual.get('random_forest')} XGB={dual.get('xgboost')}.") + desk_bits,
            "stats": stats,
        }

    if "eta" in q or "minute" in q:
        etas = state.get("eta_board") or []
        if etas:
            top = etas[0]
            return {
                "available": True,
                "answer": f"Nearest ETA: {top.get('citizen_name')} ~ {top.get('eta_min')} min.\n"
                + _format_ops_brief(stats, "citizens")
                + desk_bits,
                "stats": stats,
            }
        return {"available": True, "answer": "ETA board not ready yet." + desk_bits, "stats": stats}

    if "how many" in q or "count" in q or "sos" in q or "ambulance" in q:
        return {
            "available": True,
            "answer": _format_ops_brief(stats, "all") + desk_bits,
            "stats": stats,
        }

    return {
        "available": True,
        "answer": _format_ops_brief(stats, "all")
        + desk_bits
        + "\nTry: How many shelters? / Who declined? / Which ambulance accepted? / Who not rescued yet?",
        "stats": stats,
    }


DEFAULT_CHECKLIST = [
    {"id": "alert", "label": "Flood alert issued", "done": False},
    {"id": "boats", "label": "Boats / rescue sent", "done": False},
    {"id": "shelters", "label": "Shelters opened", "done": False},
    {"id": "medical", "label": "Ambulance on scene", "done": False},
    {"id": "allclear", "label": "All-clear confirmed", "done": False},
]
