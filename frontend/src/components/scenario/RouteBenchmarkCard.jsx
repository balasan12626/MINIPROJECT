import { memo, useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartTheme } from "../../config/chartTheme.js";
import { fetchRouteBenchmark } from "../../services/api.js";

const METHODS = [
  ["dijkstra", "Dijkstra (shortest)"],
  ["qaoa", "QAOA choice (simulated)"],
  ["exhaustive", "Exhaustive best"],
];
const lvl = (b) => `${Math.round(b * 100)}%`;

/** F6 — measured route-choice benchmark (models/route_benchmark_v1.json via
 * GET /api/benchmark/routes). Every number is read from the stored file. */
function RouteBenchmarkCard() {
  const [data, setData] = useState(undefined); // undefined = loading, null = not generated
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    fetchRouteBenchmark()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e?.message || "error"));
    return () => {
      alive = false;
    };
  }, []);

  const levels = data?.levels || [];
  const travel = useMemo(
    () =>
      levels.map((l) => ({
        level: lvl(l.blockage),
        ...Object.fromEntries(METHODS.map(([m]) => [m, l.methods?.[m]?.travel_min?.mean ?? null])),
      })),
    [levels]
  );
  const hazard = useMemo(
    () =>
      levels.map((l) => ({
        level: lvl(l.blockage),
        ...Object.fromEntries(METHODS.map(([m]) => [m, l.methods?.[m]?.hazard?.mean ?? null])),
      })),
    [levels]
  );
  const agree = useMemo(
    () =>
      levels.map((l) => ({
        level: lvl(l.blockage),
        exhaustive: l.qaoa_equals_exhaustive_pct,
        dijkstra: l.qaoa_equals_dijkstra_pct,
      })),
    [levels]
  );

  const s = data?.settings || {};
  const timing = data?.timing?.levels || [];
  return (
    <div className="panel route-bench">
      <div className="panel-head">
        <h3>Route choice benchmark — measured</h3>
        {data ? <span className="badge sim">{s.trips} synthetic trips · seed {s.seed}</span> : null}
      </div>
      {error ? <p className="error-text">Could not load the benchmark: {error}</p> : null}
      {data === undefined && !error ? <p className="hint">Loading…</p> : null}
      {data === null ? (
        <p className="hint">
          Not generated yet. Run <code>python scripts/bench_routes.py</code> (it is never run inside a request).
        </p>
      ) : null}
      {data ? (
        <>
          <p className="hint">
            Same Yen candidates (k ≤ {s.candidates_k}) as the live app, on the live road graph, with roads closed by the
            engine&apos;s own flood rule. QAOA is a classical statevector simulation ({s.qaoa_layers} layers, {s.qaoa_shots}{" "}
            shots) choosing among those candidates, so it can at best equal the exhaustive best — no speed-up is claimed.
          </p>
          <div className="grid-2">
            <div>
              <b>Mean travel time (min) by blockage</b>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={travel}>
                  <CartesianGrid {...chartTheme.grid} />
                  <XAxis {...chartTheme.axis} dataKey="level" />
                  <YAxis {...chartTheme.axis} width={44} />
                  <Tooltip {...chartTheme.tooltip} />
                  <Legend {...chartTheme.legend} />
                  {METHODS.map(([m, label], i) => (
                    <Bar key={m} dataKey={m} name={label} fill={chartTheme.series[i]} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div>
              <b>Mean flood hazard (Σ exposure × km) by blockage</b>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={hazard}>
                  <CartesianGrid {...chartTheme.grid} />
                  <XAxis {...chartTheme.axis} dataKey="level" />
                  <YAxis {...chartTheme.axis} width={44} />
                  <Tooltip {...chartTheme.tooltip} />
                  <Legend {...chartTheme.legend} />
                  {METHODS.map(([m, label], i) => (
                    <Bar key={m} dataKey={m} name={label} fill={chartTheme.series[i]} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <b>Agreement on trips with more than one candidate (%)</b>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={agree}>
              <CartesianGrid {...chartTheme.grid} />
              <XAxis {...chartTheme.axis} dataKey="level" />
              <YAxis {...chartTheme.axis} width={44} domain={[0, 100]} />
              <Tooltip {...chartTheme.tooltip} formatter={(v) => (v == null ? "no multi-candidate trips" : `${v}%`)} />
              <Legend {...chartTheme.legend} />
              <Line dataKey="exhaustive" name="QAOA = exhaustive" stroke={chartTheme.series[1]} connectNulls={false} dot />
              <Line dataKey="dijkstra" name="QAOA = Dijkstra" stroke={chartTheme.series[0]} connectNulls={false} dot />
            </LineChart>
          </ResponsiveContainer>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Blockage</th>
                  <th>Roads closed</th>
                  <th>Routed</th>
                  <th>No open road</th>
                  <th>1 candidate</th>
                  <th>QAOA = exhaustive</th>
                  <th>Straight line (ref.)</th>
                  <th>QAOA solve (mean)</th>
                </tr>
              </thead>
              <tbody>
                {levels.map((l, i) => (
                  <tr key={l.blockage}>
                    <td>{lvl(l.blockage)}</td>
                    <td>{l.roads_closed?.join(", ") || "none"}</td>
                    <td>
                      {l.routed}/{l.trips}
                    </td>
                    <td>{l.no_open_road}</td>
                    <td>{l.single_candidate_trips}</td>
                    <td>{l.qaoa_equals_exhaustive_pct == null ? "— (nothing to choose)" : `${l.qaoa_equals_exhaustive_pct}%`}</td>
                    <td>{l.methods?.direct?.travel_min?.mean ?? "—"} min</td>
                    <td>{timing[i]?.qaoa_ms?.mean != null ? `${timing[i].qaoa_ms.mean} ms` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">
            Trips are synthetic (seeded). &ldquo;1 candidate&rdquo; = the open road network leaves only one path, so every
            method returns the same route. The straight line is a reference, not a drivable route. Code{" "}
            {data.code?.commit ? data.code.commit.slice(0, 7) : "n/a"}
            {data.code?.dirty_worktree ? " (uncommitted changes)" : ""}.
          </p>
        </>
      ) : null}
    </div>
  );
}

export default memo(RouteBenchmarkCard);
