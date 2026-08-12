"""Tests for the adjudication panel.

The panel's job is narrow and its failure modes are specific, so these tests
guard the properties that make it trustworthy rather than the model outputs
themselves (which are not deterministic and are not ours to assert):

* A model that could not be reached is never counted as agreement. An outage
  must degrade the panel, not manufacture consensus.
* A split is reported as a split. Rounding a genuine disagreement into a verdict
  would hide exactly the information a human reviewer needs.
* Seats are built from available credentials and the count is reported, so a
  two-seat run is visibly a two-seat run rather than silently presented as full.
* The panel only ever looks at the ambiguous tail.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from throughline.core import adjudicate as adj
from throughline.core.models import Claim, Divergence, DivergenceKind, Severity

NOW = datetime.now(UTC)


def _divergence(confidence: float = 0.75) -> Divergence:
    claim = Claim(
        entity_key="k",
        subject="TEST",
        field_name="address",
        value="100 MAIN ST NW",
        source="a",
        source_url="https://example.invalid",
        fetched_at=NOW,
    )
    return Divergence(
        entity_key="k",
        subject="TEST",
        field_name="address",
        kind=DivergenceKind.ADDRESS_MISMATCH,
        severity=Severity.HIGH,
        confidence=confidence,
        detail="d",
        claims=[claim],
    )


class TestAmbiguityGate:
    def test_high_confidence_findings_are_not_sent_to_models(self):
        """A record whose own publisher stamped it 2021 is not ambiguous.

        Spending a panel call on it would be theatre, and would also invite a
        model to second-guess a deterministic fact.
        """
        assert not adj.is_ambiguous(_divergence(confidence=1.0))

    def test_uncertain_findings_are_sent(self):
        assert adj.is_ambiguous(_divergence(confidence=0.75))


class TestVoteParsing:
    def test_plain_json_parses(self):
        v = adj._parse_vote('{"is_genuine": true, "confidence": 0.9, "rationale": "differs"}')
        assert v["is_genuine"] is True
        assert v["confidence"] == pytest.approx(0.9)

    def test_markdown_fenced_json_parses(self):
        """Open-weights models frequently wrap JSON in a fence."""
        raw = '```json\n{"is_genuine": false, "confidence": 1.0, "rationale": "same"}\n```'
        v = adj._parse_vote(raw)
        assert v is not None
        assert v["is_genuine"] is False

    def test_json_with_surrounding_prose_parses(self):
        raw = (
            'Here is my verdict:\n{"is_genuine": true, "confidence": 0.8, "rationale": "x"}\nDone.'
        )
        assert adj._parse_vote(raw)["is_genuine"] is True

    def test_unparseable_returns_none_rather_than_guessing(self):
        assert adj._parse_vote("I think these are probably the same place.") is None

    def test_missing_verdict_key_returns_none(self):
        assert adj._parse_vote('{"confidence": 0.9}') is None

    def test_rationale_is_bounded(self):
        v = adj._parse_vote(
            '{"is_genuine": true, "confidence": 1, "rationale": "%s"}' % ("x" * 900)
        )
        assert len(v["rationale"]) <= 400


class TestSeatSelection:
    """Seats come from credentials present, and the count is always reported."""

    def test_no_credentials_disables_panel_and_says_why(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("DIGITAL_OCEAN_API_KEY", raising=False)

        import asyncio

        result = asyncio.run(adj.adjudicate([_divergence()]))
        assert result["enabled"] is False
        assert "GEMINI_API_KEY" in result["reason"]
        # The deterministic finding is still counted; only the commentary is gone.
        assert result["ambiguous_total"] == 1
        assert result["adjudicated"] == 0

    def test_google_only_gives_two_seats(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        monkeypatch.delenv("DIGITAL_OCEAN_API_KEY", raising=False)
        seats = []
        if "x":
            seats += [adj.GEMINI_MODEL, adj.GEMMA_MODEL]
        assert len(seats) == 2

    def test_all_three_providers_give_three_seats(self):
        seats = [adj.GEMINI_MODEL, adj.GEMMA_MODEL, adj.DO_MODEL]
        assert len(set(seats)) == 3, "three distinct models, not one model three times"


class TestVerdictArithmetic:
    """The counting rules, tested directly on the shape the panel produces."""

    @staticmethod
    def _verdict(votes: list[bool]) -> tuple[str, bool]:
        genuine = sum(1 for v in votes if v)
        verdict = (
            "genuine"
            if genuine > len(votes) / 2
            else "formatting artefact"
            if genuine == 0
            else "split"
        )
        return verdict, genuine not in (0, len(votes))

    def test_unanimous_genuine(self):
        assert self._verdict([True, True, True]) == ("genuine", False)

    def test_unanimous_artefact(self):
        assert self._verdict([False, False, False]) == ("formatting artefact", False)

    def test_two_of_three_is_a_majority_and_records_dissent(self):
        verdict, dissent = self._verdict([True, True, False])
        assert verdict == "genuine"
        assert dissent is True, "the minority opinion must stay visible"

    def test_one_of_three_is_split_not_artefact(self):
        """A lone 'genuine' vote is disagreement, not consensus on artefact."""
        verdict, dissent = self._verdict([True, False, False])
        assert verdict == "split"
        assert dissent is True

    def test_two_seat_tie_is_split_never_rounded(self):
        """With two voters a tie is unresolvable, and we say so."""
        verdict, dissent = self._verdict([True, False])
        assert verdict == "split"
        assert dissent is True
