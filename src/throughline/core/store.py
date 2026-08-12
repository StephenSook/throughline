"""Persistence on TimescaleDB.

Optional by design. Throughline runs and reports correctly with no database at
all — `DATABASE_URL` unset means every endpoint still works from the in-process
run, and the dashboard says so. What the database adds is the thing a snapshot
can never give you: **history**.

The product spec's north-star metric is "divergence rate per field, per
jurisdiction, over time — it should fall." A number without a series behind it
answers "how wrong is the record today" and permanently forecloses "is this
getting better", which is the question an agency has to answer to a court, a
funder, or a consent-decree monitor. So observations are appended, never
overwritten, and the rate is derived.

TimescaleDB specifically, rather than plain Postgres, because that series only
ever grows and the chart has to stay fast as it does: the hourly rate is served
from a pre-materialised continuous aggregate instead of rescanning every
observation ever recorded, and closed chunks compress columnar.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import asyncpg

from .models import Claim, Divergence
from .pipeline import RunResult

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema.sql"


class Store:
    """A thin, honest persistence layer.

    Every method degrades to a no-op when there is no database configured, and
    `status()` reports which state we are in. It must never be ambiguous from
    the outside whether history is being recorded.
    """

    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None
        self.enabled = False
        self.error: str | None = None
        self.timescale_version: str | None = None
        self.dsn_host: str | None = None

    async def connect(self) -> None:
        dsn = os.environ.get("DATABASE_URL", "").strip()
        if not dsn:
            self.error = "DATABASE_URL is not set; running without history."
            return

        # asyncpg does not accept the postgresql+driver or sslmode forms that
        # hosted providers hand out in copy-paste strings.
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

        try:
            self.pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4, timeout=20)
            async with self.pool.acquire() as conn:
                if SCHEMA_PATH.exists():
                    await conn.execute(SCHEMA_PATH.read_text())
                self.timescale_version = await conn.fetchval(
                    "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"
                )
                self.dsn_host = await conn.fetchval("SELECT inet_server_addr()::text")
            self.enabled = True
            self.error = None
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            self.pool = None
            self.enabled = False
            # Surfaced on /api/health. A database that silently failed to
            # connect would leave us reporting a rate with no series behind it
            # while looking exactly like a healthy install.
            self.error = f"{type(exc).__name__}: {exc}"

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "engine": "TimescaleDB" if self.timescale_version else None,
            "timescaledb_version": self.timescale_version,
            "error": self.error,
            "note": (
                "History is being recorded; the divergence-rate chart is served from a "
                "TimescaleDB continuous aggregate."
                if self.enabled
                else "No database configured. Every figure is still computed live from "
                "source; only cross-run history is unavailable."
            ),
        }

    async def persist(self, run: RunResult) -> dict:
        """Append one run. Returns what was written, or why nothing was."""
        if not self.enabled or self.pool is None:
            return {"persisted": False, "reason": self.error or "store disabled"}

        finished = run.finished_at or run.started_at
        try:
            async with self.pool.acquire() as conn, conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO runs (run_id, started_at, finished_at, healthy,
                        entities_resolved, claims, divergences_total, divergence_rate,
                        elapsed_ms, coverage, sources, adjudication)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                    ON CONFLICT (run_id) DO NOTHING
                    """,
                    run.run_id,
                    run.started_at,
                    finished,
                    run.healthy,
                    run.summary.get("entities_resolved", 0),
                    run.summary.get("claims", 0),
                    run.summary.get("divergences_total", 0),
                    float(run.summary.get("divergence_rate", 0.0)),
                    int(run.summary.get("elapsed_ms", 0)),
                    json.dumps(run.coverage, default=str),
                    json.dumps(run.sources, default=str),
                    json.dumps(run.summary.get("adjudication"), default=str),
                )

                await conn.copy_records_to_table(
                    "divergence_observations",
                    records=[self._obs_row(finished, run.run_id, d) for d in run.divergences],
                    columns=[
                        "observed_at",
                        "run_id",
                        "divergence_id",
                        "entity_key",
                        "subject",
                        "field",
                        "kind",
                        "severity",
                        "confidence",
                        "source",
                        "adjudicated",
                        "detail",
                    ],
                )

                # Claims are the evidence layer. Deduplicated per run because a
                # claim can back more than one divergence and double-storing it
                # would inflate the corpus without adding evidence.
                seen: set[str] = set()
                claim_rows = []
                for claim in run.claims:
                    if claim.claim_id in seen:
                        continue
                    seen.add(claim.claim_id)
                    claim_rows.append(self._claim_row(run.run_id, claim))

                await conn.copy_records_to_table(
                    "claim_observations",
                    records=claim_rows,
                    columns=[
                        "fetched_at",
                        "run_id",
                        "claim_id",
                        "entity_key",
                        "subject",
                        "field",
                        "value",
                        "source",
                        "source_url",
                        "observed_at",
                        "sha256",
                        "raw",
                    ],
                )

            return {
                "persisted": True,
                "run_id": run.run_id,
                "observations": len(run.divergences),
                "claims": len(claim_rows),
            }
        except Exception as exc:  # noqa: BLE001
            return {"persisted": False, "reason": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _obs_row(finished, run_id: str, d: Divergence) -> tuple:
        source = d.claims[0].source if d.claims else None
        return (
            finished,
            run_id,
            d.divergence_id,
            d.entity_key,
            d.subject,
            d.field_name,
            str(d.kind),
            str(d.severity),
            float(d.confidence),
            source,
            d.adjudication is not None,
            d.detail,
        )

    @staticmethod
    def _claim_row(run_id: str, c: Claim) -> tuple:
        raw = {k: v for k, v in c.raw.items() if k != "_geometry"}
        return (
            c.fetched_at,
            run_id,
            c.claim_id,
            c.entity_key,
            c.subject,
            c.field_name,
            c.value,
            c.source,
            c.source_url,
            c.observed_at,
            c.sha256,
            json.dumps(raw, default=str),
        )

    async def rate_series(self, hours: int = 168) -> list[dict]:
        """Read the north-star metric from the continuous aggregate."""
        if not self.enabled or self.pool is None:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT bucket, kind, severity, observations, entities_affected,
                       mean_confidence
                FROM divergence_rate_hourly
                WHERE bucket > now() - ($1 || ' hours')::interval
                ORDER BY bucket
                """,
                str(hours),
            )
        return [
            {
                "bucket": r["bucket"].isoformat(),
                "kind": r["kind"],
                "severity": r["severity"],
                "observations": r["observations"],
                "entities_affected": r["entities_affected"],
                "mean_confidence": round(float(r["mean_confidence"]), 3),
            }
            for r in rows
        ]

    async def run_history(self, limit: int = 100) -> list[dict]:
        if not self.enabled or self.pool is None:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT run_id, finished_at, divergence_rate, divergences_total,
                       entities_resolved, healthy
                FROM runs ORDER BY started_at DESC LIMIT $1
                """,
                limit,
            )
        return [
            {
                "run_id": r["run_id"],
                "at": r["finished_at"].isoformat() if r["finished_at"] else None,
                "divergence_rate": r["divergence_rate"],
                "divergences_total": r["divergences_total"],
                "entities_resolved": r["entities_resolved"],
                "healthy": r["healthy"],
            }
            for r in reversed(rows)
        ]

    async def hypertable_stats(self) -> dict:
        """Proof the hypertable and continuous aggregate are real, not claimed."""
        if not self.enabled or self.pool is None:
            return {}
        async with self.pool.acquire() as conn:
            hypertables = await conn.fetch(
                "SELECT hypertable_name, num_chunks, compression_enabled "
                "FROM timescaledb_information.hypertables"
            )
            caggs = await conn.fetch(
                "SELECT view_name, materialization_hypertable_name, compression_enabled "
                "FROM timescaledb_information.continuous_aggregates"
            )
            total_obs = await conn.fetchval("SELECT count(*) FROM divergence_observations")
            total_claims = await conn.fetchval("SELECT count(*) FROM claim_observations")
        return {
            "hypertables": [dict(h) for h in hypertables],
            "continuous_aggregates": [dict(c) for c in caggs],
            "total_observations": total_obs,
            "total_claims_stored": total_claims,
        }


STORE_DB = Store()
