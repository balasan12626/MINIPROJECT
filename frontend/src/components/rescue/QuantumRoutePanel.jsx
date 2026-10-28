import { memo, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartTheme } from "../../config/chartTheme.js";

const LEGS = [
  ["toPerson", "Leg 1 · unit → person"],
  ["toShelter", "Leg 2 · person → shelter"],
];

/** A schematic of the simulated circuit: H on every qubit, then p layers of
 * cost phase e^{-iγH_C} and mixer RX(2β), then measurement. */
function Circuit({ q }) {
  const n = q.qubits;
  const layers = q.layers;
  const cols = 1 + layers * 2 + 1;
  const w = 70 + cols * 64;
  const h = 18 + n * 30;
  const boxes = [];
  for (let l = 0; l < layers; l += 1) {
    boxes.push({ col: 1 + l * 2, label: `γ${l + 1}`, kind: "cost", span: true, title: `e^-iγH_C, γ=${q.gammas[l]}` });
    boxes.push({ col: 2 + l * 2, label: `β${l + 1}`, kind: "mix", span: false, title: `RX(2β), β=${q.betas[l]}` });
  }
  const x = (c) => 60 + c * 64;
  return (
    <svg className="q-circuit" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="QAOA circuit">
      {Array.from({ length: n }, (_, i) => (
        <g key={i}>
          <text x="6" y={22 + i * 30} className="q-wire-label">
            q{i}
          </text>
          <line x1="30" x2={w - 10} y1={18 + i * 30} y2={18 + i * 30} className="q-wire" />
          <rect x={x(0) - 14} y={6 + i * 30} width="28" height="24" rx="5" className="q-gate q-h" />
          <text x={x(0)} y={22 + i * 30} textAnchor="middle" className="q-gate-text">
            H
          </text>
          {boxes
            .filter((b) => !b.span)
            .map((b) => (
              <g key={`${b.col}-${i}`}>
                <rect x={x(b.col) - 18} y={6 + i * 30} width="36" height="24" rx="5" className="q-gate q-mix">
                  <title>{b.title}</title>
                </rect>
                <text x={x(b.col)} y={22 + i * 30} textAnchor="middle" className="q-gate-text">
                  {b.label}
                </text>
              </g>
            ))}
          <rect x={x(cols - 1) - 14} y={6 + i * 30} width="28" height="24" rx="5" className="q-gate q-m" />
          <text x={x(cols - 1)} y={22 + i * 30} textAnchor="middle" className="q-gate-text">
            M
          </text>
        </g>
      ))}
      {boxes
        .filter((b) => b.span)
        .map((b) => (
          <g key={b.col}>
            <rect x={x(b.col) - 20} y="6" width="40" height={n * 30 - 6} rx="6" className="q-gate q-cost">
              <title>{b.title}</title>
            </rect>
            <text x={x(b.col)} y={12 + (n * 30) / 2} textAnchor="middle" className="q-gate-text">
              {b.label}
            </text>
          </g>
        ))}
    </svg>
  );
}

