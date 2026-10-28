import { memo, useEffect, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, ErrorBar, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartTheme } from "../../config/chartTheme.js";
import { fetchWhatIf, runWhatIf, setRoad, setShelter } from "../../services/api.js";

/** F16 — what-if planner. Plays the next N simulated minutes from a COPY of
 * the live run once per option (plus a "no change" baseline) on the backend's
 * own stage machine. Nothing in the live run changes; "Apply" calls the
 * existing shelter / road endpoints, never a new mutation path. */
export const STALE_TICKS = 5;
const KINDS = [
  { kind: "add_ambulances", label: "Add ambulances" },
  { kind: "close_shelter", label: "Close a shelter" },
  { kind: "set_capacity", label: "Set shelter capacity" },
  { kind: "block_road", label: "Block a road" },
  { kind: "open_road", label: "Open a road" },
  { kind: "dispatch_policy", label: "Switch dispatch policy" },
  { kind: "preposition", label: "Pre-positioning on / off" },
];
const POLICIES = ["first_free", "greedy", "optimal", "nearest_depot"];

const fmt = (v) => (v == null ? "—" : Number(v).toFixed(1));

export function isStale(job, tick, runId) {
  if (!job) return false;
  if (runId && job.run_id && runId !== job.run_id) return true;
  return typeof tick === "number" && tick - Number(job.tick || 0) >= STALE_TICKS;
}

/** Which existing endpoint can apply an option live (null = not applicable live). */
export function applyCall(opt) {
  if (opt.kind === "close_shelter") return () => setShelter({ name: opt.name, closed: true });
  if (opt.kind === "set_capacity") return () => setShelter({ name: opt.name, capacity: Number(opt.capacity) });
  if (opt.kind === "block_road") return () => setRoad({ road_id: opt.road_id, blocked: true });
  if (opt.kind === "open_road") return () => setRoad({ road_id: opt.road_id, blocked: false });
  return null;
}

const NOT_LIVE = {
  add_ambulances: "The live fleet is fixed (10 ambulances) — no live control adds units.",
  dispatch_policy: "Dispatch policy is set on Setup and applies from the next run.",
  preposition: "Pre-positioning is set on Setup and applies from the next run.",
};

