"""FastMCP server with Data360 API tools."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP

from mcp_server import config, indicator_cache
from mcp_server.data360_client import Data360Client

logger = logging.getLogger(__name__)

_client: Data360Client | None = None
_db_pool = None  # asyncpg.Pool when RAG_ENABLED=true, None otherwise


@asynccontextmanager
async def _lifespan(server: FastMCP):
    global _client, _db_pool
    _client = Data360Client()
    if config.RAG_ENABLED:
        import asyncpg  # noqa: PLC0415

        _db_pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5)
    try:
        yield
    finally:
        await _client.close()
        if _db_pool is not None:
            await _db_pool.close()


mcp = FastMCP(
    "context-climate",
    instructions="World Bank Data360 climate and development data tools.",
    lifespan=_lifespan,
)


@mcp.tool()
async def search_indicators(
    query: str,
    top: int = 10,
    skip: int = 0,
    filter: str | None = None,
) -> dict[str, Any]:
    """Search for World Bank Data360 indicators using natural language.

    Args:
        query: Natural language search text (e.g. "drought Brazil", "CO2 emissions").
        top: Maximum number of results to return (default 10).
        skip: Number of results to skip for pagination (default 0).
        filter: Optional OData filter expression.

    Returns:
        Dict with success status, data list, total_count, returned_count, and truncated flag.
    """
    try:
        body: dict[str, Any] = {"search": query, "top": top, "skip": skip, "count": True}
        if filter is not None:
            body["filter"] = filter

        response = await _client._request("POST", "/data360/searchv2", json_body=body)

        if isinstance(response, dict) and response.get("success") is False:
            return response

        results = response.get("value", [])
        _client.cache_db_names(results)
        total_count = response.get("@odata.count") or len(results)
        returned_count = len(results)
        return {
            "success": True,
            "data": results,
            "total_count": total_count,
            "returned_count": returned_count,
            "truncated": total_count > returned_count,
        }
    except Exception as exc:
        logger.error("search_indicators failed: %s", exc)
        return {"success": False, "error": str(exc), "error_type": "api_error"}


@mcp.tool()
async def get_data(
    database_id: str,
    indicator: str,
    ref_area: str | None = None,
    time_period_from: str | None = None,
    time_period_to: str | None = None,
) -> dict[str, Any]:
    """Retrieve data values for a specific indicator by country and time period.

    Args:
        database_id: Dataset identifier (e.g. "WB_WDI").
        indicator: Indicator code (e.g. "WB_WDI_EN_ATM_CO2E_KT").
        ref_area: Country/region code (e.g. "BRA"). Optional.
        time_period_from: Start year filter (e.g. "2015"). Optional.
        time_period_to: End year filter (e.g. "2023"). Optional.

    Returns:
        Dict with success status, data list preserving API field names
        (OBS_VALUE, DATA_SOURCE, TIME_PERIOD, etc.), total_count, returned_count,
        and truncated flag.
    """
    try:
        # Standard params go through _map_params (snake_case -> UPPERCASE)
        kwargs: dict[str, Any] = {"database_id": database_id, "indicator": indicator}
        if ref_area is not None:
            kwargs["ref_area"] = ref_area

        # Map standard params to UPPERCASE, then add camelCase time period
        # params directly (API expects timePeriodFrom, not TIME_PERIOD_FROM)
        params = Data360Client._map_params(kwargs)
        if time_period_from is not None:
            params["timePeriodFrom"] = time_period_from
        if time_period_to is not None:
            params["timePeriodTo"] = time_period_to
        result = await _client._paginated_get("/data360/data", params)
        if result.get("success") and result.get("data"):
            await _client.enrich_citation_source(result["data"])
        return result
    except Exception as exc:
        logger.error("get_data failed: %s", exc)
        return {"success": False, "error": str(exc), "error_type": "api_error"}


@mcp.tool()
async def get_metadata(
    query: str,
) -> dict[str, Any]:
    """Get detailed metadata about indicators, datasets, and topics.

    Args:
        query: OData query string (e.g. "&$filter=series_description/idno eq 'WB_WDI_SP_POP_TOTL'").
            Supports $filter, $select, and $top OData parameters.

    Returns:
        Dict with success status, data list of metadata items, total_count,
        returned_count, and truncated flag.
    """
    try:
        body: dict[str, Any] = {"query": query}

        response = await _client._request("POST", "/data360/metadata", json_body=body)

        if isinstance(response, dict) and response.get("success") is False:
            return response

        if not isinstance(response, dict):
            logger.warning("get_metadata: unexpected response type %s", type(response).__name__)
            return {"success": True, "data": [], "total_count": 0, "returned_count": 0, "truncated": False}

        results = response.get("value", [])
        total_count = response.get("@odata.count") or len(results)
        returned_count = len(results)
        return {
            "success": True,
            "data": results,
            "total_count": total_count,
            "returned_count": returned_count,
            "truncated": total_count > returned_count,
        }
    except Exception as exc:
        logger.error("get_metadata failed: %s", exc)
        return {"success": False, "error": str(exc), "error_type": "api_error"}


@mcp.tool()
async def list_indicators(
    dataset_id: str,
) -> dict[str, Any]:
    """List all available indicators in a given dataset.

    Args:
        dataset_id: Dataset identifier (e.g. "WB_WDI").

    Returns:
        Dict with success status, data list of indicator ID strings,
        total_count, returned_count, and truncated flag.
    """
    try:
        params: dict[str, Any] = {"datasetId": dataset_id}

        response = await _client._request("GET", "/data360/indicators", params=params)

        if isinstance(response, dict) and response.get("success") is False:
            return response

        if not isinstance(response, list):
            logger.warning("list_indicators: unexpected response type %s", type(response).__name__)

        results = response if isinstance(response, list) else []
        return {
            "success": True,
            "data": results,
            "total_count": len(results),
            "returned_count": len(results),
            "truncated": False,
        }
    except Exception as exc:
        logger.error("list_indicators failed: %s", exc)
        return {"success": False, "error": str(exc), "error_type": "api_error"}


@mcp.tool()
async def get_disaggregation(
    dataset_id: str,
    indicator_id: str | None = None,
) -> dict[str, Any]:
    """Get available disaggregation dimensions for a dataset or indicator.

    Args:
        dataset_id: Dataset identifier (e.g. "WB_WDI").
        indicator_id: Indicator code (e.g. "WB_WDI_SP_POP_TOTL"). Optional.

    Returns:
        Dict with success status, data list of dimension objects
        (field_name, label_name, field_value), total_count, returned_count,
        and truncated flag.
    """
    try:
        params: dict[str, Any] = {"datasetId": dataset_id}
        if indicator_id is not None:
            params["indicatorId"] = indicator_id

        response = await _client._request("GET", "/data360/disaggregation", params=params)

        if isinstance(response, dict) and response.get("success") is False:
            return response

        if not isinstance(response, list):
            logger.warning("get_disaggregation: unexpected response type %s", type(response).__name__)

        results = response if isinstance(response, list) else []
        return {
            "success": True,
            "data": results,
            "total_count": len(results),
            "returned_count": len(results),
            "truncated": False,
        }
    except Exception as exc:
        logger.error("get_disaggregation failed: %s", exc)
        return {"success": False, "error": str(exc), "error_type": "api_error"}


@mcp.tool()
async def list_popular_indicators() -> dict[str, Any]:
    """List curated popular climate and development indicators.

    Returns a categorized list of ~25-30 commonly requested indicators
    with codes, names, and descriptions. No API call required - instant results.

    Returns:
        dict with success, data (list of indicators grouped by category),
        total_count, returned_count, truncated.
    """
    try:
        result = indicator_cache.get_popular_indicators()
        indicators = result["indicators"]

        groups: dict[str, list[dict[str, Any]]] = {}
        for ind in indicators:
            category = ind.get("category", "Uncategorized")
            groups.setdefault(category, []).append(
                {
                    "code": ind.get("code", ""),
                    "name": ind.get("name", ""),
                    "description": ind.get("description", ""),
                }
            )

        data = [{"category": category, "indicators": items} for category, items in groups.items()]
        total = sum(len(g["indicators"]) for g in data)
        return {
            "success": True,
            "data": data,
            "total_count": total,
            "returned_count": total,
            "truncated": False,
        }
    except Exception as exc:
        logger.error("list_popular_indicators failed: %s", exc)
        return {"success": False, "error": str(exc), "error_type": "api_error"}


if config.RAG_ENABLED:
    from mcp_server.rag.citation import build_citation_source
    from mcp_server.rag.embeddings import generate_query_embedding
    from mcp_server.rag.store import list_all_documents, search_similar

    @mcp.tool()
    async def search_documents(
        query: str,
        limit: int = 5,
        min_score: float = 0.3,
    ) -> dict[str, Any]:
        """Search uploaded documents using semantic similarity.

        Args:
            query: Natural language search query.
            limit: Maximum number of results to return (default 5).
            min_score: Minimum similarity score threshold 0–1 (default 0.3).

        Returns:
            Dict with success status, data list of matching chunks with
            content, source, similarity_score, and CITATION_SOURCE.
        """
        if _db_pool is None:
            return {"success": False, "error": "RAG database pool not initialized", "error_type": "api_error"}
        try:
            # generate_query_embedding is CPU-bound (sentence-transformers) — offload to thread
            query_embedding = await asyncio.to_thread(generate_query_embedding, query)
            async with _db_pool.acquire() as conn:
                results = await search_similar(conn, query_embedding, limit=limit, min_score=min_score)
            data = [
                {
                    "content": r.content,
                    "source": r.source,
                    "page_number": r.page_number,
                    "chunk_index": r.chunk_index,
                    "similarity_score": r.similarity_score,
                    "document_id": r.document_id,
                    "upload_date": r.upload_date.isoformat(),
                    "CITATION_SOURCE": build_citation_source(r.source, r.upload_date, r.page_number, r.chunk_index),
                }
                for r in results
            ]
            return {
                "success": True,
                "data": data,
                "total_count": len(data),
                "returned_count": len(data),
                "truncated": False,
            }
        except Exception as exc:
            logger.error("search_documents failed: %s", exc)
            return {"success": False, "error": str(exc), "error_type": "api_error"}

    @mcp.tool()
    async def list_documents(
        limit: int = 20,
    ) -> dict[str, Any]:
        """List all uploaded documents with metadata.

        Args:
            limit: Maximum number of documents to return (default 20).

        Returns:
            Dict with success status and data list of documents
            with filename, mime_type, upload_date, page_count, chunk_count.
        """
        if _db_pool is None:
            return {"success": False, "error": "RAG database pool not initialized", "error_type": "api_error"}
        try:
            async with _db_pool.acquire() as conn:
                docs = await list_all_documents(conn, limit=limit)
            data = [
                {
                    **{k: v for k, v in doc.items() if k != "upload_date"},
                    "upload_date": doc["upload_date"].isoformat() if doc.get("upload_date") else None,
                }
                for doc in docs
            ]
            return {
                "success": True,
                "data": data,
                "total_count": len(data),
                "returned_count": len(data),
                "truncated": False,
            }
        except Exception as exc:
            logger.error("list_documents failed: %s", exc)
            return {"success": False, "error": str(exc), "error_type": "api_error"}


if __name__ == "__main__":
    from mcp_server.config import MCP_PORT, MCP_TRANSPORT

    if MCP_TRANSPORT not in {"stdio", "streamable-http"}:
        raise ValueError(f"Invalid MCP_TRANSPORT '{MCP_TRANSPORT}'. Valid values: stdio, streamable-http")
    if MCP_TRANSPORT == "streamable-http":
        mcp.run(transport=MCP_TRANSPORT, port=MCP_PORT or 8001)
    else:
        mcp.run(transport=MCP_TRANSPORT)
