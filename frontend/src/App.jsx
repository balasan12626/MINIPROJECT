import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import LiveCommandCenter from "./pages/LiveCommandCenter/LiveCommandCenter.jsx";
import LiveResponse from "./pages/LiveResponse/LiveResponse.jsx";
import SimulationLab from "./pages/SimulationLab/SimulationLab.jsx";
import RescueRoute from "./pages/RescueRoute/RescueRoute.jsx";
import ThemeToggle from "./components/ThemeToggle.jsx";

export default function App() {
  return (
    <div className="app-shell eoc-shell">
      <header className="topbar glass-topbar">
        <div className="brand">
          <p className="brand-mark">VOYAMIND AI</p>
          <h1>Flood Response Command Center</h1>
          <p>Live environmental intelligence · coordinated flood response · IEEE-transparent AI</p>
        </div>
        <div className="topbar-right">
          <div className="live-pill" title="Operating mode">
            <span className="live-dot" aria-hidden /> LIVE
          </div>
          <ThemeToggle />
          <nav className="nav">
            <NavLink to="/" end>
              Command Center
            </NavLink>
            <NavLink to="/response">Response & Evacuation</NavLink>
            <NavLink to="/simulation">Simulation</NavLink>
            <NavLink to="/rescue">Rescue Route</NavLink>
          </nav>
        </div>
      </header>
      <Routes>
        <Route path="/" element={<LiveCommandCenter />} />
        <Route path="/response" element={<LiveResponse />} />
        <Route path="/simulation" element={<SimulationLab />} />
        <Route path="/simulation/run" element={<Navigate to="/simulation" replace />} />
        <Route path="/rescue" element={<RescueRoute />} />
      </Routes>
    </div>
  );
}
