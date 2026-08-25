export const FEATURE_DEFS = [
  { key: "explainable_ai", label: "Explainable AI (SHAP / SHAP-style)" },
  { key: "agent_talk", label: "Agent radio (text)" },
  { key: "vulnerable_first", label: "Vulnerable-first order" },
  { key: "model_disagreement", label: "RF vs XGBoost" },
  { key: "disagreement_debate", label: "Disagreement debate" },
  { key: "counterfactual", label: "Counterfactual rain" },
  { key: "contact_log", label: "Contact log" },
  { key: "citizen_status_board", label: "Citizen status board" },
  { key: "voice_radio", label: "Voice radio (TTS)" },
  { key: "ask_agent", label: "Ask the agent" },
  { key: "after_action_summary", label: "After-action summary" },
  { key: "run_replay", label: "Run replay" },
  { key: "sos_heatmap", label: "SOS heatmap" },
  { key: "person_card", label: "Pin person card" },
  { key: "team_paths", label: "Team path animation" },
  { key: "before_after_radius", label: "Before/after flood radius" },
  { key: "theme_toggle", label: "Dark / light theme" },
  { key: "shelter_board", label: "Shelter capacity board" },
  { key: "eta_board", label: "ETA per citizen" },
  { key: "medical_triage", label: "Medical triage tags" },
  { key: "bilingual_radio", label: "English radio (TTS)" },
  { key: "scenario_compare", label: "Scenario compare" },
  { key: "confidence_band", label: "Confidence band" },
  { key: "false_alarm_drill", label: "False-alarm drill" },
  { key: "road_blockage_impact", label: "Road blockage impact" },
  { key: "operator_checklist", label: "Operator checklist" },
  { key: "jury_mode", label: "Jury mode" },
  { key: "transfer_warning", label: "Transfer warning" },
  { key: "api_health", label: "API health strip" },
  { key: "latency_meter", label: "Latency meter" },
  { key: "whatif_rain", label: "What-if rainfall" },
  { key: "algorithm_arena", label: "Algorithm Arena (paths + policy)" },
];

/** Core panels ON; extras OFF until user turns them on (avoids stacked clutter). */
const CORE_ON = new Set([
  "explainable_ai",
  "agent_talk",
  "vulnerable_first",
  "model_disagreement",
  "contact_log",
  "sos_heatmap",
  "person_card",
  "shelter_board",
  "eta_board",
  "after_action_summary",
  "theme_toggle",
  "ask_agent",
  "citizen_status_board",
  "algorithm_arena",
]);

export const DEFAULT_FEATURES = Object.fromEntries(
  FEATURE_DEFS.map((f) => [f.key, CORE_ON.has(f.key)])
);

export default function FeatureToggles({ features, onChange, title = "FEATURES — ON shows below · OFF hides" }) {
  const feats = { ...DEFAULT_FEATURES, ...(features || {}) };

  function setOne(key, on) {
    onChange({ ...feats, [key]: on });
  }

  function showAll() {
    onChange(Object.fromEntries(FEATURE_DEFS.map((f) => [f.key, f.key !== "voice_radio"])));
  }

  function coreOnly() {
    onChange({ ...DEFAULT_FEATURES });
  }

  function allOff() {
    onChange(Object.fromEntries(FEATURE_DEFS.map((f) => [f.key, false])));
  }

  return (
    <div className="panel feature-panel">
      <h2>{title}</h2>
      <p className="hint">Use the radio for each feature. ON = show that output after Run. OFF = do not show it.</p>
      <div className="actions" style={{ marginBottom: 10 }}>
        <button type="button" className="primary" onClick={coreOnly}>Core ON</button>
        <button type="button" onClick={showAll}>All ON</button>
        <button type="button" className="danger" onClick={allOff}>All OFF</button>
      </div>
      <div className="feature-grid">
        {FEATURE_DEFS.map((f) => {
          const on = Boolean(feats[f.key]);
          return (
            <div className={`feature-card ${on ? "on" : "off"}`} key={f.key}>
              <span className="feature-name">{f.label}</span>
              <div className="toggle-pair" role="radiogroup" aria-label={f.label}>
                <label className={`radio-pill ${on ? "active" : ""}`}>
                  <input
                    type="radio"
                    name={`feat-${f.key}`}
                    checked={on}
                    onChange={() => setOne(f.key, true)}
                  />
                  ON
                </label>
                <label className={`radio-pill ${!on ? "active off" : ""}`}>
                  <input
                    type="radio"
                    name={`feat-${f.key}`}
                    checked={!on}
                    onChange={() => setOne(f.key, false)}
                  />
                  OFF
                </label>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
