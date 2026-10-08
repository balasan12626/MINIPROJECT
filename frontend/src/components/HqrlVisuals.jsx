import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { chartTheme } from "../config/chartTheme.js";

const EDGE_STROKE = {
  selected: "var(--accent)",
  closed: "var(--status-sos)",
  hazard: "var(--status-enroute)",
  congested: "var(--status-assigned)",
  open: "var(--status-safe)",
  candidate: "var(--accent)",
  rejected: "var(--muted)",
};

const METHOD_SHORT = (m) =>
  String(m || "")
    .replace("PPO + Classical QUBO", "PPO+QUBO")
    .replace("PPO + QAOA", "PPO+QAOA")
    .replace("Static Shortest Path", "Static")
    .replace("Time-Dependent A*", "A*")
    .replace("Risk-Aware Greedy", "Greedy");

function clientToSvgPoint(svg, clientX, clientY) {
  if (!svg) return { x: 0, y: 0 };
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  const ctm = svg.getScreenCTM();
  if (!ctm) return { x: 0, y: 0 };
  const local = pt.matrixTransform(ctm.inverse());
  return { x: local.x, y: local.y };
}

/** Network map with drag-drop nodes + selected route highlight.
 * `animate={false}` stops the marching-ants route animation (pass it while the
 * map is off-screen so the browser is not repainting an invisible SVG). */
