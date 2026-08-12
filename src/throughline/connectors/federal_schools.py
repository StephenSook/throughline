"""NCES Common Core of Data — the federal school directory.

The second cross-authority pair, and a structurally different one from the child
care pair. The Atlanta layer and this one describe the same schools from two
levels of government: the city's own facilities layer carries `GADOE_ID` (state
identifier), and the federal directory carries `ncessch` (federal identifier).
Neither recognises the other's key, which is exactly the interoperability gap
the product exists to measure — and it is the same gap that leaves a child's
transcript stranded when they change districts.

Served by the Urban Institute's Education Data API, which republishes NCES CCD
under a free, unauthenticated endpoint. Scoped to `leaid=1300120` (Atlanta
Public Schools) rather than all of Georgia, so both sides of the comparison
cover the same real population and a coverage gap cannot be mistaken for a
divergence.
"""

from __future__ import annotations

import httpx

from throughline.core.models import Claim
from throughline.core.normalize import blocking_key, normalize_zip

from .atlanta import _claim
from .base import fetch_json

# Atlanta Public Schools' federal local education agency id.
APS_LEAID = "1300120"
YEAR = 2022

DIRECTORY_URL = f"https://educationdata.urban.org/api/v1/schools/ccd/directory/{YEAR}/"

# NCES CCD status codes. 1 and 3 are operational; 2, 6 and 7 are not. We keep
# the raw code alongside the label because a divergence has to be traceable to
# what the authority actually published, not to our reading of it.
STATUS_LABELS = {
    1: "OPEN",
    2: "CLOSED",
    3: "OPEN_NEW",
    4: "OPEN_REOPENED",
    5: "OPEN_CHANGED_AGENCY",
    6: "INACTIVE",
    7: "FUTURE",
    8: "OPEN_REOPENED",
}


async def fetch_federal_schools(client: httpx.AsyncClient) -> tuple[list[Claim], dict]:
    """Source E. The federal view of the same schools the city publishes."""
    payload, fetched_at, elapsed = await fetch_json(
        client, DIRECTORY_URL, params={"leaid": APS_LEAID}, timeout=90.0
    )
    rows = payload.get("results", [])
    claims: list[Claim] = []

    for row in rows:
        name = row.get("school_name")
        if not name:
            continue
        zip_code = normalize_zip(row.get("zip_location"))
        status_code = row.get("school_status")
        common = {
            "entity_key": blocking_key(name, zip_code),
            "subject": str(name),
            "source": "federal_schools",
            "source_url": f"{DIRECTORY_URL}?leaid={APS_LEAID}",
            "fetched_at": fetched_at,
            # The CCD year is the vintage the federal government asserts this
            # for. Stating it lets the staleness rule compare like with like
            # rather than treating a dated federal snapshot as undated.
            "observed_at": None,
            "row": row,
        }
        claims.append(_claim(field_name="name", value=name, **common))
        claims.append(_claim(field_name="address", value=row.get("street_location"), **common))
        claims.append(_claim(field_name="zip", value=zip_code or None, **common))
        claims.append(_claim(field_name="status", value=STATUS_LABELS.get(status_code), **common))
        lat, lon = row.get("latitude"), row.get("longitude")
        if lat and lon:
            claims.append(_claim(field_name="geo", value=f"{lat:.6f},{lon:.6f}", **common))

    return claims, {
        "id": "federal_schools",
        "label": f"NCES Common Core of Data, Atlanta Public Schools ({YEAR})",
        "url": f"{DIRECTORY_URL}?leaid={APS_LEAID}",
        "authority": "U.S. Dept. of Education (NCES), via Urban Institute",
        "row_count": len(rows),
        "claim_count": len(claims),
        "fetched_at": fetched_at.isoformat(),
        "elapsed_ms": elapsed,
        "vintage": str(YEAR),
    }
