import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const EDGE_STROKE = {
  selected: "#4aa3ff",
  closed: "#e85d6c",
  hazard: "#e08a3c",
  congested: "#e6b84d",
  open: "#3ecf8e",
  candidate: "#9ad0e0",
  rejected: "#778899",
};

const METHOD_SHORT = (m) =>
  String(m || "")
    .replace("PPO + Classical QUBO", "PPO+QUBO")
    .replace("PPO + QAOA", "PPO+QAOA")
    .replace("Static Shortest Path", "Static")
    .replace("Time-Dependent A*", "A*")
    .replace("Risk-Aware Greedy", "Greedy");

/** Network map with visible road links + selected route highlight. */
export function HqrlNetworkMap({ map, selected, candidates = [] }) {
  const nodeMap = useMemo(() => {
    const m = {};
    (map?.nodes || []).forEach((n) => {
      m[n.id] = n;
    });
    return m;
  }, [map]);

  const selectedRoads = new Set(selected?.roads || []);
  const rejectedRoads = new Set();
  (candidates || []).forEach((c) => {
    if (c.status === "REJECTED" || c.qubo_pass === false) {
      (c.roads || []).forEach((r) => {
        if (!selectedRoads.has(r)) rejectedRoads.add(r);
      });
    }
  });

  const pathD = (nodes) => {
    if (!nodes?.length) return "";
    return nodes
      .map((id, i) => {
        const n = nodeMap[id];
        if (!n) return "";
        return `${i === 0 ? "M" : "L"} ${n.x} ${n.y}`;
      })
      .filter(Boolean)
      .join(" ");
  };

  const w = map?.width || 1000;
  const h = map?.height || 640;

  return (
    <div className="hqrl-map-wrap" style={{ minHeight: 320 }}>
      <div className="hqrl-map-label">SYNTHETIC · IEEE HQRL · LIVE GRAPH</div>
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Evacuation road network">
        <defs>
          <marker id="hqrl-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="#4aa3ff" />
          </marker>
          <filter id="hqrl-glow">
            <feGaussianBlur stdDeviation="2.2" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Base road network — explicit stroke so links are always visible */}
        {(map?.edges || []).map((e) => {
          const a = nodeMap[e.u];
          const b = nodeMap[e.v];
          if (!a || !b) return null;
          const isSel = selectedRoads.has(e.id);
          const isRej = rejectedRoads.has(e.id);
          let stroke = EDGE_STROKE[e.status] || EDGE_STROKE.open;
          let width = 3.2;
          let dash = e.status === "closed" ? "7 5" : undefined;
          if (isSel) {
            stroke = EDGE_STROKE.selected;
            width = 5.5;
            dash = undefined;
          } else if (isRej) {
            stroke = EDGE_STROKE.rejected;
            dash = "4 4";
            width = 2.5;
          }
          return (
            <g key={e.id}>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={stroke}
                strokeWidth={width}
                strokeLinecap="round"
                strokeDasharray={dash}
                opacity={isSel ? 1 : 0.9}
              />
              <title>{`${e.id}: ${e.u}→${e.v} · ${e.status} · flood=${e.flood} · cong=${e.congestion}`}</title>
            </g>
          );
        })}

        {/* Animated selected evacuation path */}
        {selected?.nodes?.length ? (
          <path
            d={pathD(selected.nodes)}
            fill="none"
            stroke="#4aa3ff"
            strokeWidth="3"
            strokeDasharray="12 8"
            filter="url(#hqrl-glow)"
            markerEnd="url(#hqrl-arrow)"
          >
            <animate attributeName="stroke-dashoffset" from="0" to="40" dur="1.1s" repeatCount="indefinite" />
          </path>
        ) : null}

        {(map?.nodes || []).map((n) => {
          const isShelter = n.kind === "shelter";
          const isZone = n.kind === "zone";
          const onRoute = (selected?.nodes || []).includes(n.id);
          const fill = isShelter ? "#b07cff" : isZone ? "#f4f7fa" : onRoute ? "#5ec8d8" : "#6a9aaa";
          const r = isShelter || isZone ? 13 : 8;
          return (
            <g key={n.id}>
              {onRoute ? <circle cx={n.x} cy={n.y} r={r + 5} fill="none" stroke="#4aa3ff" strokeWidth="1.5" opacity="0.7" /> : null}
              <circle cx={n.x} cy={n.y} r={r} fill={fill} stroke="#0a1218" strokeWidth="2" />
              <text x={n.x} y={n.y - r - 5} textAnchor="middle" fill="#dff4fa" fontSize="11" fontWeight="600">
                {n.id}
              </text>
              {isShelter ? (
                <text x={n.x} y={n.y + r + 13} textAnchor="middle" fill="#d4b8ff" fontSize="10">
                  {n.pct ?? 0}% · {n.status}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      <div className="hqrl-legend">
        <span><i style={{ background: EDGE_STROKE.open }} /> Open</span>
        <span><i style={{ background: EDGE_STROKE.congested }} /> Congested</span>
        <span><i style={{ background: EDGE_STROKE.hazard }} /> Hazard</span>
        <span><i style={{ background: EDGE_STROKE.closed }} /> Closed</span>
        <span><i style={{ background: EDGE_STROKE.selected }} /> Selected route</span>
        <span><i style={{ background: "#b07cff" }} /> Shelter</span>
      </div>
    </div>
  );
}

function tipStyle() {
  return { background: "#0c1c24", border: "1px solid #3a6a78", fontSize: 12, borderRadius: 8 };
}

/** Mixed chart types for benchmark results. */
export function HqrlResultCharts({ graphs }) {
  const safe = (graphs?.safe_evacuation_pct || []).map((d) => ({ method: METHOD_SHORT(d.method), value: d.value, std: d.std || 0 }));
  const unsafe = (graphs?.unsafe_route_pct || []).map((d) => ({ method: METHOD_SHORT(d.method), value: d.value }));
  const clear = (graphs?.clearance_time_min || []).map((d) => ({ method: METHOD_SHORT(d.method), value: d.value }));
  const replan = (graphs?.replanning_latency_ms || []).map((d) => ({ method: METHOD_SHORT(d.method), value: d.value }));
  const radar = safe.map((s, i) => ({
    method: s.method,
    safe: s.value,
    unsafe: unsafe[i]?.value ?? 0,
    clearance: clear[i]?.value ?? 0,
    replan: replan[i]?.value ?? 0,
  }));

  if (!safe.length) return null;

  return (
    <div className="hqrl-charts hqrl-charts-mixed">
      <div className="hqrl-chart-box">
        <h3>Safe evacuation % (bars)</h3>
        <ResponsiveContainer width="100%" height="88%">
          <BarChart data={safe} margin={{ top: 8, right: 8, left: 0, bottom: 40 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,200,210,0.15)" />
            <XAxis dataKey="method" tick={{ fill: "#9eb8c2", fontSize: 9 }} interval={0} angle={-18} textAnchor="end" height={48} />
            <YAxis tick={{ fill: "#9eb8c2", fontSize: 10 }} unit="%" />
            <Tooltip contentStyle={tipStyle()} />
            <Bar dataKey="value" radius={[5, 5, 0, 0]}>
              {safe.map((_, i) => (
                <Cell key={i} fill={["#5ec8d8", "#3ecf8e", "#e6b84d", "#7aa7ff", "#b07cff", "#4aa3ff"][i % 6]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="hqrl-chart-box">
        <h3>Unsafe route % (line)</h3>
        <ResponsiveContainer width="100%" height="88%">
          <LineChart data={unsafe} margin={{ top: 8, right: 8, left: 0, bottom: 40 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,200,210,0.15)" />
            <XAxis dataKey="method" tick={{ fill: "#9eb8c2", fontSize: 9 }} interval={0} angle={-18} textAnchor="end" height={48} />
            <YAxis tick={{ fill: "#9eb8c2", fontSize: 10 }} unit="%" />
            <Tooltip contentStyle={tipStyle()} />
            <Line type="monotone" dataKey="value" stroke="#e85d6c" strokeWidth={2.5} dot={{ r: 4, fill: "#e85d6c" }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="hqrl-chart-box">
        <h3>Clearance time (area)</h3>
        <ResponsiveContainer width="100%" height="88%">
          <AreaChart data={clear} margin={{ top: 8, right: 8, left: 0, bottom: 40 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,200,210,0.15)" />
            <XAxis dataKey="method" tick={{ fill: "#9eb8c2", fontSize: 9 }} interval={0} angle={-18} textAnchor="end" height={48} />
            <YAxis tick={{ fill: "#9eb8c2", fontSize: 10 }} unit=" min" width={48} />
            <Tooltip contentStyle={tipStyle()} />
            <Area type="monotone" dataKey="value" stroke="#5ec8d8" fill="rgba(94,200,216,0.35)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="hqrl-chart-box">
        <h3>Replanning time (horizontal bars)</h3>
        <ResponsiveContainer width="100%" height="88%">
          <BarChart data={replan} layout="vertical" margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,200,210,0.15)" />
            <XAxis type="number" tick={{ fill: "#9eb8c2", fontSize: 10 }} unit=" ms" />
            <YAxis type="category" dataKey="method" width={72} tick={{ fill: "#9eb8c2", fontSize: 9 }} />
            <Tooltip contentStyle={tipStyle()} />
            <Bar dataKey="value" fill="#e6b84d" radius={[0, 5, 5, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="hqrl-chart-box hqrl-chart-wide">
        <h3>Method radar (safe % vs replan ms)</h3>
        <ResponsiveContainer width="100%" height="88%">
          <RadarChart data={radar}>
            <PolarGrid stroke="rgba(120,200,210,0.25)" />
            <PolarAngleAxis dataKey="method" tick={{ fill: "#9eb8c2", fontSize: 9 }} />
            <PolarRadiusAxis tick={{ fill: "#7a9aa8", fontSize: 9 }} />
            <Radar name="Safe %" dataKey="safe" stroke="#3ecf8e" fill="#3ecf8e" fillOpacity={0.25} />
            <Radar name="Replan ms" dataKey="replan" stroke="#e6b84d" fill="#e6b84d" fillOpacity={0.15} />
            <Legend wrapperStyle={{ fontSize: 11, color: "#9eb8c2" }} />
            <Tooltip contentStyle={tipStyle()} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** Attractive comparison table for benchmark methods. */
export function HqrlResultsTable({ table = [] }) {
  if (!table.length) return null;
  const bestSafe = Math.max(...table.map((r) => r.safe_evacuation_pct || 0));
  return (
    <div className="hqrl-table-wrap">
      <table className="hqrl-table hqrl-table-pretty">
        <thead>
          <tr>
            <th>Method</th>
            <th>Clearance (min)</th>
            <th>Safe %</th>
            <th>Unsafe %</th>
            <th>Capacity viol.</th>
            <th>Replan (ms)</th>
            <th>Solver (ms)</th>
          </tr>
        </thead>
        <tbody>
          {table.map((r) => {
            const top = r.safe_evacuation_pct === bestSafe;
            return (
              <tr key={r.method} className={top ? "hqrl-row-best" : ""}>
                <td>
                  {METHOD_SHORT(r.method)}
                  {top ? <span className="hqrl-pill-best">best safe</span> : null}
                </td>
                <td className="num">{r.clearance_time_min}</td>
                <td className="num">{r.safe_evacuation_pct}</td>
                <td className="num">{r.unsafe_route_pct}</td>
                <td className="num">{r.capacity_violations}</td>
                <td className="num">{r.replanning_latency_ms}</td>
                <td className="num">{r.solver_execution_ms}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
