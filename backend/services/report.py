"""After-action PDF for a simulation run."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from fpdf import FPDF


def _yes_no(answered: Any) -> str:
    if answered in (True, "yes", "Yes", "true"):
        return "Yes"
    if answered in (False, "no", "No", "false"):
        return "No"
    return "not answered"


def build_report_pdf(state: dict[str, Any]) -> bytes:
    history = state.get("history") or []
    citizens = state.get("citizens") or []
    conversation = state.get("conversation") or {}
    clusters = (state.get("pipeline") or {}).get("clusters") or []
    after = state.get("after") or {}
    check = conversation.get("rescue_check") or {}
    peaks = [h.get("flood_probability") for h in history if h.get("flood_probability") is not None]
    peak_p = max(peaks) if peaks else after.get("flood_probability")
    minutes = None
    start = state.get("started_at")
    dispatched = check.get("dispatched_at")
    try:
        from datetime import datetime

        if start and dispatched:
            s = start if isinstance(start, datetime) else datetime.fromisoformat(str(start).replace("Z", "+00:00"))
            d = dispatched if isinstance(dispatched, datetime) else datetime.fromisoformat(str(dispatched).replace("Z", "+00:00"))
            minutes = round(max(0.0, (d - s).total_seconds()) / 60.0, 2)
    except Exception:  # noqa: BLE001
        minutes = None
    if minutes is None:
        auto_evt = next((e for e in (state.get("events") or []) if "sos" in str(e.get("message") or "").lower()), None)
        if auto_evt and auto_evt.get("sim_time_sec") is not None:
            minutes = round(float(auto_evt["sim_time_sec"]) / 60.0, 2)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "After-Action Report - Agentic Flood Response", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, f"Run: {state.get('run_id') or 'n/a'}  Scenario: {state.get('scenario') or 'n/a'}", ln=True)
    pdf.cell(0, 8, f"Peak flood probability: {round((peak_p or 0) * 100, 1)}%", ln=True)
    pdf.cell(0, 8, f"Minutes to dispatch: {minutes if minutes is not None else 'n/a'}", ln=True)
    pdf.cell(0, 8, f"SOS count: {len(citizens)}", ln=True)
    pdf.cell(0, 8, f"Rescue Yes/No: {_yes_no(check.get('answered'))}", ln=True)
    pdf.cell(0, 8, f"Started: {start}", ln=True)
    summary = state.get("after_action_summary") or []
    if summary:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Auto after-action summary", ln=True)
        pdf.set_font("Helvetica", size=9)
        for i, line in enumerate(summary[:5], start=1):
            pdf.multi_cell(0, 5, f"{i}. {line}")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Citizens (name, age, GPS, water depth)", ln=True)
    pdf.set_font("Helvetica", size=9)
    for c in citizens:
        line = (
            f"{c.get('citizen_name')}  age {c.get('age')}  "
            f"{c.get('lat')},{c.get('lon')}  water={c.get('water_level_note')}  people={c.get('people')}"
        )
        pdf.multi_cell(0, 5, line)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "K-means teams", ln=True)
    pdf.set_font("Helvetica", size=9)
    for cl in clusters:
        pdf.cell(0, 5, f"{cl.get('cluster_id')} n={cl.get('sos_count')} -> {cl.get('assigned_team')}", ln=True)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Agent radio (excerpt)", ln=True)
    pdf.set_font("Helvetica", size=9)
    radio = conversation.get("history") or conversation.get("turns") or []
    for turn in radio[:16]:
        pdf.multi_cell(0, 5, f"{turn.get('from')}: {turn.get('text')}")
    log = state.get("contact_log") or []
    if log:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Per-person contact log", ln=True)
        pdf.set_font("Helvetica", size=9)
        for row in log:
            pdf.multi_cell(
                0,
                5,
                f"P{row.get('person_index')} {row.get('citizen_name')} age {row.get('age')} "
                f"team={row.get('assigned_team')} status={row.get('status')} rescued={row.get('rescued')}",
            )
    # Messages appendix (WhatsApp / Telegram demo counts)
    counts = state.get("message_counts") or {}
    messages = state.get("messages") or []
    if not counts:
        try:
            from backend.services.rescue_desk import desk

            st = desk.state()
            counts = st.get("message_counts") or {}
            messages = st.get("messages") or []
        except Exception:  # noqa: BLE001
            counts, messages = {}, []
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Appendix — Messages sent (WhatsApp / Telegram)", ln=True)
    pdf.set_font("Helvetica", size=9)
    pdf.cell(
        0,
        5,
        f"WhatsApp: {counts.get('whatsapp', 0)}  |  Telegram: {counts.get('telegram', 0)}  |  "
        f"SMS: {counts.get('sms', 0)}  |  Web: {counts.get('web', 0)}",
        ln=True,
    )
    for m in messages[-20:]:
        pdf.multi_cell(
            0,
            5,
            f"[{m.get('channel')}] to {m.get('to')}: {m.get('text')}",
        )
    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    buf = BytesIO()
    buf.write(out.encode("latin-1") if isinstance(out, str) else out)
    return buf.getvalue()
