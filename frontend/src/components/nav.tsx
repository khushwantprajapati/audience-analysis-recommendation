"use client";

import Link from "next/link";

export function Nav() {
  return (
    <nav className="border-b border-border bg-card px-4 py-3">
      <div className="mx-auto flex max-w-6xl items-center gap-6">
        <Link href="/" className="font-semibold text-foreground">
          ROAS Engine
        </Link>
        <Link href="/dashboard" className="text-muted-foreground hover:text-foreground">
          Dashboard
        </Link>
        <Link href="/settings" className="text-muted-foreground hover:text-foreground">
          Settings
        </Link>
        <Link href="/history" className="text-muted-foreground hover:text-foreground">
          History
        </Link>
      </div>
    </nav>
  );
}
