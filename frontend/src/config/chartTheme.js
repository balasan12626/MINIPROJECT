// Shared Recharts styling. Values are CSS var() strings that resolve against
// the theme tokens in src/index.css (:root / body.light-theme), so charts
// follow the active theme without re-rendering. Recharts passes these through
// to SVG presentation attributes and inline styles, both of which accept var().
//
// Usage:
//   <CartesianGrid {...chartTheme.grid} />
//   <XAxis {...chartTheme.axis} dataKey="t" />
//   <Tooltip {...chartTheme.tooltip} />
//   <Line stroke={chartTheme.series[0]} />   // or chartTheme.status.sos for meaning

export const chartTheme = {
  grid: { stroke: "var(--grid)", strokeDasharray: "3 3" },
  axis: {
    stroke: "var(--axis)",
    tick: { fill: "var(--axis)", fontSize: 11 },
    tickLine: { stroke: "var(--axis)" },
    axisLine: { stroke: "var(--axis)" },
  },
  tooltip: {
    contentStyle: {
      background: "var(--card)",
      border: "1px solid var(--border)",
      borderRadius: 8,
      color: "var(--text)",
      boxShadow: "none",
    },
    labelStyle: { color: "var(--accent)" },
    itemStyle: { color: "var(--text)" },
    cursor: { stroke: "var(--border)", fill: "var(--accent-soft)" },
  },
  legend: { wrapperStyle: { color: "var(--muted)", fontSize: 12 } },
  // Categorical series order: theme accents first, then distinct hues that
  // read in both themes (no white/grey bars).
  series: [
    "var(--accent)",
    "var(--accent-2)",
    "var(--status-safe)",
    "var(--status-transport)",
    "var(--status-enroute)",
    "#f472b6",
  ],
  // Semantic colours — use these when the series *means* a status.
  status: {
    sos: "var(--status-sos)",
    assigned: "var(--status-assigned)",
    enroute: "var(--status-enroute)",
    transport: "var(--status-transport)",
    safe: "var(--status-safe)",
  },
  referenceLine: { stroke: "var(--status-sos)", strokeDasharray: "4 4" },
};

export default chartTheme;
