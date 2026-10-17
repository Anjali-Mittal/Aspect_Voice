import { useEffect, useState } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { fetchAiSummary, reloadAiSummary } from "../api/client";
import type { AiSummaryResponse } from "../api/client";
import { EmptyState } from "./EmptyState";

interface Props {
    vehicle: string;
}

// Muted palette for all slices except the largest, which gets a bright
// highlight color so the biggest issue reads instantly on the chart.
const COLORS = ["#7a1e3c", "#c0392b", "#e0562b", "#f0821e", "#f7a600", "#fdc500"];
const HIGHLIGHT_COLOR = "#fdc500";

export function AiInsightsPanel({ vehicle }: Props) {
    const [data, setData] = useState<AiSummaryResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [reloading, setReloading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedIdx, setSelectedIdx] = useState(0);

    const loadData = (force = false) => {
        if (!vehicle) return;
        if (force) {
            setReloading(true);
            reloadAiSummary(vehicle)
                .then((res) => {
                    setData(res);
                    setError(null);
                })
                .catch(() => setError("Could not reload AI insights."))
                .finally(() => setReloading(false));
        } else {
            setLoading(true);
            setError(null);
            setSelectedIdx(0);
            fetchAiSummary(vehicle)
                .then(setData)
                .catch(() => setError("Could not load AI insights."))
                .finally(() => setLoading(false));
        }
    };

    useEffect(() => {
        loadData(false);
    }, [vehicle]);

    if (loading) {
        return (
            <section>
                <div className="mb-3 flex items-center justify-between">
                    <h2 className="text-sm font-semibold text-slate-700">AI Insights</h2>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-400 shadow-sm">
                    Generating…
                </div>
            </section>
        );
    }
    if (error) {
        return (
            <section>
                <div className="mb-3 flex items-center justify-between">
                    <h2 className="text-sm font-semibold text-slate-700">AI Insights</h2>
                    <button
                        onClick={() => loadData(true)}
                        disabled={loading || reloading}
                        className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 shadow-xs transition hover:bg-slate-50 hover:text-slate-900 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
                        title="Retry loading AI insights"
                    >
                        <span>Retry</span>
                    </button>
                </div>
                <EmptyState message={error} />
            </section>
        );
    }
    if (!data || data.pie.length === 0) {
        return (
            <section>
                <div className="mb-3 flex items-center justify-between">
                    <h2 className="text-sm font-semibold text-slate-700">AI Insights</h2>
                    <button
                        onClick={() => loadData(true)}
                        disabled={loading || reloading}
                        className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 shadow-xs transition hover:bg-slate-50 hover:text-slate-900 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
                        title="Regenerate AI insights"
                    >
                        <span>Reload</span>
                    </button>
                </div>
                <EmptyState message={data?.note || "No issue data yet."} />
            </section>
        );
    }

    const maxMentions = Math.max(...data.pie.map((s) => s.mentions));
    const issues = data.issues || [];
    const selected = issues[selectedIdx] ?? issues[0];

    return (
        <section>
            <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-700">AI Insights</h2>
                <button
                    onClick={() => loadData(true)}
                    disabled={loading || reloading}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 shadow-xs transition hover:bg-slate-50 hover:text-slate-900 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
                    title="Regenerate AI insights with the latest data"
                >
                    <svg
                        className={`h-3.5 w-3.5 text-slate-500 ${reloading ? "animate-spin" : ""}`}
                        xmlns="http://www.w3.org/2000/svg"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2}
                    >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    <span>{reloading ? "Reloading…" : "Reload"}</span>
                </button>
            </div>
            <div className="grid grid-cols-1 gap-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm md:grid-cols-2">
                <div className="flex flex-col justify-center">
                    <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
                        Issue Mentions by Feature
                    </div>
                    <div className="flex justify-center">
                        <ResponsiveContainer width="100%" height={220}>
                            <PieChart>
                                <Pie
                                    data={data.pie}
                                    dataKey="mentions"
                                    nameKey="feature"
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={45}
                                    outerRadius={80}
                                    paddingAngle={2}
                                >
                                    {data.pie.map((slice, i) => (
                                        <Cell
                                            key={i}
                                            fill={slice.mentions === maxMentions ? HIGHLIGHT_COLOR : COLORS[i % COLORS.length]}
                                        />
                                    ))}
                                </Pie>
                                <Tooltip formatter={(value) => [`${value} mentions`, ""]} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>

                    <ul className="mt-8 grid grid-cols-2 gap-x-6 gap-y-2">
                        {data.pie.map((slice, i) => (
                            <li key={slice.feature} className="flex items-center gap-2 text-[13px] text-slate-700">
                                <span
                                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                                    style={{
                                        backgroundColor: slice.mentions === maxMentions ? HIGHLIGHT_COLOR : COLORS[i % COLORS.length],
                                    }}
                                />
                                <span>{slice.feature}</span>
                            </li>
                        ))}
                    </ul>
                </div>

                <div className="flex h-full flex-col">
                    {issues.length > 1 && (
                        <div className="mb-3 flex flex-wrap gap-1.5">
                            {issues.map((iss, i) => (
                                <button
                                    key={iss.feature}
                                    onClick={() => setSelectedIdx(i)}
                                    className={`rounded-full px-2.5 py-1 text-[11px] font-medium transition ${i === selectedIdx
                                            ? "bg-slate-900 text-white"
                                            : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                                        }`}
                                >
                                    {i + 1}. {iss.feature}
                                </button>
                            ))}
                        </div>
                    )}

                    <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
                        What the issue is
                    </div>
                    {selected?.narrative ? (
                        <p className="text-sm leading-relaxed text-slate-700">{selected.narrative}</p>
                    ) : (
                        <p className="text-sm text-slate-400">No narrative available.</p>
                    )}

                    {selected && selected.suggestions.length > 0 && (
                        <div className="mt-4 flex flex-1 flex-col">
                            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
                                Suggestions
                            </div>
                            <ul className="flex flex-1 flex-col justify-between gap-2">
                                {selected.suggestions.map((s, i) => (
                                    <li
                                        key={i}
                                        className="flex items-start gap-2 rounded-lg bg-indigo-50/60 px-3 py-2 text-sm text-slate-700"
                                    >
                                        <span className="mt-0.5 text-indigo-500">•</span>
                                        <span>{s}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            </div>
        </section>
    );
}