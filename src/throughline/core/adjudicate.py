"""The adjudication panel.

Models get exactly one job here, and it is a narrow one: judging whether an
*already-detected* discrepancy is a genuine conflict between authorities or an
artefact of formatting, abbreviation, or a legitimate difference in what the two
registries are recording.

They never count anything, never score severity, and never decide that a
divergence exists. Delete this entire module and Throughline still ingests four
public sources, resolves entities across them, detects six kinds of divergence,
and reports a rate — because the verdict is deterministic and lives in
`core.diverge`. That is the difference between a system and a wrapper around
somebody else's API, and it is deliberate.

Two independent voters, because one model agreeing with itself is not a panel:

  * **Gemini** — hosted frontier model, strong general judgement.
  * **Gemma** — open-weights, Apache-2.0. Present for a real architectural
    reason rather than a second opinion: an agency that cannot send record data
    to a third-party cloud can run Gemma on its own hardware and keep this
    capability. The panel is designed so the on-premises path is not a downgrade
    to nothing.

Every vote is stored with its rationale and displayed next to the deterministic
verdict, including dissent. A panel that hides disagreement is just an average.
"""

from __future__ import annotations

import asyncio
import json
import os

import httpx

from .models import Divergence

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

# Both verified present on this key via the models.list endpoint on 2026-08-12.
# Pinned rather than using a `-latest` alias so a silent upstream model swap
# cannot change the panel's behaviour between the demo and the judging.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
GEMMA_MODEL = os.environ.get("GEMMA_MODEL", "gemma-4-31b-it")

# Only the ambiguous tail is worth a model's opinion. A record whose own
# publisher stamped it 2021 is not ambiguous, and spending a panel call on it
# would be theatre.
AMBIGUOUS_MAX_CONFIDENCE = 0.9

PROMPT = """You are auditing a discrepancy found between two independent public record systems.

Entity: {subject}
Field: {field}
Discrepancy type: {kind}
What the deterministic engine found: {detail}

The conflicting values, each from a different authority:
{values}

Decide ONE question: is this a GENUINE conflict between the authorities, or is it an
artefact of formatting, abbreviation, punctuation, or the two systems legitimately
recording different things?

Treat as NOT genuine: abbreviation differences (DRIVE vs DR), punctuation, casing,
directional formatting (N. E. vs NE), suite/unit notation, obvious transliterations of
the same value.
Treat as GENUINE: different street numbers, different streets, different ZIP codes that
are not adjacent formatting variants, a value present in one authority and absent in the
other, or a date that materially contradicts the other authority.

You are judging only whether the two values conflict. You are NOT deciding severity, you
are NOT producing any count or statistic, and you must NOT invent any fact that is not in
the values above.

Respond with ONLY a JSON object, no markdown fence:
{{"is_genuine": true or false, "confidence": 0.0 to 1.0, "rationale": "one sentence"}}"""


def is_ambiguous(divergence: Divergence) -> bool:
    return divergence.confidence < AMBIGUOUS_MAX_CONFIDENCE


def _format_values(divergence: Divergence) -> str:
    lines = []
    for claim in divergence.claims:
        observed = claim.observed_at.date().isoformat() if claim.observed_at else "unknown"
        lines.append(f"  - {claim.source} says {claim.value!r} (asserted {observed})")
    return "\n".join(lines)


