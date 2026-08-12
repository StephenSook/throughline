import { useMemo, useState } from "react";
import type { Divergence, Severity } from "../lib/types";
import { severityRank } from "../lib/format";
import SeverityBadge from "./SeverityBadge";

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];

const KIND_ROOT_CAUSE: Record<string, string> = {
  STALE_RECORD: "Source's own metadata date is years old but served as current.",
  STATUS_CONFLICT: "Authorities disagree on operational status for the same entity.",
  ADDRESS_UNRESOLVABLE: "Address could not be geocoded against the Census reference.",
  ADDRESS_MISMATCH: "Authorities report different street addresses for the same entity.",
  EMPTY_REQUIRED_FIELD: "A required field is empty in one authority's record.",
  ZIP_MISMATCH: "Authorities report different ZIP codes for the same entity.",
  GEO_DIVERGENCE: "Geocoded location diverges meaningfully from the stated address.",
  MISSING_IN_CURRENT_AUTHORITY: "Present in the stale authority, absent from the current one.",
};

function rootCauseFor(kind: string, sample: Divergence): string {
  const known = KIND_ROOT_CAUSE[kind];
  if (known) return known;
  return sample.detail.length > 90 ? `${sample.detail.slice(0, 90)}…` : sample.detail;
}

interface Group {
  kind: string;
  items: Divergence[];
  worstRank: number;
}

export default function Worklist({
  divergences,
  total,
  selectedId,
  onSelect,
}: {
  divergences: Divergence[];
  total: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [activeSeverities, setActiveSeverities] = useState<Set<Severity>>(new Set(SEVERITIES));
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return divergences.filter(
      (d) => activeSeverities.has(d.severity) && (q === "" || d.subject.toLowerCase().includes(q)),
    );
  }, [divergences, search, activeSeverities]);

  const groups = useMemo<Group[]>(() => {
    const byKind = new Map<string, Divergence[]>();
    for (const d of filtered) {
      const list = byKind.get(d.kind);
      if (list) list.push(d);
      else byKind.set(d.kind, [d]);
    }
    const result: Group[] = [];
    for (const [kind, items] of byKind) {
      const worstRank = Math.min(...items.map((d) => severityRank(d.severity)));
      result.push({ kind, items, worstRank });
    }
    result.sort((a, b) => a.worstRank - b.worstRank || b.items.length - a.items.length);
    return result;
  }, [filtered]);

  function toggleSeverity(s: Severity) {
    setActiveSeverities((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next.size === 0 ? new Set(SEVERITIES) : next;
    });
  }

  function toggleGroup(kind: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  }

  return (
    <div className="border border-line bg-panel h-full flex flex-col">
      <div className="px-3 py-3 border-b border-line flex flex-col gap-2">
        <input
          type="text"
          placeholder="Search subject…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border border-line bg-bg px-2 py-1.5 text-sm outline-none focus:border-accent"
        />
        <div className="flex gap-1.5 flex-wrap">
          {SEVERITIES.map((s) => {
            const active = activeSeverities.has(s);
            return (
              <button
                key={s}
                type="button"
                onClick={() => toggleSeverity(s)}
                className={`font-mono-tab text-[10.5px] uppercase tracking-wide border px-1.5 py-0.5 ${
                  active ? "" : "opacity-35"
                } ${
                  s === "critical"
                    ? "text-crit border-crit"
                    : s === "high"
                      ? "text-high border-high"
                      : s === "medium"
                        ? "text-med border-med"
                        : "text-low border-low"
                }`}
              >
                {s}
              </button>
            );
          })}
        </div>
        <div className="text-[12px] text-muted font-mono-tab">
          {filtered.length.toLocaleString("en-US")} of {total.toLocaleString("en-US")}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {groups.map((g) => {
          const isOpen = expanded.has(g.kind);
          return (
            <div key={g.kind} className="border-b border-line">
              <button
                type="button"
                onClick={() => toggleGroup(g.kind)}
                className="w-full text-left px-3 py-2.5 flex items-start gap-2 hover:bg-bg"
              >
                <span className="font-mono-tab text-xs text-muted mt-0.5">{isOpen ? "▾" : "▸"}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-mono-tab text-[13px] font-semibold text-ink">{g.kind}</span>
                    <span className="font-mono-tab text-[12px] text-muted">{g.items.length}</span>
                  </div>
                  <div className="text-[12px] text-muted mt-0.5 truncate">{rootCauseFor(g.kind, g.items[0])}</div>
                </div>
              </button>
              {isOpen && (
                <div>
                  {g.items.map((d) => (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => onSelect(d.id)}
                      className={`w-full text-left px-3 py-2 pl-8 border-t border-line hover:bg-bg ${
                        selectedId === d.id ? "border-l-2 border-l-accent bg-bg" : ""
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[13px] truncate">{d.subject}</span>
                        <SeverityBadge severity={d.severity} />
                      </div>
                      <div className="font-mono-tab text-[11px] text-muted mt-0.5">{d.field}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {groups.length === 0 && (
          <div className="px-3 py-6 text-sm text-muted text-center">No divergences match this filter.</div>
        )}
      </div>
    </div>
  );
}
