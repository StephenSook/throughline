# Demo video script — Hack RenderATL

Built on the Sookra Pitch Arc + PAS (Problem · **Agitate** · Solution). The Agitate phase is the one 90% of pitches skip, and it is what makes the demo land as *relief* rather than as a feature tour.

**Hard rules from MLH:** under 2:00 · created today · must open with the hackathon name · repo and video stay public afterwards.

**Record:** screen capture of `https://throughline-api-yo1p.onrender.com/` — the deployed URL, never localhost.

**Target 1:50.** The required MLH intro line is technically a "company introduction first" anti-pattern, so say it fast and flat and get to the hook inside five seconds.

---

### 0:00 — 0:05 · The required line. Fast, then move.

> "Hey, I'm Stephen, and this is my demo for Hack RenderATL."

### 0:05 — 0:20 · HOOK — startling statistic + curiosity gap

*(On screen: the top of the dashboard.)*

> "Right now, the City of Atlanta is publishing a list of six hundred and eighty-one licensed child care facilities. Places where you would leave your kid.
>
> That data was last checked on October twenty-first, twenty twenty-one.
>
> The dataset says so itself. Nobody has looked since."

### 0:20 — 0:40 · AGITATE — stay in the problem longer than is comfortable

> "Four years and ten months. In that time, facilities closed. Moved. Lost a licence. A parent searching Atlanta's official open data today is reading twenty twenty-one and has no way to know it.
>
> And this is not just a stale spreadsheet. This is the exact failure that runs through child welfare. A kid in foster care exists inside six institutions that don't talk to each other — the agency, the court, the school district, Medicaid. The record is treated as true when it isn't. That's why a child shows up at a new school with no transcript and sits out for weeks.
>
> Nobody has ever measured how wrong these records actually are. So we built the thing that measures it."

### 0:40 — 0:55 · SOLUTION + DEMO BRIDGE. Click **Run reconciliation**.

> "Let me show you this running live right now, against four public sources — three City of Atlanta datasets and the U.S. Census Bureau."

*(Numbers land. **Do not talk over them.** This is the pause button.)*

### 0:55 — 1:15 · Narrate outcomes, not features

> "Twelve hundred and eighty-one entities, resolved across three authorities that share no common identifier. Seven hundred and ninety-one divergences. A fifty-three percent divergence rate.
>
> Six hundred and fifty-eight records asserted as current whose own source date is four years old.
>
> And fifty-eight addresses that the U.S. Census Bureau cannot resolve at all. That's one federal authority refusing to confirm a municipal one. Every source is public. No API key. You can reproduce this yourself in a browser."

### 1:15 — 1:38 · The "shouldn't be possible" moment. Scroll to the **coverage gate** and stop.

> "Here's the part I care about most.
>
> Our first run said thirteen hundred and thirty-one divergences. Six hundred and fifty-six of those claimed facilities were missing from the city's current licence roll.
>
> That number was wrong — and it was wrong in our favour. That roll has five hundred and six records for the entire city. Six are child care. It is far too small to prove anything.
>
> So Throughline measures whether a source is even big enough to draw a conclusion from. It measured zero point three percent against a required twenty-five. Then it deleted six hundred and fifty-six of its own findings and told you exactly why.
>
> A tool about record integrity that inflates its own number is committing the failure it exists to detect."

### 1:38 — 1:50 · The close. The line they remember.

> "Entity resolution with no shared key. Six deterministic rules. Provenance and a hash on every claim. Gemini and Gemma vote only on the ambiguous tail — delete both models and this still works. The verdict is ours, not a vendor's.
>
> We couldn't demo on real child records. They're confidential, and we refused to fake them. So we proved it on Atlanta's own public data instead.
>
> Throughline surfaces the discrepancies. Humans decide. Always."

---

## Anti-patterns this script deliberately avoids

Per the guide, never in the first 30 seconds: company introduction (constrained by MLH, so kept to 5s and flat) · agenda slide · **apology or hedge** — never say "we only had 24 hours" · technical jargon opening · generic market statistics. Lead with the person and the number, never the stack. The stack lands at 1:38, after the proof.

## Measure the shipped file before calling it final

Frame-checking is not enough — audio is a channel too, and quiet narration has shipped before.

```bash
ffprobe -v error -show_entries format=duration,size \
  -show_entries stream=width,height,r_frame_rate \
  -of default=noprint_wrappers=1 demo.mp4        # duration MUST be <= 120

ffmpeg -i demo.mp4 -af ebur128 -f null - 2>&1 | tail -12   # integrated -14 to -16 LUFS
```

If integrated loudness is below about -20 LUFS, normalize before upload:

```bash
ffmpeg -i demo.mp4 -af loudnorm=I=-15:TP=-1.5:LRA=11 -c:v copy demo-final.mp4
```

Upload to YouTube **Public** — not Unlisted; MLH requires it stay public post-event. Confirm it plays in a logged-out incognito window before pasting the link into Devpost.
