import { useState } from "react";
import { downloadSimPersonReport, downloadPersonReport } from "../services/api.js";

/**
 * Attractive Generate PDF control with loading overlay + micro-animations.
 * mode: "simulation" | "rescue"
 */
export default function PdfDownloadButton({
  personName,
  caseId,
  mode = "simulation",
  label = "Generate PDF",
  className = "",
}) {
  const [phase, setPhase] = useState("idle"); // idle | loading | done | error
  const [message, setMessage] = useState("");

  async function onClick(e) {
    e?.stopPropagation?.();
    if (phase === "loading") return;
    setPhase("loading");
    setMessage(`Building report for ${personName || caseId || "citizen"}…`);
    try {
      if (mode === "rescue") {
        await downloadPersonReport(caseId);
      } else {
        await downloadSimPersonReport(personName);
      }
      setPhase("done");
      setMessage("PDF ready — download started");
      window.setTimeout(() => {
        setPhase("idle");
        setMessage("");
      }, 1600);
    } catch (err) {
      setPhase("error");
      setMessage(err.message || "PDF failed");
      window.setTimeout(() => {
        setPhase("idle");
        setMessage("");
      }, 2800);
    }
  }

  const busy = phase === "loading";
  const btnClass = [
    "pdf-btn",
    phase === "loading" ? "is-loading" : "",
    phase === "done" ? "is-done" : "",
    phase === "error" ? "is-error" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <>
      <button type="button" className={btnClass} disabled={busy} onClick={onClick} title={label}>
        <span className="pdf-btn-glow" aria-hidden />
        {busy ? <span className="pdf-btn-spinner" aria-hidden /> : <span className="pdf-btn-icon" aria-hidden>PDF</span>}
        <span className="pdf-btn-label">
          {phase === "loading" ? "Generating…" : phase === "done" ? "Downloaded" : phase === "error" ? "Retry" : label}
        </span>
      </button>

      {phase === "loading" || phase === "done" || phase === "error" ? (
        <div className={`pdf-overlay ${phase}`} role="status" aria-live="polite">
          <div className="pdf-overlay-card">
            <div className="pdf-overlay-ring">
              {phase === "loading" ? <span className="pdf-overlay-spinner" /> : null}
              {phase === "done" ? <span className="pdf-overlay-check">✓</span> : null}
              {phase === "error" ? <span className="pdf-overlay-x">!</span> : null}
            </div>
            <h3>
              {phase === "loading" ? "Generating person PDF" : phase === "done" ? "Download started" : "Could not generate"}
            </h3>
            <p>{message}</p>
            {phase === "loading" ? (
              <div className="pdf-progress">
                <i />
              </div>
            ) : null}
            <ul className="pdf-overlay-steps">
              <li className={phase !== "idle" ? "on" : ""}>Citizen details</li>
              <li className={phase !== "idle" ? "on" : ""}>Rainfall · river · dam</li>
              <li className={phase !== "idle" ? "on" : ""}>Ambulance · shelter · cluster</li>
              <li className={phase === "done" ? "on" : ""}>Agent timeline → file</li>
            </ul>
          </div>
        </div>
      ) : null}
    </>
  );
}
