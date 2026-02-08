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
