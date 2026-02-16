"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Nav } from "@/components/nav";
import { RecommendationBadge } from "@/components/recommendation-badge";
import {
  api,
  type Account,
  type Recommendation,
  type SyncJobStatus,
  type SyncStatus,
} from "@/lib/api";

export default function DashboardPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-background">
          <Nav />
          <main className="mx-auto max-w-6xl px-4 py-6">
            <p className="text-muted-foreground">Loading…</p>
          </main>
        </div>
      }
    >
      <DashboardContent />
    </Suspense>
  );
}

function DashboardContent() {
  const searchParams = useSearchParams();
  const accountFromUrl = searchParams.get("account");

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(accountFromUrl);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<SyncJobStatus["summary"]>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [datePreset, setDatePreset] = useState("last_7d");
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [syncJob, setSyncJob] = useState<SyncJobStatus | null>(null);

  const loadAccounts = useCallback(() => {
    api
      .getAccounts()
      .then((r) => {
        setAccounts(r.accounts);
        setSelectedAccountId((prev) => {
          if (prev) return prev;
          const urlMatch = accountFromUrl ? r.accounts.find((a) => a.id === accountFromUrl) : null;
          return urlMatch ? urlMatch.id : r.accounts[0]?.id ?? null;
        });
      })
      .catch(() => setAccounts([]))
      .finally(() => setLoading(false));
  }, [accountFromUrl]);

  const loadSyncStatus = useCallback(() => {
    if (!selectedAccountId) {
      setSyncStatus(null);
      return;
    }
    api.getSyncStatus(selectedAccountId).then(setSyncStatus).catch(() => setSyncStatus(null));
  }, [selectedAccountId]);

  const loadSyncJob = useCallback(() => {
    if (!selectedAccountId) {
      setSyncJob(null);
      return;
    }
    api.getSyncJobStatus(selectedAccountId).then((job) => {
      setSyncJob(job);
      if (job.summary) {
        setSyncResult(job.summary);
      }
      if (job.status === "completed" || job.status === "failed" || job.status === "cancelled") {
        setSyncing(false);
        loadSyncStatus();
      }
    }).catch(() => setSyncJob(null));
  }, [selectedAccountId, loadSyncStatus]);

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
    if (selectedAccountId) {
      loadRecommendations();
      loadSyncStatus();
      loadSyncJob();
    } else {
      setRecommendations([]);
      setSyncStatus(null);
      setSyncJob(null);
    }
  }, [selectedAccountId, loadRecommendations, loadSyncStatus, loadSyncJob]);

  useEffect(() => {
    if (!selectedAccountId || !syncing) return;
    const timer = window.setInterval(() => {
      loadSyncJob();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [selectedAccountId, syncing, loadSyncJob]);

  const handleSync = () => {
    if (!selectedAccountId) return;
    setSyncing(true);
    setSyncResult(null);
    setErrorMsg(null);
    api
      .syncAccount(selectedAccountId, datePreset)
      .then((result) => {
        if (result.status === "in_progress") {
          loadSyncJob();
        }
      })
      .catch((e) => {
        setErrorMsg(`Sync failed: ${e.message}`);
        setSyncing(false);
      });
  };

  const handleCancelSync = () => {
    if (!selectedAccountId) return;
    api
      .cancelSync(selectedAccountId)
      .then((result) => {
        setErrorMsg(result.message);
        loadSyncJob();
      })
      .catch((e) => setErrorMsg(`Cancel failed: ${e.message}`));
  };

  const handleGenerate = () => {
    if (!selectedAccountId) return;
    setGenerating(true);
    setErrorMsg(null);
    api
      .generateRecommendations(selectedAccountId)
      .then((r) => {
        setRecommendations(r.recommendations);
        loadSyncStatus();
      })
      .catch((e) => setErrorMsg(`Generate failed: ${e.message}`))
      .finally(() => setGenerating(false));
  };

  const winners = recommendations.filter((r) => r.performance_bucket === "WINNER").length;
  const average = recommendations.filter((r) => r.performance_bucket === "AVERAGE").length;
  const losers = recommendations.filter((r) => r.performance_bucket === "LOSER").length;
  const canGenerate = syncStatus?.can_generate ?? false;
  const syncInProgress = syncing || syncJob?.status === "in_progress";

  const syncHint = useMemo(() => {
    if (syncInProgress) return "Sync in progress…";
    if (syncJob?.status === "failed") return syncJob.message ?? "Sync failed";
    if (syncJob?.status === "cancelled") return "Sync cancelled";
    if (syncJob?.status === "completed") return "Sync completed";
    return null;
  }, [syncJob, syncInProgress]);

  const formatTimeAgo = (iso: string) => {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ${mins % 60}m ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ${hrs % 24}h ago`;
  };

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
          <select
            value={datePreset}
            onChange={(e) => setDatePreset(e.target.value)}
            className="rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            <option value="yesterday">Yesterday</option>
            <option value="last_3d">Last 3 days</option>
            <option value="last_7d">Last 7 days</option>
            <option value="last_14d">Last 14 days</option>
            <option value="last_28d">Last 28 days</option>
            <option value="last_30d">Last 30 days</option>
            <option value="last_90d">Last 90 days</option>
          </select>
          <button
            onClick={handleSync}
            disabled={!selectedAccountId || syncInProgress}
            className="rounded-lg bg-secondary px-4 py-2 text-sm font-medium text-secondary-foreground hover:bg-secondary/80 disabled:opacity-50"
          >
            {syncInProgress ? "Syncing…" : "Sync now"}
          </button>
          <button
            onClick={handleCancelSync}
            disabled={!selectedAccountId || !syncInProgress}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50"
          >
            Cancel sync
          </button>
          <button
            onClick={handleGenerate}
            disabled={!selectedAccountId || generating || !canGenerate}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            title={!canGenerate ? "Sync data first before generating recommendations" : ""}
          >
            {generating ? "Generating…" : "Generate recommendations"}
          </button>
        </div>

        {syncHint && (
          <div className="mb-3 rounded-lg border border-border bg-muted/30 p-2 text-sm text-muted-foreground">{syncHint}</div>
        )}

        {selectedAccountId && syncStatus && (
          <div className="mb-4 flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
            <span>
              Last sync:{" "}
              {syncStatus.last_synced_at ? (
                <span className="font-medium text-foreground" title={new Date(syncStatus.last_synced_at).toLocaleString()}>
                  {formatTimeAgo(syncStatus.last_synced_at)}
                </span>
              ) : (
                <span className="font-medium text-amber-600">Never</span>
              )}
            </span>
            <span className="text-border">|</span>
            <span>
              Audiences: <span className="font-medium text-foreground">{syncStatus.audience_count}</span>
            </span>
            <span className="text-border">|</span>
            <span>
              With data: <span className="font-medium text-foreground">{syncStatus.audiences_with_data}</span>
            </span>
          </div>
        )}

        {syncResult && (
          <div className={`mb-4 rounded-lg border p-3 text-sm ${syncResult.errors?.length ? "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950" : "border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950"}`}>
            <p className="font-medium">
              Sync result: {syncResult.audiences_created} audiences created, {syncResult.audiences_updated} updated, {syncResult.snapshots_created} snapshots
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
        ) : recommendations.length === 0 ? (
          <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
            No recommendations yet. If sync fetched data, click <span className="font-medium text-foreground">Generate recommendations</span> to display it.
          </div>
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
          </div>
        )}
      </main>
    </div>
  );
}
