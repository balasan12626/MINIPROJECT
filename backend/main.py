from contextlib import asynccontextmanager
import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.api import agents, emergency, health, hqrl, live, ml, response, rescue_desk, simulation, sources, voice_agent
from backend.config import get_settings
from backend.database import mongo
from backend.ml.inference import load_models
from backend.services.seed import seed_if_empty
from backend.websocket.hub import HEARTBEAT_SEC, hub

limiter = Limiter(key_func=get_remote_address)


async def _live_ticker():
    from backend.services.pipeline import run_pipeline

    await asyncio.sleep(2)
    while True:
        try:
            await run_pipeline("live")
        except Exception:
            pass
        await asyncio.sleep(90)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mongo.connect()
    load_models()
    await seed_if_empty()
    ticker = None
    if os.environ.get("FLOOD_LIVE_TICKER", "1") != "0":
        ticker = asyncio.create_task(_live_ticker())
    yield
    if ticker:
        ticker.cancel()
    await mongo.disconnect()


settings = get_settings()
app = FastAPI(
    title="Agentic Real-Time Flood Response",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (health, live, ml, agents, response, simulation, hqrl, emergency, sources, rescue_desk, voice_agent):
    app.include_router(module.router)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        await ws.send_json({"type": "hello", "payload": {"status": "connected"}, "timestamp": None})
        import asyncio
        from datetime import datetime, timezone

        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=HEARTBEAT_SEC)
                if data == "ping":
                    await ws.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
            except asyncio.TimeoutError:
                await ws.send_json({"type": "heartbeat", "timestamp": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        await hub.disconnect(ws)
    except Exception:  # noqa: BLE001
        await hub.disconnect(ws)


def run() -> None:
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    run()
