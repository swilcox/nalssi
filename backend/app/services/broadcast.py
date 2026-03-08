"""
WebSocket connection manager for broadcasting live updates.

Manages connected WebSocket clients and broadcasts HTML fragments
for HTMX out-of-band swaps.
"""

import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts messages to all clients."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            "WebSocket client connected",
            extra={"total_connections": len(self.active_connections)},
        )

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.remove(websocket)
        logger.info(
            "WebSocket client disconnected",
            extra={"total_connections": len(self.active_connections)},
        )

    async def broadcast(self, message: str) -> None:
        """Broadcast an HTML fragment to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)

        for connection in disconnected:
            self.active_connections.remove(connection)

        if disconnected:
            logger.debug(
                "Cleaned up disconnected WebSocket clients",
                extra={"removed": len(disconnected)},
            )


# Global connection manager
manager = ConnectionManager()