def _parse_vote(text: str) -> dict | None:
    """Parse a model's JSON verdict, tolerating a markdown fence."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1] if "```" in cleaned[3:] else cleaned[3:]
        cleaned = cleaned.removeprefix("json").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    if "is_genuine" not in parsed:
        return None
    return {
        "is_genuine": bool(parsed["is_genuine"]),
        "confidence": float(parsed.get("confidence", 0.5)),
        "rationale": str(parsed.get("rationale", ""))[:400],
    }


def _extract_text(payload: dict) -> str:
    """Pull text out of a generateContent response.

    Reasoning models return several parts, some of which are thought summaries
    carrying no `text`. Taking parts[0] blindly loses the answer, so join every
    part that actually has text.
    """
    try:
        parts = payload["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return ""
    return "\n".join(p["text"] for p in parts if isinstance(p, dict) and "text" in p)


async def _ask(client: httpx.AsyncClient, model: str, prompt: str, api_key: str) -> dict:
    """One model, one vote.

    Returns an `error` dict rather than a vote when the model could not be
    reached or did not answer usably. A model that did not answer must never be
    silently counted as agreement — that would let an outage manufacture
    consensus.
    """
    # Enough headroom that a reasoning model's thinking budget cannot starve the
    # answer. A truncated response is indistinguishable from a refusal, and at
    # 300 tokens both models were being cut off mid-verdict.
    config = {"temperature": 0.0, "maxOutputTokens": 1024}

    async def call(with_json_mime: bool):
        generation = dict(config)
        if with_json_mime:
            generation["responseMimeType"] = "application/json"
        return await client.post(
            f"{API_ROOT}/{model}:generateContent",
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": generation},
            timeout=45.0,
        )

    try:
        # Ask for structured output first. Open-weights models on this endpoint
        # do not all accept responseMimeType, so a 400 falls back to plain text
        # and the parser strips whatever fence the model wrapped it in.
        response = await call(with_json_mime=True)
        if response.status_code == 400:
            response = await call(with_json_mime=False)
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        return {"error": f"unreachable: {type(exc).__name__}"}

    if response.status_code != 200:
        return {"error": f"HTTP {response.status_code}: {response.text[:180]}"}

    try:
        payload = response.json()
    except ValueError:
        return {"error": "response body was not JSON"}

    text = _extract_text(payload)
    if not text:
        finish = (payload.get("candidates") or [{}])[0].get("finishReason", "unknown")
        return {"error": f"no text in response (finishReason={finish})"}

    vote = _parse_vote(text)
    return vote if vote else {"error": f"unparseable verdict: {text[:120]!r}"}


async def adjudicate(divergences: list[Divergence], *, limit: int = 12) -> dict:
    """Run the panel over the ambiguous tail. Mutates `adjudication` in place.

    Bounded by `limit` because a demo should not make hundreds of model calls,
    and the bound is reported in the returned summary rather than left implicit.
    A silent cap reads as full coverage when it is not.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    candidates = [d for d in divergences if is_ambiguous(d)]

    if not api_key:
        return {
            "enabled": False,
            "reason": "GEMINI_API_KEY is not set; the panel did not run.",
            "ambiguous_total": len(candidates),
            "adjudicated": 0,
            "note": (
                "Deterministic verdicts are unaffected. The panel only reviews the "
                "ambiguous tail and never produces a count."
            ),
        }

    selected = candidates[:limit]
    adjudicated = 0

    async with httpx.AsyncClient() as client:
        for divergence in selected:
            prompt = PROMPT.format(
                subject=divergence.subject,
                field=divergence.field_name,
                kind=divergence.kind,
                detail=divergence.detail,
                values=_format_values(divergence),
            )
            gemini_vote, gemma_vote = await asyncio.gather(
                _ask(client, GEMINI_MODEL, prompt, api_key),
                _ask(client, GEMMA_MODEL, prompt, api_key),
            )

            votes = {GEMINI_MODEL: gemini_vote, GEMMA_MODEL: gemma_vote}
            valid = [v for v in votes.values() if v and "error" not in v]
            if not valid:
                divergence.adjudication = {"votes": votes, "verdict": "panel unavailable"}
                continue

            genuine = sum(1 for v in valid if v["is_genuine"])
            divergence.adjudication = {
                "votes": votes,
                "voters": len(valid),
                "genuine_votes": genuine,
                # A tie is not consensus, and we say so rather than rounding it
                # into a decision the panel did not actually reach.
                "verdict": (
                    "genuine"
                    if genuine > len(valid) / 2
                    else "formatting artefact"
                    if genuine == 0
                    else "split"
                ),
                "dissent": genuine not in (0, len(valid)),
            }
            adjudicated += 1

    return {
        "enabled": True,
        "models": [GEMINI_MODEL, GEMMA_MODEL],
        "ambiguous_total": len(candidates),
        "adjudicated": adjudicated,
        "limit": limit,
        "not_adjudicated": max(0, len(candidates) - adjudicated),
        "note": (
            "Models judge only whether an already-detected discrepancy is genuine. "
            "They produce no counts and set no severity."
        ),
    }
