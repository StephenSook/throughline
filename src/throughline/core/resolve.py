"""Entity resolution across authorities that share no identifier.

This is the hard part, and it is the part that cannot be bought. Atlanta's child
care registry, the city's licence roll, and the school facility layer describe
overlapping sets of real places, and not one of them carries a key that any of
the others recognise. Matching is therefore probabilistic, and being wrong has a
cost: a false match invents a disagreement between two places that were never
the same place, and we would report that invention to a human as a defect.

So the design is deterministic-first, per the spec: block cheaply, score
explicitly, keep every score, and refuse to merge inside a review band instead
of guessing. Nothing here is a model. Every decision is reproducible and can be
read off the stored features by somebody checking our work.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from rapidfuzz import fuzz

from .models import Claim, Entity
from .normalize import normalize_address, normalize_name

# Above ACCEPT we merge. Below REVIEW we never merge. Between them we record the
# candidate and decline to decide, which is the honest answer and also the one
# the spec demands: humans decide, always.
ACCEPT = 88.0
REVIEW = 72.0


@dataclass(slots=True)
class MatchCandidate:
    left_subject: str
    right_subject: str
    left_source: str
    right_source: str
    name_score: float
    address_score: float
    combined: float
    decision: str  # "accept" | "review" | "reject"


@dataclass(slots=True)
class SourceRecord:
    """All claims one source makes about one subject."""

    source: str
    subject: str
    block: str
    claims: list[Claim]

    def value(self, field_name: str) -> str | None:
        for c in self.claims:
            if c.field_name == field_name:
                return c.value
        return None


def group_records(claims: list[Claim]) -> list[SourceRecord]:
    grouped: dict[tuple[str, str], list[Claim]] = defaultdict(list)
    for claim in claims:
        grouped[(claim.source, claim.subject)].append(claim)
    return [
        SourceRecord(source=src, subject=subj, block=cs[0].entity_key, claims=cs)
        for (src, subj), cs in grouped.items()
    ]


def score_pair(left: SourceRecord, right: SourceRecord) -> tuple[float, float, float]:
    """Score a candidate pair. Returns (name, address, combined).

    Address agreement is weighted above name agreement because organisation
    names drift constantly across registries ("INC.", a campus suffix, a doing-
    business-as) while a normalized street address is a much stronger signal
    that two records denote the same physical place. When one side has no usable
    address we fall back to the name alone and cap the result, so a missing
    address can never manufacture a confident match.
    """
    name_score = float(
        fuzz.token_set_ratio(normalize_name(left.subject), normalize_name(right.subject))
    )

    left_addr = normalize_address(left.value("address"))
    right_addr = normalize_address(right.value("address"))
    if left_addr and right_addr:
        address_score = float(fuzz.ratio(left_addr, right_addr))
        combined = 0.4 * name_score + 0.6 * address_score
    else:
        address_score = 0.0
        combined = min(name_score, 85.0)

    return name_score, address_score, combined


def resolve(claims: list[Claim]) -> tuple[list[Entity], list[MatchCandidate]]:
    """Resolve claims into entities. Returns entities and every scored candidate.

    Candidates are returned, not just accepted matches, because the review band
    is a product surface: a supervisor needs to see what we nearly merged.
    """
    records = group_records(claims)

    blocks: dict[str, list[SourceRecord]] = defaultdict(list)
    for record in records:
        blocks[record.block].append(record)

    entities: list[Entity] = []
    candidates: list[MatchCandidate] = []
    merged: set[tuple[str, str]] = set()

    for block, members in blocks.items():
        by_source: dict[str, list[SourceRecord]] = defaultdict(list)
        for member in members:
            by_source[member.source].append(member)

        sources = sorted(by_source)
        # Only ever compare across authorities. Two rows from the same registry
        # disagreeing is that registry's internal problem, not a divergence
        # between institutions, and merging them would corrupt the count.
        for i, left_source in enumerate(sources):
            for right_source in sources[i + 1 :]:
                for left in by_source[left_source]:
                    for right in by_source[right_source]:
                        name_score, addr_score, combined = score_pair(left, right)
                        if combined < REVIEW:
                            continue
                        decision = "accept" if combined >= ACCEPT else "review"
                        candidates.append(
                            MatchCandidate(
                                left_subject=left.subject,
                                right_subject=right.subject,
                                left_source=left.source,
                                right_source=right.source,
                                name_score=round(name_score, 1),
                                address_score=round(addr_score, 1),
                                combined=round(combined, 1),
                                decision=decision,
                            )
                        )
                        if decision == "accept":
                            key = f"{block}::{left.subject}"
                            entity = Entity(
                                entity_key=key,
                                subject=left.subject,
                                claims=[*left.claims, *right.claims],
                                match_scores={
                                    f"{left.source}->{right.source}": round(combined, 1)
                                },
                            )
                            entities.append(entity)
                            merged.add((left.source, left.subject))
                            merged.add((right.source, right.subject))

        # Unmatched records still become entities. A facility that appears in the
        # stale registry and nowhere else is not noise to be dropped — it is the
        # single most interesting row in the dataset, and dropping it would make
        # the divergence rate look better than it is.
        for member in members:
            if (member.source, member.subject) not in merged:
                entities.append(
                    Entity(
                        entity_key=f"{block}::{member.subject}",
                        subject=member.subject,
                        claims=list(member.claims),
                    )
                )

    return entities, candidates
