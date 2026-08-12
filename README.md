# Throughline

**A record-integrity layer.** It reconciles what one institution *asserts* about an entity against independent authorities, and reports typed divergence with provenance and confidence on every field.

Built at **Hack RenderATL**, August 12 2026.

---

## The finding

Atlanta's public GIS publishes **`Atlanta_Child_Care_Facilities`** — 681 licensed facilities where children are placed.

Every row carries its own provenance, and it says this:

```
SOURCE      https://families.decal.ga.gov/provider/data
SOURCEDATE  1634774400000   ->   2021-10-21
```

That is the Georgia state child care licensing registry, snapshotted on **October 21, 2021**, and republished as current ever since. Anyone reading it today — a parent, a researcher, a city service, a caseworker — is reading 2021.

Nobody had measured what has drifted since. Throughline measures it.

> The spec this was built from puts it in one line: *"Silent staleness is the disease we are curing."*

## Why this matters beyond one dataset

A child in foster care exists simultaneously inside five or six institutions — the child welfare agency, the family court, whichever school district they are enrolled in, Medicaid, the placement provider. None of these systems exchange data reliably. The agency's record is treated as the authoritative account of that child's life, and it is frequently wrong.

The consequence is not administrative. It is that a child arrives at a new school with no transcript and sits out for weeks, repeats a class they already passed, or misses a prescription because nobody knew about it.

Real child-welfare records are confidential by federal law, so no hackathon project can honestly demo on them. **So we did not fake them.** Throughline runs on real public institutional records from the same city, exhibiting the same failure mode, and the number it reports is genuinely computed from live public APIs.

## Explicit non-goals

Carried from the product spec, and enforced in the code:

- **No predictive risk scoring.** Prediction from a broken record is the problem, not the fix.
- **No case management.** We never compete with the systems that feed us. Neutrality is the point.
- **No automated decision affecting a child's placement or a parent's rights.** Throughline surfaces discrepancies. Humans decide. Always.

## Status

Under active construction. See [`PLAN.md`](./PLAN.md) for live build status and ownership.

## License

MIT — see [`LICENSE`](./LICENSE).
