import { memo, useMemo } from "react";
import { Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { decimate } from "../utils/feed.js";
import { chartTheme } from "../config/chartTheme.js";

const MAX_POINTS = 200;
const MARGIN = { top: 4, right: 8, left: 0, bottom: 0 };
const AXIS = "var(--axis)";
const X_LABEL = { value: "Simulation time (s)", position: "insideBottom", offset: -2, fill: AXIS, fontSize: 11 };
const Y_LEFT_LABEL = { value: "% / m", angle: -90, position: "insideLeft", fill: AXIS, fontSize: 11 };
const Y_RIGHT_LABEL = { value: "rain mm", angle: 90, position: "insideRight", fill: AXIS, fontSize: 11 };
const tooltipFormatter = (value, name) => [value, name];
const tooltipLabel = (_, pts) => {
  const row = pts?.[0]?.payload;
  return `t=${row?.t}s${row?.edit ? " · operator edit" : ""}`;
};

const round = (v, f) => (v != null ? Math.round(v * f) / f : null);

/** Live flood-dynamics series — driven entirely by sim.history (real
 * simulation ticks). Empty until the run has ticks; stops advancing when
 * paused (history stops growing); clears on reset (history becomes []).
 *
 * Perf: data is memoised on the history identity (the sim store keeps it
 * stable between unchanged polls), decimated to ≤200 points, and animation is
 * off, so a new tick only redraws the lines instead of remounting the chart. */
function HistoryChart({ history }) {
  const data = useMemo(
    () =>
      decimate(history || [], MAX_POINTS).map((h, i) => ({
        t: Number(h.sim_time_sec != null ? h.sim_time_sec : i),
        p: h.flood_probability != null ? Math.round(h.flood_probability * 1000) / 10 : null,
        rain: round(h.rainfall_mm, 10),
        river: round(h.river_m, 10),
        peak: round(h.predicted_peak_flood_level_m, 100),
        edit: h.source === "operator_edit" ? "card edit" : "",
      })),
    [history]
  );
  if (!data.length) return <div className="muted">Awaiting first simulation tick…</div>;
  return (
    <div style={{ height: 220 }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={MARGIN}>
          <XAxis {...chartTheme.axis} dataKey="t" label={X_LABEL} />
          <YAxis {...chartTheme.axis} yAxisId="left" width={36} label={Y_LEFT_LABEL} />
          <YAxis {...chartTheme.axis} yAxisId="right" orientation="right" width={36} label={Y_RIGHT_LABEL} />
          <Tooltip {...chartTheme.tooltip} formatter={tooltipFormatter} labelFormatter={tooltipLabel} isAnimationActive={false} />
          <Legend {...chartTheme.legend} />
          <Line isAnimationActive={false} yAxisId="left" type="monotone" dataKey="p" stroke={chartTheme.status.sos} dot={false} name="flood %" connectNulls />
          <Line isAnimationActive={false} yAxisId="left" type="monotone" dataKey="river" stroke="var(--muted)" dot={false} name="river m" connectNulls />
          <Line isAnimationActive={false} yAxisId="left" type="monotone" dataKey="peak" stroke={chartTheme.status.transport} dot={false} name="predicted peak m" connectNulls />
          <Line isAnimationActive={false} yAxisId="right" type="monotone" dataKey="rain" stroke="var(--accent)" dot={false} name="rain mm" connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default memo(HistoryChart);
