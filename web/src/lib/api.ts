import type { Divergence, DivergencesResponse, Provenance, Summary } from "./types";

export const API_BASE =
  import.meta.env.VITE_API_BASE ?? "https://throughline-api-yo1p.onrender.com";

// Every endpoint here returns JSON that either IS the resource (e.g.
// /api/divergences/{id}) or wraps it in an envelope with pagination /
// degraded-banner metadata alongside it (e.g. /api/divergences → { items }).
// unwrap() only handles the transport concern, non-2xx and non-JSON bodies
// callers reach into `.items` themselves so the envelope fields aren't lost.
async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? body);
    } catch {
      // body wasn't JSON; fall back to statusText
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function getSummary(): Promise<Summary> {
  const res = await fetch(`${API_BASE}/api/summary`);
  return unwrap<Summary>(res);
}

const DIVERGENCES_PAGE_SIZE = 500; // API caps `limit` at 500 (see FastAPI Query le=500)

// The API reports 813 total divergences but rejects limit > 500, so a single
// call truncates the largest group (STALE_RECORD alone is 658). Page through
// offsets until every item is fetched so client-side grouping counts are accurate.
export async function getAllDivergences(): Promise<{ items: Divergence[]; total: number; degraded: string | null }> {
  const first = await fetch(`${API_BASE}/api/divergences?limit=${DIVERGENCES_PAGE_SIZE}&offset=0`);
  const firstPage = await unwrap<DivergencesResponse>(first);

  const items = [...firstPage.items];
  let offset = firstPage.items.length;
  while (offset < firstPage.total) {
    const res = await fetch(`${API_BASE}/api/divergences?limit=${DIVERGENCES_PAGE_SIZE}&offset=${offset}`);
    const page = await unwrap<DivergencesResponse>(res);
    items.push(...page.items);
    if (page.items.length === 0) break; // guard against an off-by-one stalling the loop
    offset += page.items.length;
  }

  return { items, total: firstPage.total, degraded: firstPage.degraded };
}

export async function getDivergence(id: string): Promise<Divergence> {
  const res = await fetch(`${API_BASE}/api/divergences/${encodeURIComponent(id)}`);
  return unwrap<Divergence>(res);
}

export async function getProvenance(claimId: string): Promise<Provenance> {
  const res = await fetch(`${API_BASE}/api/provenance/${encodeURIComponent(claimId)}`);
  return unwrap<Provenance>(res);
}
