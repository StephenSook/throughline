// web/src/components/HistoryBand.tsx
import { useQuery } from "@tanstack/react-query";

const BASE = import.meta.env.VITE_API_BASE ?? "https://throughline-api-yo1p.onrender.com";

export function HistoryBand() {
  const { data } = useQuery({
    queryKey: ["timeseries"],
    queryFn: () => fetch(`${BASE}/api/timeseries/divergence-rate?hours=168`).then(r => r.json()),
  });
  if (!data?.runs?.length) return null;

  const runs = data.runs;
  const rates = runs.map((r: any) => r.divergence_rate);
  const min = Math.min(...rates), max = Math.max(...rates);
  const span = max - min || 0.02;                       // flat data → synthetic band
  const W = 260, H = 40;
  const pts = rates.map((v: number, i: number) => {
    const x = (i / Math.max(rates.length - 1, 1)) * W;
    const y = H - ((v - (min - span / 2)) / (span * 2)) * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  return (
    <div className="card" style={{ borderLeft: "3px solid var(--accent)", padding: "16px 20px", margin: "12px 0" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 32, flexWrap: "wrap" }}>
        <div>
          <div className="label">Divergence rate — north star</div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 28, marginTop: 4 }}>
            {(rates[rates.length - 1] * 100).toFixed(1)}%
          </div>
        </div>

        <svg width={W} height={H} style={{ overflow: "visible" }}>
          <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
        </svg>

        <div style={{ fontSize: 13, color: "var(--muted)", maxWidth: 420, lineHeight: 1.5 }}>
          Stable across <strong>{runs.length}</strong> runs. This number falls only when
          the source record is corrected — not when we look at it again.
        </div>
      </div>

      {data.storage?.enabled && (
        <div className="mono" style={{ fontSize: 11, color: "var(--muted)", marginTop: 12,
             borderTop: "1px solid var(--line)", paddingTop: 10 }}>
          served from {data.storage.engine} {data.storage.timescaledb_version} continuous
          aggregate <strong>{data.view}</strong> · {data.buckets?.length ?? 0} hourly buckets
        </div>
      )}
    </div>
  );
}