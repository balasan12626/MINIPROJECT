import { memo, useCallback, useEffect, useMemo, useState } from "react";
import LiveRescueMap from "../rescue/LiveRescueMap.jsx";
import ShelterCapacityPanel from "../rescue/ShelterCapacityPanel.jsx";
import FleetPanel from "../rescue/FleetPanel.jsx";
import { fetchRunEquity, fetchRunFrames, fetchRunMessages, fetchRuns, runReportUrl } from "../../services/api.js";
import EquityPanel from "../rescue/EquityPanel.jsx";
import { deriveRescueOps } from "../../state/rescueOps.js";
import { frameTime, frameToView, messagesAt } from "../../state/replay.js";
import { formatTimeIST } from "../../utils/time.js";
import { useCityView } from "../../hooks/useCityView.js";

const EMPTY = [];
const SPEEDS = [1, 4, 16];
const pct = (p) => (p == null ? "—" : `${(p * 100).toFixed(1)}%`);

function RunList({ runs, persisted, onOpen, openId }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h3>📼 Past runs</h3>
        <span className={`badge ${persisted ? "live" : "warn"}`}>
          {persisted ? "saved in MongoDB" : "MongoDB off — last run only, not persisted"}
        </span>
      </div>
      {!runs.length ? (
        <p className="hint">No recorded runs yet. Every run is recorded from its first tick — run a scenario, then come back.</p>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>City</th>
                <th>Scenario</th>
                <th>Started</th>
                <th>Status</th>
                <th>Frames</th>
                <th>SOS</th>
                <th>Safe</th>
                <th>Peak P</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id} className={r.run_id === openId ? "is-selected" : ""}>
                  <td>
                    {r.run_id}
                    {r.persisted === false ? <span className="badge warn"> memory</span> : null}
                  </td>
                  <td>{r.city || "—"}</td>
                  <td>{r.scenario || "—"}</td>
                  <td>{formatTimeIST(r.started_at)}</td>
                  <td>{r.status || "—"}</td>
                  <td>{r.frames ?? "—"}</td>
                  <td>{r.sos ?? "—"}</td>
                  <td>{r.rescued ?? "—"}</td>
                  <td>{pct(r.peak_probability)}</td>
                  <td>
                    <button type="button" onClick={() => onOpen(r.run_id)} disabled={!r.frames}>
                      ▶ Replay
                    </button>{" "}
                    <a className="link-btn" href={runReportUrl(r.run_id)} target="_blank" rel="noreferrer">
                      PDF
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** F5 — replay a stored run. Renders the EXISTING live components from a
 * stored frame (state/replay.js frameToView); read-only, clearly labelled. */
function ReplayPlayer() {
  const [runs, setRuns] = useState(EMPTY);
  const [persisted, setPersisted] = useState(true);
  const [openId, setOpenId] = useState(null);
  const [frames, setFrames] = useState(EMPTY);
  const [messages, setMessages] = useState(EMPTY);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(4);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedKey, setSelectedKey] = useState(null);
  const [equity, setEquity] = useState(null);

  const loadRuns = useCallback(async () => {
    try {
      const d = await fetchRuns(20);
      setRuns(d.runs || EMPTY);
      setPersisted(Boolean(d.persisted));
      setError("");
    } catch (e) {
      setError(`Could not load runs: ${e?.message || "error"}`);
    }
  }, []);
  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  async function open(runId) {
    setOpenId(runId);
    setPlaying(false);
    setLoading(true);
    setError("");
    try {
      const all = [];
      let start = 1;
      // Page through every stored frame (200 per request).
      for (let guard = 0; guard < 50; guard += 1) {
        const page = await fetchRunFrames(runId, start, 200);
        all.push(...(page.frames || EMPTY));
        if (!page.frames?.length || all.length >= (page.total || 0)) break;
        start = page.frames[page.frames.length - 1].seq + 1;
      }
      const msgs = await fetchRunMessages(runId);
      setFrames(all);
      setMessages(msgs.messages || EMPTY);
      setIdx(0);
      // F14: fairness of the whole run (last frame) — optional, never blocks the replay.
      setEquity(null);
      Promise.resolve()
        .then(() => fetchRunEquity(runId))
        .then((eq) => setEquity(eq))
        .catch(() => setEquity(null));
    } catch (e) {
      setError(`Could not load run ${runId}: ${e?.message || "error"}`);
      setFrames(EMPTY);
    } finally {
      setLoading(false);
    }
  }

  // Playback: wait the real gap between two frames ÷ speed (0.3–5 s).
  useEffect(() => {
    if (!playing || idx >= frames.length - 1) {
      if (playing && idx >= frames.length - 1) setPlaying(false);
      return undefined;
    }
    const gap = (frameTime(frames[idx + 1]) ?? 0) - (frameTime(frames[idx]) ?? 0);
    const wait = Math.max(300, Math.min(5000, gap / speed));
    const t = window.setTimeout(() => setIdx((i) => Math.min(frames.length - 1, i + 1)), wait);
    return () => window.clearTimeout(t);
  }, [playing, idx, frames, speed]);

  const frame = frames[idx] || null;
  const view = useMemo(() => frameToView(frame), [frame]);
  // F7: the replayed run's own city map (older frames have no city → demo Delhi).
  const cityView = useCityView(frame?.city || null);
  const at = frameTime(frame);
  const ops = useMemo(() => (view && at !== null ? deriveRescueOps(view, at) : null), [view, at]);
  // The map's clock = the frame's time; while playing it runs on from there.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const offset = useMemo(() => (at === null ? 0 : at - Date.now()), [at, playing]);
  const shownMessages = useMemo(() => messagesAt(messages, frame), [messages, frame]);
  const select = useCallback((key) => setSelectedKey(key), []);

  return (
    <section className="replay" aria-label="Replay a past run">
      <RunList runs={runs} persisted={persisted} onOpen={open} openId={openId} />
      {error ? <p className="error-text">{error}</p> : null}
      {loading ? <p className="hint">Loading frames…</p> : null}

      {frame && ops ? (
        <>
          <div className="replay-banner" role="status">
            <b>REPLAY — not live.</b> Run {frame.run_id} · frame {frame.seq} of {frames.length} · recorded{" "}
            {formatTimeIST(frame.at)} · cause: {frame.cause}
            {persisted ? "" : " · not persisted (MongoDB off)"}
          </div>
          <div className="replay-controls">
            <button type="button" onClick={() => setPlaying((p) => !p)} disabled={idx >= frames.length - 1 && !playing}>
              {playing ? "⏸ Pause" : "▶ Play"}
            </button>
            <input
              type="range"
              min={0}
              max={Math.max(0, frames.length - 1)}
              value={idx}
              aria-label="Replay position"
              onChange={(e) => {
                setPlaying(false);
                setIdx(Number(e.target.value));
              }}
            />
            <span className="seg-control" role="radiogroup" aria-label="Replay speed">
              {SPEEDS.map((s) => (
                <button
                  key={s}
                  type="button"
                  role="radio"
                  aria-checked={speed === s}
                  className={speed === s ? "is-active" : ""}
                  onClick={() => setSpeed(s)}
                >
                  {s}×
                </button>
              ))}
            </span>
          </div>
          <div className="rescue-kpi-strip">
            {[
              ["Flood probability", pct(frame.probability)],
              ["Tier", frame.tier || "—"],
              ["Rainfall", frame.rainfall_mm != null ? `${frame.rainfall_mm} mm` : "—"],
              ["Yamuna", frame.river_m != null ? `${frame.river_m} m` : "—"],
              ["SOS", ops.counters.totalSos],
              ["Moving", (frame.counts?.en_route || 0) + (frame.counts?.to_shelter || 0)],
              ["Safe", ops.counters.rescued],
              ["Roads closed", (frame.roads_closed || EMPTY).length],
            ].map(([label, value]) => (
              <div className="rescue-kpi" key={label}>
                <b>{value}</b>
                <span>{label}</span>
              </div>
            ))}
          </div>
          <div className="grid-2 rescue-main-grid">
            <div className="panel rescue-map-panel">
              <div className="panel-head">
                <h3>Rescue map (replay)</h3>
              </div>
              <LiveRescueMap
                ops={ops}
                offset={offset}
                paused={!playing}
                selectedKey={selectedKey}
                onSelect={select}
                floodProbability={frame.probability}
                toasts={EMPTY}
                plannedRoutes="all"
                roads={EMPTY}
                onRoad={null}
                cityView={cityView}
              />
            </div>
            <div className="panel">
              <div className="panel-head">
                <h3>Agent messages up to this moment</h3>
                <span className="badge">{shownMessages.length}</span>
              </div>
              <ul className="replay-messages">
                {shownMessages.map((m) => (
                  <li key={m.id} className={`sev-${m.severity}`}>
                    <span className="muted">{formatTimeIST(m.at)}</span> <b>{m.title}</b> · {m.from_name}: {m.text}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <FleetPanel fleet={frame.fleet_board} people={ops.people} onSelect={select} acceptMode={frame.accept_mode} replay />
          <ShelterCapacityPanel allocation={frame.shelter_allocation || EMPTY} />
          <EquityPanel equity={equity} title="Fairness — this run (at its last frame)" />
        </>
      ) : null}
    </section>
  );
}

export default memo(ReplayPlayer);
