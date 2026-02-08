"use client";

import { useEffect, useState } from "react";
import { Nav } from "@/components/nav";
import { api, type SettingsResponse } from "@/lib/api";

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getSettings()
      .then(setSettings)
      .catch(() => setSettings(null))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <Nav />
      <main className="mx-auto max-w-2xl px-4 py-6">
        <h1 className="mb-6 text-2xl font-bold">Settings</h1>
        {loading ? (
          <p className="text-muted-foreground">Loading…</p>
        ) : settings ? (
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="mb-4 text-sm text-muted-foreground">
              Thresholds and weights are read from the backend config. Persistence can be added later.
            </p>
            <dl className="space-y-3 text-sm">
              <div className="flex justify-between border-b border-border pb-2">
                <dt className="text-muted-foreground">Min spend (INR)</dt>
                <dd className="font-medium">{settings.min_spend}</dd>
              </div>
              <div className="flex justify-between border-b border-border pb-2">
                <dt className="text-muted-foreground">Min purchases</dt>
                <dd className="font-medium">{settings.min_purchases}</dd>
              </div>
              <div className="flex justify-between border-b border-border pb-2">
                <dt className="text-muted-foreground">Min age (days)</dt>
                <dd className="font-medium">{settings.min_age_days}</dd>
              </div>
              <div className="flex justify-between border-b border-border pb-2">
                <dt className="text-muted-foreground">Winner threshold (norm. ROAS)</dt>
                <dd className="font-medium">{settings.winner_threshold}</dd>
              </div>
              <div className="flex justify-between border-b border-border pb-2">
                <dt className="text-muted-foreground">Loser threshold (norm. ROAS)</dt>
                <dd className="font-medium">{settings.loser_threshold}</dd>
              </div>
              <div className="flex justify-between border-b border-border pb-2">
                <dt className="text-muted-foreground">Max scale %</dt>
                <dd className="font-medium">{settings.max_scale_pct}</dd>
              </div>
              <div className="flex justify-between border-b border-border pb-2">
                <dt className="text-muted-foreground">Scale cooldown (hours)</dt>
                <dd className="font-medium">{settings.scale_cooldown_hours}</dd>
              </div>
            </dl>
          </div>
        ) : (
          <p className="text-muted-foreground">Could not load settings. Is the backend running?</p>
        )}
      </main>
    </div>
  );
}
