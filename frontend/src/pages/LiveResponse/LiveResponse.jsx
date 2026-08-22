import { useEffect, useState } from "react";
import { fetchIncidents, fetchIncident, reviewIncident, optimizeEvac, sendSos, fetchTeams, fetchClusters } from "../../services/api.js";
import { useLivePipeline } from "../../hooks/useLivePipeline.js";
import FloodMap from "../../maps/FloodMap.jsx";

export default function LiveResponse() {
  const { snapshot, reload } = useLivePipeline();
  const [incidents, setIncidents] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [reviewMsg, setReviewMsg] = useState("");
  const [sos, setSos] = useState({ lat: 28.651, lon: 77.262, people: 3, emergency_type: "flood", medical_need: false });
  const [sosMsg, setSosMsg] = useState("");
  const [clusters, setClusters] = useState(null);
  const [teams, setTeams] = useState([]);

  useEffect(() => {
    fetchIncidents().then((d) => setIncidents(d.incidents || []));
    fetchTeams().then((d) => setTeams(d.teams || []));
    fetchClusters().then(setClusters);
  }, [snapshot?.incident?.incident_id]);

  async function openIncident(id) {
    setSelected(id);
    setDetail(await fetchIncident(id));
  }

  const pred = snapshot?.prediction || {};
  const policy = snapshot?.policy || {};
  const incident = snapshot?.incident || {};
  const p = pred.flood_probability;
  const evidence = [
    snapshot?.weather?.rainfall_mm != null ? `Rainfall ${snapshot.weather.rainfall_mm} mm` : null,
    snapshot?.river?.value_m != null ? `River ${snapshot.river.value_m} m` : null,
    snapshot?.dam?.value_m != null ? `Dam ${snapshot.dam.value_m} m` : null,
    pred.risk_category ? `Risk ${pred.risk_category}` : null,
  ].filter(Boolean);

  async function decide(decision) {
    if (!incident.incident_id) return;
    const res = await reviewIncident({
      incident_id: incident.incident_id,
      decision,
      reason: decision === "approve" ? "operator approved recommended shelter/route" : "operator rejected automation",
      user: "operator",
    });
    setReviewMsg(`${decision} logged`);
    await reload();
    return res;
  }

  return (
    <div className="page">
      <div className="status-row">
        <span className="badge live">LIVE RESPONSE & EVACUATION</span>
        <span className="badge">Policy: {policy.action || "—"}</span>
      </div>
      <div className="grid-2">
        <div className="panel">
          <h2>ACTIVE INCIDENTS</h2>
          {!(incidents.length || incident.incident_id) ? <div className="unavailable">DATA UNAVAILABLE</div> : (
            <>
              {(incidents.length ? incidents : [incident]).map((it) => (
                <div key={it.incident_id} className={`list-item ${selected === it.incident_id ? "active" : ""}`} onClick={() => openIncident(it.incident_id)}>
                  <strong>INCIDENT {it.incident_id}</strong>
                  <div>{it.zone_name} · {it.type} · {it.risk_category || it.status}</div>
                  <div className="muted">Probability: {it.flood_probability != null ? `${(it.flood_probability * 100).toFixed(1)}%` : "DATA UNAVAILABLE"} · Population: {it.affected_population ?? "DATA UNAVAILABLE"}</div>
                </div>
              ))}
            </>
          )}
          <h3>INCIDENT DETAIL</h3>
          <div className="metric"><span>Location</span><b>{(detail?.incident || incident).zone_name || "DATA UNAVAILABLE"}</b></div>
          <div className="metric"><span>Rainfall</span><b>{snapshot?.weather?.rainfall_mm ?? "DATA UNAVAILABLE"} mm</b></div>
          <div className="metric"><span>Dam / River</span><b>{snapshot?.dam?.value_m ?? "DATA UNAVAILABLE"} / {snapshot?.river?.value_m ?? "DATA UNAVAILABLE"} m</b></div>
          <div className="metric"><span>Flood Probability</span><b>{p != null ? `${(p * 100).toFixed(1)}%` : "DATA UNAVAILABLE"}</b></div>
          <div className="metric"><span>Risk</span><b>{pred.risk_category || "DATA UNAVAILABLE"}</b></div>
          <div className="metric"><span>Population</span><b>{incident.affected_population ?? "DATA UNAVAILABLE"}</b></div>
          <div className="metric"><span>Road conditions</span><b>{(snapshot?.roads || []).filter((r) => r.blocked).length} blocked</b></div>
          <div className="metric"><span>Shelter availability</span><b>{(snapshot?.shelters || []).length || "DATA UNAVAILABLE"}</b></div>
        </div>
        <div>
          <div className="panel">
            <h2>DECISION POLICY</h2>
            <div className="muted">P &lt; {(policy.monitor_threshold ?? 0.5) * 100}% MONITOR · {(policy.monitor_threshold ?? 0.5) * 100}%–{(policy.auto_threshold ?? 0.6) * 100}% HUMAN REVIEW · ≥{(policy.auto_threshold ?? 0.6) * 100}% AUTOMATED (gates permitting)</div>
            <div className="metric"><span>Current action</span><b>{policy.action || "—"}</b></div>
            <div className="muted">{policy.reason}</div>
            {policy.action === "HUMAN_REVIEW" && (
              <div style={{ marginTop: 12 }}>
                <div className="badge warn">HUMAN REVIEW REQUIRED</div>
                <p>Flood Probability: {p != null ? `${(p * 100).toFixed(1)}%` : "DATA UNAVAILABLE"}</p>
                <div>Supporting Evidence:</div>
                <ul>{evidence.map((e) => <li key={e}>{e}</li>)}</ul>
                <div>Recommended: {snapshot?.shelters?.[0]?.shelter_id || "—"} / {snapshot?.routes?.[0]?.label || "—"}</div>
                <div className="actions" style={{ marginTop: 8 }}>
                  <button className="primary" onClick={() => decide("approve")}>APPROVE</button>
                  <button className="danger" onClick={() => decide("reject")}>REJECT</button>
                </div>
                {reviewMsg ? <div className="muted">{reviewMsg}</div> : null}
              </div>
            )}
            {policy.action === "AUTOMATED_RESPONSE" && (
              <div style={{ marginTop: 12 }}>
                <div className="badge crit">AUTOMATED RESPONSE ACTIVE</div>
                <div className="flow" style={{ marginTop: 10 }}>
                  {["Affected Zone", "Shelter Search", "Route Evaluation", "Optimization", "Evacuation Recommendation", "Rescue Preparation"].map((s) => (
                    <span key={s} className="stage ok">{s}</span>
                  ))}
                </div>
              </div>
            )}
            {policy.action === "MONITOR" && <div className="badge live">MONITORING — no automated dispatch</div>}
          </div>
          <div className="panel" style={{ marginTop: 12 }}>
            <h2>SHELTERS & ROUTES</h2>
            {(snapshot?.shelters || []).slice(0, 3).map((s) => (
              <div key={s.shelter_id} className="metric"><span>{s.shelter_id} {s.name}</span><b>{s.distance_km} km · {s.travel_time_min} min · seats {s.available_seats}</b></div>
            ))}
            {(snapshot?.routes || []).map((r) => (
              <div key={r.label} className="metric"><span>{r.label}</span><b>{r.distance_km} km · {r.travel_time_min} min · {r.method}</b></div>
            ))}
            {snapshot?.optimization ? (
              <div className="metric"><span>Optimization</span><b>{snapshot.optimization.method} · cost {snapshot.optimization.solution_cost}</b></div>
            ) : <div className="muted">Optimization idle until review/auto threshold</div>}
            {snapshot?.optimization === null && policy.action !== "MONITOR" ? <div className="unavailable">OPTIMIZATION FAILED — CLASSICAL FALLBACK AVAILABLE</div> : null}
            <button className="primary" onClick={() => optimizeEvac({ method: "greedy" })}>Run classical fallback</button>
          </div>
        </div>
      </div>
      <div className="panel">
        <h2>RESPONSE MAP</h2>
        <FloodMap snapshot={{ ...snapshot, teams, clusters: clusters?.clusters || [] }} />
      </div>
      <div className="grid-2">
        <div className="panel">
          <h2>CITIZEN SOS</h2>
          <div className="form-grid">
            <label>lat<input type="number" step="0.0001" value={sos.lat} onChange={(e) => setSos({ ...sos, lat: Number(e.target.value) })} /></label>
            <label>lon<input type="number" step="0.0001" value={sos.lon} onChange={(e) => setSos({ ...sos, lon: Number(e.target.value) })} /></label>
            <label>people<input type="number" value={sos.people} onChange={(e) => setSos({ ...sos, people: Number(e.target.value) })} /></label>
            <label>type<input value={sos.emergency_type} onChange={(e) => setSos({ ...sos, emergency_type: e.target.value })} /></label>
          </div>
          <div className="actions" style={{ marginTop: 10 }}>
            <button className="danger" onClick={async () => {
              try {
                const res = await sendSos(sos);
                setSosMsg(res.assignment ? `Assigned ${res.assignment.team_id}` : "SOS stored");
                if (res.clusters) setClusters(res.clusters);
                else fetchClusters().then(setClusters);
              } catch (err) {
                setSosMsg(`SOS failed: ${err.message}`);
              }
            }}>SEND SOS</button>
          </div>
          {sosMsg ? <div className="muted">{sosMsg}</div> : null}
        </div>
        <div className="panel">
          <h2>RESCUE TEAMS</h2>
          {teams.map((t) => (
            <div key={t.team_id} className="metric"><span>{t.team_id} {t.name}</span><b>{t.status}</b></div>
          ))}
          <h3>K-MEANS SOS CLUSTERS</h3>
          {!clusters?.n_sos ? <div className="muted">Send several SOS points to form clusters.</div> : (
            (clusters.clusters || []).map((c) => (
              <div className="metric" key={c.cluster_id}><span>{c.cluster_id} · {c.sos_count} SOS</span><b>{c.assigned_team}</b></div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
