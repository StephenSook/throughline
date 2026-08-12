# Devpost submission — Throughline

Paste-ready. **Every claim below was grepped against the shipped code before being written.** If something got cut, it does not appear here.

---

## Project name

**Throughline**

## Elevator pitch (200 char max)

> Atlanta serves a child care registry last refreshed in 2021 as if it were current. Throughline reconciles public records across authorities and measures how wrong they are.

---

## About the project

### Inspiration

A child in foster care exists simultaneously inside five or six institutions — the child welfare agency, the family court, whichever school district they're enrolled in, Medicaid, the placement provider. None of these systems exchange data reliably. The agency's record is treated as the authoritative account of that child's life, and it is frequently wrong.

The consequence isn't administrative. It's that a child arrives at a new school with no transcript and sits out for weeks, repeats a class they already passed, or misses a prescription because nobody knew about it.

There's one number nobody has: **how wrong is the record, actually?** We set out to build the thing that measures it.

### What it does

Throughline is a record-integrity layer. It reconciles what one institution *asserts* about an entity against independent authorities, and reports typed divergence with provenance and confidence on every field.

Real child-welfare records are confidential by federal law, so no honest hackathon project can demo on them. **We refused to fake them.** Instead we pointed Throughline at Atlanta's own public institutional records, which exhibit exactly the same failure mode — and found something nobody had measured.

**Atlanta's public GIS publishes `Atlanta_Child_Care_Facilities`: 681 licensed facilities where children are placed.** Every row carries its own provenance, and it says:

```
SOURCE      https://families.decal.ga.gov/provider/data
SOURCEDATE  1634774400000  ->  2021-10-21
```

That's the Georgia state child care licensing registry, snapshotted **21 October 2021**, republished as current ever since — four years and ten months. Georgia DECAL's own provider API is auth-gated and returns 401, so this dataset is the *only* public view of that registry.

On a live run against four public sources, Throughline reports:

| | |
|---|---|
| Entities resolved across 3 authorities | **1,281** |
| Claims ingested | **5,945** |
| Divergences | **791** |
| Critical (asserted 4.8 years ago, served as current) | **658** |
| Addresses the U.S. Census Bureau **cannot resolve** | **58** |
| Published coordinates conflicting with the federal geocode | **58** |
| Divergence rate | **53.1%** |

Every figure is computed during a run against live public APIs. Nothing is hardcoded, there's a test enforcing that, and any single number can be walked back to its raw source record via `GET /api/provenance/{claim_id}`.

### The number we refused to report

Our first run produced **1,331** divergences, 656 of them "listed as OPEN in the state registry, absent from the city's current business licence roll."

That number was wrong, and it was wrong in our favour.

The City of Atlanta's published 2026 licence roll holds **506 records for the entire city**, six of them child day care. A registry of 681 facilities can't be refuted by a roll that small — absence from it carries almost no information.

So Throughline now measures the corroborating authority's coverage before drawing any inference from absence. It measured **0.003 against a required 0.25**, suppressed its own 656 findings, and says why — on the dashboard, in the API, and in the README. Our headline dropped from 1,331 to 791.

A tool about record integrity that inflated its own count using a source it never checked would be committing the exact failure it exists to detect.

### How we built it

```
4 REAL PUBLIC SOURCES (no auth on any)
  Atlanta Child Care Facilities · Atlanta Business Licenses 2026
  Atlanta Public Schools · U.S. Census Bureau Geocoder
        -> CLAIM STORE          append-only, provenance + sha256 per claim
        -> ENTITY RESOLUTION    no shared key: blocking + rapidfuzz + address normalization
        -> DIVERGENCE ENGINE    6 deterministic rules
        -> COVERAGE GATE        can this authority support the inference at all?
        -> ADJUDICATION PANEL   Gemini 3.6 Flash + Gemma 4 31B, ambiguous tail only
        -> FastAPI + ranked worklist + provenance API
```

Python 3.12, FastAPI, httpx, rapidfuzz. Deployed on **Render**. Dashboard is Jinja2 and hand-written CSS, light and dark, no framework. CI on GitHub Actions: ruff, ruff format, pytest, and an anti-fabrication guard.

**This is not a wrapper around a model API.** Delete Gemini and Gemma entirely and Throughline still ingests four sources, resolves entities across them with no shared identifier, computes six kinds of divergence, gates them on measured coverage, and reports a rate. A test enforces that boundary: the engine modules are forbidden from importing the model layer.

The models do exactly one narrow job — judging whether an *already-detected* discrepancy is a genuine conflict or a formatting artefact. They never count, never set severity, never decide a divergence exists. Both voted independently and agreed on our test cases: unanimous "artefact" on a casing-and-abbreviation difference, unanimous "genuine" on two different street addresses. Every vote is stored and displayed with its rationale, including dissent.

Gemma is there for an architectural reason rather than a second opinion: an agency that can't send record data to a third-party cloud can run Gemma on its own hardware and keep the capability. The on-premises path isn't a downgrade to nothing.

### Challenges we ran into

**Absence isn't evidence.** Covered above — it cost us 656 findings and it's the thing we're proudest of.

**Entity resolution with no shared key.** Three registries describe overlapping sets of real places and not one carries an identifier the others recognise. A false match invents a disagreement between two places that were never the same place, and we'd report that invention to a human as a defect. So: blocking on ZIP and name head, rapidfuzz with address weighted above name, and an explicit review band (72–88) where the system *declines to merge* rather than guess. `GET /api/matches` exposes what we nearly merged.

