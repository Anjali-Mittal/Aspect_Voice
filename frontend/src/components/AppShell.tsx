import type { ReactNode } from "react";

interface Props {
  vehicles: string[];
  selectedVehicle: string;
  onSelectVehicle: (v: string) => void;
  activePage: "overview" | "insights";
  onNavigate: (page: "overview" | "insights") => void;
  children: ReactNode;
}

/** Top-level shell: nav + vehicle selector, per DASHBOARD.md section 11. */
export function AppShell({ vehicles, selectedVehicle, onSelectVehicle, activePage, onNavigate, children }: Props) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-8">
            <span className="text-lg font-semibold tracking-tight text-slate-900">AspectVoice</span>
            <nav className="flex gap-6 text-sm font-medium text-slate-500">
              <button
                onClick={() => onNavigate("overview")}
                className={`border-b-2 pb-4 -mb-4 ${
                  activePage === "overview" ? "border-slate-900 text-slate-900" : "border-transparent hover:text-slate-700"
                }`}
              >
                Overview
              </button>
              <button
                onClick={() => onNavigate("insights")}
                className={`border-b-2 pb-4 -mb-4 ${
                  activePage === "insights" ? "border-slate-900 text-slate-900" : "border-transparent hover:text-slate-700"
                }`}
              >
                Product Insights
              </button>
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-slate-500">Vehicle</label>
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
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
    </div>
  );
}
