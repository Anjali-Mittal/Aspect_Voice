import { useEffect, useState } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { fetchAiSummary } from "../api/client";
import type { AiSummaryResponse } from "../api/client";
import { EmptyState } from "./EmptyState";

interface Props {
    vehicleA: string;
    vehicleB: string;
}

const COLORS = ["#7a1e3c", "#c0392b", "#e0562b", "#f0821e", "#f7a600", "#fdc500"];
const HIGHLIGHT_COLOR = "#fdc500";

function VehicleAiBlock({ vehicle, data }: { vehicle: string; data: AiSummaryResponse }) {
    const [selectedIdx, setSelectedIdx] = useState(0);
    const issues = data.issues || [];
    const selected = issues[selectedIdx] ?? issues[0];

    if (data.pie.length === 0) {
        return (
            <div>
                <h3 className="mb-3 text-sm font-semibold text-slate-700">{vehicle}</h3>
                <EmptyState message={data.note || "No issue data yet."} />
            </div>
        );
    }

    const maxMentions = Math.max(...data.pie.map((s) => s.mentions));

    return (
        <div>
            <h3 className="mb-3 text-sm font-semibold text-slate-700">{vehicle}</h3>

            <div className="flex justify-center">
                <ResponsiveContainer width="100%" height={180}>
                    <PieChart>
                        <Pie
                            data={data.pie}
                            dataKey="mentions"
                            nameKey="feature"
                            cx="50%"
                            cy="50%"
                            innerRadius={38}
                            outerRadius={68}
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

            <ul className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1.5">
                {data.pie.map((slice, i) => (
                    <li key={slice.feature} className="flex items-center gap-1.5 text-[12px] text-slate-700">
                        <span
                            className="h-2 w-2 shrink-0 rounded-full"
                            style={{ backgroundColor: slice.mentions === maxMentions ? HIGHLIGHT_COLOR : COLORS[i % COLORS.length] }}
                        />
                        <span>{slice.feature}</span>
                    </li>
                ))}
            </ul>

            {issues.length > 0 && (
                <>
                    {issues.length > 1 && (
                        <div className="mt-4 flex flex-wrap gap-1.5">
                            {issues.map((iss, i) => (
                                <button
                                    key={iss.feature}
                                    onClick={() => setSelectedIdx(i)}
                                    className={`rounded-full px-2 py-0.5 text-[10px] font-medium transition ${i === selectedIdx ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                                        }`}
                                >
                                    {i + 1}. {iss.feature}
                                </button>
                            ))}
                        </div>
                    )}

                    <div className="mt-3 text-xs font-medium uppercase tracking-wide text-slate-500">What the issue is</div>
                    <p className="mt-1 text-sm leading-relaxed text-slate-800">
                        {selected?.narrative || "No narrative available."}
                    </p>

                    {selected && selected.suggestions.length > 0 && (
                        <div className="mt-3">
                            <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">Suggestions</div>
                            <ul className="space-y-2">
                                {selected.suggestions.map((s, i) => (
                                    <li key={i} className="flex items-start gap-2 rounded-lg bg-indigo-50 px-3 py-2 text-base leading-snug text-slate-800">
                                        <span className="mt-0.5 text-indigo-500">•</span>
                                        <span>{s}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

export function CompareAiInsightsPanel({ vehicleA, vehicleB }: Props) {
    const [dataA, setDataA] = useState<AiSummaryResponse | null>(null);
    const [dataB, setDataB] = useState<AiSummaryResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!vehicleA || !vehicleB) return;
        setLoading(true);
        setError(null);
        Promise.all([fetchAiSummary(vehicleA), fetchAiSummary(vehicleB)])
            .then(([a, b]) => {
                setDataA(a);
                setDataB(b);
            })
            .catch(() => setError("Could not load AI insights."))
            .finally(() => setLoading(false));
    }, [vehicleA, vehicleB]);

    if (loading) {
        return (
            <section>
                <h2 className="mb-3 text-sm font-semibold text-slate-700">AI Insights</h2>
                <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-400 shadow-sm">
                    Generating…
                </div>
            </section>
        );
    }
    if (error) return <EmptyState message={error} />;
    if (!dataA || !dataB) return null;

    const topA = dataA.issues?.[0];
    const topB = dataB.issues?.[0];

    return (
        <section>
            <h2 className="mb-3 text-sm font-semibold text-slate-700">AI Insights</h2>
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                {topA && topB && (
                    <p className="mb-5 border-b border-slate-100 pb-4 text-sm text-slate-600">
                        <span className="font-semibold text-slate-800">{vehicleA}</span>'s top issue is{" "}
                        <span className="font-medium">{topA.feature}</span> ({topA.mention_count} mentions), while{" "}
                        <span className="font-semibold text-slate-800">{vehicleB}</span>'s is{" "}
                        <span className="font-medium">{topB.feature}</span> ({topB.mention_count} mentions).
                    </p>
                )}
                <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
                    <VehicleAiBlock vehicle={vehicleA} data={dataA} />
                    <div className="border-t border-slate-100 pt-6 md:border-l md:border-t-0 md:pl-8 md:pt-0">
                        <VehicleAiBlock vehicle={vehicleB} data={dataB} />
                    </div>
                </div>
            </div>
        </section>
    );
}