from fastapi import APIRouter

from backend.database import mongo
from backend.ml.inference import model_status
from backend.utils.geo import utcnow
from backend.websocket.hub import hub

router = APIRouter()


@router.get("/api/health")
async def health():
    mongo_st = mongo.mongo_status()
    models = model_status()
    return {
        "status": "ok" if models.get("available") else "degraded",
        "backend": "connected",
        "mongodb": "connected" if mongo_st.get("connected") else f"unavailable: {mongo_st.get('error')}",
        "models": "available" if models.get("available") else models.get("message") or "MODEL UNAVAILABLE",
        "websocket_clients": hub.connected_count,
        "timestamp": utcnow(),
    }
