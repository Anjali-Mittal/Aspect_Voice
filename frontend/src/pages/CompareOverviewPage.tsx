import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { fetchOverview } from "../api/client";
import type { OverviewResponse, SentimentTrendPoint } from "../api/client";
import { MethodologyTooltip } from "../components/MethodologyTooltip";
import { EmptyState } from "../components/EmptyState";
import { TrendBadge } from "../components/TrendBadge";
import { MonthReviewsPanel } from "../components/MonthReviewsDrawer";

interface Props {
    vehicleA: string;
    vehicleB: string;
}

const POSITIVE_COLOR = "#10b981"; // matches single-vehicle Sentiment Trend
const NEGATIVE_COLOR = "#ef4444";

interface CompareKpiCardProps {
    label: string;
    vehicleA: string;
    vehicleB: string;
    a: string | number;
    b: string | number;
}

function CompareKpiCard({ label, vehicleA, vehicleB, a, b }: CompareKpiCardProps) {
    return (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
            <div className="mt-2 space-y-1.5">
                <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-xs text-slate-500">{vehicleA}</span>
                    <span className="text-lg font-semibold text-slate-900">{a}</span>
                </div>
                <div className="flex items-baseline justify-between gap-2 border-t border-slate-100 pt-1.5">
                    <span className="truncate text-xs text-slate-500">{vehicleB}</span>
                    <span className="text-lg font-semibold text-slate-900">{b}</span>
                </div>
            </div>
        </div>
    );
}

/** Custom legend — recharts' built-in Legend swatch is always a solid line
 * regardless of strokeDasharray, so it can't actually show which vehicle is
 * solid vs dashed. This draws the real line styles. */
function ChartLegend({ vehicleA, vehicleB }: { vehicleA: string; vehicleB: string }) {
    const LineSample = ({ dashed }: { dashed: boolean }) => (
        <svg width="24" height="10" className="shrink-0">
            <line x1="0" y1="5" x2="24" y2="5" stroke="#64748b" strokeWidth="2" strokeDasharray={dashed ? "5 3" : undefined} />
        </svg>
    );
    return (
        <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs text-slate-600">
            <span className="flex items-center gap-1.5">
                <LineSample dashed={false} /> {vehicleA}
            </span>
            <span className="flex items-center gap-1.5">
                <LineSample dashed={true} /> {vehicleB}
            </span>
            <span className="mx-1 h-3 w-px bg-slate-200" />
            <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: POSITIVE_COLOR }} /> Positive
            </span>
            <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: NEGATIVE_COLOR }} /> Negative
            </span>
        </div>
    );
}

