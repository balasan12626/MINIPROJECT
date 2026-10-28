import { memo, useEffect, useRef, useState } from "react";
import PdfDownloadButton from "../PdfDownloadButton.jsx";
import DecisionCard from "../rescue/DecisionCard.jsx";
import { askAi, fetchAiSuggest, sosPhotoUrl } from "../../services/api.js";
import { formatTimeIST } from "../../utils/time.js";

const BASE_SUGGESTIONS = [
  "How many ambulances are left?",
  "How many shelter seats are free?",
  "What is the full capacity of Mettur dam?",
  "What is happening in Mayur Vihar?",
  "What is the flood risk right now?",
  "What are the agents doing?",
];

function Kv({ k, v }) {
  if (v == null || v === "") return null;
  return (
    <div className="ai-kv">
      <span>{k}</span>
      <b>{v}</b>
    </div>
  );
}

function Card({ c }) {
  if (c.type === "person") {
    return (
      <div className="ai-card ai-person">
        <div className="ai-card-head">
          <b>
            👤 {c.name}
            {c.source === "citizen" ? <span title="SOS from the citizen phone page"> 📱</span> : null}
          </b>
          <PdfDownloadButton personName={c.name} label="Full PDF report" />
        </div>
        {c.photo_url ? (
          <a href={sosPhotoUrl(c.photo_url)} target="_blank" rel="noreferrer">
            <img className="sos-thumb" src={sosPhotoUrl(c.photo_url)} alt={`Photo sent by ${c.name}`} loading="lazy" />
          </a>
        ) : null}
        <div className="ai-kv-grid">
          <Kv k="Age / people" v={`${c.age ?? "—"} · ${c.people ?? 1} people`} />
          <Kv k="Priority" v={c.priority} />
          <Kv k="Status" v={c.stage_text} />
          <Kv k="Where" v={c.near ? `${c.near_km} km from ${c.near}` : null} />
          <Kv k="GPS" v={c.lat != null ? `${c.lat}, ${c.lon}` : null} />
          <Kv k="Water" v={c.water} />
          <Kv k="Unit" v={c.unit ? `${c.unit} (${c.unit_role}) from ${c.unit_from}` : null} />
          <Kv k="Driver accepted" v={c.driver_accepted} />
          <Kv k="Shelter" v={c.shelter} />
          <Kv k="Route to them" v={c.leg1?.km != null ? `${c.leg1.km} km · ${c.leg1.min} min` : null} />
          <Kv k="Route to shelter" v={c.leg2?.km != null ? `${c.leg2.km} km · ${c.leg2.min} min` : null} />
          <Kv k="Waiting because" v={c.stage === "queued" ? c.wait_reason : null} />
        </div>
        <DecisionCard d={c.decision} compact />
        {Object.keys(c.times || {}).length ? (
          <div className="ai-times">
            {Object.entries(c.times).map(([k, v]) => (
              <span key={k}>
                {k.replaceAll("_", " ")} <b>{v}</b>
              </span>
            ))}
          </div>
        ) : null}
      </div>
    );
  }
  if (c.type === "dam") {
    return (
      <div className="ai-card">
        <div className="ai-card-head">
          <b>🏞️ {c.name}</b>
          <span className="muted">
            {c.river} · {c.state}
          </span>
        </div>
        <div className="ai-kv-grid">
          <Kv k="Full capacity" v={c.gauge_full_ft ? `${c.gauge_full_ft} ft (gauge) · ${c.frl_m} m MSL` : `${c.frl_m} m MSL`} />
          <Kv k="Live capacity" v={c.live_capacity_mcm != null ? `${c.live_capacity_mcm} MCM · ${c.live_capacity_tmc} TMC` : null} />
          <Kv k="Level now" v={c.level_ft != null ? `${c.level_ft} ft · ${c.level_m} m` : `${c.level_m} m MSL`} />
          <Kv k="Filled" v={c.fill_pct != null ? `${c.fill_pct}% (${c.status})` : null} />
          <Kv k="Dead storage" v={c.dead_m != null ? `${c.dead_m} m MSL` : null} />
          <Kv k="Downstream" v={c.downstream} />
        </div>
      </div>
    );
  }
  if (c.type === "fleet") {
    return (
      <div className="ai-card">
        <div className="ai-card-head">
          <b>🚑 Ambulances</b>
          <span className="badge live">
            {c.ambulances_free}/{c.ambulances_total} free
          </span>
        </div>
        {c.busy?.length ? (
          <ul className="ai-list">
            {c.busy.map((a) => (
              <li key={a.name}>
                {a.name} → {a.job?.citizen_name} ({a.job?.stage})
              </li>
            ))}
          </ul>
        ) : (
          <p className="hint">No ambulance on a job.</p>
        )}
        {c.waiting?.length ? <p className="error-text">{c.waiting.length} SOS waiting for an ambulance.</p> : null}
      </div>
    );
  }
  if (c.type === "shelters") {
    return (
      <div className="ai-card">
        <div className="ai-card-head">
          <b>🏠 Shelters</b>
          <span className="badge live">{Number(c.seats_free).toLocaleString("en-IN")} seats free</span>
        </div>
        <ul className="ai-list">
          {(c.items || []).map((s) => (
            <li key={s.name}>
              {s.name}: <b>{s.seats_left}</b> of {s.capacity} free
              {s.allocated_this_run ? ` · +${s.allocated_this_run} this run` : ""}
            </li>
          ))}
        </ul>
      </div>
    );
  }
  if (c.type === "summary") {
    return (
      <div className="ai-card">
        <div className="ai-card-head">
          <b>🌊 Situation</b>
          <span className="muted">{c.run_status}</span>
        </div>
        <div className="ai-kv-grid">
          <Kv k="Flood probability" v={c.probability_pct != null ? `${c.probability_pct}%` : null} />
          <Kv k="Response" v={c.tier} />
          <Kv k="Rain" v={c.rain_mm != null ? `${c.rain_mm} mm` : null} />
          <Kv k="SOS" v={`${c.sos} · ${c.by_stage?.rescued ?? 0} safe · ${c.by_stage?.queued ?? 0} waiting`} />
        </div>
      </div>
    );
  }
  return null;
}

