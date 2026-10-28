"""F4 — citizen SOS from a phone (public, no login).

    POST /api/public/sos            multipart form → {ticket, citizen_name}
    GET  /api/public/sos/{ticket}   → this person's status only
    GET  /api/simulation/photo/{ticket}   (operator) → the stored photo

The person joins the live run through engine.add_citizen_sos — the same path
as an operator-entered SOS — so ML, the agents, dispatch and shelters treat
them like everyone else. The ticket (random uuid4 hex) is the only key the
status endpoint accepts, so names are never enumerable.
"""


import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from pydantic import BaseModel, Field

from backend.deps.auth import RequireOperator
from backend.rate_limit import limiter
from backend.simulation.engine import engine

router = APIRouter()

UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads" / "sos"
MAX_PHOTO_BYTES = 3 * 1024 * 1024
MAX_PHOTO_SIDE = 1600
PER_IP_PER_RUN = 10
BBOX_MARGIN_DEG = 0.05
TICKET_RE = re.compile(r"^[0-9a-f]{32}$")

# (run_id, ip) -> SOS count this run
_sent: dict[tuple[str | None, str], int] = {}

STAGE_TEXT = {
    "queued": "Waiting — your SOS is in the rescue queue",
    "assigned": "A rescue unit has been assigned to you",
    "en_route": "A rescue unit is on the way",
    "to_shelter": "Picked up — going to the shelter",
    "rescued": "Safe at the shelter",
    "merged": "Your SOS was joined with another report of the same people — help is coming for both",
}


def _silent(lat: float, lon: float) -> bool:
    from backend.services.towers import is_silent

    return is_silent(lat, lon, engine.silent_view)


def device_key(run_id: str | None, ip: str) -> str:
    """F30: a per-run hash of the caller's address, used only to suggest that two
    SOS came from the same phone. The address itself is never stored."""
    import hashlib

    return hashlib.sha256(f"{run_id}:{ip}".encode()).hexdigest()[:16]


def bbox() -> tuple[float, float, float, float]:
    """(lat_min, lat_max, lon_min, lon_max) of the simulated road network + margin."""
    from backend.services.seed import GRAPH_NODES

    lats = [p[0] for p in GRAPH_NODES.values()]
    lons = [p[1] for p in GRAPH_NODES.values()]
    m = BBOX_MARGIN_DEG
    return min(lats) - m, max(lats) + m, min(lons) - m, max(lons) + m


