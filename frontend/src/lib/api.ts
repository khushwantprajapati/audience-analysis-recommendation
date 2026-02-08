const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getAccounts: () => fetchApi<{ accounts: Account[] }>("/api/accounts"),
  getAccount: (id: string) => fetchApi<Account>(`/api/accounts/${id}`),
  getAudiences: (accountId: string) =>
    fetchApi<Audience[]>(`/api/audiences?account_id=${encodeURIComponent(accountId)}`),
  getAudience: (id: string) => fetchApi<Audience>(`/api/audiences/${id}`),
  getRecommendations: (accountId: string) =>
    fetchApi<Recommendation[]>(`/api/recommendations?account_id=${encodeURIComponent(accountId)}`),
  generateRecommendations: (accountId: string) =>
    fetchApi<{ recommendations: Recommendation[]; count: number }>(
      `/api/recommendations/generate?account_id=${encodeURIComponent(accountId)}`,
      { method: "POST" }
    ),
  syncAccount: (accountId: string) =>
    fetchApi<{ audiences_created: number; audiences_updated: number; snapshots_created: number; errors: string[] }>(
      `/api/ingestion/sync/${accountId}`,
      { method: "POST" }
    ),
  getSettings: () => fetchApi<SettingsResponse>("/api/settings"),
};

export const metaLoginUrl = () => `${API_BASE}/api/auth/meta/login`;

// Types used by api (import from types in components)
export type Account = {
  id: string;
  meta_account_id: string;
  account_name: string | null;
  created_at: string;
  updated_at: string;
};

export type Audience = {
  id: string;
  account_id: string;
  meta_ad_set_id: string;
  name: string;
  audience_type: string;
  lookalike_pct: number | null;
  source_quality: string | null;
  launched_at: string | null;
  current_budget: string | null;
  campaign_id: string | null;
  campaign_name: string | null;
  created_at: string;
  updated_at: string;
};

export type Recommendation = {
  id: string;
  audience_id: string;
  audience_name?: string | null;
  audience_type?: string | null;
  action: string;
  scale_percentage: number | null;
  confidence: string;
  performance_bucket: string;
  trend_state: string;
  composite_score: number | null;
  reasons: string[] | null;
  risks: string[] | null;
  metrics_snapshot: Record<string, unknown> | null;
  generated_at: string;
};

export type SettingsResponse = {
  min_spend: number;
  min_purchases: number;
  min_age_days: number;
  winner_threshold: number;
  loser_threshold: number;
  max_scale_pct: number;
  scale_cooldown_hours: number;
  [key: string]: number;
};
