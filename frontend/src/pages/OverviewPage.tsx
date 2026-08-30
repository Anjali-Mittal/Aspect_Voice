import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { fetchOverview } from "../api/client";
import type { OverviewResponse } from "../api/client";
import { KpiCard } from "../components/KpiCard";
import { EmptyState } from "../components/EmptyState";
import { TrendBadge } from "../components/TrendBadge";

interface Props {
  vehicle: string;
}

export function OverviewPage({ vehicle }: Props) {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!vehicle) return;
    setLoading(true);
    setError(null);
    fetchOverview(vehicle)
      .then(setData)
      .catch(() => setError("Could not load overview data. Is the backend running?"))
      .finally(() => setLoading(false));
  }, [vehicle]);

  if (loading) {
    return <div className="text-sm text-slate-400">Loading…</div>;
  }
  if (error) {
    return <EmptyState message={error} />;
  }
  if (!data) {
    return <EmptyState message="No data yet." />;
  }

  const { kpis, sentiment_trend, top_strengths, top_pain_points, emerging_issues } = data;
  const hasFeedback = kpis.feedback_analyzed > 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Product Overview</h1>
        <p className="mt-1 text-sm text-slate-500">
          How is {data.vehicle} performing according to customer voice?
        </p>
      </div>

      {!hasFeedback ? (
        <EmptyState message="No feedback collected yet for this vehicle. Run the pipeline to get started." />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard label="Feedback Analyzed" value={kpis.feedback_analyzed} />
            <KpiCard
              label="Overall Sentiment"
              value={`${kpis.sentiment_pct.positive}% positive`}
              sublabel={`${kpis.sentiment_pct.negative}% negative · ${kpis.sentiment_pct.neutral}% neutral`}
            />
            <KpiCard label="Negative Feedback" value={`${kpis.sentiment_pct.negative}%`} />
            <KpiCard label="High Priority Issues" value={kpis.high_priority_issues} sublabel={`${kpis.recurring_issues} recurring issues total`} />
          </div>

          <section>
            <h2 className="mb-3 text-sm font-semibold text-slate-700">Sentiment Trend</h2>
            {sentiment_trend.length === 0 ? (
              <EmptyState message="Not enough dated feedback to show a trend yet." />
            ) : (
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={sentiment_trend}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="month" stroke="#94a3b8" fontSize={12} />
                    <YAxis stroke="#94a3b8" fontSize={12} allowDecimals={false} />
                    <Tooltip />
                    <Line type="monotone" dataKey="positive" stroke="#10b981" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="neutral" stroke="#94a3b8" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="negative" stroke="#ef4444" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <section>
              <h2 className="mb-3 text-sm font-semibold text-slate-700">Top Customer Strengths</h2>
              {top_strengths.length === 0 ? (
                <EmptyState message="Not enough positively-discussed features yet." />
              ) : (
                <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
                  {top_strengths.map((s, i) => (
                    <div
                      key={s.feature}
                      className={`flex items-center justify-between px-4 py-3 text-sm ${i > 0 ? "border-t border-slate-100" : ""}`}
                    >
                      <span className="font-medium text-slate-800">{s.feature}</span>
                      <span className="text-slate-500">
                        {s.positive_pct}% positive · {s.mentions} mentions
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section>
              <h2 className="mb-3 text-sm font-semibold text-slate-700">Top Customer Pain Points</h2>
              {top_pain_points.length === 0 ? (
                <EmptyState message="No recurring issues identified yet." />
              ) : (
                <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
                  {top_pain_points.map((p, i) => (
                    <div
                      key={p.id}
                      className={`flex items-center justify-between px-4 py-3 text-sm ${i > 0 ? "border-t border-slate-100" : ""}`}
                    >
                      <div>
                        <div className="font-medium text-slate-800">{p.feature}</div>
                        <div className="text-xs text-slate-500">{p.issue}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <TrendBadge trend={p.trend} />
                        <span className="text-xs text-slate-400">{p.mentions} mentions</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          <section>
            <h2 className="mb-3 text-sm font-semibold text-slate-700">Emerging Issues</h2>
            {emerging_issues.length === 0 ? (
              <EmptyState message="No emerging issues detected — nothing trending upward right now." />
            ) : (
              <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
                {emerging_issues.map((e, i) => (
                  <div
                    key={e.id}
                    className={`flex items-center justify-between px-4 py-3 text-sm ${i > 0 ? "border-t border-slate-100" : ""}`}
                  >
                    <div>
                      <div className="font-medium text-slate-800">{e.feature}</div>
                      <div className="text-xs text-slate-500">{e.issue}</div>
                    </div>
                    <TrendBadge trend={e.trend} />
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
