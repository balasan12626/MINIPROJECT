import { useEffect, useState } from "react";
import { fetchHealth, fetchShelters, fetchTeams, fetchEmergencies, fetchMlBenchmark, fetchSources, fetchClusters } from "../../services/api.js";
import { useLivePipeline } from "../../hooks/useLivePipeline.js";
import KpiCard, { ModeBadge } from "../../components/KpiCard.jsx";
import AgentList, { PipelineFlow } from "../../components/AgentList.jsx";
import FloodMap from "../../maps/FloodMap.jsx";
import AgentTalk from "../../components/AgentTalk.jsx";

function pct(p) {
  if (p === null || p === undefined) return null;
  return `${(p * 100).toFixed(1)}%`;
}

export default function LiveCommandCenter() {
  const { snapshot, wsStatus, lastEventAt, reload } = useLivePipeline();
  const [health, setHealth] = useState(null);
  const [extras, setExtras] = useState({ shelters: [], teams: [], emergencies: [] });

  const [bench, setBench] = useState(null);

  const [sources, setSources] = useState(null);
  const [clusters, setClusters] = useState(null);

  useEffect(() => {
    fetchHealth().then(setHealth);
    fetchMlBenchmark().then(setBench);
    fetchSources().then(setSources);
    fetchClusters().then(setClusters);
    Promise.all([fetchShelters(), fetchTeams(), fetchEmergencies()]).then(([s, t, e]) => {
      setExtras({
        shelters: s.shelters || [],
        teams: t.teams || [],
        emergencies: e.emergencies || [],
      });
    });
  }, []);

  const weather = snapshot?.weather || {};
  const pred = snapshot?.prediction || {};
  const river = snapshot?.river || {};
  const dam = snapshot?.dam || {};
  const incident = snapshot?.incident || {};
  const lat = snapshot?.latencies || {};
  const stale = lastEventAt && (Date.now() - new Date(lastEventAt).getTime() > 120000);

  return (
    <div className="page">
      <ModeBadge
        mode="live"
        backend={health?.backend === "connected" ? "Connected" : health?.mongodb || "DATA SOURCE UNAVAILABLE"}
        ws={wsStatus}
        lastUpdate={lastEventAt || snapshot?.timestamp}
      />
      {stale ? <div className="unavailable">STALE DATA — last realtime event is older than 2 minutes</div> : null}
      <div className="actions">
        <button className="primary" onClick={reload}>Refresh live pipeline</button>
      </div>
      <div className="grid-4">
        <KpiCard label="Rainfall" value={weather.available === false ? null : weather.rainfall_mm} suffix=" mm" sub={weather.source} />
        <KpiCard label="Water / Dam Level" value={dam.available === false && river.available === false ? null : (river.value_m ?? dam.value_m)} suffix=" m" sub={river.station || dam.station} />
        <KpiCard label="Flood Probability" value={pred.available === false ? null : pct(pred.flood_probability)} sub={pred.model_id} />
        <KpiCard label="Risk Level" value={pred.risk_category} sub={pred.available === false ? pred.message : null} />
        <KpiCard label="Active Incidents" value={incident.incident_id ? 1 : 0} sub={incident.zone_name} />
        <KpiCard label="Available Shelters" value={extras.shelters.filter((s) => s.status === "open").length || null} />
        <KpiCard label="Rescue Teams" value={extras.teams.length || null} />
        <KpiCard label="Model" value={pred.available === false ? null : pred.model_version} sub={pred.model_id} />
      </div>
      <div className="grid-2">
        <div className="panel">
          <h2>LIVE MAP</h2>
          <FloodMap snapshot={{ ...snapshot, all_shelters: extras.shelters, teams: extras.teams, emergencies: extras.emergencies, clusters: clusters?.clusters || snapshot?.clusters || [] }} />
        </div>
        <div>
          <div className="panel">
            <h2>LIVE WEATHER</h2>
            {weather.available === false ? <div className="unavailable">{weather.message || "DATA SOURCE UNAVAILABLE"}</div> : (
              <div>
                <div className="metric"><span>Temperature</span><b>{weather.temperature_c ?? "DATA UNAVAILABLE"} °C</b></div>
                <div className="metric"><span>Rainfall</span><b>{weather.rainfall_mm ?? "DATA UNAVAILABLE"} mm</b></div>
                <div className="metric"><span>Humidity</span><b>{weather.humidity_pct ?? "DATA UNAVAILABLE"} %</b></div>
                <div className="metric"><span>Wind</span><b>{weather.wind_mps ?? "DATA UNAVAILABLE"} m/s</b></div>
                <div className="metric"><span>Pressure</span><b>{weather.pressure_hpa ?? "DATA UNAVAILABLE"} hPa</b></div>
                <div className="metric"><span>Forecast source</span><b>{snapshot?.forecast?.source || "DATA UNAVAILABLE"}</b></div>
                <div className="metric"><span>Timestamp</span><b>{weather.timestamp ? new Date(weather.timestamp).toLocaleString() : "DATA UNAVAILABLE"}</b></div>
              </div>
            )}
          </div>
          <div className="panel" style={{ marginTop: 12 }}>
            <h2>LIVE FLOOD RISK</h2>
            {pred.available === false ? <div className="unavailable">{pred.message || "MODEL UNAVAILABLE"}</div> : (
              <div>
                <div className="value" style={{ fontSize: 42 }}>{pct(pred.flood_probability)}</div>
                <div className={`badge ${pred.risk_category === "CRITICAL" || pred.risk_category === "HIGH" ? "crit" : "live"}`}>{pred.risk_category}</div>
                <div className="metric"><span>Model</span><b>{pred.model_id}</b></div>
                <div className="metric"><span>Version</span><b>{pred.model_version}</b></div>
                <div className="metric"><span>Prediction time</span><b>{pred.prediction_timestamp ? new Date(pred.prediction_timestamp).toLocaleString() : "—"}</b></div>
                <div className="metric"><span>Freshness</span><b>{pred.data_freshness_sec != null ? `${Math.round(pred.data_freshness_sec)} sec ago` : "DATA UNAVAILABLE"}</b></div>
                <div className="metric"><span>Inference</span><b>{pred.inference_latency_ms != null ? `${pred.inference_latency_ms} ms` : "DATA UNAVAILABLE"}</b></div>
                <div className="metric"><span>ML model probability</span><b>{pred.ml_probability != null ? pct(pred.ml_probability) : "DATA UNAVAILABLE"}</b></div>
                <div className="metric"><span>Source</span><b>{pred.probability_source || pred.model_id}</b></div>
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="grid-2">
        <div className="panel">
          <h2>AGENT STATUS</h2>
          <AgentList agents={snapshot?.agents} />
        </div>
        <div className="panel">
          <h2>PERFORMANCE</h2>
          {!lat.end_to_end ? <div className="unavailable">DATA UNAVAILABLE</div> : (
            <>
              {["ingestion", "ml", "agent", "optimization", "websocket", "end_to_end"].map((k) => (
                <div className="metric" key={k}><span>{k}</span><b>{lat[k] != null ? `${lat[k]} ms` : "DATA UNAVAILABLE"}</b></div>
              ))}
            </>
          )}
        </div>
      </div>
      <div className="panel">
        <h2>LIVE DECISION PIPELINE</h2>
        <PipelineFlow stages={snapshot?.stages} />
      </div>
      <div className="panel">
        <h2>ML EVALUATION (from training, not invented)</h2>
        {!bench?.evaluation ? <div className="unavailable">{bench?.message || "MODEL UNAVAILABLE"}</div> : (
          <div className="grid-4">
            {Object.entries(bench.evaluation).map(([name, m]) => (
              <div key={name} className="kpi">
                <div className="label">{name}</div>
                <div className="value" style={{ fontSize: 22 }}>{m.accuracy != null ? `${(m.accuracy * 100).toFixed(1)}%` : "—"}</div>
                <div className="sub">AUC {(m.roc_auc || 0).toFixed(3)} · F1 {(m.f1 || 0).toFixed(3)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="grid-2">
        <div className="panel">
          <h2>LIVE DATA APIS</h2>
          {!(sources?.live_apis || []).length ? <div className="unavailable">DATA UNAVAILABLE</div> : (
            (sources.live_apis || []).map((s) => (
              <div className="metric" key={s.id}>
                <span>{s.id}</span>
                <b>{s.role}{s.keyed ? " · key set" : " · no key"}</b>
              </div>
            ))
          )}
        </div>
        <div className="panel">
          <h2>SOS K-MEANS CLUSTERS</h2>
          {!clusters?.n_sos ? <div className="muted">No open SOS yet. Send requests on Response & Evacuation.</div> : (
            <>
              <div className="metric"><span>Algorithm</span><b>{clusters.algorithm} · {clusters.n_sos} SOS → {clusters.n_clusters} clusters</b></div>
              {(clusters.clusters || []).map((c) => (
                <div className="metric" key={c.cluster_id}><span>{c.cluster_id} ({c.sos_count} calls, {c.people} people)</span><b>{c.assigned_team || "unassigned"}</b></div>
              ))}
            </>
          )}
        </div>
      </div>
      <AgentTalk conversation={snapshot?.conversation} title="LIVE AGENT CONVERSATION" />
    </div>
  );
}
