"""Tests for connector plumbing.

The guard in `fetch_json` is the thing standing between a WAF challenge page and
our corpus, so it needs testing in both directions: it must catch a block page,
and it must not reject legitimate data. It initially failed the second half — a
13-byte `{"count":681}` was rejected as a suspected block — which is a guard
firing on exactly what it exists to protect.
"""

from __future__ import annotations

import httpx
import pytest

from throughline.connectors.base import SourceUnavailable, fetch_json


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestFetchJsonAcceptsRealData:
    async def test_tiny_valid_json_is_accepted(self):
        """A count query legitimately answers in a dozen bytes."""

        def handler(request):
            return httpx.Response(200, json={"count": 681})

        async with _client(handler) as client:
            payload, _, _ = await fetch_json(client, "https://x.invalid", min_bytes=8)
        assert payload == {"count": 681}

    async def test_large_payload_is_accepted(self):
        def handler(request):
            return httpx.Response(
                200, json={"features": [{"attributes": {"n": i}} for i in range(50)]}
            )

        async with _client(handler) as client:
            payload, _, _ = await fetch_json(client, "https://x.invalid")
        assert len(payload["features"]) == 50


class TestFetchJsonRejectsBlockPages:
    async def test_html_challenge_served_as_200_is_rejected(self):
        """The failure this guard exists for: a block page with a 200 status."""

        def handler(request):
            return httpx.Response(200, html="<html><body>Request blocked</body></html>")

        async with _client(handler) as client:
            with pytest.raises(SourceUnavailable) as exc:
                await fetch_json(client, "https://x.invalid", attempts=1)
        assert "WAF" in str(exc.value) or "block" in str(exc.value)

    async def test_arcgis_error_inside_200_body_is_rejected(self):
        def handler(request):
            return httpx.Response(200, json={"error": {"code": 500, "message": "not started"}})

        async with _client(handler) as client:
            with pytest.raises(SourceUnavailable) as exc:
                await fetch_json(client, "https://x.invalid", attempts=1)
        assert "service error" in str(exc.value)

    async def test_non_200_is_rejected(self):
        def handler(request):
            return httpx.Response(401, json={"detail": "auth required"})

        async with _client(handler) as client:
            with pytest.raises(SourceUnavailable) as exc:
                await fetch_json(client, "https://x.invalid", attempts=1)
        assert "401" in str(exc.value)

    async def test_valid_json_below_expected_size_is_rejected(self):
        """Truncation is still caught when the caller expects a real payload."""

        def handler(request):
            return httpx.Response(200, json={"features": []})

        async with _client(handler) as client:
            with pytest.raises(SourceUnavailable) as exc:
                await fetch_json(client, "https://x.invalid", attempts=1, min_bytes=200)
        assert "truncated or empty" in str(exc.value)
