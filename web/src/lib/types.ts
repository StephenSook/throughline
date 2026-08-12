export type Severity = "critical" | "high" | "medium" | "low";

export interface SourceHealth {
  id: string;
  label: string | null;
  ok: boolean;
  row_count: number | null;
  fetched_at: string | null;
  error: string | null;
}

export interface Coverage {
  stale_authority: string;
  current_authority: string;
  entities_in_stale_authority: number;
  corroborated_in_current_authority: number;
  coverage_ratio: number;
  min_required: number;
  sufficient_for_absence_claims: boolean;
  note: string;
}

export interface AdjudicationSummary {
  enabled: boolean;
  models: string[];
  providers: Record<string, string>;
  seats: number;
  ambiguous_total: number;
  adjudicated: number;
  limit: number;
  not_adjudicated: number;
  note: string;
  reason?: string;
}

export interface Persistence {
  persisted: boolean;
  run_id: string;
  observations: number;
  claims: number;
}

// GET /api/summary — spreads run.summary, then adds degraded / sources_healthy / sources_total.
export interface Summary {
  entities_resolved: number;
  claims: number;
  divergences_total: number;
  entities_with_divergence: number;
  divergence_rate: number;
  by_severity: Record<string, number>;
  by_kind: Record<string, number>;
  computed_at: string;
  coverage: Coverage;
  elapsed_ms: number;
  run_id: string;
  sources_ok: number;
  sources_total: number;
  adjudication: AdjudicationSummary | null;
  persistence: Persistence | null;
  degraded: string | null;
  sources_healthy: number;
}

// One entry in a divergence's values[] — a single claim from a single source.
export interface ClaimValue {
  claim_id: string;
  source: string;
  source_url: string | null;
  value: string | null;
  observed_at: string | null;
  fetched_at: string;
  age_days: number | null;
  confidence: number;
  sha256: string;
}

export interface AdjudicationVote {
  is_genuine?: boolean;
  confidence?: number;
  rationale?: string;
  error?: string;
}

export interface Adjudication {
  votes: Record<string, AdjudicationVote>;
  voters: number;
  genuine_votes: number;
  verdict: string;
  dissent: boolean;
}

export interface Divergence {
  id: string;
  entity_key: string;
  subject: string;
  field: string;
  kind: string;
  severity: Severity;
  confidence: number;
  detail: string;
  adjudication: Adjudication | null;
  values: ClaimValue[];
}

// GET /api/divergences — wrapped: the array lives at .items, not the top level.
export interface DivergencesResponse {
  total: number;
  offset: number;
  limit: number;
  degraded: string | null;
  items: Divergence[];
}

// GET /api/provenance/{claim_id}
export interface Provenance {
  claim_id: string;
  subject: string;
  field: string;
  value: string | null;
  source: string;
  source_url: string | null;
  fetched_at: string;
  observed_at: string | null;
  age_days: number | null;
  sha256: string;
  raw_source_record: Record<string, unknown>;
  verify: string;
}
