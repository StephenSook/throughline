# Devpost submission: Throughline

Paste-ready. **Every number here is read from [`FACTS.json`](./FACTS.json), written by a real reconciliation run, and every named technology was grepped against the shipped code before being written.** If something got cut, it does not appear here.

---

## Project name

**Throughline**: live draft at https://devpost.com/software/throughline-sujkg1

## Elevator pitch (200 char max)

> Atlanta publishes a child care registry last refreshed in 2021 as if it were current. Throughline reconciles public records across authorities and measures how wrong they actually are.

---

## About the project

### Inspiration

A child in foster care exists simultaneously inside five or six institutions, the child welfare agency, the family court, whichever school district they're enrolled in, Medicaid, the placement provider. None of these systems exchange data reliably. The agency's record is treated as the authoritative account of that child's life, and it is frequently wrong.

The consequence isn't administrative. It's that a child arrives at a new school with no transcript and sits out for weeks, repeats a class they already passed, or misses a prescription because nobody knew about it.

There's one number nobody has: **how wrong is the record, actually?** We built the thing that measures it.

### What it does

Throughline is a record-integrity layer. It reconciles what one institution *asserts* about an entity against independent authorities, and reports typed divergence with provenance and confidence on every field.

Real child-welfare records are confidential by federal law, so no honest hackathon project can demo on them. **We refused to fake them.** Instead we pointed Throughline at Atlanta's own public institutional records, which exhibit exactly the same failure mode, and found something nobody had measured.

**Atlanta's public GIS publishes `Atlanta_Child_Care_Facilities`: 681 licensed facilities where children are placed.** Every row carries its own provenance, and it says:

```
SOURCE      https://families.decal.ga.gov/provider/data
SOURCEDATE  1634774400000  ->  2021-10-21
```

That's the Georgia state child care licensing registry, snapshotted **21 October 2021**, republished as current ever since, four years and ten months. Georgia DECAL's own provider API is auth-gated and returns 401, so this dataset is the *only* public view of that registry.

On a live run against **five public sources**, Throughline reports:

| | |
|---|---|
| Entities resolved across 5 authorities | **1,344** |
| Claims ingested | **6,385** |
| Divergences | **813** |
| Critical, asserted 4.8 years ago, served as current | **658** |
| Published coordinates conflicting with the federal geocode | **69** |
| Addresses the U.S. Census Bureau **cannot resolve** | **58** |
| ZIP codes two authorities disagree on | **14** |
| Addresses local and federal records disagree on | **10** |
| Records with a live identifier and an empty address | **3** |
| Schools one authority calls open and another does not | **1** |
| **Divergence rate** | **51.9%** |
| Full pipeline, five live APIs | **6.4s** |

Every figure is computed during a run against live public APIs. Nothing is hardcoded, a test enforces that, and any single number walks back to its raw source record via `GET /api/provenance/{claim_id}`.

### The number we refused to report

Our first run produced **1,331** divergences, 656 of them "listed as OPEN in the state registry, absent from the city's current business licence roll."

That number was wrong, and it was wrong in our favour.

The City of Atlanta's published 2026 licence roll holds **506 records for the entire city**, six of them child day care. A registry of 681 facilities can't be refuted by a roll that small, absence from it carries almost no information.

So Throughline now measures the corroborating authority's coverage before drawing any inference from absence. It found that roll corroborates **2 of 659** entities, **0.3%**, against a required 25%, so the rule **suppresses itself** and says why, on the dashboard, in the API, and in the README.

A tool about record integrity that inflated its own count using a source it never checked would be committing the exact failure it exists to detect.

### How we built it

```
FIVE REAL PUBLIC SOURCES (no auth on any)
  Atlanta Child Care Facilities 681 · Business Licenses 2026 506
  Atlanta Public Schools 132 · NCES federal directory 88 · US Census Geocoder
   -> CLAIM STORE          append-only, provenance + sha256 per claim
   -> ENTITY RESOLUTION    no shared key: blocking + rapidfuzz + address normalization
   -> DIVERGENCE ENGINE    8 deterministic rules
   -> COVERAGE GATE        can this authority support the inference at all?
   -> ADJUDICATION PANEL   4 voters on 4 clouds, ambiguous tail only
   -> TIMESCALEDB          hypertables + continuous aggregate + compression
   -> FastAPI + ranked worklist + provenance API

  RENDER WORKFLOW  fans out one retrying probe per authority, then reconciles
```

Python 3.12, FastAPI, httpx, rapidfuzz. React + TypeScript + Tailwind dashboard on a Render Static Site, plus a zero-dependency Jinja2 dashboard the API serves itself. CI on GitHub Actions: ruff, ruff format, 69 tests, and an anti-fabrication guard.

