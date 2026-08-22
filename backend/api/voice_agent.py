from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services import voice_agent as va

router = APIRouter()


class VoiceContext(BaseModel):
    lat: float | None = None
    lon: float | None = None
    people: int | None = 2
    water_level_note: str | None = "knee-deep"
    age: int | None = None


class VoiceTurnBody(BaseModel):
    text: str = Field(..., min_length=1)
    history: list[dict] = Field(default_factory=list)
    context: VoiceContext | None = None


class VoiceStartBody(BaseModel):
    context: VoiceContext | None = None


@router.get("/api/voice-agent/status")
async def status():
    return va.voice_status()


@router.post("/api/voice-agent/start")
async def start(body: VoiceStartBody = VoiceStartBody()):
    ctx = body.context.model_dump(exclude_none=True) if body.context else {}
    return await va.opening_line(ctx)


@router.post("/api/voice-agent/turn")
async def turn(body: VoiceTurnBody):
    try:
        ctx = body.context.model_dump(exclude_none=True) if body.context else {}
        return await va.handle_turn(body.history or [], body.text.strip(), ctx)
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("voice_agent").exception("voice-agent turn failed")
        raise HTTPException(500, detail=str(exc)[:800]) from exc
