const STYLES: Record<string, string> = {
  increasing: "bg-red-50 text-red-700 border-red-200",
  decreasing: "bg-emerald-50 text-emerald-700 border-emerald-200",
  stable: "bg-slate-100 text-slate-600 border-slate-200",
  insufficient_data: "bg-slate-50 text-slate-400 border-slate-200",
};

const LABELS: Record<string, string> = {
  increasing: "Increasing",
  decreasing: "Decreasing",
  stable: "Stable",
};

export function TrendBadge({ trend }: { trend: string }) {
  if (trend === "insufficient_data") return null;
  const style = STYLES[trend] ?? STYLES.stable;
  const label = LABELS[trend] ?? trend;
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${style}`}>
      {label}
    </span>
  );
}