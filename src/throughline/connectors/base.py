"""Connector plumbing.

One rule governs this module: **a fetch is verified by its content, never by its
status code.** Enterprise and government WAFs routinely answer a rate-limited
client with a challenge page served as HTTP 200. A fetcher that trusts the
status code writes those challenge pages into the corpus under real filenames
and then reports full coverage, which is worse than failing, because the failure
is now invisible and downstream everything looks complete.

Second rule: a failed fetch is never persisted. A file that exists is a file
something later will parse.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

USER_AGENT = "Throughline/0.1 (Hack RenderATL 2026; record-integrity research)"


class SourceUnavailable(RuntimeError):
    """Raised when a source cannot be read.

    Deliberately loud. The spec's "fail visible" principle means a dead
    connector must surface in the product, because silent staleness is the
    disease we exist to cure and we do not get to reproduce it ourselves.
    """


@dataclass(slots=True)
class FetchResult:
    url: str
    rows: list[dict]
    fetched_at: datetime
    elapsed_ms: int


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict | None = None,
    min_bytes: int = 200,
    timeout: float = 45.0,
    attempts: int = 3,
) -> tuple[dict, datetime, int]:
    """GET JSON, validating the payload rather than the status line."""
    last_error: str = "not attempted"
    for attempt in range(1, attempts + 1):
        started = datetime.now(UTC)
        try:
            response = await client.get(
                url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT}
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = f"transport error: {exc!r}"
        else:
            body = response.content
            elapsed = int((datetime.now(UTC) - started).total_seconds() * 1000)

            if response.status_code != 200:
                last_error = f"HTTP {response.status_code}"
            elif len(body) < min_bytes:
                # The WAF-challenge shape: a 200 carrying a few hundred bytes of
                # HTML where a dataset should be. Name it in the error so the
                # failure is diagnosable rather than mysterious.
                last_error = (
                    f"HTTP 200 but only {len(body)} bytes — "
                    "likely a WAF challenge or block page, not data"
                )
            else:
                try:
                    payload = response.json()
                except ValueError:
                    last_error = f"HTTP 200 but body is not JSON (starts {body[:60]!r})"
                else:
                    if isinstance(payload, dict) and "error" in payload:
                        # ArcGIS reports service errors inside a 200 body.
                        last_error = f"service error in 200 body: {payload['error']}"
                    else:
                        return payload, started, elapsed

        if attempt < attempts:
            # Government and enterprise hosts block bulk readers quickly. Backing
            # off is cheaper than getting the whole run challenged.
            await asyncio.sleep(2.0 * attempt)

    raise SourceUnavailable(f"{url} — {last_error}")
