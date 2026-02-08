"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Nav } from "@/components/nav";
import { RecommendationBadge } from "@/components/recommendation-badge";
import { api, type Account, type Recommendation } from "@/lib/api";

export default function DashboardPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<{ audiences_created: number; audiences_updated: number; snapshots_created: number; errors: string[] } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadAccounts = useCallback(() => {
    api
      .getAccounts()
      .then((r) => {
        setAccounts(r.accounts);
        if (r.accounts.length && !selectedAccountId) setSelectedAccountId(r.accounts[0].id);
      })
      .catch(() => setAccounts([]))
      .finally(() => setLoading(false));
  }, [selectedAccountId]);

  const loadRecommendations = useCallback(() => {
    if (!selectedAccountId) return;
    setLoading(true);
    api
      .getRecommendations(selectedAccountId)
      .then(setRecommendations)
      .catch(() => setRecommendations([]))
      .finally(() => setLoading(false));
  }, [selectedAccountId]);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  useEffect(() => {
    if (selectedAccountId) loadRecommendations();
    else setRecommendations([]);
  }, [selectedAccountId, loadRecommendations]);

  const handleSync = () => {
    if (!selectedAccountId) return;
    setSyncing(true);
    setSyncResult(null);
    setErrorMsg(null);
    api
      .syncAccount(selectedAccountId)
      .then((result) => {
        setSyncResult(result);
        if (result.errors?.length) {
          setErrorMsg(`Sync finished with ${result.errors.length} error(s)`);
        }
        loadRecommendations();
      })
      .catch((e) => setErrorMsg(`Sync failed: ${e.message}`))
      .finally(() => setSyncing(false));
  };

  const handleGenerate = () => {
    if (!selectedAccountId) return;
    setGenerating(true);
    setErrorMsg(null);
    api
      .generateRecommendations(selectedAccountId)
      .then((r) => setRecommendations(r.recommendations))
      .catch((e) => setErrorMsg(`Generate failed: ${e.message}`))
      .finally(() => setGenerating(false));
  };

  const winners = recommendations.filter((r) => r.performance_bucket === "WINNER").length;
  const average = recommendations.filter((r) => r.performance_bucket === "AVERAGE").length;
  const losers = recommendations.filter((r) => r.performance_bucket === "LOSER").length;

  return (
    <div className="min-h-screen bg-background">
      <Nav />
      <main className="mx-auto max-w-6xl px-4 py-6">
        <div className="mb-6 flex flex-wrap items-center gap-4">
          <select
            value={selectedAccountId ?? ""}
            onChange={(e) => setSelectedAccountId(e.target.value || null)}
            className="rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            <option value="">Select account</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.account_name || a.meta_account_id}
              </option>
            ))}
          </select>
          <button
            onClick={handleSync}
            disabled={!selectedAccountId || syncing}
            className="rounded-lg bg-secondary px-4 py-2 text-sm font-medium text-secondary-foreground hover:bg-secondary/80 disabled:opacity-50"
          >
            {syncing ? "Syncing…" : "Sync now"}
          </button>
          <button
            onClick={handleGenerate}
            disabled={!selectedAccountId || generating}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {generating ? "Generating…" : "Generate recommendations"}
          </button>
        </div>

        {syncResult && (
          <div className={`mb-4 rounded-lg border p-3 text-sm ${syncResult.errors?.length ? "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950" : "border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950"}`}>
            <p className="font-medium">
              Sync complete: {syncResult.audiences_created} audiences created, {syncResult.audiences_updated} updated, {syncResult.snapshots_created} snapshots
            </p>
            {syncResult.errors?.length > 0 && (
              <details className="mt-1">
                <summary className="cursor-pointer text-amber-700 dark:text-amber-400">
                  {syncResult.errors.length} error(s) — click to expand
                </summary>
                <ul className="mt-1 list-inside list-disc text-xs text-muted-foreground">
                  {syncResult.errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
        {errorMsg && (
          <div className="mb-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
            {errorMsg}
          </div>
        )}

        <div className="mb-6 grid gap-4 sm:grid-cols-4">
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">Audiences analyzed</p>
            <p className="text-2xl font-semibold">{recommendations.length}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">Winners</p>
            <p className="text-2xl font-semibold text-emerald-600">{winners}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">Average</p>
            <p className="text-2xl font-semibold text-amber-600">{average}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">Losers</p>
            <p className="text-2xl font-semibold text-red-600">{losers}</p>
          </div>
        </div>

        {loading && !recommendations.length ? (
          <p className="text-muted-foreground">Loading…</p>
        ) : !selectedAccountId ? (
          <p className="text-muted-foreground">Select an account or connect one from the home page.</p>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border bg-card">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="px-4 py-3 text-left font-medium">Audience</th>
                    <th className="px-4 py-3 text-left font-medium">Type</th>
                    <th className="px-4 py-3 text-right font-medium">ROAS</th>
                    <th className="px-4 py-3 text-right font-medium">CPA</th>
                    <th className="px-4 py-3 text-center font-medium">Action</th>
                    <th className="px-4 py-3 text-center font-medium">Confidence</th>
                    <th className="px-4 py-3 text-right font-medium">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {recommendations.map((r) => {
                    const snap = r.metrics_snapshot as { roas?: number; cpa?: number } | null;
                    const isExpanded = expandedId === r.id;
                    return (
                      <tr
                        key={r.id}
                        className="border-b border-border hover:bg-muted/30"
                        onClick={() => setExpandedId(isExpanded ? null : r.id)}
                      >
                        <td className="px-4 py-3">
                          <Link href={`/audience/${r.audience_id}`} className="font-medium text-primary hover:underline" onClick={(e) => e.stopPropagation()}>
                            {r.audience_name || r.audience_id}
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{r.audience_type ?? "—"}</td>
                        <td className="px-4 py-3 text-right">{snap?.roas != null ? Number(snap.roas).toFixed(2) : "—"}</td>
                        <td className="px-4 py-3 text-right">{snap?.cpa != null ? Number(snap.cpa).toFixed(0) : "—"}</td>
                        <td className="px-4 py-3 text-center">
                          <RecommendationBadge action={r.action} />
                        </td>
                        <td className="px-4 py-3 text-center text-muted-foreground">{r.confidence}</td>
                        <td className="px-4 py-3 text-right">{r.composite_score != null ? r.composite_score.toFixed(2) : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {recommendations.map((r) => {
              if (expandedId !== r.id) return null;
              return (
                <div key={r.id} className="border-t border-border bg-muted/20 px-4 py-3 text-sm">
                  <p className="font-medium text-foreground">Reasons</p>
                  <ul className="list-inside list-disc text-muted-foreground">
                    {(r.reasons || []).map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                  {r.risks && r.risks.length > 0 && (
                    <>
                      <p className="mt-2 font-medium text-foreground">Risks</p>
                      <ul className="list-inside list-disc text-muted-foreground">
                        {r.risks.map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
