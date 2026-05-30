"""MCP Server configuration settings."""

import os

from dotenv import load_dotenv

load_dotenv()


def _int_env(key: str, default: int, min_val: int = 1) -> int:
    raw = os.getenv(key, str(default))
    try:
        val = int(raw)
    except ValueError:
        val = default
    return max(val, min_val)


def _float_env(key: str, default: float, min_val: float = 0.0) -> float:
    raw = os.getenv(key, str(default))
    try:
        val = float(raw)
    except ValueError:
        val = default
    return max(val, min_val)


BASE_URL = os.getenv("DATA360_BASE_URL", "https://data360api.worldbank.org")

# HTTP client settings
REQUEST_TIMEOUT = _float_env("DATA360_REQUEST_TIMEOUT", 30.0, min_val=1.0)
MAX_RETRIES = _int_env("DATA360_MAX_RETRIES", 3, min_val=0)
RETRY_BACKOFF_BASE = _float_env("DATA360_RETRY_BACKOFF_BASE", 1.0, min_val=0.0)

# Pagination settings (fixed caps, not user-configurable)
PAGE_SIZE = 1000
MAX_RECORDS = 5000

# Default `limit` for the offline search_local_indicators tool. Env-overridable.
# Defensive [1, 100] clamp is applied inside the tool, so this is just the default.
DATA360_LOCAL_SEARCH_LIMIT: int = _int_env("DATA360_LOCAL_SEARCH_LIMIT", 20, min_val=1)

# Transport settings
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
_mcp_port_raw = os.getenv("MCP_PORT")
MCP_PORT = int(_mcp_port_raw) if _mcp_port_raw is not None else None

# Database URL — shared with the Chainlit app (same DB, same env var)
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

# RAG Configuration (feature-flagged via DATA360_RAG_ENABLED)
RAG_ENABLED: bool = os.getenv("DATA360_RAG_ENABLED", "false").lower() == "true"
RAG_CHUNK_SIZE: int = _int_env("DATA360_RAG_CHUNK_SIZE", 512, min_val=1)
RAG_CHUNK_OVERLAP: int = _int_env("DATA360_RAG_CHUNK_OVERLAP", 64, min_val=0)