function LegDetail({ q, label }) {
  const data = q.candidates.map((c, i) => ({
    name: `R${i + 1}`,
    prob: Math.round(q.route_probabilities[i] * 1000) / 10,
    shots: q.shot_counts[i],
    km: c.km,
    min: c.sim_minutes,
    hazard: c.hazard,
    chosen: i === q.chosen,
  }));
  return (
    <div className="q-leg">
      <h4>{label}</h4>
      <div className="q-leg-grid">
        <div className="q-chart">
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...chartTheme.grid} />
              <XAxis {...chartTheme.axis} dataKey="name" />
              <YAxis {...chartTheme.axis} unit="%" width={40} />
              <Tooltip
                {...chartTheme.tooltip}
                formatter={(v, _n, item) => [`${v}% · ${item.payload.shots}/${q.shots} shots`, "Measured probability"]}
              />
              <Bar isAnimationActive={false} dataKey="prob" radius={[5, 5, 0, 0]}>
                {data.map((d) => (
                  <Cell key={d.name} fill={d.chosen ? "var(--status-safe)" : "var(--accent-2)"} fillOpacity={d.chosen ? 1 : 0.55} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <table className="data-table q-table">
          <thead>
            <tr>
              <th>Route</th>
              <th>km</th>
              <th>min</th>
              <th>Flood exposure</th>
              <th>QUBO cost</th>
              <th>P(measure)</th>
            </tr>
          </thead>
          <tbody>
            {q.candidates.map((c, i) => (
              <tr key={i} className={i === q.chosen ? "is-selected" : ""}>
                <td>
                  R{i + 1}
                  {i === q.chosen ? " ✓ QAOA" : ""}
                  {i === q.dijkstra ? " · Dijkstra" : ""}
                </td>
                <td>{c.km}</td>
                <td>{c.sim_minutes}</td>
                <td>{c.hazard}</td>
                <td>{c.qubo_cost}</td>
                <td>{(q.route_probabilities[i] * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="q-facts">
        <span>
          <b>{q.qubits}</b> qubits · <b>{q.layers}</b> layers · <b>{q.shots}</b> shots
        </span>
        <span>
          ⟨H⟩ <b>{q.expected_energy}</b> vs ground <b>{q.ground_energy}</b>
        </span>
        <span>
          P(one-hot) <b>{(q.feasible_probability * 100).toFixed(1)}%</b>
        </span>
        <span className={q.agrees_with_dijkstra ? "q-agree" : "q-differ"}>
          {q.agrees_with_dijkstra
            ? "Same route as Dijkstra"
            : q.matches_exhaustive
              ? "Differs from Dijkstra — lower travel + flood cost"
              : "Differs from Dijkstra"}
        </span>
      </div>
      <Circuit q={q} />
    </div>
  );
}

/** Routes tab: what the simulated QAOA did for each trip. All numbers are the
 * backend's `route_to_*.quantum` payload (backend/optimization/qaoa_route.py). */
function QuantumRoutePanel({ people = [], selectedKey, onSelect }) {
  const [leg, setLeg] = useState("both");
  const withQ = useMemo(() => people.filter((p) => p.quantum?.toPerson || p.quantum?.toShelter), [people]);
  const all = withQ.flatMap((p) => [p.quantum.toPerson, p.quantum.toShelter].filter(Boolean));
  const agree = all.filter((q) => q.agrees_with_dijkstra).length;
  const optimal = all.filter((q) => q.matches_exhaustive).length;
  const avgP = all.length ? all.reduce((n, q) => n + q.optimal_probability, 0) / all.length : null;
  const sel = people.find((p) => p.key === selectedKey && (p.quantum?.toPerson || p.quantum?.toShelter)) || withQ[0] || null;

  return (
    <div className="panel quantum-panel">
      <div className="panel-head">
        <h3>⚛️ Quantum route choice — QAOA (simulated)</h3>
        <span className="badge sim">{all.length} route decisions</span>
      </div>
      <p className="hint">
        For every trip the road graph gives up to 4 candidate routes (Yen&apos;s k-shortest paths). Choosing one is a
        one-hot QUBO — travel time plus flood exposure — solved by a QAOA circuit that is <b>simulated exactly on a
        classical computer</b>. The circuit is measured, and the cheapest sampled route is driven. No quantum hardware
        is used and no speed-up is claimed; exhaustive search is shown as the reference answer.
      </p>
      <div className="rescue-kpi-strip">
        <div className="rescue-kpi">
          <b>{all.length}</b>
          <span>QAOA decisions</span>
        </div>
        <div className="rescue-kpi is-safe">
          <b>{all.length ? `${optimal}/${all.length}` : "—"}</b>
          <span>matched exhaustive optimum</span>
        </div>
        <div className="rescue-kpi is-assigned">
          <b>{all.length ? `${agree}/${all.length}` : "—"}</b>
          <span>same as Dijkstra</span>
        </div>
        <div className="rescue-kpi is-transport">
          <b>{avgP != null ? `${(avgP * 100).toFixed(1)}%` : "—"}</b>
          <span>avg P(optimal route)</span>
        </div>
      </div>
      {withQ.length ? (
        <>
          <div className="q-person-row">
            <label>
              Person
              <select value={sel?.key || ""} onChange={(e) => onSelect?.(e.target.value, { pan: true })}>
                {withQ.map((p) => (
                  <option key={p.key} value={p.key}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="seg-control" role="radiogroup" aria-label="Leg">
              {[
                ["both", "Both legs"],
                ["toPerson", "Leg 1"],
                ["toShelter", "Leg 2"],
              ].map(([id, l]) => (
                <button key={id} type="button" role="radio" aria-checked={leg === id} className={leg === id ? "is-active" : ""} onClick={() => setLeg(id)}>
                  {l}
                </button>
              ))}
            </div>
          </div>
          {LEGS.filter(([k]) => (leg === "both" || leg === k) && sel?.quantum?.[k]).map(([k, label]) => (
            <LegDetail key={k} q={sel.quantum[k]} label={label} />
          ))}
        </>
      ) : (
        <p className="hint">QAOA decisions appear as units are allocated. Trips with a single open road need no choice.</p>
      )}
    </div>
  );
}

export default memo(QuantumRoutePanel);
