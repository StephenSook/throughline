"""In-process run state.

Holds the most recent reconciliation run plus a **golden run**: the last run
that completed with every source healthy. If a source goes down, the product
keeps serving the golden run and says so, loudly, on every surface.

That distinction is the whole point. A dashboard that silently serves stale
results while its inputs are unreachable is committing the exact failure this
system exists to detect, and we do not get to reproduce it ourselves.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from .models import Claim, Divergence
from .pipeline import RunResult, run_reconciliation


class RunStore:
    def __init__(self) -> None:
        self.current: RunResult | None = None
        self.golden: RunResult | None = None
        self.history: list[dict] = []
        self.last_error: str | None = None
        self._lock = asyncio.Lock()
        self._claims: dict[str, Claim] = {}
        self._divergences: dict[str, Divergence] = {}

    @property
    def serving_golden(self) -> bool:
        """True when what we are serving is not what we last tried to fetch."""
        return self.current is not None and not self.current.healthy and self.golden is not None

    def active(self) -> RunResult | None:
        if self.current is not None and self.current.healthy:
            return self.current
        return self.golden or self.current

    def _index(self, run: RunResult) -> None:
        self._claims = {c.claim_id: c for c in run.claims}
        self._divergences = {d.divergence_id: d for d in run.divergences}

    def claim(self, claim_id: str) -> Claim | None:
        return self._claims.get(claim_id)

    def divergence(self, divergence_id: str) -> Divergence | None:
        return self._divergences.get(divergence_id)

    async def execute(self, *, geocode: bool = True) -> RunResult:
        """Run reconciliation, promoting to golden only on a fully healthy run."""
        async with self._lock:
            try:
                run = await run_reconciliation(geocode=geocode)
            except Exception as exc:  # noqa: BLE001 - surfaced, never swallowed
                self.last_error = f"{type(exc).__name__}: {exc}"
                raise

            self.last_error = None
            self.current = run
            if run.healthy:
                self.golden = run
            self._index(self.active() or run)

            summary = self.active().summary if self.active() else run.summary
            self.history.append(
                {
                    "run_id": run.run_id,
                    "at": run.finished_at.isoformat() if run.finished_at else None,
                    "divergence_rate": summary.get("divergence_rate"),
                    "divergences_total": summary.get("divergences_total"),
                    "entities_resolved": summary.get("entities_resolved"),
                    "healthy": run.healthy,
                }
            )
            return run

    def banner(self) -> dict | None:
        """The visible degradation notice. None when everything is healthy."""
        if not self.serving_golden or self.golden is None:
            return None
        live = self.current.sources if self.current else []
        failed = [s.get("id") for s in live if not s.get("ok")]
        at = self.golden.finished_at.isoformat() if self.golden.finished_at else "unknown"
        return {
            "degraded": True,
            "message": (
                f"Showing cached run {self.golden.run_id} from {at}. "
                f"Live sources unreachable: {', '.join(failed) or 'unknown'}."
            ),
            "failed_sources": failed,
            "cached_run_id": self.golden.run_id,
        }


STORE = RunStore()


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
