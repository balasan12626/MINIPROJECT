import { useEffect, useMemo, useState } from "react";
import FloodMap from "../../maps/FloodMap.jsx";
import PdfDownloadButton from "../../components/PdfDownloadButton.jsx";
import {
  fetchRescueDesk,
  rescueSos,
  syncRescueFromSim,
  rescueAmbulanceAction,
  rescueShelterConfirm,
  rescueRescued,
  resetRescueDesk,
  rescueAdminShare,
} from "../../services/api.js";

const TABS = [
  { id: "admin", label: "Administrator" },
  { id: "ambulance", label: "Ambulance" },
  { id: "shelter", label: "Shelter" },
];

const EMPTY_SOS = {
  citizen_name: "Neha Verma",
  age: 34,
  people: 2,
  lat: 28.64,
  lon: 77.25,
  water_level_note: "knee-deep",
};

export default function RescueRoute() {
  const [tab, setTab] = useState("admin");
  const [desk, setDesk] = useState(null);
  const [sos, setSos] = useState(EMPTY_SOS);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(null);
  const [err, setErr] = useState("");

  async function reload() {
    const d = await fetchRescueDesk();
    setDesk(d);
    return d;
  }

  useEffect(() => {
    reload();
    const id = setInterval(reload, 1500);
    return () => clearInterval(id);
  }, []);

  const active = desk?.active_case;
  const cases = desk?.cases || [];
  const selectedCase = useMemo(
    () => cases.find((c) => c.case_id === selected) || active || cases[cases.length - 1] || null,
    [cases, selected, active]
  );

  async function run(fn) {
    setBusy(true);
    setErr("");
    try {
      const next = await fn();
      setDesk(next);
    } catch (e) {
      setErr(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  const mapSnapshot = {
    emergencies: cases.filter((c) => c.lat != null && c.lon != null).map((c) => ({
      ...c,
      live_status: c.status,
      pin_color: c.pin_color,
    })),
    shelters: (desk?.shelters || []).map((s) => ({
      ...s,
      available_seats: s.vacant,
    })),
    all_shelters: desk?.shelters || [],
    zones: [{ zone_id: "z1", name: "Rescue zone", lat: 28.6139, lon: 77.209 }],
    teams: (desk?.ambulances || [])
      .filter((a) => a.status === "busy")
      .map((a, i) => ({
        team_id: a.ambulance_id,
        name: a.name,
        status: a.status,
        lat: 28.62 + i * 0.01,
        lon: 77.22,
      })),
  };

  return (
    <div className="page rescue-page">
      <div className="status-row">
        <h2 style={{ margin: 0 }}>RESCUE ROUTE</h2>
        <span className="badge live">Admin → Ambulance → Shelter</span>
        <span className="badge">Amb free {desk?.ambulances_free ?? "—"}/{desk?.ambulances_total ?? 10}</span>
        <span className="badge">Vacant seats {desk?.vacant_total ?? "—"}</span>
        <span className="badge">Queue {desk?.queue_len ?? 0}</span>
      </div>
      {desk?.wait_reason ? <p className="counterfactual">{desk.wait_reason}</p> : null}
      {err ? <div className="unavailable">{err}</div> : null}

      <div className="rescue-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            className={tab === t.id ? "primary" : ""}
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="scenario-preview" style={{ marginBottom: 12 }}>
        <div className="metric"><span>Ambulances</span><b>10 total · {desk?.ambulances_free ?? 0} free</b></div>
        <div className="metric"><span>Shelters</span><b>{desk?.shelters_total ?? 5} · cap {desk?.capacity_total ?? 10000}</b></div>
        <div className="metric"><span>WhatsApp msgs</span><b>{desk?.message_counts?.whatsapp ?? 0}</b></div>
        <div className="metric"><span>Telegram msgs</span><b>{desk?.message_counts?.telegram ?? 0}</b></div>
      </div>

      <div className="grid-2">
        <div className="panel">
          <h2>MAP — PIN COLORS BY STATUS</h2>
          <p className="hint">SOS (red) → shared (gold) → assigned (blue) → en route (orange) → rescued (green)</p>
          <FloodMap snapshot={mapSnapshot} floodProbability={0.55} mapFeatures={{ person_card: true, sos_heatmap: false }} onSelectPerson={(p) => setSelected(p.case_id)} selectedPerson={selectedCase} />
        </div>

        <div className="panel">
          {tab === "admin" ? (
            <>
              <h2>ADMINISTRATOR AGENT</h2>
              <p className="hint">New SOS is shared one person at a time to ambulance + shelter. If all ambulances busy or shelters full — wait.</p>
              <div className="form-grid">
                <label>Name<input value={sos.citizen_name} onChange={(e) => setSos({ ...sos, citizen_name: e.target.value })} /></label>
                <label>Age<input type="number" value={sos.age} onChange={(e) => setSos({ ...sos, age: Number(e.target.value) })} /></label>
                <label>People<input type="number" value={sos.people} onChange={(e) => setSos({ ...sos, people: Number(e.target.value) })} /></label>
                <label>Lat<input type="number" step="0.0001" value={sos.lat} onChange={(e) => setSos({ ...sos, lat: Number(e.target.value) })} /></label>
                <label>Lon<input type="number" step="0.0001" value={sos.lon} onChange={(e) => setSos({ ...sos, lon: Number(e.target.value) })} /></label>
                <label>Water<input value={sos.water_level_note} onChange={(e) => setSos({ ...sos, water_level_note: e.target.value })} /></label>
              </div>
              <div className="actions" style={{ marginTop: 10 }}>
                <button className="primary" type="button" disabled={busy} onClick={() => run(() => rescueSos(sos))}>Send SOS</button>
                <button type="button" disabled={busy} onClick={() => run(() => syncRescueFromSim())}>Pull from Simulation</button>
                <button className="danger" type="button" disabled={busy} onClick={() => run(() => resetRescueDesk())}>Reset desk</button>
              </div>
              <h3 style={{ marginTop: 14 }}>Person cases (admin share)</h3>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Case</th>
                      <th>Name</th>
                      <th>Status</th>
                      <th>Amb</th>
                      <th>Shelter</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {cases.map((c) => (
                      <tr key={c.case_id} style={{ cursor: "pointer" }} onClick={() => setSelected(c.case_id)}>
                        <td>{c.case_id}</td>
                        <td>{c.citizen_name}</td>
                        <td><span className="status-pill" style={{ borderColor: c.pin_color, color: c.pin_color }}>{c.status}</span></td>
                        <td>{c.ambulance_id || "—"}</td>
                        <td>{c.shelter_name || c.proposed_shelter_name || "—"}</td>
                        <td>
                          <button type="button" disabled={busy} onClick={(e) => { e.stopPropagation(); run(() => rescueAdminShare(c.case_id)); }}>Share</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!cases.length ? <p className="hint">No SOS yet. Send one above or pull from Simulation.</p> : null}
              </div>
              <h3>Admin log</h3>
              <div className="timeline">
                {(desk?.admin_log || []).slice().reverse().map((l, i) => (
                  <div key={i}><b>{String(l.at || "").slice(11, 19)}</b> {l.text}</div>
                ))}
              </div>
              <h3>Messages (WhatsApp / Telegram)</h3>
              <div className="timeline">
                {(desk?.messages || []).slice().reverse().map((m) => (
                  <div key={m.id}><b>[{m.channel}]</b> → {m.to}: {m.text}</div>
                ))}
              </div>
            </>
          ) : null}

          {tab === "ambulance" ? (
            <>
              <h2>AMBULANCE TAB — 10 UNITS</h2>
              <p className="hint">Accept/Decline the shared SOS. Then: Going → Pickup → Drop to shelter → Completed.</p>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr><th>Unit</th><th>Status</th><th>Case</th></tr>
                  </thead>
                  <tbody>
                    {(desk?.ambulances || []).map((a) => (
                      <tr key={a.ambulance_id}>
                        <td>{a.name}</td>
                        <td>{a.status}</td>
                        <td>{a.current_case_id || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {active ? (
                <div className="panel" style={{ marginTop: 12 }}>
                  <h3>Active patient: {active.citizen_name}</h3>
                  <p className="hint">{active.case_id} · {active.people} people · {active.water_level_note} · GPS {active.lat},{active.lon}</p>
                  <div className="actions">
                    {(desk?.ambulances || []).filter((a) => a.status === "free").slice(0, 4).map((a) => (
                      <button key={a.ambulance_id} className="primary" type="button" disabled={busy} onClick={() => run(() => rescueAmbulanceAction(active.case_id, a.ambulance_id, "accept"))}>
                        {a.ambulance_id} Accept
                      </button>
                    ))}
                    {(desk?.ambulances || []).slice(0, 2).map((a) => (
                      <button key={`d-${a.ambulance_id}`} type="button" disabled={busy} onClick={() => run(() => rescueAmbulanceAction(active.case_id, a.ambulance_id, "decline"))}>
                        {a.ambulance_id} Decline
                      </button>
                    ))}
                  </div>
                  {active.ambulance_id ? (
                    <div className="actions" style={{ marginTop: 10 }}>
                      <button type="button" disabled={busy} onClick={() => run(() => rescueAmbulanceAction(active.case_id, active.ambulance_id, "going"))}>Going to patient</button>
                      <button type="button" disabled={busy} onClick={() => run(() => rescueAmbulanceAction(active.case_id, active.ambulance_id, "pickup"))}>Pickup</button>
                      <button type="button" disabled={busy} onClick={() => run(() => rescueAmbulanceAction(active.case_id, active.ambulance_id, "drop"))}>Drop to shelter</button>
                      <button className="primary" type="button" disabled={busy} onClick={() => run(() => rescueAmbulanceAction(active.case_id, active.ambulance_id, "completed"))}>Completed</button>
                    </div>
                  ) : null}
                  <div className="actions" style={{ marginTop: 10 }}>
                    <button type="button" disabled={busy} onClick={() => run(() => rescueRescued(active.case_id, true))}>Ask again: YES rescued</button>
                    <button type="button" disabled={busy} onClick={() => run(() => rescueRescued(active.case_id, false))}>Ask again: NOT rescued</button>
                  </div>
                </div>
              ) : (
                <p className="hint">No active shared case. Admin must send/share an SOS first.</p>
              )}
            </>
          ) : null}

          {tab === "shelter" ? (
            <>
              <h2>SHELTER TAB — 5 SHELTERS · ~10K CAPACITY</h2>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Shelter</th>
                      <th>Capacity</th>
                      <th>Filled</th>
                      <th>Vacant / left</th>
                      <th>Full?</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(desk?.shelters || []).map((s) => (
                      <tr key={s.shelter_id}>
                        <td>{s.name}</td>
                        <td>{s.capacity}</td>
                        <td>{s.filled ?? s.occupancy}</td>
                        <td>{s.vacant ?? s.left}</td>
                        <td>{s.full ? "YES" : "no"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {active ? (
                <div className="actions" style={{ marginTop: 12 }}>
                  <p className="hint">Proposed for {active.citizen_name}: {active.proposed_shelter_name || active.shelter_name}</p>
                  <button className="primary" type="button" disabled={busy} onClick={() => run(() => rescueShelterConfirm(active.case_id, true))}>Shelter Accept / Reserve</button>
                  <button type="button" disabled={busy} onClick={() => run(() => rescueShelterConfirm(active.case_id, false))}>Shelter Decline (full)</button>
                </div>
              ) : null}
            </>
          ) : null}
        </div>
      </div>

      {selectedCase ? (
        <div className="panel">
          <h2>PERSON DETAIL REPORT — {selectedCase.citizen_name}</h2>
          <p className="hint">
            From SOS → shelter: status {selectedCase.status} · ambulance {selectedCase.ambulance_name || "—"} ·
            shelter {selectedCase.shelter_name || selectedCase.proposed_shelter_name || "—"} ·
            cluster {selectedCase.cluster_id || "n/a"} · model {selectedCase.model_id || "n/a"} ·
            P {selectedCase.flood_probability != null ? `${(selectedCase.flood_probability * 100).toFixed(1)}%` : "n/a"}
          </p>
          <div className="scenario-preview">
            {Object.entries(selectedCase.timestamps || {}).map(([k, v]) => (
              <div className="metric" key={k}><span>{k}</span><b>{String(v).slice(11, 19) || String(v)}</b></div>
            ))}
          </div>
          <div className="timeline">
            {(selectedCase.journey || []).map((j, i) => (
              <div key={i}><b>{String(j.at || "").slice(11, 19)}</b> [{j.agent}] {j.event}: {j.detail}</div>
            ))}
          </div>
          <div className="actions">
            <PdfDownloadButton
              mode="rescue"
              caseId={selectedCase.case_id}
              personName={selectedCase.citizen_name}
              label="Download this person PDF"
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
