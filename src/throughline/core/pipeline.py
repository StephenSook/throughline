"""The reconciliation run.

ingest -> resolve -> diverge. One function, so that the API endpoint, the CLI,
and the Render Workflow all execute the same code path and cannot drift apart.

A run reports what it could not do as loudly as what it could. If a source is
unreachable, the run still completes over the sources that answered and records
the outage in `sources`, because a reconciliation that silently narrows its
input and then reports a lower divergence rate is worse than no reconciliation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from throughline.connectors import atlanta, census, federal_schools
from throughline.connectors.base import SourceUnavailable

from .diverge import assess_coverage, detect, summarize
from .models import Claim, Divergence
from .resolve import MatchCandidate, resolve


@dataclass(slots=True)
class RunResult:
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    claims: list[Claim] = field(default_factory=list)
    divergences: list[Divergence] = field(default_factory=list)
    candidates: list[MatchCandidate] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    coverage: dict = field(default_factory=dict)
    entity_count: int = 0

    @property
    def elapsed_ms(self) -> int:
        if self.finished_at is None:
            return 0
        return int((self.finished_at - self.started_at).total_seconds() * 1000)

    @property
    def healthy(self) -> bool:
        return all(s.get("ok") for s in self.sources)


async def run_reconciliation(*, geocode: bool = True) -> RunResult:
    started = datetime.now(UTC)
    run_id = f"run_{started.strftime('%Y%m%dT%H%M%S')}"
    result = RunResult(run_id=run_id, started_at=started)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        fetchers = {
            "atlanta_childcare": atlanta.fetch_childcare,
            "atlanta_licenses": atlanta.fetch_licenses,
            "atlanta_schools": atlanta.fetch_schools,
            "federal_schools": federal_schools.fetch_federal_schools,
        }
        gathered = await asyncio.gather(
            *(fn(client) for fn in fetchers.values()), return_exceptions=True
        )

        for source_id, outcome in zip(fetchers, gathered, strict=True):
            if isinstance(outcome, SourceUnavailable):
                result.sources.append({"id": source_id, "ok": False, "error": str(outcome)})
                continue
            if isinstance(outcome, BaseException):
                result.sources.append(
                    {"id": source_id, "ok": False, "error": f"{type(outcome).__name__}: {outcome}"}
                )
                continue
            claims, meta = outcome
            result.claims.extend(claims)
            result.sources.append({**meta, "ok": True})

        entities, candidates = resolve(result.claims)
        result.candidates = candidates
        result.entity_count = len(entities)

        geocodes: dict = {}
        if geocode:
            # Key each geocode by claim_id so a divergence can point at exactly
            # the address claim that Census declined, rather than at a string
            # that might appear on several records.
            requests: list[tuple[str, str, str]] = []
            seen: set[str] = set()
            for entity in entities:
                for claim in entity.by_field("address"):
                    if not claim.value or claim.claim_id in seen:
                        continue
                    seen.add(claim.claim_id)
                    zip_claim = next((c.value for c in entity.by_field("zip") if c.value), "")
                    requests.append((claim.claim_id, claim.value, zip_claim or ""))
            try:
                geocodes, geo_fetched = await census.geocode_batch(client, requests)
                matched = sum(1 for g in geocodes.values() if g.matched)
                result.sources.append(
                    {
                        "id": "census_geocoder",
                        "label": "U.S. Census Bureau Geocoder (Public_AR_Current)",
                        "url": census.BATCH_URL,
                        "authority": "U.S. Census Bureau",
                        "ok": True,
                        "row_count": len(geocodes),
                        "claim_count": len(requests),
                        "matched": matched,
                        "unmatched": len(geocodes) - matched,
                        "fetched_at": geo_fetched.isoformat(),
                    }
                )
            except SourceUnavailable as exc:
                result.sources.append({"id": "census_geocoder", "ok": False, "error": str(exc)})

        coverage = assess_coverage(entities)
        result.coverage = coverage
        result.divergences = detect(entities, geocodes, coverage)
        result.summary = summarize(entities, result.divergences, result.claims)
        result.summary["coverage"] = coverage

    result.finished_at = datetime.now(UTC)
    result.summary["elapsed_ms"] = result.elapsed_ms
    result.summary["run_id"] = run_id
    result.summary["sources_ok"] = sum(1 for s in result.sources if s.get("ok"))
    result.summary["sources_total"] = len(result.sources)
    return result
