"""City of Atlanta ArcGIS connectors.

Three layers on one ArcGIS Online organisation, each an independent authority
about places in Atlanta:

  A  Atlanta_Child_Care_Facilities: the city's republication of the Georgia
     DECAL state licensing registry. Every row carries its own SOURCE and
     SOURCEDATE, and that SOURCEDATE is 2021-10-21. The provenance we need is
     already in the data; nobody had read it.
  B  Business_Licenses_2026: the city's own occupational tax licence
     roll. Independent of A, and current, but small: see the coverage gate in
     `core.diverge`, which measures whether it is large enough to corroborate.
  D  Atlanta_Public_Schools: school facilities, carrying GADOE_ID,
     which lets us join to the federal directory.

Georgia DECAL's own API (dcle2-decalapiprd.azurewebsites.net) is auth-gated and
returns 401, which is precisely why layer A matters: it is the only public view
of that registry, and it has been frozen since 2021.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from throughline.core.models import Claim
from throughline.core.normalize import blocking_key, normalize_zip

from .base import fetch_json

ORG = "https://services5.arcgis.com/5RxyIIJ9boPdptdo/ArcGIS/rest/services"

# Layer ids are not guessable and not sequential; they were read off each
# service's own /FeatureServer?f=json descriptor.
CHILDCARE_URL = f"{ORG}/Atlanta_Child_Care_Facilities/FeatureServer/6/query"
LICENSES_URL = f"{ORG}/Business_Licenses_2026/FeatureServer/50/query"
SCHOOLS_URL = f"{ORG}/Atlanta_Public_Schools/FeatureServer/0/query"

_QUERY = {"where": "1=1", "outFields": "*", "f": "json", "resultRecordCount": 2000}


def _epoch_ms_to_dt(value) -> datetime | None:
    """ArcGIS dates are epoch milliseconds, and are frequently null."""
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _claim(
    *,
    entity_key: str,
    subject: str,
    field_name: str,
    value,
    source: str,
    source_url: str,
    fetched_at: datetime,
    observed_at: datetime | None,
    row: dict,
) -> Claim:
    """Build one claim.

    Module level and fully explicit rather than a closure over the ingest loop:
    a closure would capture the loop variable by reference, which is a class of
    bug where every claim in a batch silently ends up describing the last row.
    """
    return Claim(
        entity_key=entity_key,
        subject=subject,
        field_name=field_name,
        value=None if value in (None, "") else str(value).strip(),
        source=source,
        source_url=source_url,
        fetched_at=fetched_at,
        observed_at=observed_at,
        confidence=1.0,
        raw=row,
    )


async def _fetch_features(client: httpx.AsyncClient, url: str) -> tuple[list[dict], datetime, int]:
    payload, fetched_at, elapsed = await fetch_json(client, url, params=_QUERY)
    features = payload.get("features", [])
    rows = [f.get("attributes", {}) for f in features]
    geoms = [f.get("geometry") for f in features]
    for row, geom in zip(rows, geoms, strict=False):
        if geom:
            row["_geometry"] = geom
    return rows, fetched_at, elapsed


async def fetch_childcare(client: httpx.AsyncClient) -> tuple[list[Claim], dict]:
    """Source A. The stale state registry, republished as current."""
    rows, fetched_at, elapsed = await _fetch_features(client, CHILDCARE_URL)
    claims: list[Claim] = []

    for row in rows:
        name = row.get("NAME")
        if not name:
            continue
        zip_code = normalize_zip(row.get("ZIP"))
        key = blocking_key(name, zip_code)
        # SOURCEDATE is when DECAL asserted this, not when we read it. The gap
        # between those two timestamps is the entire finding.
        observed = _epoch_ms_to_dt(row.get("SOURCEDATE"))

        common = {
            "entity_key": key,
            "subject": str(name),
            "source": "atlanta_childcare",
            "source_url": CHILDCARE_URL,
            "fetched_at": fetched_at,
            "observed_at": observed,
            "row": row,
        }
        claims.append(_claim(field_name="name", value=name, **common))
        claims.append(_claim(field_name="address", value=row.get("ADDRESS"), **common))
        claims.append(_claim(field_name="zip", value=zip_code or None, **common))
        claims.append(_claim(field_name="status", value=row.get("STATUS"), **common))
        lat, lon = row.get("LATITUDE"), row.get("LONGITUDE")
        if lat and lon:
            geo = f"{float(lat):.6f},{float(lon):.6f}"
            claims.append(_claim(field_name="geo", value=geo, **common))

    declared = _epoch_ms_to_dt(rows[0].get("SOURCEDATE")) if rows else None
    meta = {
        "id": "atlanta_childcare",
        "label": "Atlanta Child Care Facilities (City of Atlanta GIS)",
        "url": CHILDCARE_URL,
        "authority": "City of Atlanta, republishing Georgia DECAL",
        "row_count": len(rows),
        "claim_count": len(claims),
        "fetched_at": fetched_at.isoformat(),
        "elapsed_ms": elapsed,
        # Read off the data itself rather than asserted by us.
        "declared_source": rows[0].get("SOURCE") if rows else None,
        "declared_source_date": declared.isoformat() if declared else None,
    }
    return claims, meta


async def fetch_licenses(client: httpx.AsyncClient) -> tuple[list[Claim], dict]:
    """Source B. The city's own licence roll, the independent check."""
    rows, fetched_at, elapsed = await _fetch_features(client, LICENSES_URL)
    claims: list[Claim] = []

    for row in rows:
        name = row.get("business_name") or row.get("BUSINESS_NAME")
        if not name:
            continue
        zip_code = normalize_zip(row.get("zip") or row.get("ZIP"))
        common = {
            "entity_key": blocking_key(name, zip_code),
            "subject": str(name),
            "source": "atlanta_licenses",
            "source_url": LICENSES_URL,
            "fetched_at": fetched_at,
            "observed_at": _epoch_ms_to_dt(row.get("commence_date")),
            "row": row,
        }
        address = row.get("street_address_1") or row.get("STREET_ADDRESS_1")
        claims.append(_claim(field_name="name", value=name, **common))
        claims.append(_claim(field_name="address", value=address, **common))
        claims.append(_claim(field_name="zip", value=zip_code or None, **common))
        claims.append(_claim(field_name="naics", value=row.get("naics_code"), **common))

    return claims, {
        "id": "atlanta_licenses",
        "label": "Atlanta Business Licenses 2026 (City of Atlanta Revenue)",
        "url": LICENSES_URL,
        "authority": "City of Atlanta, Department of Revenue",
        "row_count": len(rows),
        "claim_count": len(claims),
        "fetched_at": fetched_at.isoformat(),
        "elapsed_ms": elapsed,
    }


