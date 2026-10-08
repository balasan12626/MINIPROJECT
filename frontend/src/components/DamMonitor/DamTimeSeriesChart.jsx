import { useMemo } from "react";
import {
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const THRESHOLD_STYLE = {
  normal: { color: "#3ee0a0", label: "Normal" },
  warning: { color: "#f5c542", label: "Warning" },
  high_risk: { color: "#f0a04a", label: "High risk" },
  critical: { color: "#ff5d6c", label: "Critical" },
};

/** Time → predicted water level, with horizontal threshold reference lines. */
export default function DamTimeSeriesChart({ projection }) {
  const data = useMemo(() => {
    const series = projection?.series || [];
    if (series.length <= 150) return series;
    const step = Math.ceil(series.length / 150);
    return series.filter((_, i) => i % step === 0 || i === series.length - 1);
  }, [projection]);

  if (!projection || !data.length) {
    return <div className="muted">Run a simulation to see the predicted water-level trajectory.</div>;
  }
  const thresholds = projection.thresholds_m || {};

  return (
    <div style={{ height: 280 }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <XAxis dataKey="hour" stroke="#8aa3b0" label={{ value: "Forecast hour", position: "insideBottom", offset: -2, fill: "#8aa3b0", fontSize: 11 }} />
          <YAxis yAxisId="left" stroke="#8aa3b0" width={44} label={{ value: "level (m MSL)", angle: -90, position: "insideLeft", fill: "#8aa3b0", fontSize: 11 }} />
          <YAxis yAxisId="right" orientation="right" stroke="#8aa3b0" width={44} label={{ value: "rain mm / flow cumec", angle: 90, position: "insideRight", fill: "#8aa3b0", fontSize: 11 }} />
          <Tooltip formatter={(value, name) => [value, name]} labelFormatter={(h) => `hour ${h}`} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {Object.entries(thresholds).map(([key, level]) => {
            const style = THRESHOLD_STYLE[key];
            if (!style) return null;
            return (
              <ReferenceLine
                key={key}
                yAxisId="left"
                y={level}
                stroke={style.color}
                strokeDasharray="4 4"
                label={{ value: `${style.label} (${level}m)`, fill: style.color, fontSize: 10, position: "right" }}
              />
            );
          })}
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="predicted_level_m"
            stroke="#5ce1ff"
            strokeWidth={2.5}
            dot={false}
            name="predicted level (m)"
            isAnimationActive={false}
          />
          <Line yAxisId="right" type="monotone" dataKey="rainfall_mm" stroke="#c084fc" dot={false} name="rainfall (mm)" isAnimationActive={false} />
          <Line yAxisId="right" type="monotone" dataKey="inflow_cumec" stroke="#4aa3ff" dot={false} name="inflow (cumec)" isAnimationActive={false} />
          <Line yAxisId="right" type="monotone" dataKey="outflow_cumec" stroke="#f0a04a" dot={false} name="outflow (cumec)" isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
