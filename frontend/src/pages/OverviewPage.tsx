import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { fetchOverview } from "../api/client";
import type { OverviewResponse } from "../api/client";
import { MethodologyTooltip } from "../components/MethodologyTooltip";
import { KpiCard } from "../components/KpiCard";
import { EmptyState } from "../components/EmptyState";
import { TrendBadge } from "../components/TrendBadge";
import { MonthReviewsDrawer } from "../components/MonthReviewsDrawer";

interface Props {
  vehicle: string;
}

export function OverviewPage({ vehicle }: Props) {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
  const [selectedYear, setSelectedYear] = useState<string>("all");

  useEffect(() => {
    setSelectedYear("all");
  }, [vehicle]);

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

  const { kpis, sentiment_trend, top_strengths, top_pain_points } = data;
  const hasFeedback = kpis.feedback_analyzed > 0;

  const availableYears = Array.from(new Set(sentiment_trend.map((p) => p.month.slice(0, 4)))).sort();
  const displayedTrend = selectedYear === "all"
    ? sentiment_trend
    : sentiment_trend.filter((p) => p.month.startsWith(selectedYear));

  // Recomputed from the same points driving the chart, so these three cards
  // always match what's plotted for the selected year. high_priority_issues
  // stays as the backend's all-time figure — issue clusters are standing
  // groups (their priority_score already factors in recency), not bucketed
  // by month, so there's no per-cluster date to filter by client-side.
  const filteredTotal = displayedTrend.reduce((sum, p) => sum + p.positive + p.neutral + p.negative, 0);
  const filteredPositive = displayedTrend.reduce((sum, p) => sum + p.positive, 0);
  const filteredNegative = displayedTrend.reduce((sum, p) => sum + p.negative, 0);
  const filteredNeutral = displayedTrend.reduce((sum, p) => sum + p.neutral, 0);
  const filteredSentiment = filteredTotal > 0
    ? {
      positive: Math.round((filteredPositive / filteredTotal) * 1000) / 10,
      negative: Math.round((filteredNegative / filteredTotal) * 1000) / 10,
      neutral: Math.round((filteredNeutral / filteredTotal) * 1000) / 10,
    }
    : { positive: 0, negative: 0, neutral: 0 };

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
            <KpiCard label="Feedback Analyzed" value={filteredTotal} />
            <KpiCard
              label="Overall Sentiment"
              value={`${filteredSentiment.positive}% positive`}
              sublabel={`${filteredSentiment.negative}% negative · ${filteredSentiment.neutral}% neutral`}
            />
            <KpiCard label="Negative Feedback" value={`${filteredSentiment.negative}%`} />
            <KpiCard label="High Priority Issues" value={kpis.high_priority_issues} sublabel={`${kpis.recurring_issues} recurring issues total (all-time)`} />
          </div>

          <section>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold text-slate-700">Sentiment Trend</h2>
                <p className="mt-0.5 text-xs text-slate-400">Click a point on the chart to see that month's reviews.</p>
              </div>
              {availableYears.length > 1 && (
                <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-1 text-xs font-medium shadow-xs">
                  <button
                    onClick={() => setSelectedYear("all")}
                    className={`rounded-md px-3 py-1 cursor-pointer transition ${selectedYear === "all"
                      ? "bg-slate-900 text-white shadow-xs"
                      : "text-slate-600 hover:text-slate-900"
                      }`}
                  >
                    All Years
                  </button>
                  {availableYears.map((yr) => (
                    <button
                      key={yr}
                      onClick={() => setSelectedYear(yr)}
                      className={`rounded-md px-3 py-1 cursor-pointer transition ${selectedYear === yr
                        ? "bg-slate-900 text-white shadow-xs"
                        : "text-slate-600 hover:text-slate-900"
                        }`}
                    >
                      {yr}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {displayedTrend.length === 0 ? (
              <EmptyState message="Not enough dated feedback to show a trend for this selection." />
            ) : (
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart
                    data={displayedTrend}
                    margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                    onClick={(e) => {
                      if (e && typeof e.activeLabel === "string") setSelectedMonth(e.activeLabel);
                    }}
                    style={{ cursor: "pointer" }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="month" stroke="#94a3b8" fontSize={12} />
                    <YAxis stroke="#94a3b8" fontSize={12} allowDecimals={false} />
                    <Tooltip />
                    <Legend
                      verticalAlign="top"
                      align="right"
                      iconType="circle"
                      iconSize={8}
                      wrapperStyle={{ paddingBottom: "12px", fontSize: "12px", fontWeight: 500 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="positive"
                      name="Positive"
                      stroke="#10b981"
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 5, style: { cursor: "pointer" } }}
                    />
                    <Line
                      type="monotone"
                      dataKey="neutral"
                      name="Neutral"
                      stroke="#94a3b8"
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 5, style: { cursor: "pointer" } }}
                    />
                    <Line
                      type="monotone"
                      dataKey="negative"
                      name="Negative"
                      stroke="#ef4444"
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 5, style: { cursor: "pointer" } }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <section>
              <h2 className="mb-3 flex items-center text-sm font-semibold text-slate-700">
                Top Customer Strengths
                <MethodologyTooltip text="Per feature, the % of mentions that were positive (features with under 3 total mentions are excluded as too thin to judge)." />
              </h2>
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
              <h2 className="mb-3 flex items-center text-sm font-semibold text-slate-700">
                Top Customer Pain Points
                <MethodologyTooltip text="Negative feedback is grouped into distinct issues per feature (min. 3 mentions). Ranked by a score combining mention volume, average severity, and how recent the mentions are." />
              </h2>
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
        </>
      )}

      {selectedMonth && (
        <MonthReviewsDrawer vehicle={vehicle} month={selectedMonth} onClose={() => setSelectedMonth(null)} />
      )}
    </div>
  );
}