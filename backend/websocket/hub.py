from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from backend.utils.geo import jsonable
from fastapi import WebSocket

HEARTBEAT_SEC = 15


class Hub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.last_event_at: Optional[datetime] = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        message = {
            "type": event_type,
            "payload": jsonable(payload),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.last_event_at = datetime.now(timezone.utc)
        async with self._lock:
            clients = list(self._clients)
        stale = []
        for ws in clients:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                stale.append(ws)
        for ws in stale:
            await self.disconnect(ws)

    @property
    def connected_count(self) -> int:
        return len(self._clients)


hub = Hub()
