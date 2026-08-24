import { useEffect, useRef, useState } from "react";
import { startVoiceAgent, voiceAgentTurn, fetchVoiceAgentStatus } from "../services/api.js";

/**
 * English Voice SOS — asks ONLY name, then auto-assigns ambulance/team + shelter via GPS defaults.
 */
export default function VoiceSosAgent({ open, onClose, onSubmitted, onDraft }) {
  const [status, setStatus] = useState(null);
  const [phase, setPhase] = useState("idle");
  const [lines, setLines] = useState([]);
  const [history, setHistory] = useState([]);
  const [draft, setDraft] = useState({});
  const [assignment, setAssignment] = useState(null);
  const [error, setError] = useState("");
  const [ctx, setCtx] = useState({ lat: 28.651, lon: 77.262, people: 2, water_level_note: "knee-deep" });
  const recogRef = useRef(null);
  const listeningRef = useRef(false);
  const historyRef = useRef([]);
  const ctxRef = useRef(ctx);
  const busyRef = useRef(false);

  useEffect(() => {
    historyRef.current = history;
  }, [history]);
  useEffect(() => {
    ctxRef.current = ctx;
  }, [ctx]);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;

    async function boot() {
      const st = await fetchVoiceAgentStatus();
      if (cancelled) return;
      setStatus(st);
      if (!st?.available) {
        setError(st?.message || "GEMINI_API_KEY is not configured");
        return;
      }

      const gps = await new Promise((resolve) => {
        if (!navigator.geolocation) return resolve(null);
        navigator.geolocation.getCurrentPosition(
          (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
          () => resolve(null),
          { enableHighAccuracy: true, timeout: 6000 }
        );
      });
      const nextCtx = {
        lat: gps?.lat ?? 28.651,
        lon: gps?.lon ?? 77.262,
        people: 2,
        water_level_note: "knee-deep",
      };
      if (cancelled) return;
      setCtx(nextCtx);
      ctxRef.current = nextCtx;
      onDraft?.(nextCtx);

      try {
        const start = await startVoiceAgent(nextCtx);
        if (cancelled) return;
        setHistory(start.history || []);
        setDraft(start.draft || nextCtx);
        setLines([{ role: "agent", text: start.reply }]);
        setPhase("speaking");
        speakEnglish(start.reply, () => {
          if (!cancelled) startListening();
        });
      } catch (err) {
        if (!cancelled) setError(err.message || String(err));
      }
    }

    boot();
    return () => {
      cancelled = true;
      stopListening();
      if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function pickEnglishVoice() {
    const voices = window.speechSynthesis?.getVoices?.() || [];
    return (
      voices.find((v) => /en(-|_)IN/i.test(v.lang)) ||
      voices.find((v) => /en(-|_)GB/i.test(v.lang)) ||
      voices.find((v) => /en(-|_)US/i.test(v.lang)) ||
      voices.find((v) => String(v.lang || "").toLowerCase().startsWith("en")) ||
      null
    );
  }

  function speakEnglish(text, onEnd) {
    if (typeof window === "undefined" || !window.speechSynthesis) {
      onEnd?.();
      return;
    }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-IN";
    u.rate = 0.95;
    const voice = pickEnglishVoice();
    if (voice) u.voice = voice;
    u.onend = () => onEnd?.();
    u.onerror = () => onEnd?.();
    if (!voice && window.speechSynthesis.getVoices().length === 0) {
      window.speechSynthesis.onvoiceschanged = () => {
        const v = pickEnglishVoice();
        if (v) u.voice = v;
        window.speechSynthesis.speak(u);
      };
      return;
    }
    window.speechSynthesis.speak(u);
  }

  function stopListening() {
    listeningRef.current = false;
    try {
      recogRef.current?.stop();
    } catch {
      /* ignore */
    }
    recogRef.current = null;
  }

  function startListening() {
    const SR = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
    if (!SR) {
      setError("Microphone speech recognition is unavailable — use Chrome, or type your name below.");
      setPhase("idle");
      return;
    }
    stopListening();
    const recog = new SR();
    recogRef.current = recog;
    recog.lang = "en-IN";
    recog.continuous = false;
    recog.interimResults = true;
    listeningRef.current = true;
    setPhase("listening");

    recog.onresult = (ev) => {
      let finalText = "";
      for (let i = ev.resultIndex; i < ev.results.length; i += 1) {
        const chunk = ev.results[i][0].transcript;
        if (ev.results[i].isFinal) finalText += chunk;
      }
      if (finalText.trim()) {
        stopListening();
        handleUserText(finalText.trim());
      }
    };
    recog.onerror = () => {
      if (listeningRef.current) setPhase("idle");
    };
    recog.onend = () => {
      if (listeningRef.current) {
        try {
          recog.start();
        } catch {
          setPhase("idle");
        }
      }
    };
    try {
      recog.start();
    } catch (err) {
      setError(err.message || "Could not start microphone");
      setPhase("idle");
    }
  }

  async function handleUserText(text) {
    if (!text || busyRef.current) return;
    busyRef.current = true;
    setPhase("thinking");
    setLines((prev) => [...prev, { role: "you", text }]);
    try {
      const res = await voiceAgentTurn(text, historyRef.current, ctxRef.current);
      setHistory(res.history || []);
      if (res.draft) {
        setDraft(res.draft);
        onDraft?.(res.draft);
      }
      const reply = res.reply || "Please say your full name.";
      setLines((prev) => [...prev, { role: "agent", text: reply }]);
      if (res.assignment) {
        setAssignment(res.assignment);
        setPhase("done");
        speakEnglish(reply, () => {});
        if (res.sim) onSubmitted?.(res.sim);
      } else {
        setPhase("speaking");
        speakEnglish(reply, () => startListening());
      }
    } catch (err) {
      setError(err.message || String(err));
      setPhase("idle");
    } finally {
      busyRef.current = false;
    }
  }

  if (!open) return null;

  return (
    <div className="voice-agent-overlay" role="dialog" aria-modal="true" aria-label="English Voice Agent">
      <div className="voice-agent-card">
        <div className="status-row">
          <h2 style={{ margin: 0 }}>English Voice Agent — name only</h2>
          <button type="button" onClick={onClose}>Close</button>
        </div>
        <p className="hint">
          Gemini · English · asks for name only · GPS captured automatically · ambulance/shelter auto-assigned
          {status?.model ? ` · ${status.model}` : ""}
        </p>

        <div className={`voice-orb ${phase}`}>
          <span className="voice-orb-ring" />
          <b>
            {phase === "listening"
              ? "Listening…"
              : phase === "thinking"
                ? "Agent thinking…"
                : phase === "speaking"
                  ? "Agent speaking…"
                  : phase === "done"
                    ? "SOS registered"
                    : "Ready"}
          </b>
        </div>

        <div className="voice-actions">
          <button type="button" className="primary" disabled={phase === "thinking" || phase === "done"} onClick={startListening}>
            {phase === "listening" ? "Mic active" : "Speak"}
          </button>
          <button
            type="button"
            onClick={() => {
              const t = window.prompt("Your full name (English)");
              if (t) handleUserText(t.trim());
            }}
          >
            Type name
          </button>
        </div>

        {error ? <div className="unavailable">{error}</div> : null}

        <div className="grid-3" style={{ marginTop: 12 }}>
          <div className="metric"><span>Name</span><b>{draft.citizen_name || assignment?.citizen_name || "—"}</b></div>
          <div className="metric"><span>GPS lat</span><b>{draft.lat ?? assignment?.lat ?? "—"}</b></div>
          <div className="metric"><span>GPS lon</span><b>{draft.lon ?? assignment?.lon ?? "—"}</b></div>
          <div className="metric"><span>People</span><b>{draft.people ?? assignment?.people ?? 2}</b></div>
          <div className="metric"><span>Water</span><b>{draft.water_level_note || assignment?.water_level_note || "—"}</b></div>
          <div className="metric"><span>Status</span><b>{assignment?.ops_status || phase}</b></div>
        </div>

        {assignment ? (
          <div className="voice-assign">
            <h3>Assignment (live)</h3>
            <div className="metric"><span>Ambulance / team</span><b>{assignment.ambulance_or_team}</b></div>
            <div className="metric"><span>Shelter</span><b>{assignment.shelter_name} ({assignment.shelter_id})</b></div>
            <div className="metric"><span>Distance</span><b>{assignment.shelter_distance_km} km</b></div>
            <div className="metric"><span>Cluster</span><b>{assignment.cluster_id || "—"}</b></div>
            <p className="hint">{assignment.message}</p>
          </div>
        ) : null}

        <div className="voice-transcript">
          {lines.map((l, i) => (
            <div key={i} className={`voice-line ${l.role}`}>
              <b>{l.role === "agent" ? "Agent" : "You"}</b>
              <span>{l.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