export function CompareOverviewPage({ vehicleA, vehicleB }: Props) {
    const [dataA, setDataA] = useState<OverviewResponse | null>(null);
    const [dataB, setDataB] = useState<OverviewResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
    const [listTab, setListTab] = useState<"strengths" | "pain">("pain");

    useEffect(() => {
        if (!vehicleA || !vehicleB) return;
        setLoading(true);
        setError(null);
        Promise.all([fetchOverview(vehicleA), fetchOverview(vehicleB)])
            .then(([a, b]) => {
                setDataA(a);
                setDataB(b);
            })
            .catch(() => setError("Could not load comparison data. Is the backend running?"))
            .finally(() => setLoading(false));
    }, [vehicleA, vehicleB]);

    if (loading) return <div className="text-sm text-slate-400">Loading…</div>;
    if (error) return <EmptyState message={error} />;
    if (!dataA || !dataB) return <EmptyState message="No data yet." />;

    const hasFeedback = dataA.kpis.feedback_analyzed > 0 || dataB.kpis.feedback_analyzed > 0;

    // merge the two trend series on month so one chart can plot both.
    // Plotted as % of that month's total mentions, not raw counts — a
    // vehicle with far more total reviews would otherwise just draw taller
    // lines regardless of its actual sentiment ratio.
    const monthSet = new Set([...dataA.sentiment_trend.map((p) => p.month), ...dataB.sentiment_trend.map((p) => p.month)]);
    const months = Array.from(monthSet).sort();
    const aByMonth = Object.fromEntries(dataA.sentiment_trend.map((p) => [p.month, p]));
    const bByMonth = Object.fromEntries(dataB.sentiment_trend.map((p) => [p.month, p]));
    const toPct = (point: SentimentTrendPoint | undefined, key: "positive" | "negative") => {
        if (!point) return null;
        const total = point.positive + point.neutral + point.negative;
        return total > 0 ? Math.round((point[key] / total) * 1000) / 10 : null;
    };
    const merged = months.map((month) => ({
        month,
        a_positive: toPct(aByMonth[month], "positive"),
        a_negative: toPct(aByMonth[month], "negative"),
        b_positive: toPct(bByMonth[month], "positive"),
        b_negative: toPct(bByMonth[month], "negative"),
    }));
    const hasTrend = months.length > 0;

    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-xl font-semibold text-slate-900">
                    {vehicleA} <span className="font-normal text-slate-400">vs</span> {vehicleB}
                </h1>
                <p className="mt-1 text-sm text-slate-500">Side-by-side customer voice comparison.</p>
            </div>

            {!hasFeedback ? (
                <EmptyState message="No feedback collected yet for one or both vehicles." />
            ) : (
                <>
                    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                        <CompareKpiCard
                            label="Feedback Analyzed"
                            vehicleA={vehicleA}
                            vehicleB={vehicleB}
                            a={dataA.kpis.feedback_analyzed}
                            b={dataB.kpis.feedback_analyzed}
                        />
                        <CompareKpiCard
                            label="Overall Sentiment"
                            vehicleA={vehicleA}
                            vehicleB={vehicleB}
                            a={`${dataA.kpis.sentiment_pct.positive}% positive`}
                            b={`${dataB.kpis.sentiment_pct.positive}% positive`}
                        />
                        <CompareKpiCard
                            label="Negative Feedback"
                            vehicleA={vehicleA}
                            vehicleB={vehicleB}
                            a={`${dataA.kpis.sentiment_pct.negative}%`}
                            b={`${dataB.kpis.sentiment_pct.negative}%`}
                        />
                        <CompareKpiCard
                            label="High Priority Issues"
                            vehicleA={vehicleA}
                            vehicleB={vehicleB}
                            a={dataA.kpis.high_priority_issues}
                            b={dataB.kpis.high_priority_issues}
                        />
                    </div>

                    <section>
                        <h2 className="mb-3 text-sm font-semibold text-slate-700">Sentiment Trend (% Positive / Negative)</h2>
                        {!hasTrend ? (
                            <EmptyState message="Not enough dated feedback to show a trend yet." />
                        ) : (
                            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                                <ChartLegend vehicleA={vehicleA} vehicleB={vehicleB} />
                                <p className="mb-2 text-xs text-slate-400">Click a point to see that month's reviews.</p>
                                <ResponsiveContainer width="100%" height={280}>
                                    <LineChart
                                        data={merged}
                                        margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                                        onClick={(e) => {
                                            if (e && typeof e.activeLabel === "string") setSelectedMonth(e.activeLabel);
                                        }}
                                        style={{ cursor: "pointer" }}
                                    >
                                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                                        <XAxis dataKey="month" stroke="#94a3b8" fontSize={12} />
                                        <YAxis stroke="#94a3b8" fontSize={12} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                                        <Tooltip formatter={(value: any) => [`${value}%`]} />
                                        <Line type="monotone" dataKey="a_positive" name={`${vehicleA} · Positive`} stroke={POSITIVE_COLOR} strokeWidth={2} dot={false} connectNulls />
                                        <Line type="monotone" dataKey="a_negative" name={`${vehicleA} · Negative`} stroke={NEGATIVE_COLOR} strokeWidth={2} dot={false} connectNulls />
                                        <Line type="monotone" dataKey="b_positive" name={`${vehicleB} · Positive`} stroke={POSITIVE_COLOR} strokeWidth={2} strokeDasharray="5 3" dot={false} connectNulls />
                                        <Line type="monotone" dataKey="b_negative" name={`${vehicleB} · Negative`} stroke={NEGATIVE_COLOR} strokeWidth={2} strokeDasharray="5 3" dot={false} connectNulls />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                        )}
                    </section>

                    <section>
                        <div className="mb-3 flex items-center gap-4">
                            <div className="flex rounded-lg border border-slate-200 bg-white p-1 text-sm font-medium">
                                <button
                                    onClick={() => setListTab("pain")}
                                    className={`rounded-md px-4 py-1.5 ${listTab === "pain" ? "bg-slate-900 text-white" : "text-slate-500"}`}
                                >
                                    Pain Points
                                </button>
                                <button
                                    onClick={() => setListTab("strengths")}
                                    className={`rounded-md px-4 py-1.5 ${listTab === "strengths" ? "bg-slate-900 text-white" : "text-slate-500"}`}
                                >
                                    Strengths
                                </button>
                            </div>
                            <MethodologyTooltip
                                text={
                                    listTab === "pain"
                                        ? "Negative feedback grouped into distinct issues per feature (min. 3 mentions). Ranked by mention volume, average severity, and recency."
                                        : "Per feature, the % of mentions that were positive (features with under 3 total mentions excluded)."
                                }
                            />
                        </div>

                        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                            {[
                                { label: vehicleA, d: dataA },
                                { label: vehicleB, d: dataB },
                            ].map(({ label, d }) => (
                                <div key={label}>
                                    <h3 className="mb-3 text-sm font-semibold text-slate-700">{label}</h3>
                                    {listTab === "pain" ? (
                                        d.top_pain_points.length === 0 ? (
                                            <EmptyState message="No recurring issues identified yet." />
                                        ) : (
                                            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
                                                {d.top_pain_points.map((p, i) => (
                                                    <div key={p.id} className={`flex items-center justify-between px-4 py-3 text-sm ${i > 0 ? "border-t border-slate-100" : ""}`}>
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
                                        )
                                    ) : d.top_strengths.length === 0 ? (
                                        <EmptyState message="Not enough positively-discussed features yet." />
                                    ) : (
                                        <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
                                            {d.top_strengths.map((s, i) => (
                                                <div key={s.feature} className={`flex items-center justify-between px-4 py-3 text-sm ${i > 0 ? "border-t border-slate-100" : ""}`}>
                                                    <span className="font-medium text-slate-800">{s.feature}</span>
                                                    <span className="text-slate-500">
                                                        {s.positive_pct}% positive · {s.mentions} mentions
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </section>
                </>
            )}

            {selectedMonth && (
                <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={() => setSelectedMonth(null)}>
                    <div className="flex h-full w-full max-w-5xl shadow-xl" onClick={(e) => e.stopPropagation()}>
                        <div className="w-1/2 border-r border-slate-200">
                            <MonthReviewsPanel vehicle={vehicleA} month={selectedMonth} onClose={() => setSelectedMonth(null)} />
                        </div>
                        <div className="w-1/2">
                            <MonthReviewsPanel vehicle={vehicleB} month={selectedMonth} onClose={() => setSelectedMonth(null)} />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}