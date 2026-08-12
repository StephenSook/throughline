# Throughline

**A record-integrity layer.** It reconciles what one institution *asserts* about an entity against independent authorities, and reports typed divergence with provenance and confidence on every field.

Built at **Hack RenderATL**, 12 August 2026.

**Live:** https://throughline-api-yo1p.onrender.com · **API docs:** [`/docs`](https://throughline-api-yo1p.onrender.com/docs) · **Contract:** [`/openapi.json`](https://throughline-api-yo1p.onrender.com/openapi.json)

---

## The finding

Atlanta's public GIS publishes **`Atlanta_Child_Care_Facilities`** — 681 licensed facilities where children are placed.

Every row carries its own provenance, and it says this:

```
SOURCE      https://families.decal.ga.gov/provider/data
SOURCEDATE  1634774400000   ->   2021-10-21
```

That is the Georgia state child care licensing registry, snapshotted on **21 October 2021**, and republished as current ever since. Anyone reading it today — a parent, a researcher, a city service, a caseworker — is reading 2021.

Georgia DECAL's own provider API is auth-gated and returns 401. This dataset is the *only* public view of that registry, and it has been frozen for four years and ten months. Nobody had measured what drifted. Throughline measures it.

> The product spec this was built from puts it in one line: *"Silent staleness is the disease we are curing."*

## What it found, on a live run

Every figure below is computed during a reconciliation run against live public APIs. Nothing is hardcoded — there is a [test that enforces that](tests/test_no_fabricated_numbers.py), and you can verify any single number yourself via `/api/provenance/{claim_id}`.

| | |
|---|---|
| Entities resolved across 3 authorities | **1,281** |
| Claims ingested | **5,945** |
| Divergences detected | **791** |
| Critical (record asserted 4.8 years ago, served as current) | **658** |
| Addresses the U.S. Census Bureau **cannot resolve** | **58** |
| Published coordinates conflicting with the federal geocode | **58** |
| Divergence rate | **53.1%** |
| Pipeline wall time | **under a second** |

Run it yourself: press **Run reconciliation** on the live dashboard, or `POST /api/runs`.

## The number we refused to report

The first run produced **1,331** divergences, of which 656 were "listed as OPEN in the state registry, absent from the city's current business licence roll."

That number was wrong, and it was wrong in our favour.

The City of Atlanta's published 2026 licence roll contains **506 records for the entire city**, of which **6** are classified as child day care. A registry of 681 facilities cannot be refuted by a roll that small — absence from it carries almost no information.

So Throughline now measures the corroborating authority's coverage before drawing any inference from absence. Coverage here is **0.003** against a required 0.25, so the rule **suppresses itself** and says why, on the dashboard, in the API, and in this README. That removed 656 findings and dropped our own headline from 1,331 to 791.

A tool that inflates its divergence count using a source it never checked the coverage of would be committing the exact failure it exists to detect. The gate is in [`core/diverge.py`](src/throughline/core/diverge.py) and it is tested in both directions.

## Why this matters beyond one dataset

A child in foster care exists simultaneously inside five or six institutions — the child welfare agency, the family court, whichever school district they are enrolled in, Medicaid, the placement provider. None of these systems exchange data reliably. The agency's record is treated as the authoritative account of that child's life, and it is frequently wrong.

The consequence is not administrative. It is that a child arrives at a new school with no transcript and sits out for weeks, repeats a class they already passed, or misses a prescription because nobody knew about it.

Real child-welfare records are confidential by federal law, so no honest hackathon project can demo on them. **So we did not fake them.** Throughline runs on real public institutional records from the same city, exhibiting the same failure mode, and every number it reports is genuinely computed from live public APIs.

## How it works

```
REAL PUBLIC SOURCES  (no authentication on any of them)
 ├─ Atlanta Child Care Facilities   681 rows   the city's copy of the GA DECAL registry
 ├─ Atlanta Business Licenses 2026  506 rows   the city's own licence roll
 ├─ Atlanta Public Schools          132 rows   carries GADOE_ID
 └─ US Census Geocoder                          the federal address authority
            │
            ▼   connectors/   validate content, never status codes
      CLAIM STORE      append-only. (entity, field, value, source, observed_at, sha256)
            ▼
      ENTITY RESOLUTION    no shared key. blocking + rapidfuzz + address normalization
                           explicit review band where we decline to merge
            ▼
      DIVERGENCE ENGINE    six deterministic rules. no model runs here.
            ▼
      COVERAGE GATE        can this authority support the inference at all?
            ▼
      ADJUDICATION PANEL   Gemini 3.6 Flash + Gemma 4 31B vote on the ambiguous tail
            ▼
      FastAPI · ranked worklist · provenance API · hash-verifiable claims
```

### The parts that are ours

This is not a wrapper around a model API. **Delete Gemini and Gemma entirely and Throughline still ingests four public sources, resolves entities across them with no shared identifier, computes six kinds of divergence, gates them on measured coverage, and reports a rate.** [A test enforces that boundary](tests/test_no_fabricated_numbers.py) — the engine modules are forbidden from importing the model layer.

