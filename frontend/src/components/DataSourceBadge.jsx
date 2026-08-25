import { useEffect, useState } from "react";
import { apiUrl } from "../services/apiOrigin.js";

/** Small provenance badge for IEEE honesty. */
export default function DataSourceBadge({ kind = "SIMULATED", title }) {
  const k = String(kind || "SIMULATED").toUpperCase();
  const cls =
    k.includes("LIVE") || k === "REAL" || k === "REAL ML" || k === "LLM"
      ? "src-live"
      : k.includes("FALLBACK") || k.includes("HEURISTIC")
        ? "src-warn"
        : k.includes("SYNTHETIC") || k.includes("SIMULATED")
          ? "src-synth"
          : "src-hist";
  return (
    <span className={`data-source-badge ${cls}`} title={title || k}>
      {k}
    </span>
  );
}

export function RiskSplitPanel({ prediction }) {
  if (!prediction) return null;
  const ml = prediction.ml_probability;
  const op = prediction.flood_probability;
  const rainC = prediction.rainfall_component;
  const stageC = prediction.stage_component;
  return (
    <div className="risk-split glass-panel">
      <div className="risk-split-col">
        <DataSourceBadge kind="REAL ML" />
        <h3>Raw ML</h3>
        <b>{ml != null ? `${(Number(ml) * 100).toFixed(1)}%` : "—"}</b>
        <p className="hint">Trained model probability only</p>
      </div>
      <div className="risk-split-arrow" aria-hidden>
        →
      </div>
      <div className="risk-split-col">
        <DataSourceBadge kind="HYBRID" />
        <h3>Operational risk</h3>
        <b>{op != null ? `${(Number(op) * 100).toFixed(1)}%` : "—"}</b>
        <p className="hint">{prediction.risk_category || "—"}</p>
      </div>
      <div className="risk-split-meta">
        <div>
          Rainfall component: <b>{rainC != null ? Number(rainC).toFixed(3) : "—"}</b>
        </div>
        <div>
          Stage component: <b>{stageC != null ? Number(stageC).toFixed(3) : "—"}</b>
        </div>
        {prediction.hybrid_formula ? <p className="hint formula">{prediction.hybrid_formula}</p> : null}
      </div>
    </div>
  );
}

export function AgentExecutionTrace({ mode = "simulation" }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  function normalizeTrace(payload, via) {
    if (payload?.steps) {
      return { ...payload, via };
    }
    const events = payload?.events || [];
    const steps = events.map((ev) => ({
      agent: ev.agent || ev.agent_id || "agent",
      event: ev.event || ev.type,
      observation: ev.observation || ev.message,
      action: ev.action,
      timestamp: ev.timestamp || ev.created_at,
      source: "agent_events",
    }));
    return {
      available: Boolean(steps.length),
      mode,
      honesty: "Loaded from /api/agents/events (execution-trace unavailable or empty).",
      steps,
      via,
    };
  }

  function loadTrace() {
    setLoading(true);
    setErr("");
    const primary = apiUrl(`/api/agents/execution-trace?mode=${encodeURIComponent(mode)}`);
    return fetch(primary)
      .then(async (r) => {
        if (r.status === 404) {
          const fallback = await fetch(apiUrl("/api/agents/events?limit=40"));
          if (!fallback.ok) throw new Error(`Trace unavailable (HTTP ${fallback.status})`);
          return normalizeTrace(await fallback.json(), "events-fallback");
        }
        if (!r.ok) {
          const body = await r.json().catch(() => ({}));
          throw new Error(body.detail || body.message || `HTTP ${r.status}`);
        }
        return normalizeTrace(await r.json(), "execution-trace");
      })
      .then((d) => {
        setData(d);
        setErr("");
      })
      .catch((e) => {
        setData(null);
        setErr(e.message || "trace unavailable");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr("");
    const primary = apiUrl(`/api/agents/execution-trace?mode=${encodeURIComponent(mode)}`);
    fetch(primary)
      .then(async (r) => {
        if (!alive) return null;
        if (r.status === 404) {
          const fallback = await fetch(apiUrl("/api/agents/events?limit=40"));
          if (!fallback.ok) throw new Error(`Trace unavailable (HTTP ${fallback.status})`);
          return normalizeTrace(await fallback.json(), "events-fallback");
        }
        if (!r.ok) {
          const body = await r.json().catch(() => ({}));
          throw new Error(body.detail || body.message || `HTTP ${r.status}`);
        }
        return normalizeTrace(await r.json(), "execution-trace");
      })
      .then((d) => {
        if (alive && d) setData(d);
      })
      .catch((e) => {
        if (alive) {
          setData(null);
          setErr(e.message || "trace unavailable");
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [mode]);

  if (loading) return <div className="panel glass-panel"><p className="hint">Loading agent execution trace…</p></div>;
  if (err) {
    return (
      <div className="panel glass-panel">
        <div className="panel-head">
          <h2>Agent execution trace</h2>
          <DataSourceBadge kind="UNAVAILABLE" />
        </div>
        <p className="error-text">{err}</p>
        <button type="button" className="primary" onClick={() => loadTrace()}>
          Retry
        </button>
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="panel glass-panel agent-trace">
      <div className="panel-head">
        <h2>Agent execution trace</h2>
        <DataSourceBadge kind="REAL" title="From Mongo agent_events / pipeline progress" />
      </div>
      <p className="hint">{data.honesty}</p>
      {data.via === "events-fallback" ? (
        <p className="hint">Using events fallback — restart backend to enable `/api/agents/execution-trace`.</p>
      ) : null}
      <ol className="agent-trace-list">
        {(data.steps || []).slice(0, 24).map((s, i) => (
          <li key={`${s.timestamp}-${i}`}>
            <span className="trace-agent">{String(s.agent || "").toUpperCase()}</span>
            <span className="trace-obs">{s.observation || s.event || "—"}</span>
            {s.action ? <span className="muted">→ {s.action}</span> : null}
          </li>
        ))}
      </ol>
      {!data.steps?.length ? <p className="hint">No agent events yet — run a scenario or wait for live pipeline.</p> : null}
    </div>
  );
}


