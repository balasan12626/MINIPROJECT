"""F24 — SMS fallback: the text the phone page builds round-trips through the parser."""
import pytest

from backend.services.sms_parse import SmsParseError, parse

# Exactly what frontend/src/i18n/phonePages.js smsText() builds (asserted in phonePages.test.js).
EXAMPLE = "SOS 28.65100,77.26200 P3 WCHEST MCRITICAL Meena Devi"


def test_example_round_trips():
    assert parse(EXAMPLE) == {"citizen_name": "Meena Devi", "lat": 28.651, "lon": 77.262, "people": 3,
                              "water_level_note": "chest-deep", "medical": "critical"}


def test_without_medical_and_lowercase():
    p = parse("sos 25.6,85.1 p1 wrising ravi")
    assert p["medical"] == "none" and p["water_level_note"] == "water rising fast" and p["citizen_name"] == "ravi"


@pytest.mark.parametrize("bad", ["hello", "SOS 28.6 P3 WKNEE x", "SOS 28.6,77.2 P0 WKNEE x", "SOS 28.6,77.2 P3 WDEEP x",
                                 "SOS 28.6,77.2 P3 WKNEE MFOO x", "SOS 128.6,77.2 P3 WKNEE x"])
def test_bad_texts_are_refused(bad):
    with pytest.raises(SmsParseError):
        parse(bad)


@pytest.mark.asyncio
async def test_operator_endpoint_adds_the_sos(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.rate_limit import limiter
    from backend.simulation.engine import engine

    limiter.reset()
    added = {}

    async def add(body, quick=False, ml=None):
        added.update(body)
        return {"added_citizen_name": body["citizen_name"]}

    engine.__init__()
    engine.status, engine.run_id = "running", "SIM-SMS"
    monkeypatch.setattr(engine, "add_citizen_sos", add)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/public/sos/sms-text", json={"text": EXAMPLE})
            assert r.status_code == 200, r.text
            assert added["source"].startswith("sms") and added["medical"] == "critical"
            assert (await c.post("/api/public/sos/sms-text", json={"text": "not an sos"})).status_code == 422
    finally:
        engine.__init__()