def _image_kind(data: bytes) -> str | None:
    """Real type from the magic bytes — the file name / content-type are not trusted."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _store_photo(data: bytes, run_id: str | None, ticket: str) -> str:
    """Re-encode to JPEG (drops EXIF incl. GPS / device tags), max 1600 px."""
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse decompression bombs
    try:
        with Image.open(BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)  # keep the visible orientation
            img = img.convert("RGB")
            img.thumbnail((MAX_PHOTO_SIDE, MAX_PHOTO_SIDE))
            folder = UPLOAD_ROOT / re.sub(r"[^A-Za-z0-9_-]", "_", str(run_id or "norun"))
            folder.mkdir(parents=True, exist_ok=True)
            img.save(folder / f"{ticket}.jpg", "JPEG", quality=85)  # no exif= → none written
    except Exception as exc:  # noqa: BLE001 — truncated / hostile image
        raise HTTPException(415, "photo could not be read as an image") from exc
    return f"/api/simulation/photo/{ticket}"


def _find(ticket: str) -> dict | None:
    for row in engine.contact_log:
        if row.get("ticket") == ticket:
            return row
    return None


@router.post("/api/public/sos")
@limiter.limit("5/minute")
async def public_sos(
    request: Request,
    name: str = Form(..., min_length=1, max_length=60),
    age: Optional[int] = Form(None, ge=0, le=120),
    people: int = Form(1, ge=1, le=50),
    water: str = Form("flood water", max_length=40),
    lat: float = Form(...),
    lon: float = Form(...),
    accuracy_m: Optional[float] = Form(None, ge=0, le=100000),
    medical: str = Form("none", pattern="^(none|injured|critical)$"),
    photo: Optional[UploadFile] = File(None),
):
    if engine.status != "running" or not engine.run_id:
        raise HTTPException(409, "No live operation right now - call the emergency number instead")
    lat_min, lat_max, lon_min, lon_max = bbox()
    if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
        raise HTTPException(422, "Location is outside the area this service covers")
    ip = request.client.host if request.client else "unknown"
    key = (engine.run_id, ip)
    if _sent.get(key, 0) >= PER_IP_PER_RUN:
        raise HTTPException(429, "Too many SOS from this device for this operation")

    ticket = uuid.uuid4().hex
    photo_url = None
    if photo is not None and (photo.filename or photo.size):
        data = await photo.read(MAX_PHOTO_BYTES + 1)
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(413, "Photo larger than 3 MB")
        if data:
            if _image_kind(data) is None:
                raise HTTPException(415, "Photo must be a JPEG, PNG or WebP image")
            photo_url = _store_photo(data, engine.run_id, ticket)

    _sent[key] = _sent.get(key, 0) + 1
    st = await engine.add_citizen_sos(
        {
            "citizen_name": name.strip(),
            "age": age,
            "people": people,
            "water_level_note": water.strip() or "flood water",
            "lat": lat,
            "lon": lon,
            "accuracy_m": accuracy_m,
            "mode": "citizen",
            "source": "citizen",
            "ticket": ticket,
            "photo_url": photo_url,
            "device_key": device_key(engine.run_id, ip),
            "medical": medical,
            "medical_source": "caller (public /sos form)",
        },
        quick=False,
    )
    row = _find(ticket) or {}
    return {
        "ticket": ticket,
        "citizen_name": row.get("citizen_name") or (st or {}).get("added_citizen_name"),
        "run_id": engine.run_id,
        "photo_saved": bool(photo_url),
    }


class SmsTextBody(BaseModel):
    text: str = Field(min_length=6, max_length=320)


@router.post("/api/public/sos/sms-text")
@limiter.limit("60/minute")
async def sos_from_sms_text(request: Request, body: SmsTextBody, _user: RequireOperator):
    """F24 (operator only): the control room pastes a received SOS text (no SMS
    gateway exists); it is parsed and joins the run at `queued` like any SOS."""
    from backend.services.sms_parse import SmsParseError, parse

    if engine.status != "running" or not engine.run_id:
        raise HTTPException(409, "No live operation right now")
    try:
        sos = parse(body.text)
    except SmsParseError as e:
        raise HTTPException(422, str(e)) from None
    lat_min, lat_max, lon_min, lon_max = bbox()
    if not (lat_min <= sos["lat"] <= lat_max and lon_min <= sos["lon"] <= lon_max):
        raise HTTPException(422, "Location is outside the area this service covers")
    st = await engine.add_citizen_sos({**sos, "mode": "citizen", "source": "sms (entered by the control room)",
                                       "medical_source": "caller (SMS)"}, quick=True)
    return {"parsed": sos, "citizen_name": (st or {}).get("added_citizen_name") or sos["citizen_name"]}


@router.get("/api/public/sos/{ticket}")
@limiter.limit("30/minute")  # F31: the family lookup page uses this too — no ticket guessing
async def public_sos_status(request: Request, ticket: str):
    if not TICKET_RE.match(ticket):
        raise HTTPException(404, "unknown ticket")
    if engine.contact_log:
        from backend.services.person_ops import advance_all

        advance_all(engine.contact_log, engine.ops_ctx())
    row = _find(ticket)
    if row is None:
        raise HTTPException(404, "unknown ticket (or the operation has ended)")
    st = row.get("ops_status") or "queued"
    eta = row.get("eta_min") if st in ("assigned", "en_route") else row.get("eta_to_shelter_min") if st == "to_shelter" else None
    # Only this person's own status — no other caller's data.
    return {
        "stage": st,
        "stage_text": STAGE_TEXT.get(st, st),
        "citizen_name": row.get("citizen_name"),
        "unit": row.get("unit_name") if st != "queued" else None,
        "unit_role": row.get("unit_role") if st != "queued" else None,
        "shelter": row.get("shelter_name") if st != "queued" else None,
        "eta_min": eta,
        "waiting_reason": row.get("ops_wait_reason") if st == "queued" else None,
        "updated_at": row.get("ops_stage_at"),
        # F31: once safe, where (shelter or hospital) — for whoever holds the ticket, nothing else.
        "safe_at": (
            {"name": row.get("shelter_name"), "lat": row.get("shelter_lat"), "lon": row.get("shelter_lon"),
             "kind": row.get("destination_kind") or "shelter",
             "since": (row.get("timestamps") or {}).get("rescued")}
            if st == "rescued" else None
        ),
    }


WALK_KMH = 4.5  # walking speed for the "on foot" estimate (stated on the page)
NEAR_ROAD_KM = 2.0


@router.get("/api/public/safety")
@limiter.limit("30/minute")
async def public_safety(request: Request, lat: float, lon: float):
    """F15 — "Am I safe?" for one location, from the live operation's state:
    alert level + probability, the nearest OPEN shelter with seats that an
    open road reaches (road route + time by vehicle and on foot), closed /
    soon-closing roads nearby, and the river gauge if the city has one.
    Nothing here is stored about the caller."""
    from backend.geo.cities import active
    from backend.services import person_ops as po
    from backend.utils.geo import haversine_km

    lat_min, lat_max, lon_min, lon_max = bbox()
    if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
        raise HTTPException(422, "Location is outside the area this service covers")
    city = active()
    live = engine.status == "running" and bool(engine.run_id)
    cur = engine.current_view() if live else {}
    tier = (engine.mas.tier if live else None) or None
    ctx = engine.ops_ctx() if live else {"roads": None, "shelter_overrides": {}, "closing": None}
    me = {"lat": lat, "lon": lon, "people": 1}
    shelter, route = po._reachable_shelter(
        me, engine.contact_log if live else [], (lat, lon), ctx.get("roads"), ctx.get("shelter_overrides"),
        closing=ctx.get("closing") or None,
    )
    roads = engine.roads_now() if live else []
    forecast = engine.road_forecast() if live else {}
    near = []
    for r in roads:
        if r.get("lat") is None:
            continue
        d = haversine_km(lat, lon, float(r["lat"]), float(r["lon"]))
        if d > NEAR_ROAD_KM:
            continue
        if r.get("blocked"):
            near.append({"road_id": r["road_id"], "name": r.get("name"), "km": round(d, 2), "status": "closed"})
        elif r["road_id"] in forecast:
            near.append({"road_id": r["road_id"], "name": r.get("name"), "km": round(d, 2),
                         "status": f"forecast to flood in ~{forecast[r['road_id']]['closes_in_sim_min']} min"})
    near.sort(key=lambda x: (x["status"] != "closed", x["km"]))
    gauge = city.get("gauge") or {}
    last = engine.history[-1] if live and engine.history else {}
    p = cur.get("flood_probability")
    out = {
        "live": live,
        "city": {"id": city["id"], "name": city["name"], "flood_driver": "river" if gauge.get("available") else "rainfall"},
        "alert": {
            "tier": tier,
            "flood_probability": p,
            "advice": (
                "No live flood operation right now." if not live
                else "Move to the shelter below now if water is rising around you." if (p or 0) >= 0.75
                else "Be ready to move; keep your phone charged." if (p or 0) >= 0.5
                else "No evacuation order for this area right now."
            ),
        },
        "shelter": None,
        "hospital": None,
        # F29: the caller's spot is in a modelled silent area (towers flooded).
        "signal_warning": (
            "Your area may have no phone signal (modelled: the flood reached the towers). Your SOS will wait on your "
            "phone and send when the signal is back."
            if live and _silent(lat, lon) else None
        ),
        "roads_near_you": near[:8],
        "river": (
            {"station": gauge.get("station"), "river": gauge.get("river"), "level_m": last.get("river_m"),
             "danger_level_m": gauge.get("danger_level_m"), "warning_level_m": gauge.get("warning_level_m")}
            if gauge.get("available") else None
        ),
        "notes": [
            "Shelter seats and roads are the live operation's own state.",
            f"On-foot time assumes {WALK_KMH:g} km/h along the road route; vehicle time is the planner's road time.",
        ],
    }
    # F21: nearest OSM hospital with an open road (beds unknown unless OSM tags them).
    hosp, hroute, _ = po._reachable_hospital((lat, lon), ctx.get("roads"), closing=ctx.get("closing") or None)
    if hosp:
        out["hospital"] = {"name": hosp["name"], "lat": hosp["lat"], "lon": hosp["lon"], "km": hroute.get("km"),
                           "minutes_by_vehicle": hroute.get("sim_minutes"), "beds": hosp.get("beds"),
                           "source": "OpenStreetMap"}
    if shelter:
        km = float(route.get("km") or 0)
        out["shelter"] = {
            "name": shelter["name"],
            "lat": shelter["lat"],
            "lon": shelter["lon"],
            "seats_left": shelter.get("seats_left_before"),
            "capacity_source": shelter.get("capacity_source"),
            "route_points": route.get("points"),
            "road_km": route.get("km"),
            "vehicle_min": route.get("sim_minutes"),
            "walk_min": round(km / WALK_KMH * 60, 0) if km else None,
            "no_open_road": bool(route.get("no_open_road")),
            "flood_forecast": route.get("flood_forecast"),
        }
    return out


@router.get("/api/simulation/photo/{ticket}")
async def sos_photo(ticket: str, _user: RequireOperator):
    if not TICKET_RE.match(ticket):
        raise HTTPException(404, "unknown photo")
    hits = list(UPLOAD_ROOT.glob(f"*/{ticket}.jpg"))
    if not hits:
        raise HTTPException(404, "unknown photo")
    return FileResponse(hits[0], media_type="image/jpeg")
