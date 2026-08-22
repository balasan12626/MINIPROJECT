from typing import Any

from backend.utils.geo import jsonable
from backend.websocket.hub import hub

_last: dict[str, dict[str, Any]] = {}


def last_progress(mode: str = "simulation") -> dict[str, Any]:
    return _last.get(mode) or {}


def reset_progress(mode: str = "simulation") -> None:
    _last.pop(mode, None)


async def publish_progress(mode: str, step: str, label: str, **extra: Any) -> dict[str, Any]:
    payload = jsonable({"mode": mode, "step": step, "label": label, **extra})
    _last[mode] = payload
    await hub.broadcast("pipeline_progress", payload)
    return payload