**This is not a wrapper around a model API.** Delete all four models and Throughline still ingests five sources, resolves entities with no shared identifier, computes seven kinds of divergence, gates them on measured coverage, persists the series, and reports a rate. A test enforces that boundary: the engine modules are forbidden from importing the model layer.

The models do one narrow job: judging whether an *already-detected* discrepancy is a genuine conflict or a formatting artefact. They never count, never set severity, never decide a divergence exists.

### Challenges we ran into

**Absence isn't evidence.** Covered above, it cost us ~650 findings and it's the thing we're proudest of.

**Entity resolution with no shared key.** Five registries describe overlapping sets of real places and not one carries an identifier the others recognise. The city's school layer carries `GADOE_ID`; the federal directory carries `ncessch`; neither recognises the other. A false match invents a disagreement between two places that were never the same place. So: blocking on ZIP and name head, rapidfuzz with address weighted above name, and an explicit review band (72-88) where the system *declines to merge* rather than guess. `GET /api/matches` exposes what we nearly merged.

**Atlanta is quadrant-addressed.** NW versus NE is load-bearing, the same street number exists in more than one quadrant. `"929 CHARLES ALLEN DRIVE N. E."` and `"929 Charles Allen Dr NE"` are the same building and must normalize identically.

**A 200 isn't a success: and our own guard proved it too aggressively.** Government hosts answer rate-limited clients with challenge pages served as HTTP 200, so our connectors validate payload shape rather than the status line. Then the guard rejected a perfectly good 13-byte `{"count":681}` as a suspected block page. A WAF challenge is HTML, so size is only evidence when the body isn't valid JSON. Parse first, then judge size. Six tests now cover both directions.

**Deployed code fails differently.** Our first Render Workflow run died on `asyncio.run() cannot be called from a running event loop`, the SDK executor already runs inside a loop and awaits coroutine tasks natively. It retried four times before surfacing, which was independent evidence the retry policy worked.

### Accomplishments we're proud of

- We found something real, in public data, about children, in the host city, sitting unmeasured for four years.
- Our tool suppressed its own headline number rather than overstate it.
- 69 tests. Green CI. A guard that fails rather than skips, sees untracked files, and includes non-vacuity checks so a bug that made it scan nothing would fail rather than go green.
- Every claim on every screen is independently verifiable by a stranger, against public URLs, with no API key.

### What we learned

That the hardest part of interoperability isn't the pipes, it's knowing when your evidence doesn't support your conclusion. We spent more of the build on the coverage gate than on any single connector, and it's the part that makes the rest trustworthy.

Concretely: probabilistic entity resolution, USPS address normalization, the Census batch geocoder, ArcGIS FeatureServer layer discovery, TimescaleDB hypertables and continuous aggregates, Render's Workflows SDK, Snowflake keypair JWT auth, and structured-output prompting across four different model families on four clouds.

### What's next for Throughline

The spec this was built from sequences two products. We built **The Ledger**, the audit. Next is **The Relay**: when a child's placement changes, automatically deliver the transcript, immunization record, IEP, and current court order to the receiving school *before the child arrives*.

More immediately: the 2025 licence roll for a genuine year-over-year series, and a scheduled Workflow so the divergence rate is tracked continuously and can be shown to fall.

### Explicit non-goals

Enforced in the code, not just stated:

- **No predictive risk scoring.** Prediction from a broken record is the problem, not the fix.
- **No case management.** We never compete with the systems that feed us.
- **No automated decision affecting a child's placement or a parent's rights.** Throughline surfaces discrepancies. Humans decide. Always.

---

## Built with

`python` · `fastapi` · `render` · `render-workflows` · `timescaledb` · `tigerdata` · `google-gemini` · `gemma` · `digitalocean` · `digitalocean-gradient` · `rapidfuzz` · `arcgis` · `us-census-geocoder` · `nces` · `atlanta-open-data` · `github-actions` · `jinja2` · `httpx` · `asyncpg`

## Try it out

- Live: https://throughline-api-yo1p.onrender.com
- Repo: https://github.com/StephenSook/throughline
- API docs: https://throughline-api-yo1p.onrender.com/docs
- Proof the hypertables are real: https://throughline-api-yo1p.onrender.com/api/storage

---

## Prize categories to check: ALL EIGHT

Each is load-bearing, greppable in the shipped code, and verifiable by a judge on the deployed URL.

