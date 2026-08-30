import { useEffect, useState, useCallback } from "react";
import { checkHealth, fetchVehicles } from "./api/client";
import { AppShell } from "./components/AppShell";
import { EmptyState } from "./components/EmptyState";
import { OverviewPage } from "./pages/OverviewPage";
import { ProductInsightsPage } from "./pages/ProductInsightsPage";
import { EvidenceExplorerPage } from "./pages/EvidenceExplorerPage";

function App() {
  const [vehicles, setVehicles] = useState<string[]>([]);
  const [selectedVehicle, setSelectedVehicle] = useState("");
  const [activePage, setActivePage] = useState<"overview" | "insights">("overview");
  const [openIssueId, setOpenIssueId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [isWaking, setIsWaking] = useState(false);
  const [wakeElapsed, setWakeElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const initApp = useCallback(async () => {
    setLoading(true);
    setError(null);
    setIsWaking(false);
    setWakeElapsed(0);

    const startTime = Date.now();
    let intervalTimer: ReturnType<typeof setInterval> | null = null;

    // After 2.5 seconds, notify user that backend is waking up
    const wakeTimer = setTimeout(() => {
      setIsWaking(true);
      intervalTimer = setInterval(() => {
        setWakeElapsed(Math.floor((Date.now() - startTime) / 1000));
      }, 1000);
    }, 2500);

    const maxAttempts = 15;
    let attempt = 0;
    let success = false;

    while (attempt < maxAttempts && !success) {
      attempt++;
      try {
        const vs = await fetchVehicles();
        setVehicles(vs);
        if (vs.length > 0) setSelectedVehicle(vs[0]);
        success = true;
        break;
      } catch {
        // Send wake ping to health endpoint
        await checkHealth();
        if (attempt < maxAttempts) {
          await new Promise((resolve) => setTimeout(resolve, 3000));
        }
      }
    }

    clearTimeout(wakeTimer);
    if (intervalTimer) clearInterval(intervalTimer);

    if (!success) {
      setError("Could not connect to the backend. If hosted on a free tier (e.g. Render), it might still be starting up. Please check your connection and VITE_API_BASE_URL.");
    }
    setLoading(false);
    setIsWaking(false);
  }, []);

  useEffect(() => {
    initApp();
  }, [initApp]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-900 p-4 font-sans text-slate-100">
        <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-950/80 p-8 shadow-2xl backdrop-blur-md text-center">
          <div className="relative mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-600/10 text-indigo-400 border border-indigo-500/20">
            <div className="absolute inset-0 rounded-2xl bg-indigo-500/20 animate-ping opacity-75" />
            <svg className="h-8 w-8 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          </div>

          <h2 className="text-xl font-semibold text-white">
            {isWaking ? "Waking Up Backend Server..." : "Connecting to AspectVoice..."}
          </h2>

          <p className="mt-2 text-sm text-slate-400">
            {isWaking
              ? "Render free-tier instances spin down after inactivity. Sending wake requests to start the service..."
              : "Initializing connection and fetching vehicle data..."}
          </p>

          {isWaking && (
            <div className="mt-6 space-y-3">
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>Waking server instance</span>
                <span className="font-mono text-indigo-400 font-medium">{wakeElapsed}s elapsed</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                <div className="h-full bg-gradient-to-r from-indigo-500 to-sky-400 animate-pulse w-full rounded-full" />
              </div>
              <p className="text-xs text-slate-500 italic">This usually takes around 30–50 seconds on cold start.</p>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-900 p-4 font-sans text-slate-100">
        <div className="w-full max-w-md rounded-2xl border border-red-900/40 bg-slate-950 p-8 text-center shadow-xl">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-500/10 text-red-400">
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-white">Connection Error</h3>
          <p className="mt-2 text-sm text-slate-400">{error}</p>
          <button
            onClick={() => initApp()}
            className="mt-6 inline-flex items-center justify-center rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:ring-offset-2 focus:ring-offset-slate-950 cursor-pointer transition"
          >
            Retry Connection
          </button>
        </div>
      </div>
    );
  }

  if (vehicles.length === 0) {
    return (
      <div className="mx-auto max-w-xl p-8">
        <EmptyState message="No vehicles ingested yet. Run the pipeline (POST /pipeline/run-all) to get started." />
      </div>
    );
  }

  return (
    <AppShell
      vehicles={vehicles}
      selectedVehicle={selectedVehicle}
      onSelectVehicle={setSelectedVehicle}
      activePage={activePage}
      onNavigate={setActivePage}
    >
      {activePage === "overview" ? (
        <OverviewPage vehicle={selectedVehicle} />
      ) : (
        <ProductInsightsPage vehicle={selectedVehicle} onOpenEvidence={setOpenIssueId} />
      )}
      {openIssueId !== null && (
        <EvidenceExplorerPage issueId={openIssueId} onClose={() => setOpenIssueId(null)} />
      )}
    </AppShell>
  );
}

export default App;
