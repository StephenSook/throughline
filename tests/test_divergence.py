"""Tests for the divergence rules.

These are the tests that matter, because the rules are what produce the numbers
the product reports. They are pure functions over constructed claims, so every
case here is a statement about what Throughline will and will not call a defect.

Deliberately absent: any assertion of a specific divergence count against live
Atlanta data. Those numbers change when the city republishes, and an assertion
like `assert total == 791` would turn a correct update into a red build. Worse,
a figure hard-coded into a test is a figure the suite then *defends* — correcting
it later reads as a regression. Tests here assert behaviour; the live numbers are
computed and displayed, never asserted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from throughline.core.diverge import (
    MIN_COVERAGE_RATIO,
    assess_coverage,
    detect,
    rule_address_mismatch,
    rule_empty_required_field,
    rule_missing_in_current_authority,
    rule_stale_record,
    rule_status_conflict,
    rule_zip_mismatch,
    summarize,
)
from throughline.core.models import Claim, DivergenceKind, Entity, Severity
from throughline.core.normalize import (
    blocking_key,
    normalize_address,
    normalize_name,
    normalize_zip,
)

NOW = datetime.now(UTC)


def claim(
    *,
    source: str,
    field_name: str,
    value: str | None,
    observed_at: datetime | None = None,
    subject: str = "TEST FACILITY",
    raw: dict | None = None,
) -> Claim:
    return Claim(
        entity_key="30318|TEST",
        subject=subject,
        field_name=field_name,
        value=value,
        source=source,
        source_url=f"https://example.invalid/{source}",
        fetched_at=NOW,
        observed_at=observed_at,
        raw=raw or {},
    )


def entity(*claims: Claim) -> Entity:
    return Entity(entity_key="30318|TEST", subject="TEST FACILITY", claims=list(claims))


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------


class TestNormalize:
    def test_directional_with_periods_collapses(self):
        """'929 CHARLES ALLEN DRIVE N. E.' is a real row in the Atlanta data."""
        assert normalize_address("929 CHARLES ALLEN DRIVE N. E.") == "929 CHARLES ALLEN DR NE"

    def test_two_spellings_of_one_address_agree(self):
        left = normalize_address("1605 DONALD LEE HOLLOWELL PKWY NW")
        right = normalize_address("1605 Donald Lee Hollowell Parkway Northwest")
        assert left == right

    def test_quadrant_is_preserved(self):
        """Atlanta is quadrant-addressed; NW and NE are genuinely different places."""
        assert normalize_address("100 MAIN ST NW") != normalize_address("100 MAIN ST NE")

    def test_unit_noise_removed(self):
        assert normalize_address("500 PEACHTREE ST NE SUITE 200") == "500 PEACHTREE ST NE"

    @pytest.mark.parametrize("blank", [None, "", "   ", "\t"])
    def test_blank_address_is_empty_not_invented(self, blank):
        """A blank address must stay detectably blank — it is itself a finding."""
        assert normalize_address(blank) == ""

    def test_org_suffixes_dropped_from_names(self):
        assert normalize_name("21ST CENTURY LEADERS INC.") == normalize_name("21st Century Leaders")

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("30318", "30318"), (30318, "30318"), ("30318-1234", "30318"), ("303", ""), (None, "")],
    )
    def test_zip_normalization(self, raw, expected):
        assert normalize_zip(raw) == expected

    def test_blocking_key_groups_plausible_matches(self):
        assert blocking_key("Bright Start Academy", "30318") == blocking_key(
            "BRIGHT START ACADEMY INC", 30318
        )


# --------------------------------------------------------------------------
# Claim identity
# --------------------------------------------------------------------------


class TestClaimIdentity:
    def test_separator_injection_cannot_collide_two_claims(self):
        """Length-prefixed identity, so a separator in the data cannot merge claims.

        A joined key would let ("a\\x1fb","c") and ("a","b\\x1fc") hash identically
        and silently deduplicate two distinct assertions into one.
        """
        left = claim(source="src\x1fa", field_name="address", value="X")
        right = claim(source="src", field_name="\x1faaddress", value="X")
        assert left.claim_id != right.claim_id

    def test_claim_id_is_stable(self):
        args = {"source": "s", "field_name": "address", "value": "100 MAIN ST"}
        assert claim(**args).claim_id == claim(**args).claim_id

    def test_age_reflects_assertion_not_fetch(self):
        c = claim(
            source="s", field_name="status", value="OPEN", observed_at=NOW - timedelta(days=1000)
        )
        assert 999 < c.age_days < 1001


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


class TestStaleRecord:
    def test_four_year_old_assertion_is_critical(self):
        e = entity(
            claim(
                source="atlanta_childcare",
                field_name="status",
                value="OPEN",
                observed_at=NOW - timedelta(days=1755),
            )
        )
        found = rule_stale_record(e)
        assert len(found) == 1
        assert found[0].kind is DivergenceKind.STALE_RECORD
        assert found[0].severity is Severity.CRITICAL

    def test_recent_record_is_not_flagged(self):
        e = entity(
            claim(
                source="atlanta_childcare",
                field_name="status",
                value="OPEN",
                observed_at=NOW - timedelta(days=30),
            )
        )
        assert rule_stale_record(e) == []

    def test_no_source_date_means_no_claim_about_staleness(self):
        """Absence of a timestamp is not evidence of staleness."""
        e = entity(claim(source="s", field_name="status", value="OPEN", observed_at=None))
        assert rule_stale_record(e) == []


class TestZipMismatch:
    def test_two_authorities_disagreeing_is_flagged(self):
        e = entity(
            claim(source="a", field_name="zip", value="30318"),
            claim(source="b", field_name="zip", value="30309"),
        )
        found = rule_zip_mismatch(e)
        assert len(found) == 1
        assert found[0].kind is DivergenceKind.ZIP_MISMATCH

    def test_agreement_is_not_a_divergence(self):
        e = entity(
            claim(source="a", field_name="zip", value="30318"),
            claim(source="b", field_name="zip", value="30318"),
        )
        assert rule_zip_mismatch(e) == []

    def test_single_authority_cannot_disagree_with_itself(self):
        assert rule_zip_mismatch(entity(claim(source="a", field_name="zip", value="30318"))) == []


class TestEmptyRequiredField:
    def test_live_identifier_with_blank_address_is_flagged(self):
        """A real Atlanta schools row: valid GADOE_ID, blank address, null name."""
        e = entity(
            claim(
                source="atlanta_schools",
                field_name="address",
                value=" ",
                raw={"GADOE_ID": "1634"},
            )
        )
        found = rule_empty_required_field(e)
        assert len(found) == 1
        assert found[0].kind is DivergenceKind.EMPTY_REQUIRED_FIELD

    def test_blank_without_an_identifier_is_not_flagged(self):
        e = entity(claim(source="s", field_name="address", value=" ", raw={}))
        assert rule_empty_required_field(e) == []


# --------------------------------------------------------------------------
# The coverage gate — the honesty mechanism
# --------------------------------------------------------------------------


class TestCoverageGate:
    def _stale_only(self, n: int) -> list[Entity]:
        return [
            Entity(
                entity_key=f"k{i}",
                subject=f"F{i}",
                claims=[
                    Claim(
                        entity_key=f"k{i}",
                        subject=f"F{i}",
                        field_name="status",
                        value="OPEN",
                        source="atlanta_childcare",
                        source_url="https://example.invalid/a",
                        fetched_at=NOW,
                        observed_at=NOW - timedelta(days=1755),
                    )
                ],
            )
            for i in range(n)
        ]

    def test_thin_corroborating_source_suppresses_absence_findings(self):
        """The bug this gate exists to prevent.

        With almost no corroboration available, "absent from the current
        authority" is a fact about that authority's coverage, not about the
        facility, and counting it would inflate our own headline.
        """
        entities = self._stale_only(100)
        coverage = assess_coverage(entities)

        assert coverage["coverage_ratio"] < MIN_COVERAGE_RATIO
        assert coverage["sufficient_for_absence_claims"] is False
        assert all(rule_missing_in_current_authority(e, coverage) == [] for e in entities)

        kinds = {str(d.kind) for d in detect(entities, {}, coverage)}
        assert "MISSING_IN_CURRENT_AUTHORITY" not in kinds
        # The staleness finding is independently evidenced and must survive.
        assert "STALE_RECORD" in kinds

    def test_sufficient_coverage_permits_absence_findings(self):
        entities = self._stale_only(10)
        for e in entities[:6]:
            e.claims.append(
                Claim(
                    entity_key=e.entity_key,
                    subject=e.subject,
                    field_name="name",
                    value=e.subject,
                    source="atlanta_licenses",
                    source_url="https://example.invalid/b",
                    fetched_at=NOW,
                )
            )
        coverage = assess_coverage(entities)
        assert coverage["sufficient_for_absence_claims"] is True
        flagged = [d for e in entities for d in rule_missing_in_current_authority(e, coverage)]
        assert len(flagged) == 4

    def test_gate_explains_itself(self):
        coverage = assess_coverage(self._stale_only(50))
        assert "NOT counted" in coverage["note"]


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


class TestSummarize:
    def test_rate_counts_entities_not_findings(self):
        """Three findings on one entity is one affected entity, not three."""
        e = entity(
            claim(
                source="atlanta_childcare",
                field_name="status",
                value="OPEN",
                observed_at=NOW - timedelta(days=1755),
            ),
            claim(source="a", field_name="zip", value="30318"),
            claim(source="b", field_name="zip", value="30309"),
        )
        others = [Entity(entity_key=f"c{i}", subject=f"C{i}", claims=[]) for i in range(3)]
        entities = [e, *others]
        divergences = detect(entities, {}, assess_coverage(entities))
        result = summarize(entities, divergences, list(e.claims))

        assert len(divergences) >= 2
        assert result["entities_with_divergence"] == 1
        assert result["divergence_rate"] == pytest.approx(0.25)

    def test_empty_input_does_not_divide_by_zero(self):
        assert summarize([], [], [])["divergence_rate"] == 0.0


class TestRanking:
    def test_critical_sorts_above_medium(self):
        e = entity(
            claim(
                source="atlanta_childcare",
                field_name="status",
                value="OPEN",
                observed_at=NOW - timedelta(days=1755),
            ),
            claim(source="a", field_name="zip", value="30318"),
            claim(source="b", field_name="zip", value="30309"),
        )
        found = detect([e], {}, assess_coverage([e]))
        assert found[0].severity is Severity.CRITICAL

    def test_findings_are_deduplicated(self):
        e = entity(
            claim(source="a", field_name="zip", value="30318"),
            claim(source="b", field_name="zip", value="30309"),
            claim(source="c", field_name="zip", value="30312"),
        )
        found = detect([e], {}, assess_coverage([e]))
        assert len({d.divergence_id for d in found}) == len(found)


class TestAddressMismatch:
    def test_different_streets_are_flagged(self):
        e = entity(
            claim(source="atlanta_schools", field_name="address", value="3200 Latona Dr SW"),
            claim(source="federal_schools", field_name="address", value="845 Marietta St NW"),
        )
        found = rule_address_mismatch(e)
        assert len(found) == 1
        assert found[0].kind is DivergenceKind.ADDRESS_MISMATCH

    def test_formatting_difference_is_not_a_mismatch(self):
        """Normalization runs first, so abbreviation can never become a finding."""
        e = entity(
            claim(source="a", field_name="address", value="929 CHARLES ALLEN DRIVE N. E."),
            claim(source="b", field_name="address", value="929 Charles Allen Dr NE"),
        )
        assert rule_address_mismatch(e) == []

    def test_one_authority_cannot_mismatch_alone(self):
        e = entity(claim(source="a", field_name="address", value="100 MAIN ST NW"))
        assert rule_address_mismatch(e) == []


class TestStatusConflict:
    def test_open_versus_closed_is_critical(self):
        e = entity(
            claim(source="atlanta_schools", field_name="status", value="A"),
            claim(source="federal_schools", field_name="status", value="CLOSED"),
        )
        found = rule_status_conflict(e)
        assert len(found) == 1
        assert found[0].kind is DivergenceKind.STATUS_CONFLICT
        assert found[0].severity is Severity.CRITICAL

    def test_both_operational_is_agreement(self):
        e = entity(
            claim(source="a", field_name="status", value="OPEN"),
            claim(source="b", field_name="status", value="OPEN_NEW"),
        )
        assert rule_status_conflict(e) == []

    def test_same_source_twice_is_not_a_conflict(self):
        e = entity(
            claim(source="a", field_name="status", value="OPEN"),
            claim(source="a", field_name="status", value="CLOSED"),
        )
        assert rule_status_conflict(e) == []
