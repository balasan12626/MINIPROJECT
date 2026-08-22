import { useEffect, useState } from "react";
import { fetchLivePipeline, refreshLive } from "../services/api.js";
import { connectSocket } from "../services/ws.js";

export function useLivePipeline(autoRefreshMs = 90000) {
  const [snapshot, setSnapshot] = useState(null);
  const [wsStatus, setWsStatus] = useState("connecting");
  const [lastEventAt, setLastEventAt] = useState(null);
  const [error, setError] = useState(null);

  async function load(force = false) {
    try {
      const data = force ? await refreshLive() : await fetchLivePipeline();
      setSnapshot(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load(true);
    const id = setInterval(() => load(false), autoRefreshMs);
    const stop = connectSocket((ev) => {
      setLastEventAt(ev.timestamp || new Date().toISOString());
      setSnapshot((prev) => {
        if (!prev) return prev;
        const next = { ...prev };
        if (ev.type === "weather_update") next.weather = ev.payload;
        if (ev.type === "risk_update") next.prediction = ev.payload;
        if (ev.type === "agent_update") {
          next.agents = (next.agents || []).map((a) =>
            a.name === ev.payload.agent ? { ...a, last_event: ev.payload.message, current_action: ev.payload.action, timestamp: ev.payload.timestamp, status: ev.payload.status } : a
          );
        }
        if (ev.type === "shelter_update") next.shelters = ev.payload.shelters || next.shelters;
        if (ev.type === "route_update") next.routes = ev.payload.routes || next.routes;
        if (ev.type === "optimization_update") next.optimization = ev.payload;
        if (ev.type === "dam_update") next.dam = ev.payload;
        if (ev.type === "river_update") next.river = ev.payload;
        if (ev.type === "system_metrics") next.latencies = { ...next.latencies, ...ev.payload };
        if (ev.type === "simulation_state") next.simulation = ev.payload;
        if (ev.type === "agent_talk") next.conversation = ev.payload;
        return { ...next, timestamp: ev.timestamp };
      });
    }, setWsStatus);
    return () => {
      clearInterval(id);
      stop();
    };
  }, [autoRefreshMs]);

  return { snapshot, wsStatus, lastEventAt, error, reload: () => load(true) };
}
