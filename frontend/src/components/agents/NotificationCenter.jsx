import { memo, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { formatTimeIST } from "../../utils/time.js";

/** Traffic-light notifications for everything the agents do.
 *
 * Source: sim.multi_agent.messages (backend/agents/mas.py). Each message
 * already carries `severity` (green = normal / done, yellow = be ready /
 * action, red = critical / sudden rise / all on field) and a short `title`.
 * Rendered through a portal so the bell is on every /simulation tab. Read
 * state is a per-viewer convenience kept in localStorage. */
const SEV = {
  red: { label: "Critical", icon: "🔴" },
  yellow: { label: "Warning", icon: "🟡" },
  green: { label: "Normal / done", icon: "🟢" },
};
const RANK = { green: 0, yellow: 1, red: 2 };
const TOAST_MS = 6000;
/** Sudden rise, then tier changes, then everything else wins a pop-up slot. */
const headline = (m) => (m.kind === "sudden" ? 2 : ["field", "critical", "handover", "road"].includes(m.kind) ? 1 : 0);

function readKey(runId) {
  return `aq_notif_read_${runId || "none"}`;
}
function loadRead(runId) {
  try {
    return Number(localStorage.getItem(readKey(runId)) || 0);
  } catch {
    return 0;
  }
}
function saveRead(runId, id) {
  try {
    localStorage.setItem(readKey(runId), String(id));
  } catch {
    /* storage blocked — read state stays in memory */
  }
}

function NotificationCenter({ messages = [], runId }) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("all");
  const [agent, setAgent] = useState("all");
  const [readUpTo, setReadUpTo] = useState(() => loadRead(runId));
  const [toasts, setToasts] = useState([]);
  const [popAll, setPopAll] = useState(false);
  const seenMax = useRef(null);

  useEffect(() => {
    setReadUpTo(loadRead(runId));
    seenMax.current = null;
    setToasts([]);
  }, [runId]);

  const maxId = messages.length ? Math.max(...messages.map((m) => m.id || 0)) : 0;

  // Pop-ups for messages newer than anything seen so far (none on first load).
  useEffect(() => {
    if (seenMax.current === null) {
      seenMax.current = maxId;
      return;
    }
    if (maxId <= seenMax.current) return;
    const fresh = messages
      // By default only red alerts and headline events pop up; routine
      // dispatch / pickup / playbook lines stay in the drawer.
      .filter(
        (m) =>
          m.id > seenMax.current &&
          m.kind !== "playbook" &&
          (popAll || m.severity === "red" || headline(m) > 0)
      )
      .sort((a, b) => headline(b) - headline(a) || RANK[b.severity] - RANK[a.severity] || b.id - a.id)
      .slice(0, 3);
    seenMax.current = maxId;
    if (!fresh.length) return;
    const now = Date.now();
    setToasts((t) => [...fresh.map((m) => ({ ...m, until: now + TOAST_MS })), ...t].slice(0, 4));
  }, [maxId, messages, popAll]);

  useEffect(() => {
    if (!toasts.length) return undefined;
    const t = window.setTimeout(() => setToasts((xs) => xs.filter((x) => x.until > Date.now())), 1000);
    return () => window.clearTimeout(t);
  }, [toasts]);

  const unread = messages.filter((m) => m.id > readUpTo);
  const worst = unread.reduce((w, m) => (RANK[m.severity] > RANK[w] ? m.severity : w), "green");
  const counts = useMemo(() => {
    const c = { red: 0, yellow: 0, green: 0 };
    for (const m of messages) c[m.severity] = (c[m.severity] || 0) + 1;
    return c;
  }, [messages]);
  const agents = useMemo(() => [...new Set(messages.map((m) => m.from_name))].sort(), [messages]);
  const rows = messages.filter((m) => (filter === "all" || m.severity === filter) && (agent === "all" || m.from_name === agent));

  const markAll = () => {
    setReadUpTo(maxId);
    saveRead(runId, maxId);
  };

  if (typeof document === "undefined") return null;
  return createPortal(
    <>
      <button
        type="button"
        className={`notif-bell sev-${unread.length ? worst : "none"}`}
        aria-label={`Notifications, ${unread.length} unread`}
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden>🔔</span>
        {unread.length ? <b className="notif-count">{unread.length > 99 ? "99+" : unread.length}</b> : null}
      </button>

      <div className="notif-toasts" aria-live="polite">
        {toasts.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`notif-toast sev-${t.severity}`}
            onClick={() => {
              setOpen(true);
              setToasts((xs) => xs.filter((x) => x.id !== t.id));
            }}
          >
            <b>
              {SEV[t.severity].icon} {t.title}
            </b>
            <span>{t.text}</span>
            <small>{t.from_name}</small>
          </button>
        ))}
      </div>

      {open ? (
        <aside className="notif-drawer" role="dialog" aria-label="Notifications">
          <header className="notif-head">
            <h3>Notifications</h3>
            <button type="button" className="link-btn" onClick={markAll} disabled={!unread.length}>
              Mark all read
            </button>
            <button type="button" className="notif-close" aria-label="Close" onClick={() => setOpen(false)}>
              ✕
            </button>
          </header>
          <div className="notif-filters">
            {[
              ["all", `All ${messages.length}`],
              ["red", `🔴 ${counts.red}`],
              ["yellow", `🟡 ${counts.yellow}`],
              ["green", `🟢 ${counts.green}`],
            ].map(([id, label]) => (
              <button key={id} type="button" className={filter === id ? "is-active" : ""} onClick={() => setFilter(id)}>
                {label}
              </button>
            ))}
            <select value={agent} onChange={(e) => setAgent(e.target.value)} aria-label="Agent">
              <option value="all">All agents</option>
              {agents.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>
          <label className="notif-pref">
            <input type="checkbox" checked={popAll} onChange={(e) => setPopAll(e.target.checked)} /> Pop up every
            notification (not only red / critical)
          </label>
          <div className="notif-list">
            {rows.length === 0 ? <p className="hint">No notifications yet.</p> : null}
            {rows.map((m) => (
              <div key={m.id} className={`notif-item sev-${m.severity} ${m.id > readUpTo ? "is-unread" : ""}`}>
                <div className="notif-item-head">
                  <b>{m.title}</b>
                  <span className="muted">{formatTimeIST(m.at)}</span>
                </div>
                <div className="notif-item-text">{m.text}</div>
                <div className="notif-item-meta">
                  {m.from_name} → {(m.to_names || []).join(", ")}
                </div>
              </div>
            ))}
          </div>
          <footer className="notif-legend">
            <span>🟢 normal / done</span>
            <span>🟡 be ready / action</span>
            <span>🔴 critical / sudden rise</span>
          </footer>
        </aside>
      ) : null}
    </>,
    document.body
  );
}

export default memo(NotificationCenter);
