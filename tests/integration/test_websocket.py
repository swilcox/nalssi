"""
Integration tests for the WebSocket endpoint.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.broadcast import manager


@pytest.fixture(autouse=True)
def _clear_connections():
    """Ensure no leftover connections between tests."""
    manager.active_connections.clear()
    yield
    manager.active_connections.clear()


class TestWeatherWebSocket:
    """Tests for /ws/weather endpoint."""

    def test_websocket_connect(self):
        """Client can connect to the WebSocket endpoint."""
        client = TestClient(app)
        with client.websocket_connect("/ws/weather") as ws:
            assert len(manager.active_connections) == 1
            ws.close()

    def test_websocket_disconnect_cleans_up(self):
        """Disconnecting removes client from manager."""
        client = TestClient(app)
        with client.websocket_connect("/ws/weather"):
            assert len(manager.active_connections) == 1
        # After context exit, connection should be cleaned up
        assert len(manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_broadcast_reaches_client(self):
        """Broadcast sends HTML fragments to connected clients."""
        client = TestClient(app)
        with client.websocket_connect("/ws/weather") as ws:
            await manager.broadcast('<div id="test" hx-swap-oob="true">hello</div>')
            data = ws.receive_text()
            assert 'hx-swap-oob="true"' in data
            assert "hello" in data
