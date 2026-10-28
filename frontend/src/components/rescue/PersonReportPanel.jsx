import { memo, useMemo, useState } from "react";
import PdfDownloadButton from "../PdfDownloadButton.jsx";
import { STAGE_COLOR, STAGE_SHORT } from "../../data/rescueAssets.js";
import { downloadSimReport } from "../../services/api.js";
import { formatTimeIST } from "../../utils/time.js";
import RescueStepper, { minutesBetween } from "./RescueStepper.jsx";

const t = (v) => (v ? formatTimeIST(v).replace(" IST", "") : "—");
const mins = (v) => (v == null ? "—" : v < 1 ? `${Math.round(v * 60)} s` : `${v.toFixed(1)} min`);

/** Report tab: every person's rescue timeline (wall clock, IST) with the
 * time from SOS to driver-accept and SOS to shelter, plus per-person PDF.
 * All timestamps are the backend's own `timestamps` stamps. */
function PersonReportPanel({ people = [], selectedKey, onSelect }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const selected = people.find((p) => p.key === selectedKey) || null;

  const stats = useMemo(() => {
    const accept = [];
    const total = [];
    for (const p of people) {
      const ts = p.timestamps || {};
      const a = minutesBetween(ts.queued, ts.accepted);
      const s = minutesBetween(ts.queued, ts.rescued);
      if (a != null) accept.push(a);
      if (s != null) total.push(s);
    }
    const avg = (xs) => (xs.length ? xs.reduce((n, x) => n + x, 0) / xs.length : null);
    return { avgAccept: avg(accept), avgTotal: avg(total), done: total.length };
  }, [people]);

  async function fullPdf() {
    setBusy(true);
    setErr("");
    try {
      await downloadSimReport();
    } catch (e) {
      setErr(e?.message || "PDF failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="grid-3 report-kpis">
        <div className="panel kpi kpi-card">
          <div className="label">People rescued</div>
          <div className="value">
            {stats.done} / {people.length}
          </div>
        </div>
        <div className="panel kpi kpi-card">
          <div className="label">Avg SOS → driver accepted</div>
          <div className="value">{mins(stats.avgAccept)}</div>
        </div>
        <div className="panel kpi kpi-card">
          <div className="label">Avg SOS → safe at shelter</div>
          <div className="value">{mins(stats.avgTotal)}</div>
        </div>
      </div>

      <div className="panel person-report">
        <div className="panel-head">
          <h3>Per-person rescue report</h3>
          <button type="button" className="primary" disabled={busy} onClick={fullPdf}>
            {busy ? "Building PDF…" : "⬇ Full run report (PDF, all people)"}
          </button>
        </div>
        {err ? <p className="error-text">{err}</p> : null}
        <p className="hint">
          Clock times are IST on the demo clock (stage lengths follow route travel time, sped up). Click a person to
          open their full timeline and download their own PDF.
        </p>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Person</th>
                <th>Status</th>
                <th>SOS received</th>
                <th>Allocated</th>
                <th>Driver accepted</th>
                <th>Picked up</th>
                <th>At shelter</th>
                <th>Unit · shelter</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {people.map((p) => {
                const ts = p.timestamps || {};
                return (
                  <tr
                    key={p.key}
                    className={p.key === selectedKey ? "is-selected" : ""}
                    onClick={() => onSelect?.(p.key)}
                    style={{ cursor: "pointer" }}
                  >
                    <td>
                      <b>{p.name}</b>
                      <div className="muted">
                        {p.age != null ? `age ${p.age} · ` : ""}
                        {p.people ?? 1} people
                      </div>
                    </td>
                    <td>
                      <span className="status-pill" style={{ color: STAGE_COLOR[p.stage] }}>
                        {STAGE_SHORT[p.stage] || p.stage}
                      </span>
                    </td>
                    <td>{t(ts.queued)}</td>
                    <td>{t(ts.assigned)}</td>
                    <td>{t(ts.accepted)}</td>
                    <td>{t(ts.to_shelter)}</td>
                    <td>{t(ts.rescued)}</td>
                    <td>
                      {p.unitName && p.stage !== "queued" ? p.unitName : "—"}
                      <div className="muted">{p.shelter || "—"}</div>
                    </td>
                    <td>{mins(minutesBetween(ts.queued, ts.rescued))}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {selected ? (
        <div className="panel person-report-detail">
          <div className="panel-head">
            <h3>{selected.name} — rescue timeline</h3>
            <PdfDownloadButton personName={selected.name} label="Download person PDF" />
          </div>
          <RescueStepper p={selected} />
          <div className="person-facts">
            <span>
              <b>Unit</b> {selected.unitName && selected.stage !== "queued" ? `${selected.unitName} (${selected.unitRole})` : "—"}
            </span>
            <span>
              <b>From</b> {selected.unitBaseName || "—"}
            </span>
            <span>
              <b>Shelter</b> {selected.shelter || "—"}
            </span>
            <span>
              <b>K-means cluster</b> {selected.cluster || "—"}
            </span>
            <span>
              <b>Route</b>{" "}
              {selected.routeKm != null ? `${selected.routeKm} km + ${selected.shelterKm ?? "—"} km` : "—"}
            </span>
          </div>
          <div className="timeline person-journey">
            {(selected.journey || []).map((j, i) => (
              <div key={`${j.at}-${i}`}>
                <b>{t(j.at)}</b> <span className="muted">[{j.agent}]</span> {j.detail || j.event}
              </div>
            ))}
            {!(selected.journey || []).length ? <div className="muted">No steps logged yet.</div> : null}
          </div>
        </div>
      ) : null}
    </>
  );
}

export default memo(PersonReportPanel);
