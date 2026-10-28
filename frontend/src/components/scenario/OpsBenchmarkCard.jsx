import { memo, useEffect, useState } from "react";
import { fetchOpsBenchmark } from "../../services/api.js";

const LABEL = {
  nearest_depot: "Original rule (idealised)",
  first_free: "First free ambulance",
  greedy: "Nearest free ambulance",
  optimal: "Best overall (assignment)",
  "optimal+prepos": "Best overall + pre-positioning",
};
const n = (v) => (v == null ? "—" : v);

/** F12 — Monte-Carlo evaluation of the rescue operation (stored file from
 * scripts/monte_carlo_ops.py, served by GET /api/benchmark/ops). */
function OpsBenchmarkCard() {
  const [city, setCity] = useState(null);
  const [data, setData] = useState(undefined);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    setError("");
    fetchOpsBenchmark(city)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e?.message || "error"));
    return () => {
      alive = false;
    };
  }, [city]);

  const s = data?.settings || {};
  const paired = data?.paired_vs_first_free || {};
  return (
    <div className="panel ops-bench">
      <div className="panel-head">
        <h3>Rescue operation — Monte-Carlo evaluation</h3>
        {data?.available_cities?.length ? (
          <select aria-label="City" value={data.city} onChange={(e) => setCity(e.target.value)}>
            {data.available_cities.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      {error ? <p className="error-text">Could not load: {error}</p> : null}
      {data === undefined && !error ? <p className="hint">Loading…</p> : null}
      {data === null ? (
        <p className="hint">
          Not generated yet. Run <code>python scripts/monte_carlo_ops.py --city delhi</code>.
        </p>
      ) : null}
      {data ? (
        <>
          <p className="hint">
            {s.runs} synthetic operations on {data.city}&apos;s real road network ({data.graph?.junctions} junctions,{" "}
            {data.graph?.depots} depots, {s.ambulances} ambulances): {s.initial_sos} SOS + a surge of {s.surge_sos}, roads
            closing by the flood rule, one shelter closed mid-run. Every policy replays the same operations (paired). Times are
            simulated minutes from SOS to pickup / to safety.
          </p>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Policy</th>
                  <th>Served</th>
                  <th>To pickup — mean / p90</th>
                  <th>To safety — mean / p50 / p90</th>
                  <th>vs first free (paired, 95% CI)</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.summary || {}).map(([name, r]) => {
                  const d = paired[name];
                  return (
                    <tr key={name}>
                      <td>{LABEL[name] || name}</td>
                      <td>
                        {r.served}/{r.people}
                      </td>
                      <td>
                        {n(r.time_to_pickup_min?.mean)} / {n(r.time_to_pickup_min?.p90)}
                      </td>
                      <td>
                        {n(r.time_to_safety_min?.mean)} / {n(r.time_to_safety_min?.p50)} / {n(r.time_to_safety_min?.p90)}
                      </td>
                      <td>
                        {name === "first_free"
                          ? "baseline"
                          : name === "nearest_depot"
                            ? "not comparable (idealised)"
                            : d
                              ? `${d.mean_diff_min > 0 ? "+" : ""}${d.mean_diff_min} min [${d.ci95_min.join(", ")}] · faster in ${d.faster_in_pct_of_runs}% of runs`
                              : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <ul className="hint">
            {(data.notes || []).map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

export default memo(OpsBenchmarkCard);
