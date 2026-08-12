# Demo video script — Hack RenderATL

**Hard rules from MLH:** under 2:00 · created today · must open with the hackathon name · repo and video stay public afterwards.

**Record:** screen capture of `https://throughline-api-yo1p.onrender.com/` — the deployed URL, never localhost. Full screen, browser chrome visible so it reads as real.

Target: **1:45**. Leave headroom under the 2:00 cap.

---

### 0:00 — 0:08 · The required line, said plainly

> "Hey, I'm Stephen, and this is my demo for Hack RenderATL."

### 0:08 — 0:30 · The finding. Point at the top of the page.

> "Atlanta publishes a public dataset of six hundred and eighty-one licensed child care facilities. Places where children are placed.
>
> The dataset carries its own metadata, and it says the data came from the Georgia state licensing registry on October twenty-first, twenty twenty-one. It has been served as current ever since. Four years and ten months.
>
> Nobody had measured what drifted. So we built the thing that measures it."

### 0:30 — 0:45 · Run it live. Click **Run reconciliation**.

> "This is running right now against four live public sources. Three City of Atlanta datasets, and the U.S. Census Bureau geocoder."

*(Let the numbers land on screen. Do not talk over them.)*

> "Twelve hundred and eighty-one entities resolved across authorities that share no common identifier. Five thousand nine hundred claims. Seven hundred and ninety-one divergences. A fifty-three percent divergence rate."

### 0:45 — 1:05 · Scroll to the worklist. Open one finding.

> "Every one of these is evidence, not an opinion. This facility is asserted OPEN by a record whose own source date is four years and ten months old.
>
> And fifty-eight of these addresses cannot be resolved by the U.S. Census Bureau at all. That is one federal authority declining to confirm a municipal one. Anyone can reproduce it — every source we use is public and needs no key."

### 1:05 — 1:25 · Scroll to the **coverage gate**. This is the moment.

> "Here's the part I'm most proud of.
>
> Our first run reported thirteen hundred and thirty-one divergences. Six hundred and fifty-six of them said 'listed as open in the state registry, missing from the city's current licence roll.'
>
> That number was wrong, and it was wrong in our favour. That licence roll has five hundred and six records for the entire city. Six are child care. It's too small to prove anything.
>
> So Throughline measures the corroborating source's coverage before it draws any conclusion from absence. It measured zero point three percent, against a required twenty-five. It suppressed its own six hundred and fifty-six findings and told you why.
>
> A tool about record integrity that inflates its own headline would be committing the exact failure it exists to detect."

### 1:25 — 1:40 · What's underneath.

> "Entity resolution across sources with no shared key. Six deterministic divergence rules. Provenance and a content hash on every claim. Gemini and Gemma vote on the ambiguous tail only — delete both models and this still works. The verdict is ours, not a vendor's."

### 1:40 — 1:50 · The throughline. Land it.

> "A child in foster care lives inside six institutions that don't talk to each other, and the record is treated as true when it isn't. That's why a kid shows up at a new school with no transcript and sits out for weeks.
>
> We can't demo on real child records — they're confidential, and we refused to fake them. So we proved it on Atlanta's own public records instead.
>
> Throughline surfaces the discrepancies. Humans decide. Always."

---

## Before you call it final — measure the shipped file, don't eyeball it

```bash
ffprobe -v error -show_entries format=duration,size -show_entries stream=width,height,r_frame_rate \
  -of default=noprint_wrappers=1 demo.mp4          # duration MUST be <= 120

ffmpeg -i demo.mp4 -af ebur128 -f null - 2>&1 | tail -12   # integrated target -14 to -16 LUFS
```

If loudness is below about -20 LUFS, normalize before uploading — quiet narration has shipped before and it reads as low effort:

```bash
ffmpeg -i demo.mp4 -af loudnorm=I=-15:TP=-1.5:LRA=11 -c:v copy demo-final.mp4
```

Upload to YouTube as **Public** (not Unlisted — MLH requires it stay public post-event). Confirm it plays in a logged-out incognito window before pasting the link into Devpost.
