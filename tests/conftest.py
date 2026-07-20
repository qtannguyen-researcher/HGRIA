"""Shared pytest fixtures for integration tests."""

import queue
import pytest

from backend.core.configuration import ConfigurationManager
from backend.core.models import Session
from backend.core.state_manager import StateManager


@pytest.fixture
def test_config():
    """Provide a test configuration."""
    return ConfigurationManager()


@pytest.fixture
def test_session():
    """Provide a test session."""
    return Session()


@pytest.fixture
def test_state_manager():
    """Provide a test state manager."""
    return StateManager(None, None)


@pytest.fixture
def command_queue():
    """Provide a test command queue."""
    return queue.Queue(maxsize=20)


@pytest.fixture
def flask_app(test_config, test_session, test_state_manager, command_queue):
    """Create a Flask test app."""
    from backend.app import create_app

    app, socketio = create_app(
        test_config, test_session, test_state_manager, command_queue, None
    )
    app.config["TESTING"] = True
    return app, socketio


@pytest.fixture
def client(flask_app):
    """Provide a Flask test client."""
    app, _ = flask_app
    return app.test_client()


@pytest.fixture
def socketio_instance(flask_app):
    """Provide the SocketIO instance."""
    _, sio = flask_app
    return sio