function OptionEditor({ opt, onChange, onRemove, shelters, roads }) {
  const set = (k, v) => onChange({ ...opt, [k]: v });
  return (
    <div className="whatif-option">
      <select value={opt.kind} aria-label="Option" onChange={(e) => onChange({ kind: e.target.value })}>
        {KINDS.map((k) => (
          <option key={k.kind} value={k.kind}>
            {k.label}
          </option>
        ))}
      </select>
      {opt.kind === "add_ambulances" ? (
        <input type="number" min={1} max={10} value={opt.n ?? 3} aria-label="Ambulances to add" onChange={(e) => set("n", Number(e.target.value))} />
      ) : null}
      {opt.kind === "close_shelter" || opt.kind === "set_capacity" ? (
        <select value={opt.name || ""} aria-label="Shelter" onChange={(e) => set("name", e.target.value)}>
          <option value="">Shelter…</option>
          {shelters.map((s) => (
            <option key={s.name} value={s.name}>
              {s.name}
            </option>
          ))}
        </select>
      ) : null}
      {opt.kind === "set_capacity" ? (
        <input type="number" min={0} value={opt.capacity ?? ""} placeholder="seats" aria-label="Capacity" onChange={(e) => set("capacity", Number(e.target.value))} />
      ) : null}
      {opt.kind === "block_road" || opt.kind === "open_road" ? (
        <select value={opt.road_id || ""} aria-label="Road" onChange={(e) => set("road_id", e.target.value)}>
          <option value="">Road…</option>
          {roads
            .filter((r) => (opt.kind === "block_road" ? !r.blocked : r.blocked))
            .map((r) => (
              <option key={r.road_id} value={r.road_id}>
                {r.road_id} {r.name ? `— ${r.name}` : ""}
              </option>
            ))}
        </select>
      ) : null}
      {opt.kind === "dispatch_policy" ? (
        <select value={opt.policy || ""} aria-label="Policy" onChange={(e) => set("policy", e.target.value)}>
          <option value="">Policy…</option>
          {POLICIES.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      ) : null}
      {opt.kind === "preposition" ? (
        <select value={opt.on ? "on" : "off"} aria-label="Pre-positioning" onChange={(e) => set("on", e.target.value === "on")}>
          <option value="on">on</option>
          <option value="off">off</option>
        </select>
      ) : null}
      <button type="button" className="link-btn" onClick={onRemove}>
        Remove
      </button>
    </div>
  );
}

const ready = (o) =>
  (o.kind !== "add_ambulances" || (o.n >= 1 && o.n <= 10)) &&
  (!["close_shelter", "set_capacity"].includes(o.kind) || o.name) &&
  (o.kind !== "set_capacity" || Number.isFinite(o.capacity)) &&
  (!["block_road", "open_road"].includes(o.kind) || o.road_id) &&
  (o.kind !== "dispatch_policy" || o.policy);

export function WhatIfResults({ job, tick, runId, onApply, busy }) {
  const opts = job?.results?.options || [];
  const stale = isStale(job, tick, runId);
  const chart = opts
    .filter((o) => o.vs_baseline)
    .map((o) => ({
      label: o.label,
      diff: o.vs_baseline.mean_diff_min,
      err: [o.vs_baseline.mean_diff_min - o.vs_baseline.ci95_min[0], o.vs_baseline.ci95_min[1] - o.vs_baseline.mean_diff_min],
    }));
  return (
    <div className="whatif-results">
      <p className="hint">
        Simulated from the live state at tick {job.tick} — {job.runs} runs × next {job.horizon_min} sim min, not a forecast of the real world.
        {job.synthetic_arrivals ? ` Includes synthetic future SOS at this run's observed rate (${job.arrival_rate_per_sim_hour}/sim h).` : " No future SOS assumed."}
        {stale ? (
          <span className="badge warn" style={{ marginLeft: 6 }}>
            stale — the run has moved on
          </span>
        ) : null}
      </p>
      {job.accept_mode_note ? <p className="hint">{job.accept_mode_note}</p> : null}
      {chart.length ? (
        <div style={{ width: "100%", height: Math.max(120, 44 * chart.length + 40) }}>
          <ResponsiveContainer>
            <BarChart data={chart} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
              <CartesianGrid {...chartTheme.grid} />
              <XAxis type="number" {...chartTheme.axis} unit=" min" />
              <YAxis type="category" dataKey="label" width={170} {...chartTheme.axis} />
              <Tooltip {...chartTheme.tooltip} formatter={(v) => [`${fmt(v)} min vs no change`, "mean difference"]} />
              <ReferenceLine x={0} stroke="var(--axis)" />
              <Bar dataKey="diff" fill={chartTheme.series?.[0] || "var(--accent)"} isAnimationActive={false}>
                <ErrorBar dataKey="err" width={6} stroke="var(--text)" direction="x" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : null}
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Option</th>
              <th>Safe per run</th>
              <th>Still waiting</th>
              <th>Time to safe p50 / p90</th>
              <th>vs no change (95% CI)</th>
              <th>Faster in</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {opts.map((o) => {
              const t = o.time_to_safe_censored_min || {};
              const d = o.vs_baseline;
              const call = applyCall(o.option || {});
              return (
                <tr key={o.key}>
                  <td>{o.label}</td>
                  <td>{fmt(o.served_per_run)}</td>
                  <td>{fmt(o.still_waiting_per_run)}</td>
                  <td>
                    {fmt(t.p50)} / {fmt(t.p90)} min
                  </td>
                  <td>{d ? `${d.mean_diff_min > 0 ? "+" : ""}${fmt(d.mean_diff_min)} min [${fmt(d.ci95_min[0])}, ${fmt(d.ci95_min[1])}]` : "baseline"}</td>
                  <td>{d ? `${d.faster_in_pct_of_runs}% of runs` : "—"}</td>
                  <td>
                    {call ? (
                      <button type="button" disabled={busy} onClick={() => onApply(o.label, call)}>
                        Apply
                      </button>
                    ) : o.option?.kind && NOT_LIVE[o.option.kind] ? (
                      <span className="hint" title={NOT_LIVE[o.option.kind]}>
                        not live
                      </span>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="hint">
        Time to safe = simulated minutes from the snapshot until the person reaches a shelter; anyone still waiting at the horizon counts as the horizon
        (a lower bound). Simulated crews accept every job; routes use the shortest open road path.
      </p>
    </div>
  );
}

function WhatIfPanel({ tick, runId, status, shelters = [], roads = [], onState }) {
  const [opts, setOpts] = useState([{ kind: "add_ambulances", n: 3 }]);
  const [horizon, setHorizon] = useState(60);
  const [runs, setRuns] = useState(10);
  const [arrivals, setArrivals] = useState(true);
  const [job, setJob] = useState(null);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  function poll(id) {
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const j = await fetchWhatIf(id);
        if (j?.available === false) {
          setErr(j.message || "What-if status unavailable");
          return;
        }
        setJob(j);
        if (j.status === "queued" || j.status === "running") poll(id);
        else if (j.status === "failed") setErr(`What-if failed: ${j.error}`);
      } catch (e) {
        setErr(e?.message || "What-if status unavailable");
      }
    }, 800);
  }

  async function start() {
    setErr("");
    setNote("");
    try {
      const j = await runWhatIf({ options: opts, horizon_min: horizon, runs, arrivals });
      setJob(j);
      poll(j.job_id);
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || "What-if could not start");
    }
  }

  async function apply(label, call) {
    setBusy(true);
    try {
      const res = await call();
      onState?.(res);
      setNote(`${label} — applied to the live run.`);
    } catch (e) {
      setNote(`${label} failed: ${e?.response?.data?.detail || e?.message || "error"}`);
    } finally {
      setBusy(false);
    }
  }

  const live = status === "running" || status === "paused" || status === "completed";
  const working = job && (job.status === "queued" || job.status === "running");
  return (
    <div className="panel whatif-panel">
      <div className="panel-head">
        <h3>What-if planner</h3>
        {working ? <span className="badge warn">running {Math.round((job.progress || 0) * 100)}%</span> : null}
      </div>
      <p className="hint">Try up to 4 changes on a copy of the live run. The live run is not changed until you press Apply.</p>
      {opts.map((o, i) => (
        <OptionEditor
          key={i}
          opt={o}
          shelters={shelters}
          roads={roads}
          onChange={(n) => setOpts((xs) => xs.map((x, j) => (j === i ? n : x)))}
          onRemove={() => setOpts((xs) => xs.filter((_, j) => j !== i))}
        />
      ))}
      <div className="quick-row">
        <button type="button" disabled={opts.length >= 4} onClick={() => setOpts((xs) => [...xs, { kind: "add_ambulances", n: 3 }])}>
          + Add option
        </button>
        <label>
          Next{" "}
          <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} aria-label="Horizon">
            {[15, 30, 60, 90, 120].map((h) => (
              <option key={h} value={h}>
                {h}
              </option>
            ))}
          </select>{" "}
          sim min
        </label>
        <label>
          Runs{" "}
          <select value={runs} onChange={(e) => setRuns(Number(e.target.value))} aria-label="Runs">
            {[5, 10, 20, 30].map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input type="checkbox" checked={arrivals} onChange={(e) => setArrivals(e.target.checked)} /> future SOS at observed rate
        </label>
        <button type="button" className="primary" disabled={!live || working || !opts.every(ready)} onClick={start}>
          Run what-if
        </button>
      </div>
      {!live ? <p className="hint">Start a scenario first — the what-if copies the live run.</p> : null}
      {err ? <p className="hint" style={{ color: "var(--crit)" }}>{err}</p> : null}
      {job?.status === "done" ? <WhatIfResults job={job} tick={tick} runId={runId} onApply={apply} busy={busy} /> : null}
      {note ? <p className="hint control-note">{note}</p> : null}
    </div>
  );
}

export default memo(WhatIfPanel);
