import { useEffect, useRef, useState } from "react";
import { startVoiceAgent, voiceAgentTurn, fetchVoiceAgentStatus } from "../services/api.js";

/**
 * Tamil Voice SOS — asks ONLY name, then auto-assigns ambulance/team + shelter via GPS defaults.
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
        setError(st?.message || "GEMINI_API_KEY அமைக்கப்படவில்லை");
        return;
      }

      // Capture GPS silently — agent will not ask for it
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
        speakTamil(start.reply, () => {
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

  function pickTamilVoice() {
    const voices = window.speechSynthesis?.getVoices?.() || [];
    return (
      voices.find((v) => /ta(-|_)IN/i.test(v.lang) || /tamil/i.test(v.name)) ||
      voices.find((v) => String(v.lang || "").toLowerCase().startsWith("ta")) ||
      null
    );
  }

  function speakTamil(text, onEnd) {
    if (typeof window === "undefined" || !window.speechSynthesis) {
      onEnd?.();
      return;
    }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ta-IN";
    u.rate = 0.95;
    const voice = pickTamilVoice();
    if (voice) u.voice = voice;
    u.onend = () => onEnd?.();
    u.onerror = () => onEnd?.();
    // voices may load async
    if (!voice && window.speechSynthesis.getVoices().length === 0) {
      window.speechSynthesis.onvoiceschanged = () => {
        const v = pickTamilVoice();
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
      setError("மைக் ஆதரவு இல்லை — Chrome பயன்படுத்தவும், அல்லது கீழே தட்டச்சு செய்யவும்.");
      setPhase("idle");
      return;
    }
    stopListening();
    const recog = new SR();
    recogRef.current = recog;
    recog.lang = "ta-IN";
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
      setError(err.message || "மைக் தொடங்கவில்லை");
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
      const reply = res.reply || "தயவு செய்து உங்கள் பெயரைச் சொல்லுங்கள்.";
      setLines((prev) => [...prev, { role: "agent", text: reply }]);
      if (res.assignment) {
        setAssignment(res.assignment);
        setPhase("done");
        speakTamil(reply, () => {});
        if (res.sim) onSubmitted?.(res.sim);
      } else {
        setPhase("speaking");
        speakTamil(reply, () => startListening());
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
    <div className="voice-agent-overlay" role="dialog" aria-modal="true" aria-label="தமிழ் குரல் முகவர்">
      <div className="voice-agent-card">
        <div className="status-row">
          <h2 style={{ margin: 0 }}>தமிழ் குரல் முகவர் — பெயர் மட்டும்</h2>
          <button type="button" onClick={onClose}>மூடு</button>
        </div>
        <p className="hint">
          Gemini · தமிழ் · பெயர் மட்டும் கேட்கும் · GPS தானாக எடுக்கப்படும் · ஆம்புலன்ஸ்/தங்குமிடம் தானியங்கி ஒதுக்கீடு
          {status?.model ? ` · ${status.model}` : ""}
        </p>

        <div className={`voice-orb ${phase}`}>
          <span className="voice-orb-ring" />
          <b>
            {phase === "listening"
              ? "கேட்கிறது…"
              : phase === "thinking"
                ? "முகவர் யோசிக்கிறார்…"
                : phase === "speaking"
                  ? "முகவர் பேசுகிறார்…"
                  : phase === "done"
                    ? "SOS பதிவு ஆனது"
                    : "தயார்"}
          </b>
        </div>

        <div className="voice-actions">
          <button type="button" className="primary" disabled={phase === "thinking" || phase === "done"} onClick={startListening}>
            {phase === "listening" ? "மைக் இயக்கம்" : "பேசுங்கள்"}
          </button>
          <button
            type="button"
            onClick={() => {
              const t = window.prompt("உங்கள் பெயர் (தமிழ்/ஆங்கிலம்)");
              if (t) handleUserText(t.trim());
            }}
          >
            பெயர் தட்டச்சு
          </button>
        </div>

        {error ? <div className="unavailable">{error}</div> : null}

        <div className="grid-3" style={{ marginTop: 12 }}>
          <div className="metric"><span>பெயர்</span><b>{draft.citizen_name || assignment?.citizen_name || "—"}</b></div>
          <div className="metric"><span>GPS lat</span><b>{draft.lat ?? assignment?.lat ?? "—"}</b></div>
          <div className="metric"><span>GPS lon</span><b>{draft.lon ?? assignment?.lon ?? "—"}</b></div>
          <div className="metric"><span>நபர்கள்</span><b>{draft.people ?? assignment?.people ?? 2}</b></div>
          <div className="metric"><span>நீர்</span><b>{draft.water_level_note || assignment?.water_level_note || "—"}</b></div>
          <div className="metric"><span>நிலை</span><b>{assignment?.ops_status || phase}</b></div>
        </div>

        {assignment ? (
          <div className="voice-assign">
            <h3>ஒதுக்கீடு (நேரலை)</h3>
            <div className="metric"><span>ஆம்புலன்ஸ் / குழு</span><b>{assignment.ambulance_or_team}</b></div>
            <div className="metric"><span>தங்குமிடம்</span><b>{assignment.shelter_name} ({assignment.shelter_id})</b></div>
            <div className="metric"><span>தூரம்</span><b>{assignment.shelter_distance_km} கி.மீ</b></div>
            <div className="metric"><span>Cluster</span><b>{assignment.cluster_id || "—"}</b></div>
            <p className="hint">{assignment.message}</p>
          </div>
        ) : null}

        <div className="voice-transcript">
          {lines.map((l, i) => (
            <div key={i} className={`voice-line ${l.role}`}>
              <b>{l.role === "agent" ? "முகவர்" : "நீங்கள்"}</b>
              <span>{l.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
