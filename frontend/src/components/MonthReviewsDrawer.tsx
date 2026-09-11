import { useEffect, useState } from "react";
import { fetchFeedbackByMonth } from "../api/client";
import type { MonthFeedbackItem } from "../api/client";
import { EmptyState } from "./EmptyState";

interface Props {
    vehicle: string;
    month: string;
    onClose: () => void;
}

const SENTIMENT_STYLES: Record<string, string> = {
    positive: "text-emerald-700 bg-emerald-50",
    negative: "text-red-700 bg-red-50",
    neutral: "text-slate-600 bg-slate-100",
};

export function MonthReviewsDrawer({ vehicle, month, onClose }: Props) {
    const [items, setItems] = useState<MonthFeedbackItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        setLoading(true);
        setError(null);
        fetchFeedbackByMonth(vehicle, month)
            .then(setItems)
            .catch(() => setError("Could not load reviews. Is the backend running?"))
            .finally(() => setLoading(false));
    }, [vehicle, month]);

    return (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
            <div
                className="h-full w-full max-w-2xl overflow-y-auto bg-white shadow-xl"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="sticky top-0 flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
                    <div>
                        <span className="text-sm font-semibold uppercase tracking-wide text-slate-500">Reviews</span>
                        <div className="text-lg font-semibold text-slate-900">{month}</div>
                    </div>
                    <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
                        ✕
                    </button>
                </div>

                <div className="p-6">
                    {loading ? (
                        <div className="text-sm text-slate-400">Loading…</div>
                    ) : error ? (
                        <EmptyState message={error} />
                    ) : items.length === 0 ? (
                        <EmptyState message="No reviews found for this month." />
                    ) : (
                        <div className="space-y-3">
                            {items.map((item, i) => (
                                <div key={i} className="rounded-xl border border-slate-200 p-4">
                                    <p className="text-sm text-slate-800">{item.full_text}</p>
                                    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                                        {item.tags.map((tag, j) => (
                                            <span key={j} className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5">
                                                {tag.sentiment && (
                                                    <span
                                                        className={`rounded px-1.5 py-0.5 font-medium capitalize ${SENTIMENT_STYLES[tag.sentiment] ?? SENTIMENT_STYLES.neutral
                                                            }`}
                                                    >
                                                        {tag.sentiment}
                                                    </span>
                                                )}
                                                <span className="text-slate-600">{tag.feature}</span>
                                            </span>
                                        ))}
                                        <span className="text-slate-400">
                                            {item.source} · {item.author ?? "Anonymous"}
                                            {item.published ? ` · ${item.published.slice(0, 10)}` : ""}
                                        </span>
                                        {item.url && (
                                            <a
                                                href={item.url}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="ml-auto text-slate-500 underline hover:text-slate-800"
                                            >
                                                Open Source
                                            </a>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );

}
