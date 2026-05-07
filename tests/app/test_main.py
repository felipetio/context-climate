"""Smoke tests for the FastAPI app startup."""

import importlib

import pytest


@pytest.fixture(autouse=True)
def set_required_env_vars(monkeypatch):
    """Provide required env vars so Settings loads without a .env file."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost:5432/testdb")
    monkeypatch.setenv("MCP_SERVER_URL", "http://localhost:8001")
    # Required by Chainlit's ensure_jwt_secret() when password_auth_callback is registered
    monkeypatch.setenv("CHAINLIT_AUTH_SECRET", "test-secret-for-ci-do-not-use-in-prod")


def test_fastapi_app_imports_without_error():
    """The FastAPI app module should be importable when env vars are set."""
    import app.config
    import app.main

    importlib.reload(app.config)
    importlib.reload(app.main)

    from app.main import app  # intentional late import after reload

    assert app is not None
    assert app.title == "Context Climate"


def test_fastapi_app_has_correct_title():
    """FastAPI app title should be 'Context Climate'."""
    import app.main

    importlib.reload(app.main)

    from app.main import app

    assert app.title == "Context Climate"


def test_config_loads_with_valid_env(monkeypatch):
    """Settings should load successfully when all required env vars are present."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.setenv("MCP_SERVER_URL", "http://mcp.example.com:8001")

    from app.config import Settings

    # Pass _env_file=None to prevent reading a local .env file during tests
    settings = Settings(_env_file=None)
    assert settings.anthropic_api_key == "sk-ant-test"
    assert settings.database_url == "postgresql://user:pass@localhost:5432/db"
    assert settings.mcp_server_url == "http://mcp.example.com:8001"


def test_config_default_mcp_server_url(monkeypatch):
    """MCP_SERVER_URL should default to http://localhost:8001/mcp if not set.

    The /mcp suffix is required because FastMCP's streamable-http transport mounts
    the JSON-RPC endpoint at /mcp, not at the server root.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)

    from app.config import Settings

    # Pass _env_file=None so a local .env won't override the deleted var
    settings = Settings(_env_file=None)
    assert settings.mcp_server_url == "http://localhost:8001/mcp"
