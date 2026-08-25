from contextlib import asynccontextmanager
import asyncio
import os
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.api import agents, emergency, health, hqrl, live, ml, response, rescue_desk, simulation, sources, voice_agent
from backend.config import get_settings
from backend.database import mongo
from backend.ml.inference import load_models
from backend.rate_limit import limiter
from backend.services.seed import seed_if_empty
from backend.websocket.hub import HEARTBEAT_SEC, hub


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
_docs = settings.api_docs_enabled
app = FastAPI(
    title="Voyamind AI — Flood Response API",
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_origins = settings.cors_list
if not _origins:
    _origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
# Never pair credentials with wildcard origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


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
