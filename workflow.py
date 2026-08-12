"""Render Workflow — continuous record-integrity monitoring.

This is the product's real production shape, not a demo wrapper. The spec's
Phase 1 is *"productize the audit as continuous monitoring"*: a one-off answer
to "how wrong is the record" is a consulting deliverable, whereas the thing an
agency can act on is a number that gets recomputed on a schedule and watched for
movement. The API's `POST /api/runs` exists so a human can force a run; this
workflow is how it happens without one.

Why a Workflow rather than a cron job or a background worker:

* **Per-task retries and timeouts.** Four third-party public endpoints, three of
  them municipal. They rate-limit, they 500, and one candidate source was
  already dead when we started. A source that fails needs to retry with backoff
  on its own without dragging the other three down with it.
* **Fan-out.** Source checks are independent and run concurrently, then a single
  reconcile consumes the result. That is an orchestration graph, which is what a
  Workflow expresses and what a cron entry cannot.
* **Scales to zero.** Reconciliation is bursty: seconds of work on an interval.
  Paying for an always-on worker to idle between runs would be wrong.

Deployed as a separate Render service (New > Workflow). Render Blueprints cannot
yet declare Workflows, so `render.yaml` deliberately does not try to.
"""

from __future__ import annotations

import asyncio

from render_sdk import Retry, Workflows

from throughline.connectors import atlanta
from throughline.core.state import STORE

app = Workflows(
    # Municipal ArcGIS endpoints are intermittently slow rather than reliably
    # down, so retry with backoff before declaring a source unavailable.
    default_retry=Retry(max_retries=3, wait_duration_ms=1500, backoff_scaling=1.5),
    default_timeout=900,
    default_plan="starter",
)

SOURCES = {
    "atlanta_childcare": atlanta.CHILDCARE_URL,
    "atlanta_licenses": atlanta.LICENSES_URL,
    "atlanta_schools": atlanta.SCHOOLS_URL,
}


@app.task(
    name="check_source",
    retry=Retry(max_retries=3, wait_duration_ms=1000, backoff_scaling=2.0),
    timeout_seconds=180,
)
def check_source(source_id: str) -> dict:
    """Probe one authority. Fans out — one invocation per source.

    Reports reachability and row count without interpreting anything. Each
    source retries in isolation, which is the whole reason these are separate
    tasks rather than one loop.
    """
    import httpx

    from throughline.connectors.base import SourceUnavailable, fetch_json

    url = SOURCES.get(source_id)
    if url is None:
        raise ValueError(f"unknown source {source_id!r}")

    async def _probe() -> dict:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            try:
                payload, fetched_at, elapsed_ms = await fetch_json(
                    client,
                    url,
                    params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
                )
            except SourceUnavailable as exc:
                # Returned rather than raised once retries are exhausted: an
                # unreachable source is a finding the product must surface, not
                # a crash that hides the other three.
                return {"source": source_id, "ok": False, "error": str(exc), "url": url}
            return {
                "source": source_id,
                "ok": True,
                "row_count": payload.get("count"),
                "elapsed_ms": elapsed_ms,
                "fetched_at": fetched_at.isoformat(),
                "url": url,
            }

    return asyncio.run(_probe())


@app.task(
    name="reconcile",
    retry=Retry(max_retries=2, wait_duration_ms=3000, backoff_scaling=2.0),
    timeout_seconds=900,
)
def reconcile(adjudicate_tail: bool = True) -> dict:
    """Run a full reconciliation and append the result to history.

    Deliberately calls the same `STORE.execute` the HTTP API calls. One code
    path for the scheduled run and the human-triggered run, so the scheduled
    number and the number on the dashboard cannot drift apart.
    """
    run = asyncio.run(STORE.execute(geocode=True, adjudicate_tail=adjudicate_tail))
    summary = run.summary
    return {
        "run_id": run.run_id,
        "healthy": run.healthy,
        "elapsed_ms": run.elapsed_ms,
        "entities_resolved": summary.get("entities_resolved"),
        "divergences_total": summary.get("divergences_total"),
        "divergence_rate": summary.get("divergence_rate"),
        "persistence": summary.get("persistence"),
        "coverage_sufficient": (run.coverage or {}).get("sufficient_for_absence_claims"),
        "sources": [{"id": s.get("id"), "ok": s.get("ok")} for s in run.sources],
    }


@app.task(name="monitor", timeout_seconds=1800)
def monitor() -> dict:
    """Fan out over every source, then reconcile. The scheduled entry point."""
    checks = [check_source(source_id) for source_id in SOURCES]
    unreachable = [c["source"] for c in checks if not c.get("ok")]

    # Reconcile regardless. A partial run over the sources that answered is more
    # useful than no run, and the result records which sources were missing so a
    # narrowed input can never be mistaken for an improved divergence rate.
    result = reconcile()
    result["source_checks"] = checks
    result["unreachable"] = unreachable
    return result


if __name__ == "__main__":
    app.start()
