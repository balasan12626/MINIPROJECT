import { useMemo, useState } from "react";
import PdfDownloadButton from "../PdfDownloadButton.jsx";
import { STAGES, STAGE_COLOR, STAGE_LABEL, STAGE_SHORT } from "../../data/rescueAssets.js";
import { useStageChanges } from "../../hooks/useRescueOps.js";
import { formatTimeIST } from "../../utils/time.js";

/** Every timestamp in the roster is IST, same formatter as the event feed. */
const hhmmss = (v) => formatTimeIST(v);

const etaText = (p) => {
  if (p.stage === "rescued") return "arrived";
  if (p.stage === "to_shelter") return p.etaShelterMin != null ? `${p.etaShelterMin} min → shelter` : "—";
  return p.etaMin != null ? `${p.etaMin} min` : "pending";
};

const PRIORITY_RANK = { child: 0, elderly: 1, "chest-deep": 2, standard: 3 };

/** Live SOS roster — the ONE per-person table. The old Citizen Status Board,
 * Per-person Contact Log and ETA-per-citizen list are merged in here as the
 * expandable row details. Every cell traces to GET /api/simulation/state. */
export default function LivePeopleTable({ people = [], selectedKey, onSelect }) {
  const [stageFilter, setStageFilter] = useState("all");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState("order");
  const [expanded, setExpanded] = useState(() => new Set());

  const flashing = useStageChanges(people);

  const counts = useMemo(() => {
    const c = { all: people.length };
    for (const s of STAGES) c[s] = 0;
    for (const p of people) c[p.stage] = (c[p.stage] || 0) + 1;
    return c;
  }, [people]);

  const priorities = useMemo(() => {
    const set = new Set(people.map((p) => p.priority).filter(Boolean));
    return [...set].sort();
  }, [people]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    let out = people.filter((p) => {
      if (stageFilter !== "all" && p.stage !== stageFilter) return false;
      if (priorityFilter !== "all" && p.priority !== priorityFilter) return false;
      if (!q) return true;
      return [p.name, p.key, p.cluster, p.team, p.ambulance, p.shelter]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(q);
    });
    out = [...out];
    if (sortBy === "priority") {
      out.sort(
        (a, b) =>
          (PRIORITY_RANK[a.priority] ?? 9) - (PRIORITY_RANK[b.priority] ?? 9) ||
          (a.rescueOrder || 99) - (b.rescueOrder || 99)
      );
    } else if (sortBy === "stage") {
      out.sort((a, b) => STAGES.indexOf(a.stage) - STAGES.indexOf(b.stage));
    } else if (sortBy === "eta") {
      out.sort((a, b) => (a.etaMin ?? 1e9) - (b.etaMin ?? 1e9));
    } else {
      out.sort((a, b) => (a.rescueOrder || 99) - (b.rescueOrder || 99));
    }
    return out;
  }, [people, stageFilter, priorityFilter, query, sortBy]);

  const toggleRow = (key) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  if (!people.length) {
    return (
      <div className="panel">
        <div className="panel-head">
          <h3>Live SOS roster</h3>
        </div>
        <p className="hint">Run a scenario to start the live rescue simulation.</p>
      </div>
    );
  }

  return (
    <div className="panel rescue-table-panel">
      <div className="panel-head">
        <h3>Live SOS roster ({people.length})</h3>
        <span className="badge live">STAGE TIME = ROUTE TRAVEL TIME</span>
      </div>

      {/* ---- summary / stage filter chips ---- */}
      <div className="ask-chips rescue-stage-chips" role="radiogroup" aria-label="Filter by stage">
        <label className={`radio-pill ${stageFilter === "all" ? "active" : ""}`}>
          <input
            type="radio"
            name="stage-filter"
            checked={stageFilter === "all"}
            onChange={() => setStageFilter("all")}
          />
          All <b>{counts.all}</b>
        </label>
        {STAGES.map((s) => (
          <label
            key={s}
            className={`radio-pill ${stageFilter === s ? "active" : ""}`}
            style={stageFilter === s ? { borderColor: STAGE_COLOR[s], color: STAGE_COLOR[s] } : undefined}
            title={STAGE_LABEL[s]}
          >
            <input type="radio" name="stage-filter" checked={stageFilter === s} onChange={() => setStageFilter(s)} />
            {STAGE_SHORT[s]} <b>{counts[s] || 0}</b>
          </label>
        ))}
      </div>

      <div className="rescue-table-controls">
        <label>
          <span>Search</span>
          <input
            type="search"
            value={query}
            placeholder="Name, team, shelter…"
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label>
          <span>Priority</span>
          <select value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)}>
            <option value="all">All</option>
            {priorities.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Sort by</span>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
            <option value="order">Rescue order</option>
            <option value="priority">Priority</option>
            <option value="stage">Stage</option>
            <option value="eta">ETA</option>
          </select>
        </label>
      </div>

      <div className="table-wrap rescue-table-wrap">
        <table className="data-table rescue-table">
          <thead>
            <tr>
              <th>#</th>
              <th className="sticky-name">Name</th>
              <th>Age</th>
              <th>People</th>
              <th>Cluster</th>
              <th>Priority</th>
              <th>Triage</th>
              <th className="sticky-stage">Stage</th>
              <th>Team</th>
              <th>Ambulance</th>
              <th>Shelter</th>
              <th>SOS time</th>
              <th>Stage since</th>
              <th>ETA</th>
              <th>PDF</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const open = expanded.has(p.key);
              const sosTime = p.timestamps?.queued || p.journey?.[0]?.at || null;
              return [
                <tr
                  key={p.key}
                  className={`rescue-row ${p.key === selectedKey ? "is-selected" : ""} ${
                    flashing.has(p.key) ? "is-flash" : ""
                  }`}
                  onClick={() => onSelect?.(p.key, { pan: true })}
                >
                  <td>{p.rescueOrder ?? "—"}</td>
                  <td className="sticky-name">
                    <button
                      type="button"
                      className="rescue-expand"
                      aria-expanded={open}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleRow(p.key);
                      }}
                    >
                      {open ? "▾" : "▸"}
                    </button>
                    {p.name}
                  </td>
                  <td>{p.age ?? "—"}</td>
                  <td>{p.people ?? "—"}</td>
                  <td>{p.cluster || "—"}</td>
                  <td>{p.priority || "—"}</td>
                  <td>{p.triage || "—"}</td>
                  <td className="sticky-stage">
                    <span className={`status-pill ${p.stage}`} title={STAGE_LABEL[p.stage]}>
                      {STAGE_SHORT[p.stage]}
                    </span>
                  </td>
                  <td>{p.team || "—"}</td>
                  <td>{p.ambulance || "—"}</td>
                  <td>{p.shelter || "—"}</td>
                  <td>{hhmmss(sosTime)}</td>
                  <td>{hhmmss(p.stageStartedAt)}</td>
                  <td>{etaText(p)}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <PdfDownloadButton personName={p.name} />
                  </td>
                </tr>,
                open ? (
                  <tr key={`${p.key}-detail`} className="rescue-row-detail">
                    <td colSpan={15}>
                      <div className="rescue-detail-grid">
                        <div>
                          <b>Contact log</b>
                          <div className="metric"><span>Called</span><b>{hhmmss(p.calledAt)}</b></div>
                          <div className="metric"><span>Answered</span><b>{p.answered == null ? "—" : p.answered ? "Yes" : "No"}</b></div>
                          <div className="metric"><span>Rescued</span><b>{p.rescued == null ? "pending" : String(p.rescued)}</b></div>
                          <div className="metric"><span>Water</span><b>{p.waterNote || "—"}</b></div>
                        </div>
                        <div>
                          <b>Unit &amp; ETA</b>
                          <div className="metric">
                            <span>Unit</span>
                            <b>
                              {p.unitName || "—"}
                              {p.unitRole ? ` (${p.unitRole === "ambulance" ? "ambulance" : "rescue team"})` : ""}
                            </b>
                          </div>
                          <div className="metric"><span>Dispatched from</span><b>{p.unitBaseName || p.team || "—"}</b></div>
                          <div className="metric">
                            <span>To person</span>
                            <b>{p.etaMin != null ? `${p.etaMin} min · ${p.routeKm ?? "?"} km` : "pending dispatch"}</b>
                          </div>
                          <div className="metric">
                            <span>To shelter</span>
                            <b>{p.etaShelterMin != null ? `${p.etaShelterMin} min · ${p.shelterKm ?? "?"} km` : "—"}</b>
                          </div>
                          {p.waitReason ? <p className="counterfactual">{p.waitReason}</p> : null}
                        </div>
                      </div>
                      <div className="rescue-timeline">
                        <b>Stage timeline</b>
                        {(p.journey || []).length === 0 ? (
                          <p className="hint">No journey entries yet.</p>
                        ) : (
                          <div className="timeline">
                            {(p.journey || []).map((j, i) => (
                              <div key={`${j.at}-${i}`}>
                                <b>{hhmmss(j.at)}</b>{" "}
                                <span className={`status-pill ${j.status || ""}`}>{j.event}</span>{" "}
                                <span className="muted">[{j.agent}]</span> {j.detail}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                ) : null,
              ];
            })}
          </tbody>
        </table>
      </div>
      {rows.length === 0 ? <p className="hint">No one matches those filters.</p> : null}
    </div>
  );
}
