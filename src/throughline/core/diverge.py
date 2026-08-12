"""The divergence engine.

Six deterministic rules. No model runs here, and that is deliberate: the verdict
this system reports has to be reproducible by a person with a spreadsheet and
the same public URLs, or it is worth nothing to the agency that would act on it.
Models adjudicate the ambiguous tail elsewhere; they never decide that a
divergence exists.

Severity is assigned by consequence to a person, not by how wrong the data
looks. A child care facility the state still lists as open, which the city's
current licence roll does not know about, is a place a parent might drive to.
That ranks above a ZIP typo no matter how confident we are in the typo.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from .models import Claim, Divergence, DivergenceKind, Entity, Severity
from .normalize import normalize_address

# A licensing registry is expected to drift a little. Two years is already far
# outside any defensible refresh cadence for data about where children are
# placed, so it is the point at which staleness stops being routine.
STALE_DAYS_HIGH = 730.0
STALE_DAYS_CRITICAL = 1460.0

# Roughly 250 m. Below this, disagreement is geocoder precision and rooftop-vs-
# centroid placement, not a real conflict about where a building is.
GEO_DIVERGENCE_KM = 0.25

CURRENT_AUTHORITY = "atlanta_licenses"
STALE_AUTHORITY = "atlanta_childcare"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _parse_geo(value: str | None) -> tuple[float, float] | None:
    if not value or "," not in value:
        return None
    try:
        lat_s, lon_s = value.split(",", 1)
        return float(lat_s), float(lon_s)
    except ValueError:
        return None


def rule_stale_record(entity: Entity) -> list[Divergence]:
    """The record asserts a fact whose own source date is far in the past.

    This rule reads the timestamp the publisher put on its own data. We are not
    inferring staleness from absence of change; the row says when it was true.
    """
    out: list[Divergence] = []
    for claim in entity.claims:
        if claim.field_name != "status" or claim.observed_at is None:
            continue
        age = claim.age_days
        if age is None or age < STALE_DAYS_HIGH:
            continue
        severity = Severity.CRITICAL if age >= STALE_DAYS_CRITICAL else Severity.HIGH
        years = age / 365.25
        out.append(
            Divergence(
                entity_key=entity.entity_key,
                subject=entity.subject,
                field_name="status",
                kind=DivergenceKind.STALE_RECORD,
                severity=severity,
                confidence=1.0,
                detail=(
                    f"{claim.source} asserts status {claim.value!r}, but the record's own "
                    f"source date is {claim.observed_at.date().isoformat()} "
                    f"— {years:.1f} years ago. It is being served as current."
                ),
                claims=[claim],
            )
        )
    return out


def rule_address_unresolvable(entity: Entity, geocodes: dict) -> list[Divergence]:
    """A municipal authority asserts an address the federal geocoder declines."""
    out: list[Divergence] = []
    for claim in entity.by_field("address"):
        if not claim.value:
            continue
        result = geocodes.get(claim.claim_id)
        # Absent means Census never answered for it, which is evidence about our
        # run and not about the address. Only an explicit non-match counts.
        if result is None or result.matched:
            continue
        out.append(
            Divergence(
                entity_key=entity.entity_key,
                subject=entity.subject,
                field_name="address",
                kind=DivergenceKind.ADDRESS_UNRESOLVABLE,
                severity=Severity.HIGH,
                confidence=0.9,
                detail=(
                    f"{claim.source} lists the address {claim.value!r}, which the U.S. "
                    "Census Bureau geocoder cannot resolve against current TIGER "
                    "address ranges."
                ),
                claims=[claim],
            )
        )
    return out


def rule_geo_divergence(entity: Entity, geocodes: dict) -> list[Divergence]:
    """Published coordinates and the federal geocode disagree about location."""
    out: list[Divergence] = []
    geo_claim = next((c for c in entity.by_field("geo") if c.value), None)
    if geo_claim is None:
        return out
    published = _parse_geo(geo_claim.value)
    if published is None:
        return out

    for addr_claim in entity.by_field("address"):
        result = geocodes.get(addr_claim.claim_id)
        if result is None or not result.matched or result.lat is None:
            continue
        distance = _haversine_km(published[0], published[1], result.lat, result.lon)
        if distance < GEO_DIVERGENCE_KM:
            continue
        out.append(
            Divergence(
                entity_key=entity.entity_key,
                subject=entity.subject,
                field_name="geo",
                kind=DivergenceKind.GEO_DIVERGENCE,
                severity=Severity.MEDIUM,
                confidence=0.8,
                detail=(
                    f"Published coordinates sit {distance:.2f} km from where the U.S. "
                    f"Census Bureau geocodes the same record's own address "
                    f"({addr_claim.value!r})."
                ),
                claims=[geo_claim, addr_claim],
            )
        )
    return out


def rule_zip_mismatch(entity: Entity) -> list[Divergence]:
    """Two authorities put the same place in different ZIP codes."""
    zips = [c for c in entity.by_field("zip") if c.value]
    distinct = {c.value for c in zips}
    if len(distinct) < 2:
        return []
    sources = ", ".join(sorted({f"{c.source}={c.value}" for c in zips}))
    return [
        Divergence(
            entity_key=entity.entity_key,
            subject=entity.subject,
            field_name="zip",
            kind=DivergenceKind.ZIP_MISMATCH,
            severity=Severity.MEDIUM,
            confidence=0.85,
            detail=f"Authorities disagree on ZIP code: {sources}.",
            claims=zips,
        )
    ]


# An authority can only be used as counter-evidence for records it plausibly
# covers. Below this share, "absent from that authority" is a statement about
# the authority's coverage, not about the entity.
MIN_COVERAGE_RATIO = 0.25


def assess_coverage(entities: list[Entity]) -> dict:
    """Measure whether the current authority can corroborate the stale one.

    Written because the first run of this engine produced 656 findings of
    "listed as open, absent from the current licence roll", and that number was
    an artifact rather than a finding. The City of Atlanta's published 2026
    licence roll contains 506 records in total for the entire city, of which 6
    are classified as child day care. A registry of 681 facilities cannot be
    refuted by a roll that small: absence from it carries almost no information.

    Reporting those 656 as divergences would have inflated our own headline
    using a source we had not checked the coverage of, which is precisely the
    failure this product exists to detect. So we measure coverage first and,
    when it is too thin, we say so instead of counting.
    """
    stale_entities = [e for e in entities if STALE_AUTHORITY in e.sources()]
    corroborated = [e for e in stale_entities if CURRENT_AUTHORITY in e.sources()]
    total = len(stale_entities)
    ratio = (len(corroborated) / total) if total else 0.0
    sufficient = ratio >= MIN_COVERAGE_RATIO
    return {
        "stale_authority": STALE_AUTHORITY,
        "current_authority": CURRENT_AUTHORITY,
        "entities_in_stale_authority": total,
        "corroborated_in_current_authority": len(corroborated),
        "coverage_ratio": round(ratio, 4),
        "min_required": MIN_COVERAGE_RATIO,
        "sufficient_for_absence_claims": sufficient,
        "note": (
            "Absence from the current authority is reported as a divergence."
            if sufficient
            else (
                "Absence from the current authority is NOT counted as a divergence. "
                "The published licence roll covers too few of these entities to "
                "support that inference, so a gap here is a limit on the corroborating "
                "source, not evidence about the facility."
            )
        ),
    }


def rule_missing_in_current_authority(entity: Entity, coverage: dict) -> list[Divergence]:
    """Listed as open in the stale registry; absent from the current roll.

    Gated on measured coverage. When the corroborating authority is too thin to
    support the inference, this rule reports nothing at all rather than
    reporting something hedged, because a hedge still lands in the count and the
    count is what people quote.
    """
    if not coverage.get("sufficient_for_absence_claims"):
        return []

    sources = entity.sources()
    if STALE_AUTHORITY not in sources or CURRENT_AUTHORITY in sources:
        return []

    status = entity.one(STALE_AUTHORITY, "status")
    if status is None or (status.value or "").upper() != "OPEN":
        return []

    return [
        Divergence(
            entity_key=entity.entity_key,
            subject=entity.subject,
            field_name="status",
            kind=DivergenceKind.MISSING_IN_CURRENT_AUTHORITY,
            severity=Severity.HIGH,
            confidence=0.6,
            detail=(
                "Listed as OPEN in the state licensing registry snapshot, with no "
                "corresponding record in the City of Atlanta's current business "
                "licence roll. Requires human reconciliation: absence from the "
                "licence roll does not by itself establish that the facility closed."
            ),
            claims=[status],
        )
    ]


def rule_empty_required_field(entity: Entity) -> list[Divergence]:
    """A record that exists, carries a live identifier, and says nothing."""
    out: list[Divergence] = []
    for claim in entity.claims:
        if claim.field_name != "address":
            continue
        if claim.value is not None and normalize_address(claim.value):
            continue
        identifier = claim.raw.get("GADOE_ID") or claim.raw.get("license_number")
        if not identifier:
            continue
        out.append(
            Divergence(
                entity_key=entity.entity_key,
                subject=entity.subject,
                field_name="address",
                kind=DivergenceKind.EMPTY_REQUIRED_FIELD,
                severity=Severity.MEDIUM,
                confidence=1.0,
                detail=(
                    f"Record carries a live identifier ({identifier}) but its address "
                    f"field is empty or unusable ({claim.value!r})."
                ),
                claims=[claim],
            )
        )
    return out


def detect(
    entities: list[Entity],
    geocodes: dict | None = None,
    coverage: dict | None = None,
) -> list[Divergence]:
    """Run every rule over every entity. Ranked by severity, then confidence."""
    geocodes = geocodes or {}
    coverage = coverage if coverage is not None else assess_coverage(entities)
    found: list[Divergence] = []
    for entity in entities:
        found.extend(rule_stale_record(entity))
        found.extend(rule_address_unresolvable(entity, geocodes))
        found.extend(rule_geo_divergence(entity, geocodes))
        found.extend(rule_zip_mismatch(entity))
        found.extend(rule_missing_in_current_authority(entity, coverage))
        found.extend(rule_empty_required_field(entity))

    order = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
    }
    # Deduplicate: the same rule firing twice on one entity and field is one
    # finding, not two, and inflating the count would be the exact dishonesty
    # this product exists to detect.
    unique: dict[str, Divergence] = {}
    for divergence in found:
        unique.setdefault(divergence.divergence_id, divergence)

    return sorted(
        unique.values(),
        key=lambda d: (order[d.severity], -d.confidence, d.subject),
    )


def summarize(entities: list[Entity], divergences: list[Divergence], claims: list[Claim]) -> dict:
    """Aggregate counts. Every number the product displays originates here."""
    by_severity: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for divergence in divergences:
        by_severity[str(divergence.severity)] = by_severity.get(str(divergence.severity), 0) + 1
        by_kind[str(divergence.kind)] = by_kind.get(str(divergence.kind), 0) + 1

    affected = len({d.entity_key for d in divergences})
    total = len(entities)
    return {
        "entities_resolved": total,
        "claims": len(claims),
        "divergences_total": len(divergences),
        "entities_with_divergence": affected,
        # The north star from the spec: the share of records where at least one
        # authority disagrees with another. It should fall over time.
        "divergence_rate": round(affected / total, 4) if total else 0.0,
        "by_severity": by_severity,
        "by_kind": by_kind,
        "computed_at": datetime.now(UTC).isoformat(),
    }
