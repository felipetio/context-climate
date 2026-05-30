"""Singleton loader and relevance search for offline indicator data."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent

_popular_indicators: list[dict[str, Any]] | None = None
_metadata_indicators: list[dict[str, Any]] | None = None


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


def get_metadata_indicators() -> list[dict[str, Any]]:
    """Return full metadata indicator list (loaded once, cached in memory).

    The metadata file is a bare JSON list — assign directly, no `.get` unwrap.
    """
    global _metadata_indicators
    if _metadata_indicators is None:
        _metadata_indicators = _load_json("metadata_indicators.json")
        logger.info("Loaded %d metadata indicators", len(_metadata_indicators))
    return _metadata_indicators


def search_local_metadata(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search indicator metadata with cascading first-match-wins relevance scoring.

    Scoring rules (evaluated top-down, the first match assigns the score):
      100 — exact code match (case-insensitive equality of full code)
       90 — code substring (case-insensitive `query in code`)
       80 — query word in name (any whitespace-split query word equals any
            whitespace-split name word, lowercase)
       70 — query substring in name (`query in name`, lowercase)
       40 — query substring in description (`query in description`, lowercase)
        0 — no match (record dropped)

    Empty/whitespace-only query short-circuits to `[]` (would otherwise match
    every record at score 90 via the substring rule).
    """
    query_clean = query.strip()
    if not query_clean:
        return []

    indicators = get_metadata_indicators()
    query_lower = query_clean.lower()
    query_words = query_lower.split()
    results: list[dict[str, Any]] = []

    for ind in indicators:
        code = ind.get("code", "").lower()
        name = ind.get("name", "").lower()
        desc = ind.get("description", "").lower()
        name_words = name.split()

        if query_lower == code:
            score = 100
        elif query_lower in code:
            score = 90
        elif any(word in name_words for word in query_words):
            score = 80
        elif query_lower in name:
            score = 70
        elif query_lower in desc:
            score = 40
        else:
            score = 0

        if score == 0:
            continue

        results.append(
            {
                "indicator": ind.get("code", ""),
                "name": ind.get("name", ""),
                "description": ind.get("description", "")[:200],
                "source": ind.get("source", "")[:100],
                "relevance_score": score,
            }
        )

    results.sort(key=lambda r: r["relevance_score"], reverse=True)
    return results[:limit]
