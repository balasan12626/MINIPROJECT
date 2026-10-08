import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import LiveCommandCenter from "./pages/LiveCommandCenter/LiveCommandCenter.jsx";
import LiveResponse from "./pages/LiveResponse/LiveResponse.jsx";
import SimulationLab from "./pages/SimulationLab/SimulationLab.jsx";
import RescueRoute from "./pages/RescueRoute/RescueRoute.jsx";
import ThemeToggle from "./components/ThemeToggle.jsx";
import { fetchModelsV2 } from "./services/api.js";

export default function App() {
  const location = useLocation();
  const isSimulation = location.pathname.startsWith("/simulation");
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
            <NavLink to="/" end>
              Command Center
            </NavLink>
            <NavLink to="/response">Response</NavLink>
            <NavLink to="/simulation">Simulation</NavLink>
            <NavLink to="/rescue">Rescue Route</NavLink>
          </nav>
        </div>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<LiveCommandCenter />} />
          <Route path="/response" element={<LiveResponse />} />
          <Route path="/simulation" element={<SimulationLab />} />
          <Route path="/simulation/run" element={<Navigate to="/simulation" replace />} />
          <Route path="/rescue" element={<RescueRoute />} />
        </Routes>
      </main>
    </div>
  );
}
