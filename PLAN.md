# Throughline — Plan & Coordination

> Living status doc for Stephen + Khadim. Updated on every task change and pushed to `main`.
> Single source of truth for who is working on what. **Atomic commits — never bundle a status change with code.**

**Team:** **Stephen** — backend, connectors, entity resolution, divergence engine, TimescaleDB, Render Workflow, models, API, server-rendered dashboard, deploy, CI.
**Khadim** — React dashboard, charts, divergence detail view, design polish.
**Deadline:** 2026-08-12 **20:00 EDT** (Devpost, hard).
**Repo:** https://github.com/StephenSook/throughline
**Live API:** https://throughline-api-yo1p.onrender.com
**Contract:** https://throughline-api-yo1p.onrender.com/openapi.json
**Hackathon:** Hack RenderATL (MLH × RenderATL)

Legend: ✅ done · 🟡 in progress · ⬜ not started · ⛔ blocked · ✂️ cut
**Stale lock TTL: 30 minutes** (single-day sprint). A 🟡 task without a fresh timestamp in Notes is claimable.

---

## ⏱️ Status snapshot (last sync 17:15)

Backend engine is **working on real data**. Deployed and green since 16:45.

Live measured numbers from a real run (not seeded, not hardcoded):

| Metric | Value |
|---|---|
| Entities resolved across 3 authorities | **1,281** |
| Claims ingested | **5,945** |
| Divergences detected | **675** |
| Critical (stale record) | **658** |
| Divergence rate | **51.91%** |
| Pipeline wall time | ~0.7 s |

**The finding:** `Atlanta_Child_Care_Facilities` (681 licensed facilities) declares its own
`SOURCE = https://families.decal.ga.gov/provider/data` and `SOURCEDATE = 2021-10-21`.
The City of Atlanta has been republishing a **4.8-year-old snapshot of the Georgia state
child care licensing registry** as current data.

---

## 🌅 Khadim — read this first

Welcome. Everything you need is already deployed and public. You are not blocked on me for anything.

### Your action items, in order

1. **Look at the live API.** `https://throughline-api-yo1p.onrender.com/openapi.json` is the
   contract. `/docs` gives you Swagger UI you can click through. Every endpoint returns real
   data from real Atlanta public records — there is no mock server to outgrow.
2. **Scaffold the frontend** in `web/` at the repo root: Vite + React + TypeScript + Tailwind +
   TanStack Query + Recharts. Keep it in `web/` so it deploys as a separate Render Static Site
   and never collides with the Python service.
3. **Build these four views**, in this priority order. If you only finish the first two, we
   still ship:
   - **Summary** — the stat tiles: entities resolved, claims, divergences, divergence rate,
     sources healthy. From `GET /api/summary`.
   - **Worklist** — the ranked divergence table from `GET /api/divergences`. Sorted by
     severity, not by age. Severity chips: critical / high / medium / low.
   - **Divergence detail** — from `GET /api/divergences/{id}`. This is the money screen. Show
     every conflicting value side by side with its source, its fetch timestamp, its age, and
     its sha256. A judge must be able to read this panel and go verify it themselves.
   - **Divergence rate chart** — from `GET /api/timeseries/divergence-rate`. Recharts line.
4. **Design constraints.** Dark and light both work. This is a product about children's
   records — it should look like a serious civic instrument, not a crypto dashboard. Muted,
   high-contrast, generous whitespace, one accent colour used only for severity. No emoji in
   the UI chrome.

### What Stephen is doing in parallel — do not touch these

`src/throughline/**` (all Python), `render.yaml`, `.github/workflows/**`, `docs/**`, `README.md`.
If you need an API shape changed, write it in **Open Questions** below and ping me — do not
edit the Python.

### Contact path

1. In person at the venue (Expo Hall, 3rd floor)
2. Text / call Stephen
3. Comment in this file under Open Questions and push — I re-read it every commit

---

## Status Dashboard

### Phase 0 — Scaffold & deploy

| # | Component | File(s) | Owner | Status | Notes |
|---|---|---|---|---|---|
| 0.1 | Repo, public from creation, MIT | root | **Stephen** | ✅ 16:43 | Public at creation per MLH ("code must be available in a public repository"). First commit `a1586c0`, timestamped today — no prior work. |
| 0.2 | Python scaffold, uv lock | `pyproject.toml`, `uv.lock` | **Stephen** | ✅ 16:43 | Python ≥3.11, FastAPI + httpx + rapidfuzz. `uv sync --frozen` matches the proven Render build command. |
| 0.3 | Render web service | `render.yaml` | **Stephen** | ✅ 16:45 | **Dedicated new service** `throughline-api` (`srv-d9ucq00n74is73devadg`) — deliberately not reusing any of the 10 existing services in the workspace. |
| 0.4 | Deploy gate: 200 from the internet | — | **Stephen** | ✅ 16:45 | `curl https://throughline-api-yo1p.onrender.com/api/health` → HTTP 200 in 0.25s, serving commit `9e9bfec`. Deployed empty *before* writing the engine, so deploy risk was retired first. |
| 0.5 | Collaborator invite | — | **Stephen** | ✅ 16:44 | `khadimswe` invited with write access. |
| 0.6 | PLAN.md, no hooks | `PLAN.md` | **Stephen** | ✅ 17:15 | Manual coordination only — no `.githooks`, no `scripts/plan`, no CLI. Mirrors Hometown-Pathway-Atlas. Both of us just type in the Notes column. |