async def fetch_schools(client: httpx.AsyncClient) -> tuple[list[Claim], dict]:
    """Source D. School facilities, carrying GADOE_ID for the federal join."""
    rows, fetched_at, elapsed = await _fetch_features(client, SCHOOLS_URL)
    claims: list[Claim] = []

    for row in rows:
        # Some rows carry a GADOE_Name and a live GADOE_ID but a null SchoolName
        # and a blank address. That is not a parsing problem on our side, it is
        # the defect, so we keep the row and let the divergence rules speak.
        name = row.get("SchoolName") or row.get("GADOE_Name")
        if not name:
            continue
        zip_code = normalize_zip(row.get("ZIP_CODE"))
        common = {
            "entity_key": blocking_key(name, zip_code),
            "subject": str(name),
            "source": "atlanta_schools",
            "source_url": SCHOOLS_URL,
            "fetched_at": fetched_at,
            "observed_at": None,
            "row": row,
        }
        claims.append(_claim(field_name="name", value=name, **common))
        claims.append(_claim(field_name="address", value=row.get("ADDRESS"), **common))
        claims.append(_claim(field_name="zip", value=zip_code or None, **common))
        claims.append(_claim(field_name="status", value=row.get("Status"), **common))

    return claims, {
        "id": "atlanta_schools",
        "label": "Atlanta Public Schools facilities (City of Atlanta GIS)",
        "url": SCHOOLS_URL,
        "authority": "City of Atlanta / Atlanta Public Schools",
        "row_count": len(rows),
        "claim_count": len(claims),
        "fetched_at": fetched_at.isoformat(),
        "elapsed_ms": elapsed,
    }
