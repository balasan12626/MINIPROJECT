import { memo, useEffect, useMemo, useRef, useState } from "react";
import { confirmRescue } from "../services/api.js";
import { collapseFeed } from "../utils/feed.js";
import { formatTimeIST } from "../utils/time.js";
import DataSourceBadge from "./DataSourceBadge.jsx";

const FEED_CAP = 50;
const turnKey = (t) => `${t.from}|${t.to}|${t.text}`;

/* Grounding: a turn may quote a probability that was true when it was
 * generated but is not the current simulation state. Decimal percentages
 * ("62.3%") and non-round ones are how the backend prints model outputs;
 * round multiples of 5 are usually policy thresholds ("≥ 60%"), which are not
 * state values and are left alone. */
const PCT_RE = /(\d{1,3}(?:\.\d+)?)\s?%/g;

function groundText(text, known) {
  const s = String(text ?? "");
  if (!known.length) return s;
  const parts = [];
  let last = 0;
  let m;
  PCT_RE.lastIndex = 0;
  while ((m = PCT_RE.exec(s))) {
    const v = Number(m[1]);
    const looksLikeState = m[1].includes(".") || v % 5 !== 0;
    if (!looksLikeState || known.some((k) => Math.abs(k - v) <= 1.5)) continue;
    parts.push(s.slice(last, m.index));
    parts.push(
      <span key={m.index} className="talk-stale-num" title="This number is not in the current simulation state">
        <s>{m[0]}</s> <em className="muted">(not current)</em>
      </span>
    );
    last = m.index + m[0].length;
  }
  if (!parts.length) return s;
  parts.push(s.slice(last));
  return parts;
}

const TalkRow = memo(function TalkRow({ turn, count, side, known }) {
  const body = useMemo(() => groundText(turn.text, known), [turn.text, known]);
  return (
    <div className={`talk-bubble ${side}`}>
      <div className="talk-meta">
        {turn.from} → {turn.to}
        {count > 1 ? <b className="feed-count"> ×{count}</b> : null}
      </div>
      <div>{body}</div>
    </div>
  );
});

const pctOf = (p) => (p == null || Number.isNaN(Number(p)) ? null : Math.round(Number(p) * 1000) / 10);
const fmtPct = (p) => (p == null ? "—" : `${p.toFixed(1)}%`);

/** Grounding strip: the values the conversation is about, read straight from
 * the current simulation state (not from the generated text). */
function GroundingStrip({ grounding, conversationP }) {
  if (!grounding) return null;
  const nowP = pctOf(grounding.probability);
  const talkP = pctOf(conversationP);
  const drift = nowP != null && talkP != null && Math.abs(nowP - talkP) > 1;
  return (
    <div className="talk-grounding hint" style={{ marginBottom: 8 }}>
      <b>Current state</b> · flood probability {fmtPct(nowP)}
      {grounding.river_m != null ? ` · river ${Number(grounding.river_m).toFixed(2)} m` : ""}
      {grounding.rainfall_mm != null ? ` · rain ${Number(grounding.rainfall_mm).toFixed(1)} mm` : ""}
      {grounding.sim_time_sec != null ? ` · sim t=${Math.round(grounding.sim_time_sec)} s` : ""}
      {grounding.status ? ` · run ${grounding.status}` : ""}
      {drift ? (
        <div>
          Conversation was generated at P={fmtPct(talkP)}; the current state is P={fmtPct(nowP)}. Numbers that are not in
          the current state are struck through.
        </div>
      ) : null}
    </div>
  );
}

