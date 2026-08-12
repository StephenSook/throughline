import { useQuery } from "@tanstack/react-query";
import { getDivergence } from "../lib/api";
import ProvenanceCard from "./ProvenanceCard";
import AdjudicationVotes from "./AdjudicationVotes";
import SeverityBadge from "./SeverityBadge";

export default function DetailPanel({ id }: { id: string | null }) {
  const query = useQuery({
    queryKey: ["divergence", id],
    queryFn: () => getDivergence(id as string),
    enabled: id != null,
  });

  if (id == null) {
    return (
      <div className="flex items-center justify-center h-full text-muted text-sm border border-line bg-panel">
        Select a row from the worklist to see its detail and provenance.
      </div>
    );
  }

  if (query.isLoading) {
    return <div className="p-4 text-sm text-muted border border-line bg-panel">Loading…</div>;
  }

  if (query.isError) {
    return (
      <div className="p-4 text-sm text-crit border border-line bg-panel">
        {(query.error as Error).message}
      </div>
    );
  }

  const d = query.data!;

  return (
    <div className="border border-line bg-panel overflow-y-auto h-full">
      <div className="px-4 py-4 border-b border-line">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <h2 className="text-lg font-semibold m-0">{d.subject}</h2>
          <SeverityBadge severity={d.severity} />
        </div>
        <div className="font-mono-tab text-xs text-muted mt-1">
          {d.kind} · {d.field} · confidence {d.confidence.toFixed(2)} · {d.entity_key}
        </div>
      </div>

      <div className="px-4 py-3 border-b border-line">
        <p className="text-[15px] leading-relaxed m-0">{d.detail}</p>
        {d.adjudication && <AdjudicationVotes adjudication={d.adjudication} />}
      </div>

      <div className="px-4 py-4 flex flex-col gap-3">
        {d.values.map((v) => (
          <ProvenanceCard key={v.claim_id} value={v} />
        ))}
      </div>
    </div>
  );
}
