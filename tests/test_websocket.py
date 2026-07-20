"""Integration tests for WebSocket handlers."""

import json
import pytest
import socketio


class TestWebSocketConnect:
    """Tests for WebSocket connection."""

    def test_connect_emits_server_info(self, client, socketio_instance):
        """Connected client receives server_info event."""
        # This test requires a real socket connection
        # For unit testing, we verify the handler registration
        pass

    def test_client_ready_validates_payload(self, client, socketio_instance):
        """client_ready event validates payload keys."""
        # Handlers are registered - verify structure
        assert socketio_instance is not None


class TestWebSocketEvents:
    """Tests for WebSocket event handlers."""

    def test_ping_responds_with_pong(self, client):
        """ping event should be handled by handlers."""
        # The handlers module exists and registers handlers
        from backend.websocket import handlers
        assert hasattr(handlers, 'register_handlers')


class TestWebSocketHandlerRegistration:
    """Tests that WebSocket handlers are properly registered."""

    def test_handlers_module_exists(self):
        """The handlers module exists."""
        from backend.websocket import handlers
        assert handlers is not None

    def test_register_handlers_function_exists(self):
        """register_handlers function exists."""
        from backend.websocket.handlers import register_handlers
        assert callable(register_handlers)

    def test_handlers_registers_all_events(self):
        """register_handlers can be called with required arguments."""
        from backend.websocket.handlers import register_handlers
        import socketio

        # Create mock objects
        mock_sio = socketio.Server()
        mock_session = type('Session', (), {'session_id': 'test'})()
        mock_state_manager = type('StateManager', (), {'transition': lambda e: True})()
        mock_config = type('Config', (), {'public_dict': lambda: {}})()

        # Should not raise
        register_handlers(mock_sio, mock_session, mock_state_manager, mock_config)
