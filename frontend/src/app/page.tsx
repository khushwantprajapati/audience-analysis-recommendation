"use client";

import { useEffect, useState } from "react";
import { Nav } from "@/components/nav";
import { api, metaLoginUrl, type Account } from "@/lib/api";

export default function Home() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getAccounts()
      .then((r) => setAccounts(r.accounts))
      .catch(() => setAccounts([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <Nav />
      <main className="mx-auto max-w-3xl px-4 py-16">
        <h1 className="mb-2 text-3xl font-bold tracking-tight text-foreground">
          ROAS Audience Recommendation Engine
        </h1>
        <p className="mb-8 text-muted-foreground">
          Connect your Meta Ads account to get ROAS-first recommendations: scale, hold, pause, or retest audiences with clear reasoning and guardrails.
        </p>
        <div className="flex flex-col gap-4">
          <a
            href={metaLoginUrl()}
            className="inline-flex w-fit items-center justify-center rounded-lg bg-primary px-6 py-3 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            Connect Meta Account
          </a>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading accounts…</p>
          ) : accounts.length > 0 ? (
            <div className="rounded-lg border border-border bg-card p-4">
              <p className="mb-2 text-sm font-medium text-foreground">Connected accounts</p>
              <ul className="list-inside list-disc text-sm text-muted-foreground">
                {accounts.map((a) => (
                  <li key={a.id}>
                    {a.account_name || a.meta_account_id}{" "}
                    <a href="/dashboard" className="text-primary hover:underline">
                      Open dashboard
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
}
