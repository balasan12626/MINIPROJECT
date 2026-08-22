export default function AgentList({ agents = [] }) {
  if (!agents.length) return <div className="unavailable">DATA UNAVAILABLE</div>;
  return (
    <div>
      {agents.map((a) => (
        <div className="agent" key={a.name}>
          <div>
            <strong>{statusDot(a.status)} {a.name}</strong>
            <div className="muted">{a.last_event || "—"}</div>
          </div>
          <div className="muted">
            <div>{a.current_action}</div>
            <div>{a.timestamp ? new Date(a.timestamp).toLocaleTimeString() : "—"}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function statusDot(status) {
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
