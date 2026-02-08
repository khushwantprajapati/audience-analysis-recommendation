"use client";

type Action = "SCALE" | "HOLD" | "PAUSE" | "RETEST";

const styles: Record<Action, string> = {
  SCALE: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
  HOLD: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  PAUSE: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  RETEST: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
};

export function RecommendationBadge({ action }: { action: string }) {
  const s = styles[(action as Action) in styles ? (action as Action) : "HOLD"];
  return (
    <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${s}`}>
      {action}
    </span>
  );
}