/** AI tab: ask anything about people, places, dams, ambulances, shelters. */
function AiAssistant() {
  const [chat, setChat] = useState([]);
  const [names, setNames] = useState([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [chat, busy]);

  // Suggestion chips use real names from the current run (refreshed after each answer).
  useEffect(() => {
    let alive = true;
    fetchAiSuggest().then((r) => alive && Array.isArray(r?.people) && setNames(r.people.filter(Boolean)));
    return () => {
      alive = false;
    };
  }, [chat.length]);

  async function ask(text) {
    const question = (text ?? q).trim();
    if (!question || busy) return;
    setQ("");
    const history = chat.map((m) => ({ role: m.role, text: m.role === "user" ? m.text : m.answer }));
    setChat((c) => [...c, { role: "user", text: question, at: new Date().toISOString() }]);
    setBusy(true);
    try {
      const res = await askAi(question, history);
      setChat((c) => [...c, { role: "assistant", ...res }]);
    } catch (e) {
      setChat((c) => [...c, { role: "assistant", answer: `Could not reach the assistant: ${e?.message || "error"}`, source: "error" }]);
    } finally {
      setBusy(false);
    }
  }

  const suggestions = [...(names.length ? [`Give me the full report of ${names[0]}`, `Where is ${names[Math.min(1, names.length - 1)]}?`] : []), ...BASE_SUGGESTIONS];

  return (
    <section className="panel ai-panel" aria-label="AI assistant">
      <div className="panel-head">
        <h3>🤖 AI assistant — ask about people, places, dams, ambulances, shelters</h3>
        {chat.length ? (
          <button type="button" className="link-btn" onClick={() => setChat([])}>
            Clear chat
          </button>
        ) : null}
      </div>
      <p className="hint">
        Answers come only from the live simulation and the dam registry. You can ask several questions at once — separate
        them with “?”. Follow-ups like “where is she now?” use the last person you asked about.
      </p>
      <div className="ai-chat">
        {chat.length === 0 ? (
          <div className="ai-empty">
            <span aria-hidden>💬</span>
            <p>Try one of these:</p>
          </div>
        ) : null}
        {chat.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="ai-msg ai-user">
              <div className="ai-bubble">{m.text}</div>
            </div>
          ) : (
            <div key={i} className="ai-msg ai-bot">
              <div className="ai-bubble">
                <div className="ai-answer">{m.answer}</div>
                <div className="ai-meta">
                  <span className={`badge ${m.source === "groq" ? "live" : m.source === "error" ? "crit" : "sim"}`}>
                    {m.source === "groq" ? `AI · grounded (${m.model})` : m.source === "error" ? "error" : "facts from the live state"}
                  </span>
                  {m.asked_at ? <span className="muted">{formatTimeIST(m.asked_at)}</span> : null}
                </div>
                {m.cards?.length ? (
                  <div className="ai-cards">
                    {m.cards.map((c, j) => (
                      <Card key={j} c={c} />
                    ))}
                  </div>
                ) : null}
                {m.facts?.length ? (
                  <details className="ai-facts">
                    <summary>Facts used ({m.facts.length})</summary>
                    <ul>
                      {m.facts.map((f, j) => (
                        <li key={j}>{f}</li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </div>
            </div>
          )
        )}
        {busy ? (
          <div className="ai-msg ai-bot">
            <div className="ai-bubble ai-typing">
              <i />
              <i />
              <i />
            </div>
          </div>
        ) : null}
        <div ref={endRef} />
      </div>
      <div className="ai-suggest">
        {suggestions.map((s) => (
          <button key={s} type="button" disabled={busy} onClick={() => ask(s)}>
            {s}
          </button>
        ))}
      </div>
      <form
        className="ai-input"
        onSubmit={(e) => {
          e.preventDefault();
          ask();
        }}
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="e.g. Where is Priya Sharma? How many ambulances are left?"
          aria-label="Ask the AI assistant"
        />
        <button type="submit" className="primary" disabled={busy || !q.trim()}>
          Ask
        </button>
      </form>
    </section>
  );
}

export default memo(AiAssistant);
