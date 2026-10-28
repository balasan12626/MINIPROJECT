import { memo } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartTheme } from "../../config/chartTheme.js";
import { formatTimeIST } from "../../utils/time.js";

/** F18 — the forecast series that drives this run's rainfall (served by the
 * backend in state.rain_forecast). Labelled forecast, with source and fetch time. */
function RainForecastCard({ forecast, tick }) {
  if (!forecast) return null;
  const data = (forecast.per_tick || []).map((p) => ({ tick: p.tick, day: p.rainfall_mm, hour: p.rainfall_1h_mm }));
  const now = data.find((d) => d.tick === tick);
  return (
    <div className="panel rain-forecast-card">
      <div className="panel-head">
        <h3>Rainfall — forecast (Open-Meteo)</h3>
        <span className="badge sim">forecast, not observed</span>
      </div>
      <p className="hint">
        Each tick uses the forecast 24-hour rainfall total starting at that tick&apos;s simulated time
        {now ? ` — now ${now.day.toFixed(1)} mm / 24 h, ${now.hour.toFixed(1)} mm this hour` : ""}. Fetched{" "}
        {forecast.fetched_at ? formatTimeIST(forecast.fetched_at) : "—"} for {forecast.lat}, {forecast.lon}.
      </p>
      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ left: 4, right: 12, top: 6, bottom: 4 }}>
            <CartesianGrid {...chartTheme.grid} />
            <XAxis dataKey="tick" {...chartTheme.axis} label={{ value: "tick", position: "insideBottomRight", offset: -2, fill: "var(--axis)", fontSize: 11 }} />
            <YAxis {...chartTheme.axis} unit=" mm" width={56} />
            <Tooltip {...chartTheme.tooltip} />
            <Line type="monotone" dataKey="day" name="24-h total (mm)" stroke={chartTheme.series?.[0] || "var(--accent)"} dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="hour" name="this hour (mm)" stroke={chartTheme.series?.[1] || "var(--warn)"} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="hint">{forecast.attribution}</p>
    </div>
  );
}

export default memo(RainForecastCard);
