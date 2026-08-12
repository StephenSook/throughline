"""US Census Bureau Geocoder — the federal address authority.

This is the connector that makes the whole audit defensible. When Atlanta says a
licensed child care facility sits at an address, and the U.S. Census Bureau's
TIGER address ranges cannot resolve that address at all, that is not our opinion
about data quality. It is one federal authority declining to confirm a municipal
authority, and anybody can reproduce it against a public, unauthenticated
endpoint in a browser.

Uses the **batch** endpoint. Geocoding ~800 addresses one at a time is both slow
enough to eat a demo window and exactly the request pattern that gets a bulk
reader blocked.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

import httpx

from .base import USER_AGENT, SourceUnavailable

BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
ONELINE_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
BENCHMARK = "Public_AR_Current"

# The batch endpoint accepts 10,000 rows, but a smaller chunk fails smaller: one
# rejected chunk costs us 500 addresses, not the entire run.
CHUNK = 500


class GeocodeResult:
    __slots__ = ("key", "matched", "matched_address", "lat", "lon", "tiger_line")

    def __init__(
        self,
        key: str,
        matched: bool,
        matched_address: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        tiger_line: str | None = None,
    ) -> None:
        self.key = key
        self.matched = matched
        self.matched_address = matched_address
        self.lat = lat
        self.lon = lon
        self.tiger_line = tiger_line


def _build_csv(rows: list[tuple[str, str, str, str]]) -> bytes:
    """Census batch format, headerless: id, street, city, state, zip."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row_id, street, state, zip_code in rows:
        writer.writerow([row_id, street, "Atlanta", state, zip_code])
    return buf.getvalue().encode("utf-8")


async def geocode_batch(
    client: httpx.AsyncClient,
    addresses: list[tuple[str, str, str]],
    *,
    timeout: float = 180.0,
) -> tuple[dict[str, GeocodeResult], datetime]:
    """Geocode (key, street, zip) triples. Returns results keyed by `key`.

    A key absent from the returned mapping was never answered for; a key present
    with `matched=False` was actively declined by Census. The caller must not
    conflate those two, because only the second is evidence about the address.
    """
    fetched_at = datetime.now(UTC)
    results: dict[str, GeocodeResult] = {}
    usable = [(k, s, "GA", z) for k, s, z in addresses if s and s.strip()]

    for start in range(0, len(usable), CHUNK):
        chunk = usable[start : start + CHUNK]
        payload = _build_csv(chunk)
        try:
            response = await client.post(
                BATCH_URL,
                data={"benchmark": BENCHMARK},
                files={"addressFile": ("addresses.csv", payload, "text/csv")},
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
            )
        except (httpx.TimeoutException, httpx.TransportError):
            # A chunk that never answered tells us nothing about its addresses.
            # Leave those keys absent rather than recording a false "unmatched".
            continue

        if response.status_code != 200 or len(response.content) < 20:
            continue

        text = response.text
        for record in csv.reader(io.StringIO(text)):
            # id, input, match status, match type, matched address, coords, ...
            if len(record) < 3:
                continue
            key, status = record[0], record[2].strip()
            if status == "Match" and len(record) >= 6:
                coords = record[5].split(",") if record[5] else []
                lon = float(coords[0]) if len(coords) == 2 else None
                lat = float(coords[1]) if len(coords) == 2 else None
                results[key] = GeocodeResult(
                    key,
                    True,
                    record[4] or None,
                    lat,
                    lon,
                    record[6] if len(record) > 6 else None,
                )
            elif status in ("No_Match", "Tie"):
                results[key] = GeocodeResult(key, False)

    if not results and usable:
        raise SourceUnavailable(
            f"{BATCH_URL} — geocoded 0 of {len(usable)} addresses; "
            "treating as source outage rather than as evidence"
        )
    return results, fetched_at
