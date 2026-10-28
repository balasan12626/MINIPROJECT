import { Suspense, lazy, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import SimulationLab from "./pages/SimulationLab/SimulationLab.jsx";
import ThemeToggle from "./components/ThemeToggle.jsx";
import { fetchModelsV2 } from "./services/api.js";

// Phone pages (no app chrome, lazy-loaded): driver app (F3), citizen SOS (F4).
const DriverApp = lazy(() => import("./pages/DriverApp/DriverApp.jsx"));
const CitizenSos = lazy(() => import("./pages/CitizenSos/CitizenSos.jsx"));
const SafePage = lazy(() => import("./pages/SafePage/SafePage.jsx"));
const FindPage = lazy(() => import("./pages/FindPage/FindPage.jsx"));
const PHONE_PAGES = ["/driver/", "/sos", "/safe", "/find"];

export default function App() {
  const location = useLocation();
  if (PHONE_PAGES.some((p) => location.pathname.startsWith(p))) {
    return (
      <Suspense fallback={<p className="hint">Loading…</p>}>
        <Routes>
          <Route path="/driver/:unit" element={<DriverApp />} />
          <Route path="/sos" element={<CitizenSos />} />
          <Route path="/safe" element={<SafePage />} />
          <Route path="/find" element={<FindPage />} />
        </Routes>
      </Suspense>
    );
  }
  return <MainApp location={location} />;
}

function MainApp({ location }) {
  // Command Center and Response are live-ops views even though they now live
  // as subtabs of /simulation.
  const tab = new URLSearchParams(location.search).get("tab");
  const isSimulation = location.pathname.startsWith("/simulation") && tab !== "command" && tab !== "response";
  const [model, setModel] = useState(null);

  useEffect(() => {
    let alive = true;
    fetchModelsV2()
      .then((d) => {
        if (alive) setModel(d);
      })
      .catch(() => {
        if (alive) setModel(null);
      });
    return () => {
      alive = false;
    };
  }, []);

  const modelVersion = model?.available ? model.version : null;

  return (
    <div className="app-shell eoc-shell">
      <header className="topbar glass-topbar">
        <div className="brand">
          <div className="brand-lockup">
            <div className="brand-logo" aria-hidden>
              <span className="brand-logo-wave" />
            </div>
            <div>
              <p className="brand-mark">AQUASENTINEL</p>
              <h1>Intelligent Flood Response &amp; Digital Twin Platform</h1>
            </div>
          </div>
          <p className="brand-tagline">
            Live environmental intelligence · coordinated response · IEEE-transparent AI
          </p>
        </div>
        <div className="topbar-right">
          <div className={`live-pill ${isSimulation ? "sim-pill" : ""}`} title="Operating mode">
            <span className="live-dot" aria-hidden />
            <span>{isSimulation ? "SIM MODE" : "LIVE OPS"}</span>
          </div>
          <div className="live-pill model-pill" title="Active flood ML model version">
            <span>{modelVersion ? `ML MODEL · V${modelVersion.split(".")[0]} (${modelVersion})` : "ML MODEL · N/A"}</span>
          </div>
          <ThemeToggle />
          <nav className="nav" aria-label="Primary">
            <NavLink to="/simulation">Simulation</NavLink>
          </nav>
        </div>
      </header>
      <main className="app-main">
        <Routes>
          {/* Everything lives in /simulation; the old pages are its subtabs. */}
          <Route path="/simulation" element={<SimulationLab />} />
          <Route path="/" element={<Navigate to="/simulation?tab=command" replace />} />
          <Route path="/response" element={<Navigate to="/simulation?tab=response" replace />} />
          <Route path="/rescue" element={<Navigate to="/simulation?tab=rescue" replace />} />
          <Route path="/simulation/run" element={<Navigate to="/simulation" replace />} />
          <Route path="*" element={<Navigate to="/simulation" replace />} />
        </Routes>
      </main>
    </div>
  );
}
