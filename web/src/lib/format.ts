export function formatInt(n: number): string {
  return n.toLocaleString("en-US");
}

export function formatPct(ratio: number, digits = 1): string {
  return `${(ratio * 100).toFixed(digits)}%`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatAgeYears(ageDays: number | null): string | null {
  if (ageDays == null) return null;
  return `${(ageDays / 365.25).toFixed(1)}y`;
}

export const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

export function severityRank(severity: string): number {
  return SEVERITY_ORDER[severity] ?? 99;
}
