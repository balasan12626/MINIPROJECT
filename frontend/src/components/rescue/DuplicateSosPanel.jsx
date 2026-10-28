import { memo, useState } from "react";
import { postJson } from "../../services/api.js";

/** F30 — possible duplicate SOS. The backend only SUGGESTS pairs
 * (person_ops.duplicate_candidates: ≤ 75 m and ≤ 20 sim min apart, with similar
 * names or the same phone); the operator decides every merge. A merged SOS stays
 * in the roster with its history and its unit is freed. */
function DuplicateSosPanel({ candidates = [], merged = [], onState }) {
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  if (!candidates.length && !merged.length) return null;

  async function act(label, url, body) {
    setBusy(label);
    setNote("");
    try {
      const res = await postJson(url, body);
      onState?.(res);
      const m = res?.merge;
      setNote(m ? `${m.drop} merged into ${m.keep}${m.freed_unit ? ` — ${m.freed_unit} freed` : ""}.` : `${label} — done.`);
    } catch (e) {
      setNote(`${label} failed: ${e?.response?.data?.detail || e?.message || "error"}`);
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="panel dup-panel">
      <div className="panel-head">
        <h3>Possible duplicate SOS</h3>
        <span className="badge warn">{candidates.length} to review</span>
      </div>
      <p className="hint">Suggestions only — nothing is merged until you choose. A merged SOS keeps its history; its unit is freed.</p>
      {candidates.length ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>SOS</th>
                <th>Same as?</th>
                <th>Why</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {candidates.slice(0, 20).map((d) => (
                <tr key={d.key}>
                  <td>{d.a}</td>
                  <td>{d.b}</td>
                  <td>{(d.reasons || []).join(" · ")}</td>
                  <td className="dup-actions">
                    <button type="button" disabled={!!busy} onClick={() => act(`Merge ${d.b}`, "/api/simulation/sos/merge", { keep: d.a, drop: d.b })}>
                      Merge into {d.a}
                    </button>
                    <button type="button" className="link-btn" disabled={!!busy} onClick={() => act("Not a duplicate", "/api/simulation/sos/not-duplicate", { a: d.a, b: d.b })}>
                      Not a duplicate
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {merged.length ? <p className="hint">Merged this run: {merged.map((m) => `${m.name} → ${m.into}`).join(", ")}</p> : null}
      {note ? <p className="hint control-note">{note}</p> : null}
    </div>
  );
}

export default memo(DuplicateSosPanel);
