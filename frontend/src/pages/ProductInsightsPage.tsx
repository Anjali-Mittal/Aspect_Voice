import { useEffect, useState } from "react";
import { fetchFeatures, fetchFeatureSummary, fetchIssues } from "../api/client";
import type { Feature, FeatureSummary, IssueSummary } from "../api/client";
import { EmptyState } from "../components/EmptyState";

interface Props {
  vehicle: string;
  onOpenEvidence: (issueId: number) => void;
}

type SentimentFilter = "negative" | "positive" | "neutral";

const SEVERITY_STYLES: Record<string, string> = {
  high: "text-red-700 bg-red-50",
  medium: "text-amber-700 bg-amber-50",
  low: "text-slate-600 bg-slate-100",
};

const UNCATEGORIZED = "Uncategorized";

export function ProductInsightsPage({ vehicle, onOpenEvidence }: Props) {
  const [features, setFeatures] = useState<Feature[]>([]);
  const [openCategories, setOpenCategories] = useState<Set<string>>(new Set());
  const [selectedFeature, setSelectedFeature] = useState<string | null>(null);
  const [featureSummary, setFeatureSummary] = useState<FeatureSummary | null>(null);
  const [issues, setIssues] = useState<IssueSummary[]>([]);
  const [sentimentFilter, setSentimentFilter] = useState<SentimentFilter>("negative");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // load features once per vehicle
  useEffect(() => {
    if (!vehicle) return;
    fetchFeatures(vehicle).then(setFeatures).catch(() => setFeatures([]));
    setOpenCategories(new Set()); // all collapsed by default, including on vehicle switch
    setSelectedFeature(null);
    setFeatureSummary(null);
  }, [vehicle]);

  // load issues whenever vehicle, selected feature, or sentiment filter changes
  useEffect(() => {
    if (!vehicle) return;
    setLoading(true);
    setError(null);
    const filters: { feature?: string; sentiment?: string } = {
      sentiment: sentimentFilter,
    };
    if (selectedFeature) filters.feature = selectedFeature;

    fetchIssues(vehicle, filters)
      .then(setIssues)
      .catch(() => setError("Could not load insights. Is the backend running?"))
      .finally(() => setLoading(false));
  }, [vehicle, selectedFeature, sentimentFilter]);

  function handleSelectFeature(feature: string) {
    const next = selectedFeature === feature ? null : feature;
    setSelectedFeature(next);
    if (next) {
      fetchFeatureSummary(next, vehicle).then(setFeatureSummary).catch(() => setFeatureSummary(null));
    } else {
      setFeatureSummary(null);
    }
  }

  function toggleCategory(category: string) {
    setOpenCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  }

  // group by category; features without a category fall into a trailing "Uncategorized" group
  const groups: { category: string; features: Feature[] }[] = [];
  const groupIndex = new Map<string, number>();
  for (const f of features) {
    const category = f.category || UNCATEGORIZED;
    if (!groupIndex.has(category)) {
      groupIndex.set(category, groups.length);
      groups.push({ category, features: [] });
    }
    groups[groupIndex.get(category)!].features.push(f);
  }

  // sort categories by number of sub-categories (descending), ties alphabetical
  groups.sort((a, b) => {
    if (a.category === UNCATEGORIZED) return 1;
    if (b.category === UNCATEGORIZED) return -1;
    if (b.features.length !== a.features.length) {
      return b.features.length - a.features.length;
    }
    return a.category.localeCompare(b.category);
  });

  // sort sub-categories within each category alphabetically
  for (const group of groups) {
    group.features.sort((a, b) => a.feature.localeCompare(b.feature));
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
            <div className="space-y-2">
              {groups.map(({ category, features: groupFeatures }) => {
                const isOpen = openCategories.has(category);
                return (
                  <div key={category} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                    <button
                      onClick={() => toggleCategory(category)}
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium text-slate-700 hover:bg-slate-50"
                    >
                      <span>{category}</span>
                      <span className="flex items-center gap-2 text-xs text-slate-400">
                        {groupFeatures.length}
                        <span className={`transition-transform ${isOpen ? "rotate-90" : ""}`}>›</span>
                      </span>
                    </button>
                    {isOpen && (
                      <div className="border-t border-slate-100">
                        {groupFeatures.map((f) => (
                          <button
                            key={f.feature}
                            onClick={() => handleSelectFeature(f.feature)}
                            className={`block w-full border-t border-slate-100 px-3 py-2 pl-5 text-left text-sm first:border-t-0 ${selectedFeature === f.feature
                                ? "bg-slate-900 text-white"
                                : "text-slate-700 hover:bg-slate-50"
                              }`}
                          >
                            {f.feature}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
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

          {/* Sentiment filter tabs */}
          <div className="flex gap-2">
            {(["negative", "positive", "neutral"] as SentimentFilter[]).map((f) => (
              <button
                key={f}
                onClick={() => setSentimentFilter(f)}
                className={`rounded-full px-3.5 py-1.5 text-xs font-medium cursor-pointer transition capitalize ${sentimentFilter === f
                    ? "bg-slate-900 text-white shadow-sm"
                    : "border border-slate-300 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
              >
                {f}
              </button>
            ))}
          </div>

          {/* Ranked issue/insight table */}
          <section>
            {loading ? (
              <div className="text-sm text-slate-400">Loading…</div>
            ) : error ? (
              <EmptyState message={error} />
            ) : issues.length === 0 ? (
              <EmptyState message={`No ${sentimentFilter} feedback matches this filter yet.`} />
            ) : (
              <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="px-4 py-2 font-medium">
                        {sentimentFilter === "negative" ? "Issue" : sentimentFilter === "positive" ? "Strength / Highlight" : "Observation"}
                      </th>
                      <th className="px-4 py-2 font-medium">Mentions</th>
                      <th className="px-4 py-2 font-medium">
                        {sentimentFilter === "negative" ? "Severity" : "Sentiment"}
                      </th>
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
                          {sentimentFilter === "negative" ? (
                            <span className={`rounded px-2 py-0.5 text-xs font-medium capitalize ${SEVERITY_STYLES[issue.severity_bucket] ?? "text-slate-600 bg-slate-100"}`}>
                              {issue.severity_bucket}
                            </span>
                          ) : (
                            <span className={`rounded px-2 py-0.5 text-xs font-medium capitalize ${
                              sentimentFilter === "positive" ? "text-emerald-700 bg-emerald-50" : "text-slate-600 bg-slate-100"
                            }`}>
                              {sentimentFilter}
                            </span>
                          )}
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