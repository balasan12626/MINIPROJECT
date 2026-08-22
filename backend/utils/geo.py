from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_object_id(value: Any) -> bool:
    try:
        mod = value.__class__.__module__ or ""
    except Exception:  # noqa: BLE001
        return False
    name = type(value).__name__
    return name == "ObjectId" or mod == "bson" or mod.startswith("bson.")


def jsonable(doc: Any) -> Any:
    if doc is None or isinstance(doc, (str, int, float, bool)):
        return doc
    if _is_object_id(doc):
        return str(doc)
    if isinstance(doc, datetime):
        if doc.tzinfo is None:
            doc = doc.replace(tzinfo=timezone.utc)
        return doc.astimezone(timezone.utc).isoformat()
    if isinstance(doc, dict):
        return {str(k): jsonable(v) for k, v in doc.items()}
    if isinstance(doc, (list, tuple, set)):
        return [jsonable(v) for v in doc]
    if isinstance(doc, bytes):
        return doc.decode("utf-8", errors="replace")
    if hasattr(doc, "isoformat"):
        try:
            return doc.isoformat()
        except Exception:  # noqa: BLE001
            pass
    try:
        return str(doc)
    except Exception:  # noqa: BLE001
        return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def risk_category(probability: float | None) -> str | None:
    if probability is None:
        return None
    if probability >= 0.70:
        return "CRITICAL"
    if probability >= 0.50:
        return "HIGH"
    if probability >= 0.35:
        return "MODERATE"
    return "LOW"
