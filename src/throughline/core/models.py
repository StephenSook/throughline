"""The data model.

Two ideas carry the whole system.

A **Claim** is one authority's assertion about one field of one entity, at one
point in time, with the evidence attached. We never collapse claims into a
"current value" — that collapse is exactly what the institutions we read from
already did, and it is what destroyed the information we are trying to recover.

A **Divergence** is what we found when two authorities disagreed. It carries the
claims that produced it, so every number this system reports can be walked back
to a source URL and a fetch timestamp by a person who does not trust us.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class Severity(StrEnum):
    """Ranked by consequence to a person, never by age of the record.

    The spec is explicit that the supervisor worklist sorts by child-safety
    severity and not by how long a flag has been sitting there.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DivergenceKind(StrEnum):
    STALE_RECORD = "STALE_RECORD"
    ADDRESS_UNRESOLVABLE = "ADDRESS_UNRESOLVABLE"
    GEO_DIVERGENCE = "GEO_DIVERGENCE"
    ZIP_MISMATCH = "ZIP_MISMATCH"
    MISSING_IN_CURRENT_AUTHORITY = "MISSING_IN_CURRENT_AUTHORITY"
    EMPTY_REQUIRED_FIELD = "EMPTY_REQUIRED_FIELD"


def _canonical_sha256(payload: dict) -> str:
    """Content hash of a source record.

    Length-prefixing is unnecessary here because we hash a single JSON document
    rather than joining fields, but the ordering must be stable or the same
    record hashes differently on every run and provenance becomes meaningless.
    """
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Claim:
    """One authority's assertion about one field, with its evidence."""

    entity_key: str
    subject: str
    field_name: str
    value: str | None
    source: str
    source_url: str
    fetched_at: datetime
    observed_at: datetime | None = None
    confidence: float = 1.0
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.raw)

    @property
    def claim_id(self) -> str:
        """Stable identifier. Built from length-prefixed parts, never a join.

        Joining on a separator lets ("a\\x1fb", "c") and ("a", "b\\x1fc") collide
        into one identity, which would silently deduplicate two distinct claims.
        Length-prefixing removes the class rather than banning a character we
        cannot police in third-party data.
        """
        parts = [self.source, self.entity_key, self.field_name, self.value or ""]
        material = "".join(f"{len(p)}:{p}" for p in parts)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    @property
    def age_days(self) -> float | None:
        """How old the *asserted* fact is, not how recently we fetched it."""
        if self.observed_at is None:
            return None
        now = datetime.now(UTC)
        observed = self.observed_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        return (now - observed).total_seconds() / 86400.0


@dataclass(slots=True)
class Entity:
    """A real-world thing that several authorities each describe separately."""

    entity_key: str
    subject: str
    claims: list[Claim] = field(default_factory=list)
    match_scores: dict[str, float] = field(default_factory=dict)

    def sources(self) -> set[str]:
        return {c.source for c in self.claims}

    def by_field(self, field_name: str) -> list[Claim]:
        return [c for c in self.claims if c.field_name == field_name]

    def one(self, source: str, field_name: str) -> Claim | None:
        for c in self.claims:
            if c.source == source and c.field_name == field_name:
                return c
        return None


@dataclass(slots=True)
class Divergence:
    """A disagreement between authorities, with the claims that produced it."""

    entity_key: str
    subject: str
    field_name: str
    kind: DivergenceKind
    severity: Severity
    confidence: float
    detail: str
    claims: list[Claim] = field(default_factory=list)
    adjudication: dict | None = None

    @property
    def divergence_id(self) -> str:
        parts = [self.entity_key, self.field_name, str(self.kind)]
        material = "".join(f"{len(p)}:{p}" for p in parts)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "id": self.divergence_id,
            "entity_key": self.entity_key,
            "subject": self.subject,
            "field": self.field_name,
            "kind": str(self.kind),
            "severity": str(self.severity),
            "confidence": round(self.confidence, 3),
            "detail": self.detail,
            "adjudication": self.adjudication,
            "values": [
                {
                    "claim_id": c.claim_id,
                    "source": c.source,
                    "source_url": c.source_url,
                    "value": c.value,
                    "observed_at": c.observed_at.isoformat() if c.observed_at else None,
                    "fetched_at": c.fetched_at.isoformat(),
                    "age_days": round(c.age_days, 1) if c.age_days is not None else None,
                    "confidence": c.confidence,
                    "sha256": c.sha256,
                }
                for c in self.claims
            ],
        }
