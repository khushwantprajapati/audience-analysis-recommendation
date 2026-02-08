"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Nav } from "@/components/nav";
import { RecommendationBadge } from "@/components/recommendation-badge";
import { api, type Audience, type Recommendation } from "@/lib/api";

export default function AudienceDetailPage() {
  const params = useParams();
  const id = params?.id as string;
  const [audience, setAudience] = useState<Audience | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    api
      .getAudience(id)
      .then(setAudience)
      .catch(() => setAudience(null))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (!audience?.account_id || !id) return;
    api
      .getRecommendations(audience.account_id)
      .then((recs) => setRecommendations(recs.filter((r) => r.audience_id === id)))
      .catch(() => setRecommendations([]));
  }, [audience?.account_id, id]);

  const latest = recommendations[0];

  if (loading && !audience) return <div className="min-h-screen bg-background"><Nav /><main className="p-4">Loading…</main></div>;
  if (!audience) return <div className="min-h-screen bg-background"><Nav /><main className="p-4">Audience not found.</main></div>;

  return (
    <div className="min-h-screen bg-background">
      <Nav />
      <main className="mx-auto max-w-4xl px-4 py-6">
        <Link href="/dashboard" className="mb-4 inline-block text-sm text-primary hover:underline">← Dashboard</Link>
        <h1 className="mb-2 text-2xl font-bold text-foreground">{audience.name}</h1>
        <p className="mb-6 text-muted-foreground">
          Type: {audience.audience_type} · Campaign: {audience.campaign_name ?? "—"}
        </p>

        {latest && (
          <div className="mb-8 rounded-lg border border-border bg-card p-6">
            <h2 className="mb-4 text-lg font-semibold">Current recommendation</h2>
            <div className="mb-4 flex items-center gap-4">
              <RecommendationBadge action={latest.action} />
              <span className="text-muted-foreground">Confidence: {latest.confidence}</span>
              {latest.scale_percentage != null && <span>Scale: +{latest.scale_percentage}%</span>}
            </div>
            <p className="mb-2 text-sm font-medium text-foreground">Reasons</p>
            <ul className="list-inside list-disc text-sm text-muted-foreground">
              {(latest.reasons || []).map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
            {latest.risks && latest.risks.length > 0 && (
              <>
                <p className="mt-3 text-sm font-medium text-foreground">Risks</p>
                <ul className="list-inside list-disc text-sm text-muted-foreground">
                  {latest.risks.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </>
            )}
            <p className="mt-3 text-xs text-muted-foreground">
              Generated: {latest.generated_at ? new Date(latest.generated_at).toLocaleString() : "—"}
            </p>
          </div>
        )}

        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="mb-4 text-lg font-semibold">Metrics snapshot</h2>
          {latest?.metrics_snapshot && typeof latest.metrics_snapshot === "object" ? (
            <dl className="grid gap-2 sm:grid-cols-2">
              {Object.entries(latest.metrics_snapshot).map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-border pb-1">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="font-medium">{v != null ? String(v) : "—"}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-muted-foreground">No metrics yet. Sync and generate recommendations from the dashboard.</p>
          )}
        </div>

        {recommendations.length > 1 && (
          <div className="mt-8 rounded-lg border border-border bg-card p-6">
            <h2 className="mb-4 text-lg font-semibold">Recommendation history</h2>
            <ul className="space-y-2">
              {recommendations.slice(1, 6).map((r) => (
                <li key={r.id} className="flex items-center gap-4 text-sm">
                  <RecommendationBadge action={r.action} />
                  <span className="text-muted-foreground">{r.generated_at ? new Date(r.generated_at).toLocaleString() : ""}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>
    </div>
  );
}
