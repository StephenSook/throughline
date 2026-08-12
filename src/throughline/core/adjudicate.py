"""The adjudication panel.

Models get exactly one job here, and it is a narrow one: judging whether an
*already-detected* discrepancy is a genuine conflict between authorities or an
artefact of formatting, abbreviation, or a legitimate difference in what the two
registries are recording.

They never count anything, never score severity, and never decide that a
divergence exists. Delete this entire module and Throughline still ingests five
public sources, resolves entities across them, detects seven kinds of
divergence, persists the series, and reports a rate — because the verdict is
deterministic and lives in `core.diverge`. That is the difference between a
system and a wrapper around somebody else's API, and it is deliberate.

**Four independent voters, on four different clouds.** One model agreeing with
itself is not a panel, and two voters cannot break a tie:

  * **Gemini 3.6 Flash** — hosted frontier model, Google. Strong general
    judgement.
  * **Gemma 4 31B** — open-weights, Apache-2.0, Google AI Studio. Present for a
    real architectural reason rather than a second opinion: an agency that
    cannot send record data to a third-party cloud can run Gemma on its own
    hardware and keep this capability, so the on-premises path is not a
    downgrade to nothing.
  * **GPT-OSS-120B** — open-weights, Apache-2.0, served on DigitalOcean Gradient.
    A different vendor on different infrastructure, so a single provider outage
    degrades the panel rather than ending it, and no one company's model can
    quietly decide every ambiguous case.
  * **Llama 3.3 70B** — on Snowflake Cortex, reached through the SQL API. The
    warehouse-native vantage point: an agency whose records already live in
    Snowflake can adjudicate without the data crossing its own warehouse
    boundary at all.

Two voters can only agree or deadlock. More can produce a majority, and the
minority opinion stays visible: every vote is stored with its rationale and
displayed next to the deterministic verdict, dissent included. A panel that
hides disagreement is just an average wearing a panel's clothes.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime

import httpx

from .models import Divergence

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

# All three verified present on their providers' model-list endpoints on
# 2026-08-12. Pinned rather than using `-latest` aliases so a silent upstream
# model swap cannot change the panel's behaviour between demo and judging.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
GEMMA_MODEL = os.environ.get("GEMMA_MODEL", "gemma-4-31b-it")
DO_MODEL = os.environ.get("DO_MODEL", "openai-gpt-oss-120b")

# DigitalOcean Gradient serverless inference. OpenAI-compatible, so the third
# voter needs a different request shape from the two Google-hosted ones.
DO_ROOT = "https://inference.do-ai.run/v1/chat/completions"

# Snowflake Cortex. Verified available on this account 2026-08-12 via
# SNOWFLAKE.CORTEX.COMPLETE; several advertised model names are not enabled in
# every region, so this one was picked by probing rather than from docs.
SNOWFLAKE_MODEL = os.environ.get("SNOWFLAKE_MODEL", "llama3.3-70b")

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


async def _ask_digitalocean(client: httpx.AsyncClient, prompt: str, token: str) -> dict:
    """The third voter, on DigitalOcean Gradient's OpenAI-compatible endpoint."""
    try:
        response = await client.post(
            DO_ROOT,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "model": DO_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 500,
            },
            timeout=60.0,
        )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        return {"error": f"unreachable: {type(exc).__name__}"}

    if response.status_code != 200:
        return {"error": f"HTTP {response.status_code}: {response.text[:180]}"}

    try:
        text = response.json()["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, ValueError):
        return {"error": "unexpected response shape"}

    vote = _parse_vote(text)
    return vote if vote else {"error": f"unparseable verdict: {text[:120]!r}"}


def _snowflake_jwt(account: str, user: str, private_key_pem: str) -> str | None:
    """Mint a short-lived JWT for Snowflake keypair auth.

    Snowflake's REST APIs authenticate with a JWT whose issuer embeds the
    SHA-256 fingerprint of the registered public key, which is what proves we
    hold the matching private half. Nothing here is a shared secret in transit:
    the private key never leaves this process and the token expires in minutes.
    """
    try:
        import base64
        import hashlib
        from datetime import timedelta

        import jwt
        from cryptography.hazmat.primitives import serialization

        key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
        der = key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(der).digest()).decode()

        qualified = f"{account.upper()}.{user.upper()}"
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "iss": f"{qualified}.{fingerprint}",
                "sub": qualified,
                "iat": now,
                "exp": now + timedelta(minutes=15),
            },
            key,
            algorithm="RS256",
        )
    except Exception:  # noqa: BLE001 - a seat that cannot mint a token simply does not sit
        return None


