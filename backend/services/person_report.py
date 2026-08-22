"""Per-person rescue journey PDF — SOS → ambulance → shelter, full detail."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from fpdf import FPDF


def _s(val: Any, fallback: str = "-") -> str:
    if val is None or val == "":
        return fallback
    text = str(val)
    for a, b in (("\u2014", "-"), ("\u2013", "-"), ("\u2192", "->"), ("\u00b7", "|"), ("\u2022", "*")):
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


def _pct(p: Any) -> str:
    if p is None:
        return "-"
    try:
        return f"{round(float(p) * 100, 1)}%"
    except (TypeError, ValueError):
        return str(p)


class PersonPDF(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Agentic Flood Response - page {self.page_no()}", align="C")


def _section(pdf: FPDF, title: str, fill=(0, 120, 140)) -> None:
    pdf.ln(3)
    pdf.set_fill_color(*fill)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, _s(title), ln=True, fill=True)
    pdf.set_text_color(30, 30, 30)


def _kv_table(pdf: FPDF, rows: list[tuple[str, str]]) -> None:
    label_w, value_w = 58, 132
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(220, 242, 248)
    pdf.cell(label_w, 7, "Field", border=1, fill=True)
    pdf.cell(value_w, 7, "Value", border=1, ln=True, fill=True)
    pdf.set_font("Helvetica", size=9)
    for i, (k, v) in enumerate(rows):
        if i % 2:
            pdf.set_fill_color(245, 250, 252)
        else:
            pdf.set_fill_color(255, 255, 255)
        pdf.cell(label_w, 7, _s(k)[:40], border=1, fill=True)
        pdf.cell(value_w, 7, _s(v)[:78], border=1, ln=True, fill=True)


def build_person_pdf(report: dict[str, Any]) -> bytes:
    case = report.get("case") or {}
    env = report.get("environment") or {}
    name = _s(case.get("citizen_name") or "Citizen")
    status = _s(case.get("status") or "in progress")

    pdf = PersonPDF()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    # Header banner
    pdf.set_fill_color(8, 36, 52)
    pdf.rect(0, 0, 210, 32, "F")
    pdf.set_xy(10, 7)
    pdf.set_text_color(122, 237, 255)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, "PERSON RESCUE REPORT", ln=True)
    pdf.set_font("Helvetica", size=10)
    pdf.set_x(10)
    pdf.set_text_color(200, 230, 240)
    pdf.cell(0, 6, f"{name}  |  status: {status}  |  SOS to shelter journey", ln=True)

    pdf.set_y(38)
    pdf.set_text_color(20, 20, 20)

    _section(pdf, "1. Citizen identity")
    _kv_table(
        pdf,
        [
            ("Name", name),
            ("Case / ID", _s(case.get("case_id"))),
            ("Age", _s(case.get("age"))),
            ("People in SOS", _s(case.get("people"))),
            ("Water depth", _s(case.get("water_level_note"))),
            ("Priority / triage", _s(case.get("vulnerability") or case.get("triage"))),
            ("GPS latitude", _s(case.get("lat"))),
            ("GPS longitude", _s(case.get("lon"))),
            ("Current status", status),
            ("Rescued", "YES" if case.get("rescued") in (True, "yes") else ("NO" if case.get("rescued") in (False, "no") else "in progress")),
        ],
    )

    _section(pdf, "2. Live environment (rainfall / river / dam)", fill=(20, 90, 110))
    _kv_table(
        pdf,
        [
            ("Scenario", _s(env.get("scenario") or case.get("scenario"))),
            ("Run ID", _s(env.get("run_id"))),
            ("Current rainfall", _s(env.get("rainfall_mm"), "-") + (" mm" if env.get("rainfall_mm") is not None else "")),
            ("River water level", _s(env.get("river_m"), "-") + (" m" if env.get("river_m") is not None else "")),
            ("Dam / barrage level", _s(env.get("dam_m"), "-") + (" m" if env.get("dam_m") is not None else "")),
            ("Flood probability (ML)", _pct(case.get("flood_probability") if case.get("flood_probability") is not None else env.get("flood_probability"))),
            ("Risk category", _s(env.get("risk_category"))),
            ("ML model", _s(case.get("model_id") or env.get("model_id"))),
            ("Random Forest", _pct(env.get("rf"))),
            ("XGBoost", _pct(env.get("xgb"))),
        ],
    )

    _section(pdf, "3. Assignment - ambulance, shelter, K-means", fill=(40, 100, 70))
    _kv_table(
        pdf,
        [
            ("K-means cluster", _s(case.get("cluster_id"))),
            ("Assigned rescue team", _s(case.get("assigned_team"))),
            ("Ambulance", _s(case.get("ambulance_name") or case.get("ambulance_id") or "not assigned yet")),
            ("Shelter", _s(case.get("shelter_name") or case.get("shelter_id") or "not assigned yet")),
            ("Ambulances free (system)", _s(report.get("ambulances_free"))),
            ("Shelter vacant seats", _s(report.get("vacant_total"))),
        ],
    )

    _section(pdf, "4. Timeline - SOS to shelter (agent logs)", fill=(120, 70, 40))
    journey = case.get("journey") or []
    if not journey:
        pdf.set_font("Helvetica", size=9)
        pdf.multi_cell(0, 5, "No journey steps logged yet. Status will advance: queued -> assigned -> en_route -> to_shelter -> rescued.")
    else:
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(255, 236, 210)
        tw, aw, ew, dw = 22, 40, 30, 98
        pdf.cell(tw, 6, "Time", border=1, fill=True)
        pdf.cell(aw, 6, "Agent", border=1, fill=True)
        pdf.cell(ew, 6, "Event", border=1, fill=True)
        pdf.cell(dw, 6, "Detail", border=1, ln=True, fill=True)
        pdf.set_font("Helvetica", size=8)
        for i, step in enumerate(journey):
            if i % 2:
                pdf.set_fill_color(255, 250, 240)
            else:
                pdf.set_fill_color(255, 255, 255)
            t = str(step.get("at") or "")
            t = t[11:19] if "T" in t else t[:8]
            pdf.cell(tw, 6, _s(t), border=1, fill=True)
            pdf.cell(aw, 6, _s(step.get("agent"))[:24], border=1, fill=True)
            pdf.cell(ew, 6, _s(step.get("event"))[:16], border=1, fill=True)
            pdf.cell(dw, 6, _s(step.get("detail"))[:70], border=1, ln=True, fill=True)

    ts = case.get("timestamps") or {}
    if ts:
        _section(pdf, "5. Stage timestamps", fill=(60, 60, 90))
        _kv_table(pdf, [(str(k), str(v)) for k, v in ts.items()])

    counts = report.get("message_counts") or {}
    _section(pdf, "6. Messages sent (WhatsApp / Telegram)", fill=(70, 50, 90))
    _kv_table(
        pdf,
        [
            ("WhatsApp", str(counts.get("whatsapp", 0))),
            ("Telegram", str(counts.get("telegram", 0))),
            ("SMS", str(counts.get("sms", 0))),
            ("Web", str(counts.get("web", 0))),
        ],
    )

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(
        0,
        4,
        "This report is for one citizen only: SOS alert through ambulance pickup to shelter admission, "
        "with ML flood context and agent activity for that person.",
    )

    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    buf = BytesIO()
    buf.write(out.encode("latin-1") if isinstance(out, str) else out)
    return buf.getvalue()
