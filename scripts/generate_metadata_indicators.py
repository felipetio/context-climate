"""Generate mcp_server/metadata_indicators.json from the live Data360 API.

Fetches all WB_WDI indicator metadata via the searchv2 endpoint and writes
a bare JSON array to mcp_server/metadata_indicators.json.

Usage:
    uv run python scripts/generate_metadata_indicators.py

The generated file is committed to the repo. Re-run this script whenever
the WDI indicator catalog changes and you want to refresh the local copy.
"""

import asyncio
import json
import re
from pathlib import Path

import httpx

BASE_URL = "https://data360api.worldbank.org"
DATABASE_ID = "WB_WDI"
OUTPUT_PATH = Path(__file__).parent.parent / "mcp_server" / "metadata_indicators.json"
PAGE_SIZE = 1000
REQUEST_TIMEOUT = 60.0
MIN_EXPECTED_RECORDS = 500  # refuse to overwrite the committed file with fewer (matches the test lower bound)

# Well-formed short-code shape — mirrors tests/mcp_server/test_metadata_indicators.py.
SHORT_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_]+")


async def fetch_all() -> list[dict]:
    """Fetch all WB_WDI indicators from the Data360 searchv2 endpoint."""
    records: list[dict] = []
    seen_codes: set[str] = set()
    skip = 0

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        while True:
            body = {
                "search": "*",
                "filter": f"series_description/database_id eq '{DATABASE_ID}'",
                "top": PAGE_SIZE,
                "skip": skip,
                "count": True,
            }
            response = await client.post(f"{BASE_URL}/data360/searchv2", json=body)
            response.raise_for_status()
            data = response.json()

            batch = data.get("value", [])
            if not batch:
                break

            for item in batch:
                sd = item.get("series_description") or {}
                idno = sd.get("idno") or ""
                db_id = sd.get("database_id") or DATABASE_ID
                code = idno.removeprefix(f"{db_id}_").strip()
                description = sd.get("definition_long") or sd.get("definition_short") or ""
                name = (sd.get("name") or "").strip()
                source = (sd.get("database_name") or "").strip()

                # Skip anything the validation suite would reject. name/source must be
                # non-empty; description may be empty (AC2). The code must be a clean
                # short code — removeprefix() silently no-ops when idno lacks the prefix,
                # so guard against a leftover fully-qualified WB_* id or other malformed shape.
                if not name or not source:
                    continue
                if not code or code.upper().startswith("WB_") or not SHORT_CODE_PATTERN.fullmatch(code):
                    print(f"  Skipping malformed code {code!r} (idno={idno!r})")
                    continue
                if code in seen_codes:
                    continue  # Data360 occasionally returns the same idno twice; keep the first.
                seen_codes.add(code)

                records.append(
                    {
                        "code": code,
                        "name": name,
                        "description": description,
                        "source": source,
                    }
                )

            print(f"  Fetched {len(records)} records so far (skip={skip})...")
            skip += PAGE_SIZE

            if len(batch) < PAGE_SIZE:
                break  # last page

    return records


def main() -> None:
    print(f"Fetching {DATABASE_ID} indicators from Data360 API...")
    records = asyncio.run(fetch_all())
    print(f"Total: {len(records)} records fetched.")

    if len(records) < MIN_EXPECTED_RECORDS:
        raise SystemExit(
            f"Aborting: only {len(records)} records fetched (expected >= {MIN_EXPECTED_RECORDS}). "
            f"Refusing to overwrite {OUTPUT_PATH} with a likely-incomplete result."
        )

    OUTPUT_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
