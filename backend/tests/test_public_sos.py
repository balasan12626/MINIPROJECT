"""F4 — citizen SOS from a phone (public endpoint, photo checks, ticket status)."""
from io import BytesIO

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from backend.api import public_sos
from backend.main import app
from backend.rate_limit import limiter
from backend.simulation.engine import engine

LAT, LON = 28.651, 77.262  # inside the Delhi road network


@pytest.fixture(autouse=True)
def live_run(tmp_path, monkeypatch):
    limiter.reset()
    public_sos._sent.clear()
    monkeypatch.setattr(public_sos, "UPLOAD_ROOT", tmp_path / "sos")
    engine.__init__()
    engine.status = "running"
    engine.run_id = "SIM-TEST"
    yield
    engine.__init__()
    limiter.reset()


@pytest.fixture
def fast_add(monkeypatch):
    """Stand-in for add_citizen_sos that skips the pipeline / LLM chat but
    appends the row exactly as the engine would (ensure_ops at queued)."""
    from backend.services.person_ops import ensure_ops

    async def add(body, quick=False, ml=None):
        row = {"citizen_name": body["citizen_name"], "lat": body["lat"], "lon": body["lon"], "people": body["people"],
               **{k: body[k] for k in ("ticket", "photo_url", "source") if body.get(k) is not None}}
        ensure_ops(row, len(engine.contact_log) + 1)
        engine.contact_log.append(row)
        return {"added_citizen_name": row["citizen_name"]}

    monkeypatch.setattr(engine, "add_citizen_sos", add)


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _form(**over):
    base = {"name": "Meena Devi", "age": "67", "people": "3", "water": "waist-deep", "lat": str(LAT), "lon": str(LON)}
    base.update({k: str(v) for k, v in over.items()})
    return base


def _jpeg_with_exif() -> bytes:
    img = Image.new("RGB", (40, 30), (200, 10, 10))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    exif[0x0110] = "SecretPhone"  # Model
    buf = BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


@pytest.mark.asyncio
async def test_valid_sos_joins_the_live_run_at_queued():
    async with _client() as c:
        r = await c.post("/api/public/sos", data=_form())
        assert r.status_code == 200, r.text
        ticket = r.json()["ticket"]
        row = next(x for x in engine.contact_log if x.get("ticket") == ticket)
        # entered at queued, then the normal pipeline (it may already be dispatched)
        assert row["journey"][0]["event"] == "QUEUED" and row["timestamps"]["queued"]
        assert row["ops_status"] in ("queued", "assigned", "en_route")
        assert row["source"] == "citizen"
        status = (await c.get(f"/api/public/sos/{ticket}")).json()
        assert status["stage"] in ("queued", "assigned", "en_route")
        assert status["citizen_name"] == row["citizen_name"]


@pytest.mark.asyncio
async def test_outside_area_is_422_and_no_run_is_409(fast_add):
    async with _client() as c:
        assert (await c.post("/api/public/sos", data=_form(lat=19.07, lon=72.87))).status_code == 422
        engine.status = "idle"
        assert (await c.post("/api/public/sos", data=_form())).status_code == 409
    assert engine.contact_log == []


@pytest.mark.asyncio
async def test_non_image_photo_is_415_even_with_an_image_name(fast_add):
    async with _client() as c:
        files = {"photo": ("flood.jpg", b"%PDF-1.4 not really a photo", "image/jpeg")}
        r = await c.post("/api/public/sos", data=_form(), files=files)
    assert r.status_code == 415
    assert engine.contact_log == []


@pytest.mark.asyncio
async def test_photo_is_reencoded_without_exif(fast_add, tmp_path):
    async with _client() as c:
        r = await c.post("/api/public/sos", data=_form(), files={"photo": ("p.jpg", _jpeg_with_exif(), "image/jpeg")})
        assert r.status_code == 200, r.text
        ticket = r.json()["ticket"]
        assert r.json()["photo_saved"]
        saved = list((tmp_path / "sos").glob(f"*/{ticket}.jpg"))
        assert len(saved) == 1
        with Image.open(saved[0]) as img:
            assert not dict(img.getexif()), "EXIF must be stripped"
        photo = await c.get(f"/api/simulation/photo/{ticket}")
        assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_ticket_status_shows_only_that_person(fast_add):
    async with _client() as c:
        t1 = (await c.post("/api/public/sos", data=_form(name="Asha"))).json()["ticket"]
        await c.post("/api/public/sos", data=_form(name="Ravi"))
        body = (await c.get(f"/api/public/sos/{t1}")).json()
        assert body["citizen_name"] == "Asha"
        assert "Ravi" not in str(body)
        assert (await c.get("/api/public/sos/" + "0" * 32)).status_code == 404
        assert (await c.get("/api/public/sos/Asha")).status_code == 404