function AgentTalk({ conversation, title = "LIVE AGENT CONVERSATION", onTalked, voiceEnabled = false, grounding = null }) {
  const logRef = useRef(null);
  const spokenRef = useRef("");
  const history = useMemo(
    () => (conversation?.history?.length ? conversation.history : conversation?.turns || []),
    [conversation?.history, conversation?.turns]
  );
  const rows = useMemo(() => collapseFeed(history, { key: turnKey, cap: FEED_CAP }), [history]);
  const check = conversation?.rescue_check;
  const [showAsk, setShowAsk] = useState(false);
  const [busy, setBusy] = useState(false);

  // Percentages that exist in the current state (flood P + the model outputs
  // the backend quotes in the admin band).
  const known = useMemo(() => {
    if (!grounding) return [];
    return [grounding.probability, ...(grounding.extraProbabilities || [])].map(pctOf).filter((v) => v != null);
  }, [grounding]);

  useEffect(() => {
    const box = logRef.current;
    if (!box) return;
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    if (nearBottom) box.scrollTop = box.scrollHeight;
  }, [rows.length, conversation?.timestamp]);

  useEffect(() => {
    if (typeof window === "undefined" || !window.speechSynthesis) return undefined;
    if (!voiceEnabled) return undefined;
    if (!history.length) return undefined;
    const lastTwo = history.slice(-2);
    const key = lastTwo.map((t) => `${t.from}:${t.text}`).join("|");
    if (!key || key === spokenRef.current) return undefined;
    spokenRef.current = key;
    window.speechSynthesis.cancel();
    lastTwo.forEach((turn, i) => {
      const u = new SpeechSynthesisUtterance(`${turn.from}. ${turn.text}`);
      u.rate = 1.05;
      u.pitch = i % 2 ? 1.05 : 0.95;
      window.speechSynthesis.speak(u);
    });
    return () => window.speechSynthesis.cancel();
  }, [history, voiceEnabled]);

  useEffect(() => {
    if (check?.status !== "pending" || check?.answered) {
      setShowAsk(false);
      return undefined;
    }
    const due = check.ask_after_sec ?? 8;
    const started = check.dispatched_at ? new Date(check.dispatched_at).getTime() : Date.now();
    const wait = Math.max(0, due * 1000 - (Date.now() - started));
    const id = setTimeout(() => setShowAsk(true), wait);
    return () => clearTimeout(id);
  }, [check?.status, check?.dispatched_at, check?.ask_after_sec, check?.answered]);

  async function answer(rescued) {
    setBusy(true);
    try {
      const res = await confirmRescue(rescued, conversation?.mode || "simulation");
      onTalked?.(res);
      setShowAsk(false);
    } finally {
      setBusy(false);
    }
  }

  if (!conversation?.available && !history.length) {
    return (
      <div className="panel">
        <h2>{title}</h2>
        <div className="muted">{conversation?.message || "Agents talk here when flood probability updates."}</div>
      </div>
    );
  }

  return (
    <div className="panel">
      <h2>{title}</h2>
      <div className="status-row" style={{ marginBottom: 10 }}>
        <span className={`badge ${conversation.band === "auto" ? "crit" : conversation.band === "admin" ? "warn" : "live"}`}>
          {(conversation.band || "—").toUpperCase()}
        </span>
        <span className="badge">{conversation.policy_hint || "threshold talk"}</span>
        {conversation.source === "groq" ? (
          <DataSourceBadge kind="LLM" title={conversation.model || "Groq"} />
        ) : (
          <DataSourceBadge
            kind="FALLBACK"
            title={conversation.llm_error ? `Scripted fallback (${conversation.llm_error})` : "Scripted fallback"}
          />
        )}
        <span className="muted">Source: {conversation.source === "groq" ? "LLM" : "SCRIPTED FALLBACK"}</span>
        {conversation.timestamp ? <span className="muted">Updated {formatTimeIST(conversation.timestamp)}</span> : null}
        {(conversation.speakers || []).length ? <span className="muted">{conversation.speakers.join(" ↔ ")}</span> : null}
      </div>
      <GroundingStrip grounding={grounding} conversationP={conversation.flood_probability} />
      {conversation.llm_error ? (
        <div className="hint talk-llm-note" style={{ marginBottom: 6, opacity: 0.8 }}>
          Note: {String(conversation.llm_error)}
        </div>
      ) : null}
      {conversation.dispatch?.called ? (
        <div className="muted" style={{ marginBottom: 8 }}>
          Auto-called: {(conversation.dispatch.teams || []).map((t) => `${t.name || t.team_id} → ${t.place}`).join(" · ")}
        </div>
      ) : null}
      {conversation.spike?.sudden ? (
        <div className="badge warn" style={{ marginBottom: 8 }}>
          Monitor: {(conversation.spike.alerts || []).map((a) => `${a.label} ${a.from_value}→${a.to_value} in ${a.seconds}s`).join(" · ") || `${conversation.spike.seconds_since_last}s spike`}
        </div>
      ) : null}
      {history.length > rows.reduce((n, r) => n + r.count, 0) ? (
        <div className="hint">Showing the latest {FEED_CAP} turns.</div>
      ) : null}
      <div className="talk-log" ref={logRef}>
        {rows.map((r, i) => (
          <TalkRow key={`${i}-${r.key}`} turn={r.last} count={r.count} side={i % 2 ? "right" : "left"} known={known} />
        ))}
      </div>
      {showAsk && check?.status === "pending" ? (
        <div className="rescue-ask">
          <p>Rescue, ambulance and disaster teams are on scene. Were people rescued?</p>
          <div className="actions">
            <button className="primary" disabled={busy} onClick={() => answer(true)}>Yes — rescued</button>
            <button className="danger" disabled={busy} onClick={() => answer(false)}>No — still missing</button>
          </div>
        </div>
      ) : null}
      {check?.status === "answered" ? (
        <div className="muted" style={{ marginTop: 8 }}>Operator answer: {check.answered === "yes" ? "YES — rescued" : "NO — continue search"}</div>
      ) : null}
    </div>
  );
}

export default memo(AgentTalk);
