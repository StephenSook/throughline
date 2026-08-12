export default function Header() {
  return (
    <header className="border-b border-line px-6 py-4 flex items-baseline justify-between gap-4 flex-wrap">
      <div className="flex items-baseline gap-3">
        <span className="text-xl font-semibold tracking-tight">Throughline</span>
        <span className="text-sm text-muted">record integrity layer</span>
      </div>
      <a
        href={`${import.meta.env.VITE_API_BASE ?? "https://throughline-api-yo1p.onrender.com"}/docs`}
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs font-mono-tab text-muted hover:text-accent"
      >
        API docs ↗
      </a>
    </header>
  );
}