async def _ask_snowflake(client: httpx.AsyncClient, prompt: str) -> dict:
    """The fourth voter, on Snowflake Cortex.

    A warehouse-native model, which is a genuinely different vantage point: an
    agency whose records already live in Snowflake can adjudicate without the
    data leaving its own warehouse boundary at all.
    """
    account = os.environ.get("SNOWFLAKE_ACCOUNT", "").strip()
    user = os.environ.get("SNOWFLAKE_USER", "").strip()
    # A PEM survives a lot of transport mangling on its way into a platform's
    # environment UI. Accept the three shapes it actually arrives in: real
    # newlines, escaped \n, and either wrapped in quotes by a .env paste.
    pem = os.environ.get("SNOWFLAKE_PRIVATE_KEY", "").strip()
    if len(pem) >= 2 and pem[0] == pem[-1] and pem[0] in "\"'":
        pem = pem[1:-1]
    pem = pem.replace("\\n", "\n").strip()

    token = _snowflake_jwt(account, user, pem)
    if token is None:
        return {"error": "could not mint Snowflake JWT from the configured key"}

    # Reached through the SQL API rather than the Cortex inference endpoint.
    # `/api/v2/cortex/inference:complete` returns 403 "account is not allowed to
    # access this endpoint" on trial accounts, while `SNOWFLAKE.CORTEX.COMPLETE`
    # over `/api/v2/statements` works on the same credentials — so the model is
    # reached the way a warehouse user would actually reach it, in SQL.
    statement = f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{SNOWFLAKE_MODEL}', ?) AS verdict"
    try:
        response = await client.post(
            f"https://{account}.snowflakecomputing.com/api/v2/statements",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Snowflake-Authorization-Token-Type": "KEYPAIR_JWT",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "statement": statement,
                "timeout": 60,
                "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
                "role": os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
                # Bound rather than interpolated: the prompt carries values from
                # third-party records, and concatenating those into SQL would be
                # an injection waiting for a record with a quote in it.
                "bindings": {"1": {"type": "TEXT", "value": prompt}},
            },
            timeout=90.0,
        )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        return {"error": f"unreachable: {type(exc).__name__}"}

    if response.status_code not in (200, 202):
        # Name the host in the error. A 404 from Snowflake is almost always a
        # wrong account identifier resolving to a real but empty host, and
        # without the host in the message that is indistinguishable from the
        # endpoint being gone.
        return {
            "error": (
                f"HTTP {response.status_code} from {account}.snowflakecomputing.com"
                f" — {response.text[:140]}"
            )
        }

    try:
        rows = response.json().get("data") or []
        text = rows[0][0] if rows and rows[0] else ""
    except (ValueError, IndexError, TypeError):
        return {"error": "unexpected SQL API response shape"}

    if not text:
        return {"error": "no content in Cortex response"}

    vote = _parse_vote(text)
    return vote if vote else {"error": f"unparseable verdict: {text[:120]!r}"}


async def adjudicate(divergences: list[Divergence], *, limit: int = 6) -> dict:
    """Run the panel over the ambiguous tail. Mutates `adjudication` in place.

    Bounded by `limit` because a demo should not make hundreds of model calls,
    and the bound is reported in the returned summary rather than left implicit.
    A silent cap reads as full coverage when it is not.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    do_token = os.environ.get("DIGITAL_OCEAN_API_KEY", "").strip()
    candidates = [d for d in divergences if is_ambiguous(d)]

    seats: list[str] = []
    if api_key:
        seats += [GEMINI_MODEL, GEMMA_MODEL]
    if do_token:
        seats.append(DO_MODEL)
    snowflake_ready = all(
        os.environ.get(k, "").strip()
        for k in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PRIVATE_KEY")
    )
    if snowflake_ready:
        seats.append(SNOWFLAKE_MODEL)

    if not seats:
        return {
            "enabled": False,
            "reason": (
                "No model credentials configured (GEMINI_API_KEY, DIGITAL_OCEAN_API_KEY); "
                "the panel did not run."
            ),
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
            # Every seat votes concurrently and independently. No voter sees
            # another's answer, so agreement means agreement rather than one
            # model anchoring the rest.
            calls = []
            if api_key:
                calls.append(_ask(client, GEMINI_MODEL, prompt, api_key))
                calls.append(_ask(client, GEMMA_MODEL, prompt, api_key))
            if do_token:
                calls.append(_ask_digitalocean(client, prompt, do_token))
            if snowflake_ready:
                calls.append(_ask_snowflake(client, prompt))

            results = await asyncio.gather(*calls)
            votes = dict(zip(seats, results, strict=True))
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
        "models": seats,
        "providers": {
            GEMINI_MODEL: "Google AI Studio",
            GEMMA_MODEL: "Google AI Studio (open weights)",
            DO_MODEL: "DigitalOcean Gradient (open weights)",
            SNOWFLAKE_MODEL: "Snowflake Cortex (warehouse-native)",
        },
        "seats": len(seats),
        "ambiguous_total": len(candidates),
        "adjudicated": adjudicated,
        "limit": limit,
        "not_adjudicated": max(0, len(candidates) - adjudicated),
        "note": (
            "Models judge only whether an already-detected discrepancy is genuine. "
            "They produce no counts and set no severity."
        ),
    }
