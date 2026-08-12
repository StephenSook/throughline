import type { Summary } from "../lib/types";
import { formatInt, formatPct } from "../lib/format";

function Tile({ label, value, hero = false }: { label: string; value: string; hero?: boolean }) {
  return (
    <div className="bg-panel px-4 py-4">
      <div className="text-[11px] uppercase tracking-wider text-muted">{label}</div>
      <div
        className={`font-mono-tab mt-1 font-semibold ${
          hero ? "text-[34px] text-accent" : "text-[27px] text-ink"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

export default function StatTiles({ summary }: { summary: Summary }) {
  return (
    <div className="border border-line bg-line grid gap-px grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
      <Tile label="Divergence rate" value={formatPct(summary.divergence_rate)} hero />
      <Tile label="Divergences" value={formatInt(summary.divergences_total)} />
      <Tile label="Entities resolved" value={formatInt(summary.entities_resolved)} />
      <Tile label="Claims ingested" value={formatInt(summary.claims)} />
      <Tile label="Sources healthy" value={`${summary.sources_healthy}/${summary.sources_total}`} />
    </div>
  );
}
