import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { ClaimValue } from "../lib/types";
import { getProvenance } from "../lib/api";
import { formatAgeYears, formatDate } from "../lib/format";

function CopySha({ sha256 }: { sha256: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        await navigator.clipboard.writeText(sha256);
        setCopied(true);
        setTimeout(() => setCopied(false), 1200);
      }}
      className="font-mono-tab text-[11px] text-muted hover:text-accent underline decoration-dotted underline-offset-2"
      title="Click to copy full hash"
    >
      sha {sha256.slice(0, 10)}
      {copied ? " · copied" : ""}
    </button>
  );
}

export default function ProvenanceCard({ value }: { value: ClaimValue }) {
  const [open, setOpen] = useState(false);
  const ageYears = value.age_days != null ? value.age_days / 365.25 : null;
  const ageOverYear = ageYears != null && ageYears > 1;

  const provenanceQuery = useQuery({
    queryKey: ["provenance", value.claim_id],
    queryFn: () => getProvenance(value.claim_id),
    enabled: open,
  });

  return (
    <div className="border border-line bg-panel px-3 py-3">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <span className="font-semibold text-sm">{value.source}</span>
        <span className="font-mono-tab text-[11px] text-muted">confidence {value.confidence.toFixed(2)}</span>
      </div>
      <div className="font-mono-tab text-lg mt-1">{value.value ?? "(empty)"}</div>

      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
        <dt className="text-muted">observed</dt>
        <dd className="font-mono-tab">{formatDate(value.observed_at)}</dd>
        <dt className="text-muted">fetched</dt>
        <dd className="font-mono-tab">{formatDate(value.fetched_at)}</dd>
        {ageYears != null && (
          <>
            <dt className="text-muted">age</dt>
            <dd className={`font-mono-tab ${ageOverYear ? "text-crit font-semibold" : ""}`}>
              {value.age_days!.toFixed(1)}d · {formatAgeYears(value.age_days)}
            </dd>
          </>
        )}
      </dl>

      <div className="mt-2 flex items-center justify-between gap-3 flex-wrap">
        <CopySha sha256={value.sha256} />
        {value.source_url && (
          <a
            href={value.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono-tab text-[11px] break-all opacity-85 hover:opacity-100"
          >
            {value.source_url}
          </a>
        )}
      </div>

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="mt-2 font-mono-tab text-[11px] text-muted hover:text-accent"
      >
        {open ? "▾ hide raw source record" : "▸ view raw source record"}
      </button>

      {open && (
        <div className="mt-2 border border-line bg-bg p-2 overflow-x-auto">
          {provenanceQuery.isLoading && (
            <div className="font-mono-tab text-[11px] text-muted">loading…</div>
          )}
          {provenanceQuery.isError && (
            <div className="font-mono-tab text-[11px] text-crit">
              {(provenanceQuery.error as Error).message}
            </div>
          )}
          {provenanceQuery.data && (
            <pre className="font-mono-tab text-[11px] whitespace-pre-wrap break-all m-0">
              {JSON.stringify(provenanceQuery.data.raw_source_record, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
