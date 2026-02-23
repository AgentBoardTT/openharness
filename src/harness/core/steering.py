"""Steering channel for real-time user interjection."""

from __future__ import annotations

import anyio
from anyio.abc import ObjectReceiveStream, ObjectSendStream


class SteeringChannel:
    """Allows the user to push messages into the agent loop between turns.

    Uses anyio memory object streams for async-safe communication.
    """

    def __init__(self, buffer_size: int = 16) -> None:
        send: ObjectSendStream[str]
        recv: ObjectReceiveStream[str]
        send, recv = anyio.create_memory_object_stream[str](max_buffer_size=buffer_size)
        self._send = send
        self._recv = recv
        self._pending: list[str] = []

    async def send(self, message: str) -> None:
        """Push a steering message (called by user/UI thread)."""
        await self._send.send(message)

    def send_nowait(self, message: str) -> None:
        """Push a steering message without waiting (non-blocking)."""
        self._send.send_nowait(message)

    async def receive(self) -> str | None:
        """Receive a pending steering message, or None if empty.

        Non-blocking: returns immediately if no message is pending.
        """
        try:
            with anyio.fail_after(0):
                return await self._recv.receive()
        except (TimeoutError, anyio.EndOfStream, anyio.WouldBlock):
            return None

    def has_pending(self) -> bool:
        """Check if there are pending messages (best-effort, non-blocking)."""
        try:
            stats = self._recv.statistics()
            return stats.current_buffer_used > 0
        except Exception:
            return False

    async def close(self) -> None:
        """Close the channel."""
        await self._send.aclose()
        await self._recv.aclose()