### Phase 1 — The engine (real data)

| # | Component | File(s) | Owner | Status | Notes |
|---|---|---|---|---|---|
| 1.1 | Data model: Claim / Entity / Divergence | `core/models.py` | **Stephen** | ✅ 16:52 | Claims are append-only and never collapsed to a "current value" — that collapse is what destroyed the information we're recovering. Claim IDs are **length-prefixed**, never separator-joined, so two distinct claims cannot collide into one identity. |
| 1.2 | Normalization | `core/normalize.py` | **Stephen** | ✅ 16:53 | USPS suffix map + Atlanta quadrant directionals. Quadrants are load-bearing: same street number exists in NW and NE, and dropping the directional would merge two different places. |
| 1.3 | Connector plumbing | `connectors/base.py` | **Stephen** | ✅ 16:56 | **Validates content, not status code.** A WAF challenge page served as HTTP 200 would otherwise land in the corpus as data. Rejects <200-byte bodies and ArcGIS errors embedded in 200 responses. Failed fetches are never persisted. |
| 1.4 | Atlanta connectors (A, B, D) | `connectors/atlanta.py` | **Stephen** | ✅ 17:02 | Verified live: childcare **681**, licences **506**, schools **132**. Layer IDs are non-obvious (6, 50, 0) and were read off each `FeatureServer?f=json`. |
| 1.5 | Census geocoder connector | `connectors/census.py` | **Stephen** | ✅ 17:00 | Batch endpoint, 500-row chunks. Distinguishes "Census declined this address" (evidence) from "Census never answered" (not evidence) — only the first can produce a finding. |
| 1.6 | Entity resolution | `core/resolve.py` | **Stephen** | ✅ 17:04 | Blocking on ZIP + name head, rapidfuzz scoring, address weighted 0.6 over name 0.4. Explicit review band (72–88) where we **decline to merge** rather than guess. Unmatched records are kept, not dropped — a facility appearing in only the stale registry is the most interesting row, and dropping it would flatter the rate. |
| 1.7 | Divergence engine, 6 rules | `core/diverge.py` | **Stephen** | ✅ 17:05 | `STALE_RECORD`, `ADDRESS_UNRESOLVABLE`, `GEO_DIVERGENCE`, `ZIP_MISMATCH`, `MISSING_IN_CURRENT_AUTHORITY`, `EMPTY_REQUIRED_FIELD`. Deterministic — no model runs here, so every verdict is reproducible by hand from public URLs. |
| 1.8 | **Coverage gate** | `core/diverge.py` | **Stephen** | ✅ 17:14 | First run reported 656 `MISSING_IN_CURRENT_AUTHORITY`. Investigated instead of shipping it: the licence roll is **506 records for the whole city, 6 of them child day care**, so absence from it proves nothing. Measured coverage ratio = **0.003** vs 0.25 required → the rule now **suppresses itself** and says why. Killed 656 false findings and dropped the headline from 1,331 to **675 fully-evidenced** ones. |
| 1.9 | Pipeline: ingest → resolve → diverge | `core/pipeline.py` | **Stephen** | ✅ 17:12 | One code path shared by the API, the CLI and the Render Workflow so they cannot drift. Partial-source runs complete and record the outage rather than silently narrowing input. |

### Phase 2 — API, persistence, models  *(in progress)*

| # | Component | File(s) | Owner | Status | Notes |
|---|---|---|---|---|---|
| 2.1 | All API endpoints on real data | `api/main.py` | **Stephen** | 🟡 17:15 | |
| 2.2 | TimescaleDB hypertable + continuous aggregate | `core/store.py`, `schema.sql` | **Stephen** | ⬜ | Tiger Cloud free tier. **Not** Render Postgres: it ships timescaledb Apache-edition only, which has no continuous aggregates. |
| 2.3 | Render Workflow | `workflow.py` | **Stephen** | ⬜ | `render_sdk` 0.7.0. Blueprints can't create Workflows — dashboard only. |
| 2.4 | Gemini adjudication + assessment narrative | `core/adjudicate.py` | **Stephen** | ⬜ | Models judge the ambiguous tail only. They never produce a number. |
| 2.5 | Server-rendered dashboard | `api/templates/` | **Stephen** | ⬜ | Ships with the API. This is the product's face regardless of whether the React app lands. |
| 2.6 | CI: ruff + pytest + anti-fabrication guard | `.github/workflows/ci.yml` | **Stephen** | ⬜ | Guard must **fail**, not skip, under CI, and must see untracked files. |

### Phase 3 — Frontend

