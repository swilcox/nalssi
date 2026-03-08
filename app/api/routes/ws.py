"""
WebSocket endpoint for live weather updates.
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.broadcast import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/weather")
async def weather_ws(websocket: WebSocket):
    """
    WebSocket endpoint for live weather and alert updates.

    Clients connect and receive HTML fragments with hx-swap-oob="true"
    whenever new weather data is collected.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; we only send server->client messages.
            # Receiving handles ping/pong and detects disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
