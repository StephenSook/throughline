import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { HistoryBand } from "./components/HistoryBand";
import { getAllDivergences, getSummary } from "./lib/api";
import Header from "./components/Header";
import DegradedBanner from "./components/DegradedBanner";
import StatTiles from "./components/StatTiles";
import CoveragePanel from "./components/CoveragePanel";
import Worklist from "./components/Worklist";
import DetailPanel from "./components/DetailPanel";

export default function App() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const summaryQuery = useQuery({ queryKey: ["summary"], queryFn: getSummary });
  const divergencesQuery = useQuery({ queryKey: ["divergences", "all"], queryFn: getAllDivergences });

  const degraded = summaryQuery.data?.degraded ?? divergencesQuery.data?.degraded ?? null;

  return (
    <div className="h-screen flex flex-col">
      <Header />

      <div className="px-4 py-4 flex flex-col gap-3">
        {degraded && <DegradedBanner message={degraded} />}

        {summaryQuery.isLoading && <div className="text-sm text-muted">Loading summary…</div>}
        {summaryQuery.isError && (
          <div className="text-sm text-crit">{(summaryQuery.error as Error).message}</div>
        )}
        {summaryQuery.data && (
  <>
    <StatTiles summary={summaryQuery.data} />
    {!summaryQuery.data.coverage.sufficient_for_absence_claims && (
      <CoveragePanel coverage={summaryQuery.data.coverage} />
    )}
    <HistoryBand />
  </>
)}
      </div>

      <main className="flex-1 min-h-0 px-4 pb-4 grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-4">
        {divergencesQuery.isLoading && (
          <div className="text-sm text-muted lg:col-span-2">Loading divergences…</div>
        )}
        {divergencesQuery.isError && (
          <div className="text-sm text-crit lg:col-span-2">{(divergencesQuery.error as Error).message}</div>
        )}
        {divergencesQuery.data && (
          <>
            <div className="min-h-0">
              <Worklist
                divergences={divergencesQuery.data.items}
                total={divergencesQuery.data.total}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
            </div>
            <div className="min-h-0">
              <DetailPanel id={selectedId} />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
