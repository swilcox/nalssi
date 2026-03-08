"""
Tests for the WebSocket broadcast manager.
"""

import pytest

from app.services.broadcast import ConnectionManager


class TestConnectionManager:
    """Tests for ConnectionManager."""

    def test_initial_state(self):
        """Manager starts with no connections."""
        mgr = ConnectionManager()
        assert mgr.active_connections == []

    @pytest.mark.asyncio
    async def test_connect_adds_websocket(self):
        """connect() accepts and stores the websocket."""

        class FakeWebSocket:
            accepted = False

            async def accept(self):
                self.accepted = True

        mgr = ConnectionManager()
        ws = FakeWebSocket()
        await mgr.connect(ws)

        assert ws.accepted
        assert ws in mgr.active_connections

    def test_disconnect_removes_websocket(self):
        """disconnect() removes the websocket from active list."""
        mgr = ConnectionManager()
        ws = object()
        mgr.active_connections.append(ws)

        mgr.disconnect(ws)
        assert ws not in mgr.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self):
        """broadcast() sends message to all connected clients."""

        class FakeWebSocket:
            messages = []

            async def accept(self):
                pass

            async def send_text(self, msg):
                self.messages.append(msg)

        mgr = ConnectionManager()
        ws1 = FakeWebSocket()
        ws1.messages = []
        ws2 = FakeWebSocket()
        ws2.messages = []

        await mgr.connect(ws1)
        await mgr.connect(ws2)

        await mgr.broadcast("<div>test</div>")

        assert ws1.messages == ["<div>test</div>"]
        assert ws2.messages == ["<div>test</div>"]

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self):
        """broadcast() cleans up clients that fail to receive."""

        class DeadWebSocket:
            async def accept(self):
                pass

            async def send_text(self, msg):
                raise ConnectionError("gone")

        class GoodWebSocket:
            messages = []

            async def accept(self):
                pass

            async def send_text(self, msg):
                self.messages.append(msg)

        mgr = ConnectionManager()
        dead = DeadWebSocket()
        good = GoodWebSocket()
        good.messages = []

        await mgr.connect(dead)
        await mgr.connect(good)

        await mgr.broadcast("hello")

        assert dead not in mgr.active_connections
        assert good in mgr.active_connections
        assert good.messages == ["hello"]

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self):
        """broadcast() with no connections is a no-op."""
        mgr = ConnectionManager()
        await mgr.broadcast("no one listening")
        assert mgr.active_connections == []
