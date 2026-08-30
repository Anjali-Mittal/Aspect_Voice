import { useEffect, useState } from "react";
import { fetchVehicles } from "./api/client";
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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchVehicles()
      .then((vs) => {
        setVehicles(vs);
        if (vs.length > 0) setSelectedVehicle(vs[0]);
      })
      .catch(() => setError("Could not reach the backend. Is it running and is VITE_API_BASE_URL set correctly?"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="p-8 text-sm text-slate-400">Loading…</div>;
  }

  if (error) {
    return (
      <div className="mx-auto max-w-xl p-8">
        <EmptyState message={error} />
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