Built here, not bought:

- **Entity resolution with no shared key** ([`core/resolve.py`](src/throughline/core/resolve.py)). Blocking on ZIP and name head, rapidfuzz scoring with address weighted above name, and an explicit review band (72–88) where the system **declines to merge** rather than guess. Unmatched records are kept, never dropped: a facility that appears in the stale registry and nowhere else is the most interesting row in the dataset, and dropping it would flatter the rate.
- **Address normalization** ([`core/normalize.py`](src/throughline/core/normalize.py)). Atlanta is quadrant-addressed, so `NW` versus `NE` is load-bearing — dropping the directional would merge two genuinely different places.
- **Six divergence rules** ([`core/diverge.py`](src/throughline/core/diverge.py)), all deterministic, so every verdict is reproducible by hand from public URLs.
- **The coverage gate**, above.
- **Provenance on every claim** ([`core/models.py`](src/throughline/core/models.py)). Claim identity is length-prefixed, never separator-joined, so a delimiter inside third-party data cannot collide two distinct claims into one.

### Where the models are used

Only on the ambiguous tail, and only to answer one question: is this discrepancy a genuine conflict, or an artefact of formatting? Two independent voters, every vote stored and displayed with its rationale, including dissent.

Gemma is present for an architectural reason rather than a second opinion: an agency that cannot send record data to a third-party cloud can run Gemma on its own hardware and keep this capability. The on-premises path is not a downgrade to nothing.

**The models never produce a number.** They do not count, do not set severity, and do not decide that a divergence exists.

## Explicit non-goals

Carried from the product spec, and enforced in the code:

- **No predictive risk scoring.** Prediction from a broken record is the problem, not the fix.
- **No case management.** We never compete with the systems that feed us. Neutrality is the point.
- **No automated decision affecting a child's placement or a parent's rights.** Throughline surfaces discrepancies. Humans decide. Always.

## Verify anything here

Every source is public and unauthenticated. Pick any claim and check it yourself:

```bash
# Live summary — every figure computed, none stored as a constant
curl https://throughline-api-yo1p.onrender.com/api/summary

# The ranked worklist
curl 'https://throughline-api-yo1p.onrender.com/api/divergences?limit=5'

# The raw source record behind any single claim, with URL, fetch time and sha256
curl https://throughline-api-yo1p.onrender.com/api/provenance/<claim_id>

# Source health and the coverage gate's own arithmetic
curl https://throughline-api-yo1p.onrender.com/api/sources

# What we nearly merged but declined to — the entity-resolution review band
curl https://throughline-api-yo1p.onrender.com/api/matches
```

## Run it locally

```bash
git clone https://github.com/StephenSook/throughline
cd throughline
uv sync --extra dev
uv run pytest -q                      # 41 tests
uv run uvicorn throughline.api.main:app --reload
open http://localhost:8000
```

No API key is required to run the engine. `GEMINI_API_KEY` (from [AI Studio](https://aistudio.google.com/apikey)) enables the adjudication panel; without it the panel reports that it is disabled and every deterministic verdict is unaffected. See [`.env.example`](.env.example).

## Stack

| | |
|---|---|
| Backend | Python 3.12, FastAPI, httpx, asyncio |
| Entity resolution | rapidfuzz, custom USPS-style normalizer |
| Models | Gemini 3.6 Flash, Gemma 4 31B (both via Google AI Studio) |
| Deploy | Render |
| Dashboard | Jinja2 + hand-written CSS, light and dark, no framework |
| CI | GitHub Actions — ruff, ruff format, pytest, anti-fabrication guard |

## Data sources

| Source | Authority | Rows | Endpoint |
|---|---|---|---|
| Child Care Facilities | City of Atlanta, republishing Georgia DECAL | 681 | [ArcGIS FeatureServer](https://services5.arcgis.com/5RxyIIJ9boPdptdo/ArcGIS/rest/services/Atlanta_Child_Care_Facilities/FeatureServer/6/query?where=1%3D1&outFields=*&f=json) |
| Business Licenses 2026 | City of Atlanta, Dept. of Revenue | 506 | [ArcGIS FeatureServer](https://services5.arcgis.com/5RxyIIJ9boPdptdo/ArcGIS/rest/services/Business_Licenses_2026/FeatureServer/50/query?where=1%3D1&outFields=*&f=json) |
| Public Schools | City of Atlanta / APS | 132 | [ArcGIS FeatureServer](https://services5.arcgis.com/5RxyIIJ9boPdptdo/ArcGIS/rest/services/Atlanta_Public_Schools/FeatureServer/0/query?where=1%3D1&outFields=*&f=json) |
| Geocoder | U.S. Census Bureau | per-call | [Public_AR_Current](https://geocoding.geo.census.gov/geocoder/locations/onelineaddress) |

## Team

**Stephen Sookra** — backend, connectors, entity resolution, divergence engine, coverage gate, adjudication panel, API, dashboard, deploy, CI.
**Khadim** — frontend dashboard.

Live build status and ownership: [`PLAN.md`](./PLAN.md).

## License

MIT — see [`LICENSE`](./LICENSE).
