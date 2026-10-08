import { memo } from "react";
import { formatTimeIST } from "../utils/time.js";

/* Placeholder actions the backend agent graph starts with (backend/agents/
 * graph.py sets "awaiting input"). Once the run is over they are stale, so the
 * row shows the run's real state instead of a sticky "awaiting input". */
const PLACEHOLDER = /^(awaiting input|waiting|idle|—)?$/i;

function actionText(a, runStatus) {
  const raw = String(a.current_action || "").trim();
  if (!PLACEHOLDER.test(raw)) return raw;
  if (runStatus === "completed") return "done — run completed";
  if (runStatus === "paused") return "paused with the run";
  if (runStatus === "running") return "standing by for the next tick";
  return raw || "—";
}

function AgentList({ agents = [], runStatus }) {
  if (!agents?.length) return <div className="unavailable">DATA UNAVAILABLE</div>;
  return (
    <div>
      {agents.map((a) => (
        <div className="agent" key={a.name}>
          <div>
            <strong>{statusDot(a.status, runStatus)} {a.name}</strong>
            <div className="muted">{a.last_event || "—"}</div>
          </div>
          <div className="muted">
            <div>{actionText(a, runStatus)}</div>
            <div>{formatTimeIST(a.timestamp)}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default memo(AgentList);

function statusDot(status, runStatus) {
  if (runStatus === "completed") return "⚪";
  if (!status) return "⚪";
  const s = status.toUpperCase();
  if (s === "ACTIVE" || s === "OK") return "🟢";
  if (s === "WAIT" || s === "IDLE") return "🟡";
  return "🟢";
}

export function PipelineFlow({ stages = {} }) {
  const order = ["LIVE_DATA", "ML_PREDICTION", "AGENTS", "RISK_ENGINE", "DECISION_POLICY", "OPTIMIZATION", "SHELTER", "ROUTE", "RESPONSE"];
  return (
    <div className="flow">
      {order.map((key, i) => (
        <span key={key} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span className={`stage ${stages[key] && stages[key] !== "unavailable" && stages[key] !== "idle" ? "ok" : ""}`}>
            {key.replaceAll("_", " ")} · {stages[key] || "—"}
          </span>
          {i < order.length - 1 ? <span className="arrow">↓</span> : null}
        </span>
      ))}
    </div>
  );
}
