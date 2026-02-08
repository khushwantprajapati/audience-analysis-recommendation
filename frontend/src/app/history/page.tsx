"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Nav } from "@/components/nav";
import { RecommendationBadge } from "@/components/recommendation-badge";
import { api, type Account, type Recommendation } from "@/lib/api";

export default function HistoryPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getAccounts().then((r) => {
      setAccounts(r.accounts);
      if (r.accounts.length && !selectedAccountId) setSelectedAccountId(r.accounts[0].id);
    }).catch(() => setAccounts([])).finally(() => setLoading(false));
  }, [selectedAccountId]);

  useEffect(() => {
    if (!selectedAccountId) return;
    api.getRecommendations(selectedAccountId).then(setRecommendations).catch(() => setRecommendations([]));
  }, [selectedAccountId]);

  const byDate = recommendations.reduce<Record<string, Recommendation[]>>((acc, r) => {
    const d = r.generated_at ? new Date(r.generated_at).toISOString().slice(0, 10) : "";
    if (!acc[d]) acc[d] = [];
    acc[d].push(r);
    return acc;
  }, {});
  const dates = Object.keys(byDate).sort().reverse();

  return (
    <div className="min-h-screen bg-background">
      <Nav />
      <main className="mx-auto max-w-4xl px-4 py-6">
        <h1 className="mb-6 text-2xl font-bold">Recommendation history</h1>
        <div className="mb-6">
          <select
            value={selectedAccountId ?? ""}
            onChange={(e) => setSelectedAccountId(e.target.value || null)}
            className="rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            <option value="">Select account</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>{a.account_name || a.meta_account_id}</option>
            ))}
          </select>
        </div>
        {loading ? (
          <p className="text-muted-foreground">Loading…</p>
        ) : !selectedAccountId ? (
          <p className="text-muted-foreground">Select an account.</p>
        ) : (
          <div className="space-y-6">
            {dates.map((d) => (
              <div key={d} className="rounded-lg border border-border bg-card p-4">
                <h2 className="mb-3 font-medium text-foreground">{d}</h2>
                <ul className="space-y-2">
                  {(byDate[d] || []).map((r) => (
                    <li key={r.id} className="flex items-center gap-4 text-sm">
                      <RecommendationBadge action={r.action} />
                      <Link href={`/audience/${r.audience_id}`} className="text-primary hover:underline">
                        {r.audience_name || r.audience_id}
                      </Link>
                      <span className="text-muted-foreground">
                        {r.generated_at ? new Date(r.generated_at).toLocaleTimeString() : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            {dates.length === 0 && <p className="text-muted-foreground">No recommendations yet. Generate from the dashboard.</p>}
          </div>
        )}
      </main>
    </div>
  );
}
