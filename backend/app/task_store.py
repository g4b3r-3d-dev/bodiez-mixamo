from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket


@dataclass
class TaskState:
    history: list[dict[str, Any]] = field(default_factory=list)
    sockets: set[WebSocket] = field(default_factory=set)
    done: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskState] = {}
        self._lock = asyncio.Lock()

    async def create(self, task_id: str) -> None:
        async with self._lock:
            self._tasks[task_id] = TaskState()

    async def exists(self, task_id: str) -> bool:
        async with self._lock:
            return task_id in self._tasks

    async def connect(self, task_id: str, websocket: WebSocket) -> list[dict[str, Any]]:
        async with self._lock:
            state = self._tasks.get(task_id)
            if state is None:
                raise KeyError(task_id)
        async with state.lock:
            state.sockets.add(websocket)
            return list(state.history)

    async def disconnect(self, task_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            state = self._tasks.get(task_id)
        if state is None:
            return
        async with state.lock:
            state.sockets.discard(websocket)

    async def publish(self, task_id: str, event: dict[str, Any]) -> None:
        async with self._lock:
            state = self._tasks.get(task_id)
        if state is None:
            return

        async with state.lock:
            state.history.append(event)
            if event.get("type") in {"success", "error"}:
                state.done = True
            sockets = list(state.sockets)

        stale: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_json(event)
            except Exception:
                stale.append(socket)

        if stale:
            async with state.lock:
                for socket in stale:
                    state.sockets.discard(socket)


store = TaskStore()
