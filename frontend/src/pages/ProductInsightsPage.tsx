import { useEffect, useState } from "react";
import { fetchFeatures, fetchFeatureSummary, fetchIssues } from "../api/client";
import type { FeatureSummary, IssueSummary } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { TrendBadge } from "../components/TrendBadge";

interface Props {
  vehicle: string;
  onOpenEvidence: (issueId: number) => void;
}

type PriorityFilter = "all" | "high" | "emerging";

const SEVERITY_STYLES: Record<string, string> = {
  high: "text-red-700 bg-red-50",
  medium: "text-amber-700 bg-amber-50",
  low: "text-slate-600 bg-slate-100",
};

export function ProductInsightsPage({ vehicle, onOpenEvidence }: Props) {
  const [features, setFeatures] = useState<{ feature: string; description: string }[]>([]);
  const [selectedFeature, setSelectedFeature] = useState<string | null>(null);
  const [featureSummary, setFeatureSummary] = useState<FeatureSummary | null>(null);
  const [issues, setIssues] = useState<IssueSummary[]>([]);
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // load features once per vehicle
  useEffect(() => {
    if (!vehicle) return;
    fetchFeatures(vehicle).then(setFeatures).catch(() => setFeatures([]));
    setSelectedFeature(null);
    setFeatureSummary(null);
  }, [vehicle]);

  // load issues whenever vehicle, selected feature, or priority filter changes
  useEffect(() => {
    if (!vehicle) return;
    setLoading(true);
    setError(null);
    const filters: { feature?: string; trend?: string; min_priority?: number } = {};
    if (selectedFeature) filters.feature = selectedFeature;
    if (priorityFilter === "emerging") filters.trend = "increasing";
    if (priorityFilter === "high") filters.min_priority = 0.6;

    fetchIssues(vehicle, filters)
      .then(setIssues)
      .catch(() => setError("Could not load issues. Is the backend running?"))
      .finally(() => setLoading(false));
  }, [vehicle, selectedFeature, priorityFilter]);

  function handleSelectFeature(feature: string) {
    const next = selectedFeature === feature ? null : feature;
    setSelectedFeature(next);
    if (next) {
      fetchFeatureSummary(next, vehicle).then(setFeatureSummary).catch(() => setFeatureSummary(null));
    } else {
      setFeatureSummary(null);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Product Insights</h1>
        <p className="mt-1 text-sm text-slate-500">
          What are customers talking about, and what should the product team investigate?
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-[240px_1fr]">
        {/* Feature sidebar — DASHBOARD.md section 5.1 */}
        <aside className="space-y-1">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Discovered Features
          </div>
          {features.length === 0 ? (
            <EmptyState message="No feature ontology discovered yet." />
          ) : (
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
              {features.map((f, i) => (
                <button
                  key={f.feature}
                  onClick={() => handleSelectFeature(f.feature)}
                  className={`block w-full px-3 py-2 text-left text-sm ${i > 0 ? "border-t border-slate-100" : ""} ${
                    selectedFeature === f.feature
                      ? "bg-slate-900 text-white"
                      : "text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  {f.feature}
                </button>
              ))}
            </div>
          )}
        </aside>

        <div className="space-y-6">
          {/* Feature summary panel — DASHBOARD.md section 5.2, shown only when a feature is selected */}
          {selectedFeature && (
            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700">
                  {selectedFeature}
                </h2>
                <button
                  onClick={() => handleSelectFeature(selectedFeature)}
                  className="text-xs text-slate-400 hover:text-slate-600"
                >
                  Clear
                </button>
              </div>
              {!featureSummary || featureSummary.mentions === 0 ? (
                <EmptyState message={featureSummary?.note ?? "No data yet for this feature."} />
              ) : (
                <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
                  <div>
                    <div className="text-xs text-slate-400">Mentions</div>
                    <div className="font-medium text-slate-800">{featureSummary.mentions}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400">Positive</div>
                    <div className="font-medium text-emerald-600">{featureSummary.sentiment_pct?.positive}%</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400">Neutral</div>
                    <div className="font-medium text-slate-600">{featureSummary.sentiment_pct?.neutral}%</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400">Negative</div>
                    <div className="font-medium text-red-600">{featureSummary.sentiment_pct?.negative}%</div>
                  </div>
                  <div className="col-span-2 md:col-span-4">
                    <div className="mb-1 text-xs text-slate-400">Severity distribution</div>
                    <div className="flex gap-3 text-xs">
                      <span className="text-red-600">High {featureSummary.severity_pct?.high}%</span>
                      <span className="text-amber-600">Medium {featureSummary.severity_pct?.medium}%</span>
                      <span className="text-slate-500">Low {featureSummary.severity_pct?.low}%</span>
                    </div>
                  </div>
                </div>
              )}
            </section>
          )}

          {/* Priority / R&D filter tabs — DASHBOARD.md section 7 */}
          <div className="flex gap-2">
            {(["all", "high", "emerging"] as PriorityFilter[]).map((f) => (
              <button
                key={f}
                onClick={() => setPriorityFilter(f)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                  priorityFilter === f
                    ? "bg-slate-900 text-white"
                    : "border border-slate-300 text-slate-600 hover:bg-slate-100"
                }`}
              >
                {f === "all" ? "All Issues" : f === "high" ? "High Priority" : "Emerging"}
              </button>
            ))}
          </div>

          {/* Ranked issue table — DASHBOARD.md section 6 */}
          <section>
            {loading ? (
              <div className="text-sm text-slate-400">Loading…</div>
            ) : error ? (
              <EmptyState message={error} />
            ) : issues.length === 0 ? (
              <EmptyState message="No issues match this filter yet." />
            ) : (
              <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="px-4 py-2 font-medium">Issue</th>
                      <th className="px-4 py-2 font-medium">Mentions</th>
                      <th className="px-4 py-2 font-medium">Severity</th>
                      <th className="px-4 py-2 font-medium">Trend</th>
                      <th className="px-4 py-2 font-medium">Priority</th>
                    </tr>
                  </thead>
                  <tbody>
                    {issues.map((issue) => (
                      <tr
                        key={issue.id}
                        onClick={() => onOpenEvidence(issue.id)}
                        className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50"
                      >
                        <td className="px-4 py-3">
                          <div className="font-medium text-slate-800">{issue.feature}</div>
                          <div className="text-xs text-slate-500">{issue.issue}</div>
                        </td>
                        <td className="px-4 py-3 text-slate-600">{issue.mentions}</td>
                        <td className="px-4 py-3">
                          <span className={`rounded px-2 py-0.5 text-xs font-medium capitalize ${SEVERITY_STYLES[issue.severity_bucket]}`}>
                            {issue.severity_bucket}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <TrendBadge trend={issue.trend} />
                        </td>
                        <td className="px-4 py-3 font-medium text-slate-800">
                          {Math.round(issue.priority_score * 100)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
