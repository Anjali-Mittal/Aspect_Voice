import type { ReactNode } from "react";

export type NavPage = "overview" | "insights" | "competitor";

interface Props {
  vehicles: string[];
  selectedVehicle: string;
  onSelectVehicle: (v: string) => void;
  activePage: NavPage;
  onNavigate: (page: NavPage) => void;
  compareVehicle: string;
  onSelectCompareVehicle: (v: string) => void;
  children: ReactNode;
}

/** Top-level shell: nav + vehicle selector(s).
 * Displays Overview, Product Insights, and Competitor Analysis tabs.
 * When on Competitor Analysis, a second vehicle picker is shown for comparison. */
export function AppShell({
  vehicles,
  selectedVehicle,
  onSelectVehicle,
  activePage,
  onNavigate,
  compareVehicle,
  onSelectCompareVehicle,
  children,
}: Props) {
  const isCompetitor = activePage === "competitor";

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className={`mx-auto flex items-center justify-between px-6 py-4 ${isCompetitor ? "max-w-[1500px]" : "max-w-6xl"}`}>
          <div className="flex items-center gap-8">
            <span className="text-lg font-semibold tracking-tight text-slate-900">AspectVoice</span>
            <nav className="flex gap-6 text-sm font-medium text-slate-500">
              <button
                onClick={() => onNavigate("overview")}
                className={`border-b-2 pb-4 -mb-4 cursor-pointer transition ${activePage === "overview" ? "border-slate-900 text-slate-900" : "border-transparent hover:text-slate-700"
                  }`}
              >
                Overview
              </button>
              <button
                onClick={() => onNavigate("insights")}
                className={`border-b-2 pb-4 -mb-4 cursor-pointer transition ${activePage === "insights" ? "border-slate-900 text-slate-900" : "border-transparent hover:text-slate-700"
                  }`}
              >
                Product Insights
              </button>
              <button
                onClick={() => onNavigate("competitor")}
                className={`border-b-2 pb-4 -mb-4 cursor-pointer transition ${activePage === "competitor" ? "border-slate-900 text-slate-900" : "border-transparent hover:text-slate-700"
                  }`}
              >
                Competitor Analysis
              </button>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-slate-500">
                {isCompetitor ? "Vehicle A" : "Vehicle"}
              </label>
              <select
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900"
                value={selectedVehicle}
                onChange={(e) => onSelectVehicle(e.target.value)}
              >
                {vehicles.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            {isCompetitor && (
              <div className="flex items-center gap-2">
                <label className="text-xs font-medium text-slate-500">vs.</label>
                <select
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900"
                  value={compareVehicle}
                  onChange={(e) => onSelectCompareVehicle(e.target.value)}
                >
                  {vehicles.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>
      </header>
      <main className={`mx-auto px-6 py-8 ${isCompetitor ? "max-w-[1500px]" : "max-w-6xl"}`}>{children}</main>
    </div>
  );
}