| # | Component | File(s) | Owner | Status | Notes |
|---|---|---|---|---|---|
| 3.1 | Vite + React + TS scaffold | `web/` | **Khadim** | ⬜ | |
| 3.2 | Summary tiles | `web/src/` | **Khadim** | ⬜ | |
| 3.3 | Divergence worklist | `web/src/` | **Khadim** | ⬜ | |
| 3.4 | Divergence detail + provenance panel | `web/src/` | **Khadim** | ⬜ | The money screen. |
| 3.5 | Divergence rate chart | `web/src/` | **Khadim** | ⬜ | |

### Phase 4 — Submission

| # | Component | Owner | Status | Notes |
|---|---|---|---|---|
| 4.1 | Freeze (19:05) — claim-correcting changes only | **Stephen** | ⬜ | |
| 4.2 | Judge-path smoke test, cold incognito | **Stephen** | ⬜ | |
| 4.3 | Demo video ≤2:00, recorded today | **Stephen** | ⬜ | Must open "…this is my demo for Hack RenderATL". |
| 4.4 | Devpost submission | **Stephen** | ⬜ | Primary judged artifact. Draft during Phase 2, not after the video. |

---

## Shared Contracts

| Contract | Owner | Consumers | Definition |
|---|---|---|---|
| REST API shape | Stephen | Khadim | `GET /openapi.json` on the live service. Generated from the code, so it cannot drift from the implementation. |
| Divergence object | Stephen | Khadim | `{id, entity_key, subject, field, kind, severity, confidence, detail, values[], adjudication?}` — see `Divergence.to_dict()` in `core/models.py`. |
| `values[]` entry | Stephen | Khadim | `{claim_id, source, source_url, value, observed_at, fetched_at, age_days, confidence, sha256}`. Every one of these renders in the provenance panel. |
| Severity vocabulary | Stephen | Khadim | Exactly `critical` \| `high` \| `medium` \| `low`. Ranked by consequence to a person, never by record age. |
| CORS | Stephen | Khadim | Open on GET/POST so the static site can call the API cross-origin. |

**Contract changes are announced here BEFORE they are committed.** Contract drift is the number one small-team integration bug.

---

## Decisions

### D1 — The load-bearing core runs on real public records, never synthetic
Real child-welfare records are confidential by federal law, so no honest hackathon demo can use them. Rather than fabricate a child cohort, the divergence engine runs on real Atlanta public institutional records exhibiting the same failure mode. Every number the product reports is computed from live public APIs and is independently verifiable by anyone. **Locked 16:00 by Stephen.**

### D2 — Deterministic before probabilistic; models never decide
All six divergence rules are deterministic Python. LLMs adjudicate only the ambiguous tail, and every vote is stored and displayed alongside the deterministic verdict. Delete every model from this system and it still ingests, resolves, diverges, and charts. That is the difference between a system and a wrapper. **Locked 16:05 by Stephen.**

### D3 — Tiger Cloud, not Render Postgres
Render ships the `timescaledb` extension but documents "Community features are not available" — the Apache edition, with no continuous aggregates and no compression, which are precisely the two capabilities we need. **Locked 16:20 by Stephen.**

### D4 — The coverage gate suppresses our own headline
When a corroborating authority covers too few of the entities in question, absence from it is a fact about that authority, not about the entity. Measured at 0.003 here, so 656 findings were suppressed. A tool that inflates its own divergence count using an unchecked source would be committing the exact error it exists to detect. **Locked 17:14 by Stephen.**

### D5 — The backend ships its own dashboard
Khadim's React app is an upgrade, not a dependency. The server-rendered dashboard is the shipped product, so the demo cannot be blocked on frontend availability. **Locked 16:00 by Stephen.**

---

## Open Questions

- [ ] **Q1 (Khadim):** Do you want me to scaffold `web/` with Vite + Tailwind + a typed API client so you only write components, or would you rather set it up yourself? Answer here and I'll do it in the next commit.
- [ ] **Q2 (Stephen):** Render Workflows is public beta and metered — decision point at 18:10. If it isn't live by then, we fall back to a cron job **and drop the Render Workflows track claim entirely** rather than claim something unwired.
- [ ] **Q3 (Stephen):** Whether to add `Revenue_BizLicenses_2025` (layer 46) as a fourth source. It would give a genuine year-over-year time series, but only if the 17:55 gate is already met.

---

## Risk Register

| Risk | Mitigation |
|---|---|
| **The clock (20:00 EDT hard)** | Pre-decided cut ladder. Deploy went green at 16:45, before any engine code existed. |
| A source goes down mid-demo | Golden run persisted before freeze, with a visible "cached run" banner. Never silent. |
| Render free-tier cold start during judging | Keepalive cron on offset minutes from 18:00. Verified by newest-run age, not by green runs. |
| Claiming a track we didn't wire | Every named tool gets grepped against shipped source before README, video, and Devpost text. If it got cut, the word doesn't appear. |
| Overclaiming a divergence count | The coverage gate (D4). Already caught one 656-finding inflation. |
| Contract drift between Stephen + Khadim | `/openapi.json` is generated from the code. Changes announced in Shared Contracts before commit. |
| PLAN.md drift | Atomic plan commits. 30-minute stale-lock TTL. |

---

_Last updated: 2026-08-12 17:15 EDT by Stephen — coverage gate landed, 656 false findings suppressed, engine green on real data._
