import type { Severity } from "../lib/types";

const COLOR: Record<string, string> = {
  critical: "text-crit border-crit",
  high: "text-high border-high",
  medium: "text-med border-med",
  low: "text-low border-low",
};

export default function SeverityBadge({ severity }: { severity: Severity | string }) {
  return (
    <span
      className={`font-mono-tab text-[10.5px] uppercase tracking-wide border px-1.5 py-0.5 whitespace-nowrap ${
        COLOR[severity] ?? "text-muted border-line"
      }`}
    >
      {severity}
    </span>
  );
}
