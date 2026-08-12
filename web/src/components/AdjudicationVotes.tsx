import type { Adjudication } from "../lib/types";

export default function AdjudicationVotes({ adjudication }: { adjudication: Adjudication }) {
  return (
    <div className="border border-line border-l-2 border-l-accent bg-bg px-3 py-2 mt-3">
      <div className="text-xs text-muted mb-2">
        Panel verdict: <b className="text-ink">{adjudication.verdict}</b>
        {adjudication.dissent && (
          <span className="ml-2 text-[10px] font-mono-tab uppercase tracking-wide text-high border border-high px-1.5 py-0.5">
            models disagreed
          </span>
        )}
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {Object.entries(adjudication.votes).map(([model, vote]) => (
          <div key={model} className="border border-line bg-panel px-2 py-2">
            <div className="font-mono-tab text-xs font-semibold text-ink">{model}</div>
            {vote.error ? (
              <div className="font-mono-tab text-[11px] text-muted mt-1">unavailable: {vote.error}</div>
            ) : (
              <>
                <div className="mt-1">
                  <span
                    className={`font-mono-tab text-[10px] uppercase tracking-wide border px-1.5 py-0.5 ${
                      vote.is_genuine ? "text-crit border-crit" : "text-ok border-ok"
                    }`}
                  >
                    {vote.is_genuine ? "genuine" : "artefact"}
                  </span>
                  <span className="font-mono-tab text-[11px] text-muted ml-2">
                    {vote.confidence?.toFixed(2)}
                  </span>
                </div>
                {vote.rationale && (
                  <div className="text-[12px] text-muted mt-1">{vote.rationale}</div>
                )}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