@pytest.mark.asyncio
async def test_rate_limit_returns_429(fast_add):
    async with _client() as c:
        codes = [(await c.post("/api/public/sos", data=_form(name=f"P{i}"))).status_code for i in range(6)]
    assert codes[:5] == [200] * 5
    assert codes[5] == 429


# ---------------------------------------------------------------- F15 /api/public/safety
@pytest.mark.asyncio
async def test_safety_outside_area_is_422():
    async with _client() as c:
        assert (await c.get("/api/public/safety", params={"lat": 19.07, "lon": 72.87})).status_code == 422


@pytest.mark.asyncio
async def test_safety_with_no_run_says_so_and_stores_nothing():
    engine.status = "idle"
    async with _client() as c:
        r = await c.get("/api/public/safety", params={"lat": LAT, "lon": LON})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live"] is False
    assert body["alert"]["tier"] is None and body["alert"]["flood_probability"] is None
    assert body["alert"]["advice"] == "No live flood operation right now."
    assert body["roads_near_you"] == []
    assert engine.contact_log == []


@pytest.mark.asyncio
async def test_safety_in_a_live_run_routes_to_an_open_shelter():
    async with _client() as c:
        r = await c.get("/api/public/safety", params={"lat": LAT, "lon": LON})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live"] is True
    s = body["shelter"]
    assert s and s["name"] and s["route_points"]
    if s["road_km"]:
        assert s["walk_min"] == round(float(s["road_km"]) / public_sos.WALK_KMH * 60, 0)
    assert engine.contact_log == [], "asking must not create an SOS"


@pytest.mark.asyncio
async def test_safety_lists_an_operator_closed_road_nearby():
    from backend.utils.geo import haversine_km

    near = [r for r in engine.roads_now() if r.get("lat") is not None
            and haversine_km(LAT, LON, float(r["lat"]), float(r["lon"])) <= public_sos.NEAR_ROAD_KM]
    if not near:
        pytest.skip("no mapped road within the 'near you' radius of the test point")
    engine.road_overrides[near[0]["road_id"]] = True
    async with _client() as c:
        body = (await c.get("/api/public/safety", params={"lat": LAT, "lon": LON})).json()
    closed = [x for x in body["roads_near_you"] if x["road_id"] == near[0]["road_id"]]
    assert closed and closed[0]["status"] == "closed"


@pytest.mark.asyncio
async def test_safety_rate_limit_returns_429():
    async with _client() as c:
        codes = [(await c.get("/api/public/safety", params={"lat": LAT, "lon": LON})).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30
    assert codes[30] == 429


@pytest.mark.asyncio
async def test_family_lookup_by_ticket_only_shows_where_the_person_is_safe(fast_add):
    """F31: once rescued, the ticket shows the shelter (or hospital) + pin; a name or partial ticket shows nothing."""
    async with _client() as c:
        t = (await c.post("/api/public/sos", data=_form(name="Asha"))).json()["ticket"]
        await c.post("/api/public/sos", data=_form(name="Ravi"))
        row = next(x for x in engine.contact_log if x.get("ticket") == t)
        row.update({"ops_status": "rescued", "shelter_name": "Talkatora Indoor Stadium", "shelter_lat": 28.62,
                    "shelter_lon": 77.19, "destination_kind": "shelter"})
        row["timestamps"]["rescued"] = row["timestamps"]["queued"]
        body = (await c.get(f"/api/public/sos/{t}")).json()
        assert body["stage"] == "rescued" and body["safe_at"]["name"] == "Talkatora Indoor Stadium"
        assert body["safe_at"]["lat"] == 28.62 and "Ravi" not in str(body)
        assert (await c.get("/api/public/sos/Asha")).status_code == 404
        assert (await c.get(f"/api/public/sos/{t[:16]}")).status_code == 404


@pytest.mark.asyncio
async def test_status_lookup_is_rate_limited(fast_add):
    async with _client() as c:
        t = (await c.post("/api/public/sos", data=_form(name="Asha"))).json()["ticket"]
        codes = [(await c.get(f"/api/public/sos/{t}")).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429
