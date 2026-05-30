"""Singleton loader for offline indicator data files."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent

_popular_indicators: list[dict[str, Any]] | None = None


def _load_json(filename: str) -> list | dict:
    """Load a JSON file from the mcp_server directory using UTF-8."""
    path = DATA_DIR / filename
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def get_popular_indicators() -> dict[str, Any]:
    """Return curated popular indicators (loaded once, cached in memory)."""
    global _popular_indicators
    if _popular_indicators is None:
        data = _load_json("popular_indicators.json")
        _popular_indicators = data.get("indicators", data) if isinstance(data, dict) else data
        logger.info("Loaded %d popular indicators", len(_popular_indicators))
    return {"indicators": _popular_indicators, "total": len(_popular_indicators)}
