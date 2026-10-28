"""After-action PDF for a simulation run."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from fpdf import FPDF, XPos, YPos


def _yes_no(answered: Any) -> str:
    if answered in (True, "yes", "Yes", "true"):
        return "Yes"
    if answered in (False, "no", "No", "false"):
        return "No"
    return "not answered"


def _safe_pdf_text(value: Any, max_chunk_chars: int = 40) -> str:
    if value is None:
        return ""
    text = str(value)
    replacements = {
        "—": "-",
        "–": "-",
        "·": " - ",
        "•": " - ",
        "“": '"',
        "”": '"',
        "’": "'",
        "‘": "'",
        "…": "...",
        "\u00a0": " ",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = text.encode("latin-1", "replace").decode("latin-1")
    parts: list[str] = []
    for word in text.split():
        if len(word) <= max_chunk_chars:
            parts.append(word)
            continue
        for idx in range(0, len(word), max_chunk_chars):
            parts.append(word[idx : idx + max_chunk_chars])
    return " ".join(parts)


def _pct(p: Any) -> str:
    # A missing probability is "n/a", never a fabricated 0%.
    return "n/a" if p is None else f"{round(float(p) * 100, 1)}%"


def _ist(value: Any) -> str:
    """Timestamps in the report are shown in IST, like the UI."""
    from datetime import datetime, timedelta, timezone

    if not value:
        return "n/a"
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y, %H:%M:%S IST")


def build_report_pdf(state: dict[str, Any]) -> bytes:
    history = state.get("history") or []
    citizens = state.get("citizens") or []
    conversation = state.get("conversation") or {}
    clusters = (state.get("pipeline") or {}).get("clusters") or []
    after = state.get("after") or {}
    check = conversation.get("rescue_check") or {}
    # Canonical values come from the engine's `current` block (SimulationEngine.current_view);
    # the history scan is only a fallback for states saved before it existed.
    current = state.get("current") or {}
    peaks = [h.get("flood_probability") for h in history if h.get("flood_probability") is not None]
    peak_p = current.get("peak_flood_probability")
    if peak_p is None:
        peak_p = max(peaks) if peaks else after.get("flood_probability")
    final_p = current.get("flood_probability")
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
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def _mc(text: str) -> None:
        # fpdf2's multi_cell defaults to new_x=RIGHT, which drifts the cursor
        # toward the page edge across successive calls until width hits 0.
        pdf.multi_cell(0, 5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _safe_pdf_text("After-Action Report - Agentic Flood Response"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, _safe_pdf_text(f"Run: {state.get('run_id') or 'n/a'}  Scenario: {state.get('scenario') or 'n/a'}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 8, _safe_pdf_text(f"Peak flood probability: {_pct(peak_p)}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 8, _safe_pdf_text(f"Final flood probability: {_pct(final_p)}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 8, _safe_pdf_text(f"Minutes to dispatch: {minutes if minutes is not None else 'n/a'}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 8, _safe_pdf_text(f"SOS count: {len(citizens)}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 8, _safe_pdf_text(f"Rescue Yes/No: {_yes_no(check.get('answered'))}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 8, _safe_pdf_text(f"Started: {_ist(start)}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    summary = state.get("after_action_summary") or []
    if summary:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, _safe_pdf_text("Auto after-action summary"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", size=9)
        for i, line in enumerate(summary[:5], start=1):
            _mc(_safe_pdf_text(f"{i}. {line}"))
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _safe_pdf_text("Citizens (name, age, GPS, water depth)"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=9)
    for c in citizens:
        line = (
            f"{c.get('citizen_name')}  age {c.get('age')}  "
            f"{c.get('lat')},{c.get('lon')}  water={c.get('water_level_note')}  people={c.get('people')}"
        )
        _mc(_safe_pdf_text(line))
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _safe_pdf_text("K-means teams"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=9)
    for cl in clusters:
        pdf.cell(0, 5, _safe_pdf_text(f"{cl.get('cluster_id')} n={cl.get('sos_count')} -> {cl.get('assigned_team')}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _safe_pdf_text("Agent radio (excerpt)"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=9)
    radio = conversation.get("history") or conversation.get("turns") or []
    for turn in radio[:16]:
        _mc(_safe_pdf_text(f"{turn.get('from')}: {turn.get('text')}"))
    log = state.get("contact_log") or []
    if log:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, _safe_pdf_text("Per-person contact log"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", size=9)
        for row in log:
            ts = row.get("timestamps") or {}

            def _t(key: str, ts: dict = ts) -> str:
                v = _ist(ts.get(key)) if ts.get(key) else "-"
                return v.split(", ")[-1] if v != "-" else v

            _mc(
                _safe_pdf_text(
                    f"P{row.get('person_index')} {row.get('citizen_name')} age {row.get('age')} "
                    f"people={row.get('people')} status={row.get('ops_status') or row.get('status')} "
                    f"unit={row.get('unit_name') or row.get('assigned_team')} shelter={row.get('shelter_name') or '-'}"
                )
            )
            _mc(
                _safe_pdf_text(
                    f"    SOS {_t('queued')} | allocated {_t('assigned')} | accepted {_t('accepted')} | "
                    f"picked up {_t('to_shelter')} | at shelter {_t('rescued')}"
                )
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
    pdf.cell(0, 8, _safe_pdf_text("Appendix - Messages sent (WhatsApp / Telegram)"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=9)
    pdf.cell(
        0,
        5,
        _safe_pdf_text(
            f"WhatsApp: {counts.get('whatsapp', 0)}  |  Telegram: {counts.get('telegram', 0)}  |  "
            f"SMS: {counts.get('sms', 0)}  |  Web: {counts.get('web', 0)}"
        ),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    for m in messages[-20:]:
        _mc(_safe_pdf_text(f"[{m.get('channel')}] to {m.get('to')}: {m.get('text')}"))
    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    buf = BytesIO()
    buf.write(out.encode("latin-1") if isinstance(out, str) else out)
    return buf.getvalue()