**Atlanta is quadrant-addressed.** NW versus NE is load-bearing — the same street number exists in more than one quadrant, and dropping the directional merges two genuinely different places. `"929 CHARLES ALLEN DRIVE N. E."` and `"929 Charles Allen Dr NE"` are the same building and must normalize identically.

**A 200 isn't a success.** Government and enterprise hosts answer rate-limited clients with challenge pages served as HTTP 200. Our connectors validate payload shape and size, never the status line, and a failed fetch is never persisted — a file that exists is a file something downstream will parse.

### Accomplishments we're proud of

- We found something real, in public data, about children, in the host city — and it had been sitting there unmeasured for four years.
- Our tool suppressed its own headline number rather than overstate it.
- 41 tests. Green CI. A guard that fails rather than skips, sees untracked files, and includes non-vacuity checks so a bug that made it scan nothing would fail rather than go green.
- Every claim on every screen is independently verifiable by a stranger, against public URLs, with no API key.

### What we learned

That the hardest part of interoperability isn't the pipes — it's knowing when your evidence doesn't support your conclusion. We spent more of the build on the coverage gate than on any single connector, and it's the part that makes the rest trustworthy.

Also, concretely: probabilistic entity resolution, USPS address normalization, the Census batch geocoder, ArcGIS FeatureServer layer discovery, and structured-output prompting against two different model families.

### What's next for Throughline

The spec this was built from sequences two products. Tonight we built **The Ledger** — the audit. Next is **The Relay**: when a child's placement changes, automatically deliver the transcript, immunization record, IEP, and current court order to the receiving school *before the child arrives*.

More immediately: the second year of Atlanta's licence roll to get a genuine year-over-year series, and persistence so the divergence rate can be tracked across runs and shown to fall.

### Explicit non-goals

Enforced in the code, not just stated:

- **No predictive risk scoring.** Prediction from a broken record is the problem, not the fix.
- **No case management.** We never compete with the systems that feed us.
- **No automated decision affecting a child's placement or a parent's rights.** Throughline surfaces discrepancies. Humans decide. Always.

---

## Built with

`python` · `fastapi` · `render` · `google-gemini` · `gemma` · `rapidfuzz` · `arcgis` · `us-census-geocoder` · `atlanta-open-data` · `github-actions` · `jinja2` · `httpx`

## Try it out

- Live: https://throughline-api-yo1p.onrender.com
- Repo: https://github.com/StephenSook/throughline
- API docs: https://throughline-api-yo1p.onrender.com/docs

---

## Prize categories to check

Claim only these four. Each is load-bearing and greppable in the shipped code.

- [x] **Best Hack for Good**
- [x] **Best Use of Atlanta Open Data** — three City of Atlanta datasets are the engine's input, not decoration
- [x] **Best Use of Gemini API** — adjudication panel
- [x] **Best Use of Gemma 4** — second independent voter, `gemma-4-31b-it`

**Do NOT check:** Render Workflows (we deploy on Render but did not build a Workflow service — cut rather than overclaim), Tiger Data, Snowflake, DigitalOcean. None are wired, so none are claimed.

## Required form fields

**"Which of the following AI tools did you use?"** → `Gemini`

**"Did you implement a generative AI model or API in your hack?"**

> Yes. Gemini 3.6 Flash and Gemma 4 31B (both via Google AI Studio) form a two-model adjudication panel that votes on whether an already-detected discrepancy is a genuine conflict between authorities or an artefact of formatting and abbreviation. Each model votes independently, every vote is stored and displayed with its rationale including dissent, and a model that fails to answer is recorded as an error rather than counted as agreement.
>
> Deliberately, the models are used only on the ambiguous tail and never produce a number. They do not count, do not set severity, and do not decide that a divergence exists — all six divergence rules are deterministic Python. Delete both models and the system still ingests four public sources, resolves entities across them with no shared identifier, computes divergences, and reports a rate. A test in our CI enforces that boundary by forbidding the engine modules from importing the model layer.
>
> We chose Gemma alongside Gemini for an architectural reason rather than a second opinion: an agency that cannot send record data to a third-party cloud can run Gemma on its own hardware and retain the capability.

**"Gemini Project Number"** → `150614014893`

**"Share feedback about any technology you interacted with at this hackathon"**

> Render: creating the web service and deploying from a GitHub repo took under two minutes, and having the deploy green before we wrote any engine code removed the usual end-of-hackathon deployment panic entirely. Worth noting for other teams that Render Postgres ships TimescaleDB in Apache edition only, so continuous aggregates are unavailable there.
>
> Gemini API: `models.list` was the fastest way to confirm exactly which model IDs a key can reach, which saved us guessing. One gotcha worth flagging — with `maxOutputTokens` set low, a reasoning model's thinking budget can consume the entire allowance and return a candidate with no text part at all, which is indistinguishable from a refusal. Raising the cap and joining every text part fixed it. `responseMimeType: application/json` made verdicts parse reliably.
>
> Atlanta Open Data: the `opendata.atlantaga.gov` portal is dead (TLS failure, Azure 404 behind it), but the underlying ArcGIS Online organisation is fully live and unauthenticated. Layer IDs are non-obvious and non-sequential — child care is layer 6, business licences layer 50 — so `/FeatureServer?f=json` is essential for discovery. Several datasets carry `SOURCE` and `SOURCEDATE` columns that make provenance auditing possible, which is exactly what our project depends on.
