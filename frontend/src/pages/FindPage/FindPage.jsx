import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { SosStatus } from "../CitizenSos/CitizenSos.jsx";
import "../DriverApp/driverApp.css";

const TICKET = /^[0-9a-f]{32}$/;

/** F31 — family lookup (/find). Only the SOS ticket (shared by the person who
 * sent the SOS) shows that person's status and, once safe, which shelter or
 * hospital they reached. No search by name, phone or face; nothing public. */
export default function FindPage() {
  const [params] = useSearchParams();
  const fromLink = (params.get("t") || "").trim().toLowerCase();
  const [draft, setDraft] = useState(fromLink);
  const [ticket, setTicket] = useState(TICKET.test(fromLink) ? fromLink : "");
  const [error, setError] = useState("");

  function submit(e) {
    e.preventDefault();
    const t = draft.trim().toLowerCase().replace(/^.*[?&]t=/, "");
    if (!TICKET.test(t)) {
      setError("That is not an SOS ticket. Paste the link or the 32-character ticket you were sent.");
      return;
    }
    setError("");
    setTicket(t);
  }

  return (
    <div className="drv-page">
      <header className="drv-head">
        <div>
          <p className="drv-kicker">AQUASENTINEL · FIND FAMILY</p>
          <h1>Where is my family member?</h1>
        </div>
      </header>
      <p className="drv-banner is-ok">
        Only people with the SOS ticket can see this. There is no search by name, phone number or photo.
      </p>
      <form className="drv-card" onSubmit={submit}>
        <label className="drv-field">
          SOS ticket or link
          <input value={draft} onChange={(e) => setDraft(e.target.value)} autoComplete="off" spellCheck="false" />
        </label>
        {error ? <p className="drv-banner is-error">{error}</p> : null}
        <button type="submit" className="drv-btn accept">
          Show status
        </button>
      </form>
      {ticket ? <SosStatus key={ticket} ticket={ticket} /> : null}
    </div>
  );
}
