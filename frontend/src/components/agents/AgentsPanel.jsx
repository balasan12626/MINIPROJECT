import { memo, useEffect, useMemo, useRef, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartTheme } from "../../config/chartTheme.js";
import { overrideSimulation } from "../../services/api.js";
import { formatTimeIST } from "../../utils/time.js";
import PlaybookEditor from "./PlaybookEditor.jsx";

const TIER_STYLE = {
  WAITING: { cls: "tier-wait", icon: "⏳", title: "Waiting" },
  ADMIN: { cls: "tier-admin", icon: "🧑‍💼", title: "Handed to Administrator" },
  READY: { cls: "tier-ready", icon: "⚠️", title: "CRITICAL — be ready" },
  FIELD: { cls: "tier-field", icon: "🚨", title: "ALL ON THE FIELD" },
};
const AGENT_ICON = {
  manager: "🎯",
  administrator: "🧑‍💼",
  probability: "📊",
  flood: "🌧️",
  dam: "🏞️",
  ambulance: "🚑",
  rescue: "🚒",
  shelter: "🏠",
  route: "⚛️",
  notify: "🔔",
};
const pct = (p) => (typeof p === "number" ? `${(p * 100).toFixed(1)}%` : "—");

/* ------------------------------------------------------------------ gauge */
function TierGauge({ ma }) {
  const p = ma?.probability;
  const ready = (ma?.thresholds?.ready ?? 0.5) * 100;
  const field = (ma?.thresholds?.field ?? 0.75) * 100;
  const st = TIER_STYLE[ma?.tier] || TIER_STYLE.WAITING;
  return (
    <div className={`panel tier-panel ${st.cls}`}>
      <div className="tier-head">
        <span className="tier-icon" aria-hidden>
          {st.icon}
        </span>
        <div>
          <div className="tier-title">{st.title}</div>
          <div className="tier-label">{ma?.tier_label || "Run a scenario to start the agents."}</div>
        </div>
        <div className="tier-p">
          <b>{pct(p)}</b>
          <span>flood probability</span>
        </div>
      </div>
      <div className="tier-bar" role="img" aria-label={`Flood probability ${pct(p)}`}>
        <i className="zone zone-admin" style={{ width: `${ready}%` }} />
        <i className="zone zone-ready" style={{ width: `${field - ready}%` }} />
        <i className="zone zone-field" style={{ width: `${100 - field}%` }} />
        {typeof p === "number" ? <span className="tier-needle" style={{ left: `${Math.min(100, p * 100)}%` }} /> : null}
      </div>
      <div className="tier-scale">
        <span>0%</span>
        <span style={{ left: `${ready}%` }}>{ready}% · be ready</span>
        <span style={{ left: `${field}%` }}>{field}% · all on field</span>
        <span>100%</span>
      </div>
      <div className="tier-legend">
        <span>
          <i className="zone-admin" /> Below {ready}%: Manager hands over to the Administrator (human review)
        </span>
        <span>
          <i className="zone-ready" /> {ready}–{field}%: CRITICAL, ambulances / rescue / shelters notified to be ready
        </span>
        <span>
          <i className="zone-field" /> Above {field}%: all units on the field
        </span>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------- network graph */
const W = 520;
const H = 360;
function AgentNetwork({ agents = [], messages = [], focus, onFocus }) {
  const pos = useMemo(() => {
    const out = {};
    const ring = agents.filter((a) => a.key !== "manager");
    out.manager = [W / 2, H / 2];
    ring.forEach((a, i) => {
      const ang = (i / ring.length) * Math.PI * 2 - Math.PI / 2;
      out[a.key] = [W / 2 + Math.cos(ang) * 205, H / 2 + Math.sin(ang) * 140];
    });
    return out;
  }, [agents]);

  // Edges that carried one of the latest 12 messages glow.
  const hot = useMemo(() => {
    const s = new Map();
    messages.slice(0, 12).forEach((m, i) => {
      for (const to of m.to || []) {
        const k = [m.from, to].sort().join("|");
        if (!s.has(k)) s.set(k, i);
      }
    });
    return s;
  }, [messages]);

  const edges = agents.filter((a) => a.key !== "manager").map((a) => ["manager", a.key]);
  const extra = [
    ["flood", "probability"],
    ["ambulance", "shelter"],
    ["rescue", "shelter"],
  ];

  return (
    <svg className="agent-net" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Agent network">
      {[...edges, ...extra].map(([a, b]) => {
        if (!pos[a] || !pos[b]) return null;
        const k = [a, b].sort().join("|");
        const age = hot.get(k);
        const isHot = age != null;
        const isFocus = focus && (a === focus || b === focus);
        return (
          <line
            key={k}
            x1={pos[a][0]}
            y1={pos[a][1]}
            x2={pos[b][0]}
            y2={pos[b][1]}
            className={`net-edge ${isHot ? "is-hot" : ""} ${isFocus ? "is-focus" : ""}`}
            style={isHot ? { opacity: 1 - age * 0.06 } : undefined}
          />
        );
      })}
      {agents.map((a) => {
        const [x, y] = pos[a.key] || [0, 0];
        const big = a.key === "manager";
        return (
          <g
            key={a.key}
            transform={`translate(${x},${y})`}
            className={`net-node status-${String(a.status).toLowerCase()} ${focus === a.key ? "is-focus" : ""}`}
            onClick={() => onFocus?.(focus === a.key ? null : a.key)}
            role="button"
            tabIndex={0}
          >
            <circle r={big ? 38 : 28} />
            <text className="net-icon" y={big ? -2 : -1} textAnchor="middle" dominantBaseline="middle">
              {AGENT_ICON[a.key]}
            </text>
            <text className="net-label" y={big ? 54 : 43} textAnchor="middle">
              {a.name.replace(" Agent", "").replace(" (QAOA)", "")}
            </text>
            <text className="net-status" y={big ? 68 : 56} textAnchor="middle">
              {a.status}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* ------------------------------------------------------------ message board */
const KIND_CLASS = {
  critical: "msg-critical",
  field: "msg-field",
  handover: "msg-handover",
  alert: "msg-alert",
  dispatch: "msg-dispatch",
  ack: "msg-ack",
  sudden: "msg-field",
  done: "msg-ack",
};
function MessageBoard({ messages = [], focus, onFocus }) {
  const rows = focus ? messages.filter((m) => m.from === focus || (m.to || []).includes(focus)) : messages;
  return (
    <div className="panel msg-board">
      <div className="panel-head">
        <h3>Agent messages</h3>
        <span className="fleet-summary">
          {focus ? (
            <button type="button" className="link-btn" onClick={() => onFocus(null)}>
              Showing {focus} · clear
            </button>
          ) : null}
          <span className="badge sim">{rows.length}</span>
        </span>
      </div>
      <div className="msg-list">
        {rows.length === 0 ? <p className="hint">Messages appear once the run starts.</p> : null}
        {rows.map((m, i) => (
          <div key={m.id ?? `${m.at}-${i}`} className={`msg sev-${m.severity || "green"} ${KIND_CLASS[m.kind] || ""}`}>
            <span className="msg-avatar" aria-hidden>
              {AGENT_ICON[m.from] || "•"}
            </span>
            <div className="msg-body">
              <div className="msg-meta">
                <b>{m.title ? `${m.title} · ` : ""}{m.from_name}</b> → {(m.to_names || []).join(", ")}
                <span className="muted"> · {formatTimeIST(m.at)}</span>
              </div>
              <div className="msg-text">{m.text}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* --------------------------------------------------------- rainfall demo */
const sleep = (ms) => new Promise((r) => window.setTimeout(r, ms));

function RainfallDemo({ history = [], thresholds, onState }) {
  const [fromCm, setFromCm] = useState(1);
  const [toCm, setToCm] = useState(50);
  const [steps, setSteps] = useState(10);
  const [gap, setGap] = useState(1.5);
  const [run, setRun] = useState(null); // {i, n, rain, p}
  const [err, setErr] = useState("");
  const stop = useRef(false);
  useEffect(() => () => {
    stop.current = true;
  }, []);

  async function start() {
    stop.current = false;
    setErr("");
    const n = Math.max(2, Math.min(30, Number(steps) || 10));
    try {
      for (let i = 0; i <= n; i += 1) {
        if (stop.current) break;
        const cm = Number(fromCm) + ((Number(toCm) - Number(fromCm)) * i) / n;
        const res = await overrideSimulation({ rainfall_mm: Math.round(cm * 100) / 10 });
        onState?.(res);
        const last = res?.history?.[res.history.length - 1];
        setRun({ i, n, rain: cm, p: last?.flood_probability ?? null, tier: res?.multi_agent?.tier });
        if (i < n) await sleep(Math.max(1.1, Number(gap) || 1.5) * 1000);
      }
    } catch (e) {
      setErr(e?.message || "Override failed");
    } finally {
      setRun((r) => (r ? { ...r, done: true } : r));
    }
  }

  async function handBack() {
    stop.current = true;
    try {
      onState?.(await overrideSimulation({ clear: ["rainfall_mm"] }));
    } catch (e) {
      setErr(e?.message || "Could not clear the override");
    }
  }

  const data = useMemo(
    () =>
      history.slice(-80).map((h) => ({
        t: h.sim_time_sec,
        p: h.flood_probability != null ? Math.round(h.flood_probability * 1000) / 10 : null,
        rain: h.rainfall_mm != null ? Math.round(h.rainfall_mm) / 10 : null,
        edit: h.source === "operator_edit",
      })),
    [history]
  );
  const busy = run && !run.done;
  const ready = (thresholds?.ready ?? 0.5) * 100;
  const field = (thresholds?.field ?? 0.75) * 100;

  return (
    <div className="panel rain-demo">
      <div className="panel-head">
        <h3>Scenario demo — change the rainfall and watch the agents</h3>
        {run ? (
          <span className={`badge ${run.done ? "live" : "warn"}`}>
            {run.done ? "Done" : `Step ${run.i}/${run.n}`} · {run.rain.toFixed(1)} cm · P {run.p != null ? `${(run.p * 100).toFixed(1)}%` : "—"}
          </span>
        ) : null}
      </div>
      <p className="hint">
        Each step sends the new 24 h rainfall into the running simulation; the flood model re-scores it and the agents
        react. 1 cm = 10 mm.
      </p>
      <div className="form-grid rain-demo-grid">
        <label>
          From (cm)
          <input type="number" min="0" step="0.5" value={fromCm} disabled={busy} onChange={(e) => setFromCm(e.target.value)} />
        </label>
        <label>
          To (cm)
          <input type="number" min="0" step="0.5" value={toCm} disabled={busy} onChange={(e) => setToCm(e.target.value)} />
        </label>
        <label>
          Steps
          <input type="number" min="2" max="30" value={steps} disabled={busy} onChange={(e) => setSteps(e.target.value)} />
        </label>
        <label>
          Seconds per step
          <input type="number" min="1.1" step="0.1" value={gap} disabled={busy} onChange={(e) => setGap(e.target.value)} />
        </label>
      </div>
      <div className="actions">
        <button type="button" className="primary" disabled={busy} onClick={start}>
          ▶ Play rainfall {fromCm} → {toCm} cm
        </button>
        <button type="button" disabled={!busy} onClick={() => (stop.current = true)}>
          ■ Stop
        </button>
        <button type="button" disabled={busy} onClick={handBack}>
          Hand rainfall back to the scenario
        </button>
      </div>
      {busy ? (
        <div className="rain-progress" aria-hidden>
          <i style={{ width: `${(run.i / run.n) * 100}%` }} />
        </div>
      ) : null}
      {err ? <p className="error-text">{err}</p> : null}
      <div className="rain-chart">
        {data.length < 2 ? (
          <p className="hint">The chart fills as the simulation ticks.</p>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={data} margin={{ top: 10, right: 12, left: 0, bottom: 4 }}>
              <CartesianGrid {...chartTheme.grid} />
              <ReferenceArea yAxisId="p" y1={field} y2={100} fill="var(--status-sos)" fillOpacity={0.08} />
              <ReferenceArea yAxisId="p" y1={ready} y2={field} fill="var(--status-enroute)" fillOpacity={0.08} />
              <ReferenceLine yAxisId="p" y={ready} stroke="var(--status-enroute)" strokeDasharray="5 4" label={{ value: `${ready}% ready`, fill: "var(--status-enroute)", fontSize: 11, position: "insideTopLeft" }} />
              <ReferenceLine yAxisId="p" y={field} stroke="var(--status-sos)" strokeDasharray="5 4" label={{ value: `${field}% field`, fill: "var(--status-sos)", fontSize: 11, position: "insideTopLeft" }} />
              <XAxis {...chartTheme.axis} dataKey="t" unit="s" />
              <YAxis {...chartTheme.axis} yAxisId="p" domain={[0, 100]} unit="%" width={44} />
              <YAxis {...chartTheme.axis} yAxisId="r" orientation="right" unit=" cm" width={52} />
              <Tooltip {...chartTheme.tooltip} />
              <Line isAnimationActive={false} yAxisId="p" type="monotone" dataKey="p" name="Flood probability %" stroke="var(--accent)" strokeWidth={2.5} dot={false} />
              <Line isAnimationActive={false} yAxisId="r" type="stepAfter" dataKey="rain" name="Rainfall cm" stroke="var(--status-transport)" strokeWidth={1.8} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------- panel */
function AgentsPanel({ ma, history, onState }) {
  const [focus, setFocus] = useState(null);
  const agents = ma?.agents || [];
  const messages = ma?.messages || [];
  return (
    <section className="agents-tab" aria-label="Multi-agent system">
      <TierGauge ma={ma} />
      <div className="grid-2 agents-grid">
        <div className="panel">
          <div className="panel-head">
            <h3>Multi-agent network</h3>
            <span className="badge sim">{agents.length} agents</span>
          </div>
          <AgentNetwork agents={agents} messages={messages} focus={focus} onFocus={setFocus} />
          <p className="hint">Click an agent to filter its messages. Glowing links carried the latest messages.</p>
        </div>
        <MessageBoard messages={messages} focus={focus} onFocus={setFocus} />
      </div>
      <div className="agent-cards">
        {agents.map((a) => (
          <button
            key={a.key}
            type="button"
            className={`agent-card status-${String(a.status).toLowerCase()} ${focus === a.key ? "is-focus" : ""}`}
            onClick={() => setFocus(focus === a.key ? null : a.key)}
          >
            <span className="agent-card-icon" aria-hidden>
              {AGENT_ICON[a.key]}
            </span>
            <span className="agent-card-main">
              <b>{a.name}</b>
              <span className="agent-card-role">{a.role}</span>
              <span className="agent-card-obs">{a.observation}</span>
              {a.action ? <span className="agent-card-action">Now: {a.action}</span> : null}
            </span>
            <span className="agent-card-status">
              {a.status}
              <small>{a.messages_sent} msgs</small>
            </span>
          </button>
        ))}
      </div>
      {ma?.notified?.length ? (
        <div className="panel">
          <div className="panel-head">
            <h3>Notifications sent ({ma.tier === "FIELD" ? "all on field" : "be ready"})</h3>
            <span className="badge warn">{formatTimeIST(ma.tier_since)}</span>
          </div>
          <div className="notified-list">
            {ma.notified.map((n) => (
              <span key={n.unit} className={`notified-chip type-${n.type}`}>
                {n.type === "ambulance" ? "🚑" : "🏠"} {n.unit} · <b>{n.status}</b>
              </span>
            ))}
          </div>
        </div>
      ) : null}
      {ma?.sudden_events?.length ? (
        <div className="panel sudden-panel">
          <div className="panel-head">
            <h3>🔴 Sudden rises detected</h3>
            <span className="badge crit">{ma.sudden_events.length}</span>
          </div>
          {ma.sudden_events
            .slice()
            .reverse()
            .map((s) => (
              <div key={s.at} className="metric">
                <span>{formatTimeIST(s.at)}</span>
                <b>{s.reasons.join(" · ")}</b>
              </div>
            ))}
        </div>
      ) : null}
      <RainfallDemo history={history} thresholds={ma?.thresholds} onState={onState} />
      <PlaybookEditor agents={agents} tier={ma?.tier} />
      {ma?.note ? <p className="hint">{ma.note}</p> : null}
    </section>
  );
}

export default memo(AgentsPanel);
