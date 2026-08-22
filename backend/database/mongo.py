from datetime import datetime, timezone
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

from backend.config import get_settings

COLLECTIONS = [
    "weather_observations",
    "rainfall_observations",
    "water_levels",
    "dam_observations",
    "river_observations",
    "flood_predictions",
    "risk_events",
    "shelters",
    "roads",
    "routes",
    "agent_events",
    "optimization_runs",
    "benchmark_results",
    "simulation_runs",
    "simulation_events",
    "emergency_requests",
    "rescue_teams",
    "rescue_assignments",
    "system_metrics",
    "incidents",
    "audit_logs",
    "human_reviews",
    "pipeline_state",
]

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None
_mongo_ok = False
_mongo_error = "not initialized"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def connect() -> None:
    global _client, _db, _mongo_ok, _mongo_error
    settings = get_settings()
    try:
        _client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=2500)
        await _client.admin.command("ping")
        _db = _client[settings.database_name]
        await ensure_indexes(_db)
        _mongo_ok = True
        _mongo_error = ""
    except Exception as exc:  # noqa: BLE001
        _mongo_ok = False
        _mongo_error = str(exc)
        _db = None


async def disconnect() -> None:
    global _client, _db, _mongo_ok
    if _client is not None:
        _client.close()
    _client = None
    _db = None
    _mongo_ok = False


def mongo_status() -> dict[str, Any]:
    return {"connected": _mongo_ok, "error": _mongo_error or None}


def get_db() -> Optional[AsyncIOMotorDatabase]:
    return _db


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.weather_observations.create_index([("timestamp", DESCENDING)])
    await db.rainfall_observations.create_index([("timestamp", DESCENDING)])
    await db.water_levels.create_index([("timestamp", DESCENDING)])
    await db.dam_observations.create_index([("timestamp", DESCENDING)])
    await db.river_observations.create_index([("timestamp", DESCENDING)])
    await db.flood_predictions.create_index([("timestamp", DESCENDING)])
    await db.risk_events.create_index([("timestamp", DESCENDING)])
    await db.agent_events.create_index([("timestamp", DESCENDING)])
    await db.agent_events.create_index([("agent", ASCENDING), ("timestamp", DESCENDING)])
    await db.shelters.create_index([("shelter_id", ASCENDING)], unique=True)
    await db.roads.create_index([("road_id", ASCENDING)], unique=True)
    await db.routes.create_index([("created_at", DESCENDING)])
    await db.incidents.create_index([("incident_id", ASCENDING)], unique=True)
    await db.incidents.create_index([("status", ASCENDING), ("updated_at", DESCENDING)])
    await db.emergency_requests.create_index([("created_at", DESCENDING)])
    await db.rescue_teams.create_index([("team_id", ASCENDING)], unique=True)
    await db.simulation_runs.create_index([("run_id", ASCENDING)], unique=True)
    await db.simulation_events.create_index([("run_id", ASCENDING), ("sim_time_sec", ASCENDING)])
    await db.audit_logs.create_index([("timestamp", DESCENDING)])
    await db.human_reviews.create_index([("incident_id", ASCENDING), ("timestamp", DESCENDING)])
    await db.optimization_runs.create_index([("created_at", DESCENDING)])
    await db.benchmark_results.create_index([("created_at", DESCENDING)])
    await db.system_metrics.create_index([("timestamp", DESCENDING)])


async def insert(collection: str, doc: dict[str, Any]) -> Optional[str]:
    db = get_db()
    if db is None:
        return None
    now = utcnow()
    doc.setdefault("created_at", now)
    doc.setdefault("updated_at", now)
    if "timestamp" not in doc:
        doc["timestamp"] = now
    try:
        # Copy so Motor/PyMongo cannot leave a live ObjectId on shared in-memory docs
        payload = dict(doc)
        result = await db[collection].insert_one(payload)
        oid = str(result.inserted_id)
        doc["_id"] = oid
        return oid
    except PyMongoError:
        return None


async def upsert(collection: str, query: dict[str, Any], doc: dict[str, Any]) -> bool:
    db = get_db()
    if db is None:
        return False
    now = utcnow()
    doc["updated_at"] = now
    doc.setdefault("created_at", now)
    try:
        await db[collection].update_one(query, {"$set": doc}, upsert=True)
        return True
    except PyMongoError:
        return False


async def find_latest(collection: str, query: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    db = get_db()
    if db is None:
        return None
    try:
        doc = await db[collection].find_one(query or {}, sort=[("timestamp", DESCENDING)])
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except PyMongoError:
        return None


async def find_many(
    collection: str,
    query: Optional[dict[str, Any]] = None,
    limit: int = 50,
    sort_field: str = "timestamp",
    direction: int = DESCENDING,
) -> list[dict[str, Any]]:
    db = get_db()
    if db is None:
        return []
    try:
        cursor = db[collection].find(query or {}).sort(sort_field, direction).limit(limit)
        out = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            out.append(doc)
        return out
    except PyMongoError:
        return []


async def update_many(collection: str, query: dict[str, Any], doc: dict[str, Any]) -> int:
    db = get_db()
    if db is None:
        return 0
    try:
        result = await db[collection].update_many(query, {"$set": doc})
        return int(result.modified_count)
    except PyMongoError:
        return 0
