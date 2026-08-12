import { useQuery } from "@tanstack/react-query";

const BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  "https://throughline-api-yo1p.onrender.com";

const MONO = 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace';

interface Run {
  run_id: string;
  at: string;
  divergence_rate: number;
  healthy: boolean;
}

export function HistoryBand() {
  const { data } = useQuery({
    queryKey: ["timeseries"],
    queryFn: () =>
      fetch(`${BASE}/api/timeseries/divergence-rate?hours=168`).then((r) => r.json()),
  });

  if (!data?.runs?.length) return null;

  const runs: Run[] = data.runs;
  const latest = runs[runs.length - 1].divergence_rate;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 20,
        padding: "10px 16px",
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderLeft: "3px solid var(--accent)",
        flexWrap: "wrap",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontFamily: MONO, fontSize: 22, color: "var(--ink)" }}>
          {(latest * 100).toFixed(1)}%
        </span>
        <span
          style={{
            fontSize: 10,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--muted)",
          }}
        >
          divergence rate: north star
        </span>
      </div>

      {/* one tick per run: cadence, not a fake trend */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 24 }}>
        {runs.map((r) => (
          <div
            key={r.run_id}
            title={`${r.run_id} · ${(r.divergence_rate * 100).toFixed(1)}%`}
            style={{
              width: 2,
              height: r.healthy ? 24 : 12,
              background: r.healthy ? "var(--accent)" : "var(--crit)",
              opacity: 0.75,
            }}
          />
        ))}
      </div>

      <span style={{ fontSize: 11, color: "var(--muted)", flex: 1, minWidth: 260 }}>
        Stable across <strong>{runs.length}</strong> runs. This falls only when the
        source record is corrected.
        {data.storage?.enabled && (
          <span style={{ fontFamily: MONO, marginLeft: 8 }}>
            · {data.storage.engine} {data.storage.timescaledb_version} continuous
            aggregate <strong>{data.view}</strong>
          </span>
        )}
      </span>
    </div>
  );
}