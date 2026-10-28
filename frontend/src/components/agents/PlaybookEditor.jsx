import { memo, useEffect, useState } from "react";
import { fetchPlaybook, savePlaybook } from "../../services/api.js";

const TRIGGERS = [
  ["ADMIN", "Below 50 %", "sev-green"],
  ["READY", "≥ 50 % CRITICAL", "sev-yellow"],
  ["FIELD", "≥ 75 % ALL ON FIELD", "sev-red"],
  ["SUDDEN", "Sudden rise", "sev-red"],
  ["ROAD_BLOCKED", "Road blocked", "sev-yellow"],
  ["SHELTER_CLOSED", "Shelter closed", "sev-yellow"],
];

/** Operator-editable playbook: what every agent does per tier and when the
 * flood picture jumps suddenly. Saved to the backend (PUT /api/simulation/
 * playbook); the agents quote these exact lines in their messages. */
function PlaybookEditor({ agents = [], tier }) {
  const [book, setBook] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchPlaybook().then((b) => alive && b?.actions && setBook(b));
    return () => {
      alive = false;
    };
  }, []);

  if (!book) return <div className="panel">Loading the agent playbook…</div>;

  const edit = (trig, agent, text) => {
    setBook((b) => ({ ...b, actions: { ...b.actions, [trig]: { ...b.actions[trig], [agent]: text } } }));
    setDirty(true);
    setMsg("");
  };
  const num = (key, v) => {
    setBook((b) => ({ ...b, [key]: v === "" ? "" : Number(v) }));
    setDirty(true);
  };

  async function save(body) {
    setBusy(true);
    setMsg("");
    try {
      const out = await savePlaybook(body);
      setBook(out);
      setDirty(false);
      setMsg(
        body.reset
          ? "Defaults restored."
          : out?.persisted
            ? "Saved — the agents use it from the next event, and it survives a backend restart."
            : "Saved for this backend session only (MongoDB is off) — the agents use it from the next event."
      );
    } catch (e) {
      setMsg(e?.message || "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel playbook">
      <div className="panel-head">
        <h3>Agent playbook — what every agent does (editable)</h3>
        <span className="fleet-summary">
          {dirty ? <span className="badge warn">Unsaved</span> : null}
          <button type="button" className="primary" disabled={busy || !dirty} onClick={() => save(book)}>
            Save playbook
          </button>
          <button type="button" disabled={busy} onClick={() => save({ reset: true })}>
            Reset defaults
          </button>
        </span>
      </div>
      <div className="playbook-thresholds">
        <label>
          Sudden rise: probability jump ≥
          <input
            type="number"
            min="1"
            max="100"
            value={book.sudden_rise_points}
            onChange={(e) => num("sudden_rise_points", e.target.value)}
          />
          points between ticks
        </label>
        <label>
          or rainfall jump ≥
          <input type="number" min="1" value={book.sudden_rain_mm} onChange={(e) => num("sudden_rain_mm", e.target.value)} />
          mm (or the Isolation-Forest card monitor fires)
        </label>
      </div>
      {msg ? <p className="hint">{msg}</p> : null}
      <div className="table-wrap">
        <table className="data-table playbook-table">
          <thead>
            <tr>
              <th>Agent</th>
              {TRIGGERS.map(([id, label, cls]) => (
                <th key={id} className={`${cls} ${tier === id ? "is-now" : ""}`}>
                  {label}
                  {tier === id ? " · NOW" : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.key}>
                <td>
                  <b>{a.name}</b>
                </td>
                {TRIGGERS.map(([id]) => (
                  <td key={id} className={tier === id ? "is-now" : ""}>
                    <textarea
                      rows={2}
                      value={book.actions?.[id]?.[a.key] ?? ""}
                      onChange={(e) => edit(id, a.key, e.target.value)}
                      aria-label={`${a.name} — ${id}`}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">
        When the tier changes or a sudden rise is detected, each agent posts its line from this table to the message
        board and the notification centre. The Probability Agent&apos;s line is the ML action.
      </p>
    </div>
  );
}

export default memo(PlaybookEditor);
