import { useState } from "react";

function riskTone(label, value) {
  const text = String(value || "").toUpperCase();
  if (label?.toLowerCase().includes("risk") || text.includes("CRITICAL") || text.includes("HIGH")) {
    if (text.includes("CRITICAL")) return "tone-crit";
    if (text.includes("HIGH")) return "tone-warn";
    if (text.includes("MODERATE") || text.includes("MEDIUM")) return "tone-sim";
    if (text.includes("LOW")) return "tone-live";
  }
  return "";
}

export default function KpiCard({ label, value, suffix = "", sub, editable = false, numericValue, onCommit, loading = false, loadingLabel = "AWAITING ML…" }) {
  const missing = value === null || value === undefined || value === "" || Number.isNaN(value);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const tone = riskTone(label, value);

  function startEdit() {
    setDraft(numericValue == null || Number.isNaN(numericValue) ? "" : String(numericValue));
    setEditing(true);
  }

  async function save() {
    const n = Number(draft);
    if (Number.isNaN(n)) return;
    setEditing(false);
    await onCommit?.(n);
  }

  return (
    <div className={`panel kpi kpi-card ${tone}`.trim()}>
      <div className="label" style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <span>{label}</span>
        {editable ? (
          <button type="button" className="kpi-edit" onClick={editing ? save : startEdit}>
            {editing ? "Save" : "Edit"}
          </button>
        ) : null}
      </div>
      {editing ? (
        <input
          className="kpi-input"
          type="number"
          step="0.01"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && save()}
        />
      ) : missing && loading ? (
        <div className="kpi-loading">
          <span className="run-spinner" aria-hidden />
          {loadingLabel}
        </div>
      ) : missing ? (
        <div className="unavailable">DATA UNAVAILABLE</div>
      ) : (
        <div className="value">
          {value}
          {suffix}
        </div>
      )}
      {sub ? <div className="sub">{sub}</div> : null}
    </div>
  );
}

export function ModeBadge({ mode, backend, ws, lastUpdate }) {
  const live = mode !== "simulation";
  return (
    <div className="status-row status-bar">
      <span className={`badge ${live ? "live" : "sim"}`}>
        {live ? "LIVE MODE" : "SIMULATION MODE — SYNTHETIC DATA"}
      </span>
      <span className="badge">Backend: {backend || "Unknown"}</span>
      <span className={`badge ${ws === "connected" ? "live" : "crit"}`}>
        {ws === "connected" ? "WebSocket: Connected" : "REALTIME CONNECTION LOST"}
      </span>
      <span className="badge">Last Update: {lastUpdate || "—"}</span>
    </div>
  );
}