- [x] **Best Hack for Good**
- [x] **Best Use of Atlanta Open Data**, three City of Atlanta datasets are the engine's input, not decoration
- [x] **Best Use of Render Workflows**, `workflow.py`, service `throughline-workflow`, three registered tasks, green run returning 813 divergences across three concurrently-probed authorities
- [x] **Best Use of Tiger Data** (both listings). TimescaleDB 2.29.1 on Tiger Cloud: two hypertables, the `divergence_rate_hourly` continuous aggregate, a compression policy on closed chunks. Proof: `/api/storage`
- [x] **Best Use of Gemini API**, panel seat 1, `gemini-3.6-flash`
- [x] **Best Use of Gemma 4**, panel seat 2, `gemma-4-31b-it`
- [x] **Best Use of DigitalOcean**, panel seat 3, `openai-gpt-oss-120b` on Gradient serverless inference
- [x] **Best Use of Snowflake API**, panel seat 4, `llama3.3-70b` via Cortex over the SQL API v2, keypair JWT auth

Verified live on the deployed API: all four seats returned verdicts on the Thomasville finding. Proof a judge can click: `/api/panel`.

## Required form fields

**"Which of the following AI tools did you use?"** → `Gemini`

*(The dropdown is single-select. Gemini is the right answer, it is panel seat 1 and the field that gates the Gemini prize. Gemma, DigitalOcean Gradient and Snowflake Cortex are all named in the textarea below.)*

**"Did you implement a generative AI model or API in your hack?"**

> Yes: as a four-seat adjudication panel on four different clouds. Gemini 3.6 Flash (Google AI Studio), Gemma 4 31B (Google AI Studio, open weights), GPT-OSS-120B (DigitalOcean Gradient, open weights) and Llama 3.3 70B (Snowflake Cortex, reached over the SQL API with keypair JWT auth) each vote independently on whether an already-detected discrepancy is a genuine conflict between authorities or an artefact of formatting and abbreviation. Every vote is stored and displayed with its rationale including dissent, and a model that fails to answer is recorded as an error rather than counted as agreement.
>
> Four seats rather than one is deliberate: two voters can only agree or deadlock, more produce a majority with a visible minority, and four vendors on four infrastructures mean a single provider outage degrades the panel instead of ending it. We saw exactly that in production. DigitalOcean returned 402 when trial credits ran out, and the panel reported it as an error rather than counting it as agreement.
>
> Deliberately, the models are used only on the ambiguous tail and never produce a number. They do not count, do not set severity, and do not decide that a divergence exists, all eight divergence rules are deterministic Python. Delete all four models and the system still ingests five public sources, resolves entities across them with no shared identifier, computes divergences, persists the time series, and reports a rate. A test in our CI enforces that boundary by forbidding the engine modules from importing the model layer.

**"Gemini Project Number"** → `150614014893`

**"Share feedback about any technology you interacted with at this hackathon"**

> **Render**: creating the web service and deploying from GitHub took under two minutes, and getting a green deploy before writing any engine code removed the usual end-of-hackathon deployment panic entirely. Render Workflows (beta) was the highlight: `render_sdk` 0.7.0, tasks as decorated functions with per-task retry and timeout, and a fan-out shape a cron entry can't express. Two things worth flagging for other teams: Blueprints can't yet declare Workflows, so `render.yaml` covers the web service only and the Workflow is created in the dashboard; and tasks must be `async def`, the executor already runs inside an event loop, so `asyncio.run()` inside a task raises. One more: Render Postgres ships TimescaleDB in Apache edition only, so continuous aggregates aren't available there.
>
> **Tiger Data**: the Tiger CLI made this the smoothest integration of the night: `brew install --cask timescale/tap/tiger-cli`, OAuth login, `tiger service create`, and a ready TimescaleDB service in about ninety seconds with the password stored in the system keyring rather than pasted anywhere. Continuous aggregates are exactly right for a longitudinal benchmark, since the series only grows and the chart has to stay fast as it does.
>
> **Gemini API**: `models.list` was the fastest way to confirm which model IDs a key can actually reach. One gotcha: with `maxOutputTokens` set low, a reasoning model's thinking budget can consume the whole allowance and return a candidate with no text part, which is indistinguishable from a refusal. Raising the cap and joining every text part fixed it; `responseMimeType: application/json` made verdicts parse reliably.
>
> **DigitalOcean Gradient**: pleasant surprise: the standard DO API token works directly against the OpenAI-compatible inference endpoint, no separate model-access key needed, and `openai-gpt-oss-120b` returned clean structured JSON first try.
>
> **Atlanta Open Data**: the `opendata.atlantaga.gov` portal is dead (TLS failure, Azure 404 behind it), but the underlying ArcGIS Online organisation is fully live and unauthenticated. Layer IDs are non-obvious and non-sequential, child care is layer 6, business licences layer 50, so `/FeatureServer?f=json` is essential for discovery. Several datasets carry `SOURCE` and `SOURCEDATE` columns that make provenance auditing possible, which is exactly what our project depends on.
