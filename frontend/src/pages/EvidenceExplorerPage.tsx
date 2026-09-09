import { useEffect, useState } from "react";
import { fetchIssueDetail, fetchEvidence } from "../api/client";
import type { IssueDetail, EvidenceItem } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { TrendBadge } from "../components/TrendBadge";

interface Props {
  issueId: number;
  onClose: () => void;
}

const SENTIMENT_STYLES: Record<string, string> = {
  positive: "text-emerald-700 bg-emerald-50",
  negative: "text-red-700 bg-red-50",
  neutral: "text-slate-600 bg-slate-100",
};

export function EvidenceExplorerPage({ issueId, onClose }: Props) {
  const [detail, setDetail] = useState<IssueDetail | null>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([fetchIssueDetail(issueId), fetchEvidence(issueId)])
      .then(([d, e]) => {
        setDetail(d);
        setEvidence(e);
      })
      .catch(() => setError("Could not load evidence. Is the backend running?"))
      .finally(() => setLoading(false));
  }, [issueId]);

  const maxCount = detail ? Math.max(1, ...detail.monthly_trend.map((m) => m.count)) : 1;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <div
        className="h-full w-full max-w-2xl overflow-y-auto bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
          <span className="text-sm font-semibold uppercase tracking-wide text-slate-500">Evidence Explorer</span>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
            ✕
          </button>
        </div>

        {loading ? (
          <div className="p-6 text-sm text-slate-400">Loading…</div>
        ) : error || !detail ? (
          <div className="p-6">
            <EmptyState message={error ?? "Not found."} />
          </div>
        ) : (
          <div className="space-y-6 p-6">
            {/* Header — feature, priority, trend, confidence */}
            <div>
              <h1 className="text-lg font-semibold text-slate-900">{detail.feature}</h1>
              <p className="mt-1 text-sm text-slate-500">{detail.issue}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-slate-900 px-2.5 py-1 text-xs font-medium text-white">
                  Priority {Math.round(detail.priority_score * 100)}/100
                </span>
                <TrendBadge trend={detail.trend} />
                <span className="rounded-full border border-slate-200 px-2.5 py-1 text-xs text-slate-500">
                  Confidence {Math.round(detail.confidence * 100)}%
                </span>
              </div>
            </div>

            {/* Why was this identified — section 9.1 */}
            <div className="grid grid-cols-3 gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-center text-sm">
              <div>
                <div className="text-lg font-semibold text-slate-900">{detail.mentions}</div>
                <div className="text-xs text-slate-500">relevant mentions</div>
              </div>
              <div>
                <div className="text-lg font-semibold text-slate-900">{detail.source_group_count}</div>
                <div className="text-xs text-slate-500">source groups</div>
              </div>
              <div>
                <div className="text-lg font-semibold text-slate-900 capitalize">{detail.severity_bucket}</div>
                <div className="text-xs text-slate-500">avg severity</div>
              </div>
            </div>

            {/* Monthly trend bars */}
            {detail.monthly_trend.length > 0 && (
              <div>
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Trend</div>
                <div className="flex items-end gap-3">
                  {detail.monthly_trend.map((m) => (
                    <div key={m.month} className="flex flex-col items-center gap-1">
                      <div
                        className="w-8 rounded-t bg-slate-700"
                        style={{ height: `${8 + (m.count / maxCount) * 60}px` }}
                        title={`${m.count} mentions`}
                      />
                      <div className="text-xs text-slate-400">{m.month}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}


            {/* Evidence list — Observed vs AI Interpretation, section 9.2 */}
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Representative Feedback ({evidence.length})
              </div>
              <div className="space-y-3">
                {evidence.map((item, i) => (
                  <div key={i} className="rounded-xl border border-slate-200 p-4">
                    <p className="text-sm text-slate-800">{item.observed.full_text}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                      {item.ai_interpretation.sentiment && (
                        <span
                          className={`rounded px-2 py-0.5 font-medium capitalize ${
                            SENTIMENT_STYLES[item.ai_interpretation.sentiment] ?? SENTIMENT_STYLES.neutral
                          }`}
                        >
                          {item.ai_interpretation.sentiment}
                        </span>
                      )}
                      <span className="text-slate-400">
                        {item.observed.source} · {item.observed.author ?? "Anonymous"}
                        {item.observed.published ? ` · ${item.observed.published.slice(0, 10)}` : ""}
                      </span>
                      {item.observed.url && (
                        <a
                          href={item.observed.url}
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
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
