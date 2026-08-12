import type { Coverage } from "../lib/types";
import { formatInt, formatPct } from "../lib/format";

export default function CoveragePanel({ coverage }: { coverage: Coverage }) {
  return (
    <div className="border border-line border-l-[3px] border-l-med bg-panel px-4 py-3">
      <div className="font-semibold text-sm mb-1">Coverage gate, findings suppressed</div>
      <p className="text-sm text-muted m-0">
        {coverage.note}
        <br />
        Measured coverage of <code className="font-mono-tab text-ink">{coverage.stale_authority}</code> by{" "}
        <code className="font-mono-tab text-ink">{coverage.current_authority}</code>:{" "}
        <code className="font-mono-tab text-ink">
          {formatInt(coverage.corroborated_in_current_authority)} / {formatInt(coverage.entities_in_stale_authority)} ={" "}
          {formatPct(coverage.coverage_ratio)}
        </code>
        , against a required <code className="font-mono-tab text-ink">{formatPct(coverage.min_required, 0)}</code>.
      </p>
    </div>
  );
}
