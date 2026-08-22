import { useEffect, useRef, useState } from "react";
import { confirmRescue } from "../services/api.js";

export default function AgentTalk({ conversation, title = "LIVE AGENT CONVERSATION", onTalked, voiceEnabled = false }) {
  const endRef = useRef(null);
  const logRef = useRef(null);
  const spokenRef = useRef("");
  const history = conversation?.history?.length ? conversation.history : conversation?.turns || [];
  const check = conversation?.rescue_check;
  const [showAsk, setShowAsk] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const box = logRef.current;
    if (!box) return;
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    if (nearBottom) box.scrollTop = box.scrollHeight;
  }, [history.length, conversation?.timestamp]);

  useEffect(() => {
    if (typeof window === "undefined" || !window.speechSynthesis) return;
    if (!voiceEnabled) {
      window.speechSynthesis.cancel();
      return;
    }
    if (!history.length) return;
    const lastTwo = history.slice(-2);
    const key = lastTwo.map((t) => `${t.from}:${t.text}`).join("|");
    if (!key || key === spokenRef.current) return;
    spokenRef.current = key;
    window.speechSynthesis.cancel();
    lastTwo.forEach((turn, i) => {
      const u = new SpeechSynthesisUtterance(`${turn.from}. ${turn.text}`);
      u.rate = 1.05;
      u.pitch = i % 2 ? 1.05 : 0.95;
      window.speechSynthesis.speak(u);
    });
    return () => window.speechSynthesis.cancel();
  }, [history.length, voiceEnabled, conversation?.timestamp]);

  useEffect(() => {
    if (check?.status !== "pending" || check?.answered) {
      setShowAsk(false);
      return;
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
        <span className="muted">{conversation.source === "groq" ? "LLM radio" : conversation.llm_error ? `fallback (${conversation.llm_error})` : "scripted fallback"}</span>
        {(conversation.speakers || []).length ? <span className="muted">{conversation.speakers.join(" ↔ ")}</span> : null}
      </div>
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
      <div className="talk-log" ref={logRef}>
        {history.map((turn, i) => (
          <div className={`talk-bubble ${i % 2 ? "right" : "left"}`} key={`${turn.from}-${i}`}>
            <div className="talk-meta">{turn.from} → {turn.to}</div>
            <div>{turn.text}</div>
          </div>
        ))}
        <div ref={endRef} />
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
