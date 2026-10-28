import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { chartTheme } from "../../config/chartTheme.js";

const THRESHOLD_STYLE = {
  normal: { color: "var(--sev-green)", label: "Normal" },
  warning: { color: "var(--sev-yellow)", label: "Warning" },
  high_risk: { color: "var(--status-enroute)", label: "High risk" },
  critical: { color: "var(--sev-red)", label: "Critical" },
};

const round = (v) => Math.round(v * 100) / 100;

/** Forecast hour → predicted reservoir level, with the threshold bands, and
 * a second panel for rainfall / inflow / outflow. The level axis is fitted to
 * the projection and its thresholds (a 0–600 m axis made a 489 m level look
 * like a flat line). */
export default function DamTimeSeriesChart({ projection }) {
  const data = useMemo(() => {
    const series = projection?.series || [];
    if (series.length <= 150) return series;
    const step = Math.ceil(series.length / 150);
    return series.filter((_, i) => i % step === 0 || i === series.length - 1);
  }, [projection]);

  const thresholds = useMemo(() => projection?.thresholds_m || {}, [projection]);
  const domain = useMemo(() => {
    const levels = data.map((d) => d.predicted_level_m).filter((v) => typeof v === "number");
    if (!levels.length) return ["auto", "auto"];
    const tv = Object.values(thresholds).filter((v) => typeof v === "number");
    const lo = Math.min(...levels, ...tv.filter((v) => v >= Math.min(...levels) - 15));
    const hi = Math.max(...levels, ...tv.filter((v) => v <= Math.max(...levels) + 15));
    const pad = Math.max(0.5, (hi - lo) * 0.12);
    return [round(lo - pad), round(hi + pad)];
  }, [data, thresholds]);

  if (!projection || !data.length) {
    return <div className="muted">Run a simulation to see the predicted water-level trajectory.</div>;
  }

  return (
    <div className="dam-chart-stack">
      <div style={{ height: 260 }}>
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 8, right: 86, left: 4, bottom: 0 }}>
            <defs>
              <linearGradient id="damLevelFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid {...chartTheme.grid} />
            <XAxis {...chartTheme.axis} dataKey="hour" unit="h" />
            <YAxis {...chartTheme.axis} domain={domain} width={52} tickFormatter={(v) => v.toFixed(1)} label={{ value: "m MSL", angle: -90, position: "insideLeft", fill: "var(--axis)", fontSize: 11 }} />
            <Tooltip {...chartTheme.tooltip} formatter={(v) => [`${v} m MSL`, "Predicted level"]} labelFormatter={(h) => `Forecast hour ${h}`} />
            {Object.entries(thresholds).map(([key, level]) => {
              const style = THRESHOLD_STYLE[key];
              if (!style || level < domain[0] || level > domain[1]) return null;
              return (
                <ReferenceLine
                  key={key}
                  y={level}
                  stroke={style.color}
                  strokeDasharray="5 4"
                  label={{ value: `${style.label} ${level} m`, fill: style.color, fontSize: 10, position: "right" }}
                />
              );
            })}
            <Area
              type="monotone"
              dataKey="predicted_level_m"
              stroke="var(--accent)"
              strokeWidth={2.5}
              fill="url(#damLevelFill)"
              dot={false}
              name="Predicted level (m MSL)"
              isAnimationActive={false}
              baseValue={domain[0]}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div style={{ height: 170 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 4, right: 86, left: 4, bottom: 0 }}>
            <CartesianGrid {...chartTheme.grid} />
            <XAxis {...chartTheme.axis} dataKey="hour" unit="h" />
            <YAxis {...chartTheme.axis} yAxisId="flow" width={58} unit="" />
            <YAxis {...chartTheme.axis} yAxisId="rain" orientation="right" width={48} unit=" mm" />
            <Tooltip {...chartTheme.tooltip} labelFormatter={(h) => `Forecast hour ${h}`} />
            <Legend {...chartTheme.legend} />
            <Line yAxisId="flow" type="monotone" dataKey="inflow_cumec" stroke="var(--status-safe)" strokeWidth={2} dot={false} name="Inflow (cumec)" isAnimationActive={false} />
            <Line yAxisId="flow" type="monotone" dataKey="outflow_cumec" stroke="var(--status-enroute)" strokeWidth={2} dot={false} name="Outflow (cumec)" isAnimationActive={false} />
            <Line yAxisId="rain" type="monotone" dataKey="rainfall_mm" stroke="var(--status-transport)" strokeWidth={1.8} dot={false} name="Rainfall (mm)" isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