export const HqrlNetworkMap = memo(function HqrlNetworkMap({ map, selected, candidates = [], animate = true }) {
  const svgRef = useRef(null);
  const dragRef = useRef(null);
  const [positions, setPositions] = useState({});
  const [dragId, setDragId] = useState(null);
  const [activeId, setActiveId] = useState(null);

  const nodeKey = (map?.nodes || []).map((n) => n.id).join("|");

  // Init / rebuild only when node set changes — keep user drag positions across live polls
  useEffect(() => {
    setPositions((prev) => {
      const next = {};
      (map?.nodes || []).forEach((n) => {
        const keep = prev[n.id];
        next[n.id] = {
          ...n,
          x: keep ? Number(keep.x) : Number(n.x) || 0,
          y: keep ? Number(keep.y) : Number(n.y) || 0,
        };
      });
      return next;
    });
  }, [nodeKey, map?.width, map?.height]);

  // Merge non-position fields (pct/status) from live map without moving dragged nodes
  useEffect(() => {
    if (!map?.nodes?.length) return;
    setPositions((prev) => {
      if (!Object.keys(prev).length) return prev;
      const next = { ...prev };
      map.nodes.forEach((n) => {
        if (!next[n.id]) return;
        next[n.id] = {
          ...next[n.id],
          ...n,
          x: next[n.id].x,
          y: next[n.id].y,
        };
      });
      return next;
    });
  }, [map]);

  const nodeMap = useMemo(() => {
    const m = {};
    Object.values(positions).forEach((n) => {
      m[n.id] = n;
    });
    if (!Object.keys(m).length) {
      (map?.nodes || []).forEach((n) => {
        m[n.id] = n;
      });
    }
    return m;
  }, [positions, map]);

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

  const startDrag = useCallback((e, id) => {
    e.preventDefault();
    e.stopPropagation();
    const p = clientToSvgPoint(svgRef.current, e.clientX, e.clientY);
    const node = positions[id] || nodeMap[id];
    if (!node) return;
    dragRef.current = {
      id,
      ox: p.x - Number(node.x),
      oy: p.y - Number(node.y),
    };
    setDragId(id);
    setActiveId(id);
    e.currentTarget.setPointerCapture?.(e.pointerId);
  }, [positions, nodeMap]);

  const moveDrag = useCallback((e) => {
    const d = dragRef.current;
    if (!d) return;
    e.preventDefault();
    const p = clientToSvgPoint(svgRef.current, e.clientX, e.clientY);
    const x = Math.max(20, Math.min(w - 20, p.x - d.ox));
    const y = Math.max(20, Math.min(h - 20, p.y - d.oy));
    setPositions((prev) => {
      const cur = prev[d.id];
      if (!cur) return prev;
      return { ...prev, [d.id]: { ...cur, x, y } };
    });
  }, [w, h]);

  const stopDrag = useCallback((e) => {
    if (!dragRef.current) return;
    try {
      e.currentTarget.releasePointerCapture?.(e.pointerId);
    } catch {
      /* ignore */
    }
    dragRef.current = null;
    setDragId(null);
  }, []);

  const nodesList = Object.keys(positions).length
    ? Object.values(positions)
    : map?.nodes || [];

  return (
    <div className={`hqrl-map-wrap ${dragId ? "is-dragging" : ""}`} style={{ minHeight: 320 }}>
      <div className="hqrl-map-label">SYNTHETIC · IEEE HQRL · LIVE GRAPH · drag nodes</div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label="Evacuation road network — drag nodes to rearrange"
        className="hqrl-map-svg"
        onPointerMove={moveDrag}
        onPointerUp={stopDrag}
        onPointerLeave={stopDrag}
        onPointerCancel={stopDrag}
      >
        <defs>
          <marker id="hqrl-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="var(--accent)" />
          </marker>
          <filter id="hqrl-glow">
            <feGaussianBlur stdDeviation="2.2" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

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
              <title>{`${e.id}: ${e.u}→${e.v} · ${e.status}`}</title>
            </g>
          );
        })}

        {selected?.nodes?.length ? (
          <path
            d={pathD(selected.nodes)}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="3"
            strokeDasharray="12 8"
            filter="url(#hqrl-glow)"
            markerEnd="url(#hqrl-arrow)"
            pointerEvents="none"
          >
            {animate ? <animate attributeName="stroke-dashoffset" from="0" to="40" dur="1.1s" repeatCount="indefinite" /> : null}
          </path>
        ) : null}

        {nodesList.map((n) => {
          const isShelter = n.kind === "shelter";
          const isZone = n.kind === "zone";
          const onRoute = (selected?.nodes || []).includes(n.id);
          const fill = isShelter ? "var(--status-transport)" : isZone ? "var(--text)" : onRoute ? "var(--accent)" : "var(--muted)";
          const r = isShelter || isZone ? 13 : 8;
          const dragging = dragId === n.id;
          const active = activeId === n.id;
          return (
            <g
              key={n.id}
              className={`hqrl-node ${dragging ? "dragging" : ""} ${active ? "active" : ""}`}
              style={{ cursor: dragging ? "grabbing" : "grab" }}
              onPointerDown={(e) => startDrag(e, n.id)}
              onClick={() => setActiveId(n.id)}
            >
              {onRoute || active ? (
                <circle cx={n.x} cy={n.y} r={r + 6} fill="none" stroke="var(--accent)" strokeWidth="1.5" opacity="0.85" />
              ) : null}
              <circle
                cx={n.x}
                cy={n.y}
                r={dragging ? r + 2 : r}
                fill={fill}
                stroke={active ? "var(--text)" : "var(--card)"}
                strokeWidth={active ? 2.5 : 2}
              />
              <text x={n.x} y={n.y - r - 5} textAnchor="middle" fill="var(--text)" fontSize="11" fontWeight="600" pointerEvents="none">
                {n.id}
              </text>
              {isShelter ? (
                <text x={n.x} y={n.y + r + 13} textAnchor="middle" fill="var(--status-transport)" fontSize="10" pointerEvents="none">
                  {n.pct ?? 0}% · {n.status}
                </text>
              ) : null}
              <title>{`${n.id} · ${n.kind || "node"} — drag to move`}</title>
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
        <span><i style={{ background: "var(--status-transport)" }} /> Shelter</span>
        <span className="hqrl-drag-hint">Drag any node to rearrange the graph</span>
      </div>
      {activeId ? (
        <div className="hqrl-node-card">
          <b>{activeId}</b>
          <span>{nodeMap[activeId]?.kind || "node"}</span>
          {nodeMap[activeId]?.status ? <span>{nodeMap[activeId].status}</span> : null}
          {nodeMap[activeId]?.pct != null ? <span>{nodeMap[activeId].pct}% seats used</span> : null}
        </div>
      ) : null}
    </div>
  );
});



/** Mixed chart types for benchmark results. Memoised; animation off. */
export const HqrlResultCharts = memo(function HqrlResultCharts({ graphs }) {
  const { safe, unsafe, clear, replan, radar } = useMemo(() => {
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
    return { safe, unsafe, clear, replan, radar };
  }, [graphs]);

  if (!safe.length) return null;

  return (
    <div className="hqrl-charts hqrl-charts-mixed">
      <div className="hqrl-chart-box">
        <h3>Safe evacuation % (bars)</h3>
        <ResponsiveContainer width="100%" height="88%">
          <BarChart data={safe} margin={{ top: 8, right: 8, left: 0, bottom: 40 }}>
            <CartesianGrid {...chartTheme.grid} />
            <XAxis {...chartTheme.axis} dataKey="method" tick={{ fill: "var(--axis)", fontSize: 9 }} interval={0} angle={-18} textAnchor="end" height={48} />
            <YAxis {...chartTheme.axis} tick={{ fill: "var(--axis)", fontSize: 10 }} unit="%" />
            <Tooltip {...chartTheme.tooltip} />
            <Bar isAnimationActive={false} dataKey="value" radius={[5, 5, 0, 0]}>
              {safe.map((_, i) => (
                <Cell key={i} fill={chartTheme.series[i % chartTheme.series.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="hqrl-chart-box">
        <h3>Unsafe route % (line)</h3>
        <ResponsiveContainer width="100%" height="88%">
          <LineChart data={unsafe} margin={{ top: 8, right: 8, left: 0, bottom: 40 }}>
            <CartesianGrid {...chartTheme.grid} />
            <XAxis {...chartTheme.axis} dataKey="method" tick={{ fill: "var(--axis)", fontSize: 9 }} interval={0} angle={-18} textAnchor="end" height={48} />
            <YAxis {...chartTheme.axis} tick={{ fill: "var(--axis)", fontSize: 10 }} unit="%" />
            <Tooltip {...chartTheme.tooltip} />
            <Line isAnimationActive={false} type="monotone" dataKey="value" stroke="var(--status-sos)" strokeWidth={2.5} dot={{ r: 4, fill: "var(--status-sos)" }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="hqrl-chart-box">
        <h3>Clearance time (area)</h3>
        <ResponsiveContainer width="100%" height="88%">
          <AreaChart data={clear} margin={{ top: 8, right: 8, left: 0, bottom: 40 }}>
            <CartesianGrid {...chartTheme.grid} />
            <XAxis {...chartTheme.axis} dataKey="method" tick={{ fill: "var(--axis)", fontSize: 9 }} interval={0} angle={-18} textAnchor="end" height={48} />
            <YAxis {...chartTheme.axis} tick={{ fill: "var(--axis)", fontSize: 10 }} unit=" min" width={48} />
            <Tooltip {...chartTheme.tooltip} />
            <Area isAnimationActive={false} type="monotone" dataKey="value" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.3} strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="hqrl-chart-box">
        <h3>Replanning time (horizontal bars)</h3>
        <ResponsiveContainer width="100%" height="88%">
          <BarChart data={replan} layout="vertical" margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
            <CartesianGrid {...chartTheme.grid} />
            <XAxis {...chartTheme.axis} type="number" tick={{ fill: "var(--axis)", fontSize: 10 }} unit=" ms" />
            <YAxis {...chartTheme.axis} type="category" dataKey="method" width={72} tick={{ fill: "var(--axis)", fontSize: 9 }} />
            <Tooltip {...chartTheme.tooltip} />
            <Bar isAnimationActive={false} dataKey="value" fill="var(--status-assigned)" radius={[0, 5, 5, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="hqrl-chart-box hqrl-chart-wide">
        <h3>Method radar (safe % vs replan ms)</h3>
        <ResponsiveContainer width="100%" height="88%">
          <RadarChart data={radar}>
            <PolarGrid stroke="var(--grid)" />
            <PolarAngleAxis dataKey="method" tick={{ fill: "var(--axis)", fontSize: 9 }} />
            <PolarRadiusAxis tick={{ fill: "var(--axis)", fontSize: 9 }} />
            <Radar isAnimationActive={false} name="Safe %" dataKey="safe" stroke="var(--status-safe)" fill="var(--status-safe)" fillOpacity={0.25} />
            <Radar isAnimationActive={false} name="Replan ms" dataKey="replan" stroke="var(--status-assigned)" fill="var(--status-assigned)" fillOpacity={0.15} />
            <Legend {...chartTheme.legend} />
            <Tooltip {...chartTheme.tooltip} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
});

/** Attractive comparison table for benchmark methods. */
export const HqrlResultsTable = memo(function HqrlResultsTable({ table = [] }) {
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
});
