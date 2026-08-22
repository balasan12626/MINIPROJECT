import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export default function HistoryChart({ history = [] }) {
  if (!history.length) return <div className="muted">No series yet</div>;
  const data = history.map((h, i) => ({
    t: Number(h.sim_time_sec != null ? h.sim_time_sec : i),
    i,
    p: h.flood_probability != null ? Math.round(h.flood_probability * 1000) / 10 : null,
    rain: h.rainfall_mm != null ? Math.round(h.rainfall_mm * 10) / 10 : null,
    river: h.river_m != null ? Math.round(h.river_m * 10) / 10 : null,
    edit: h.source === "operator_edit" ? "card edit" : "",
  }));
  const stamp = `${data.length}-${data[data.length - 1]?.p}-${data[data.length - 1]?.rain}`;
  return (
    <div style={{ height: 180 }} key={stamp}>
      <ResponsiveContainer>
        <LineChart data={data}>
          <XAxis dataKey="t" stroke="#8aa3b0" />
          <YAxis stroke="#8aa3b0" />
          <Tooltip
            formatter={(value, name) => [value, name]}
            labelFormatter={(_, pts) => {
              const row = pts?.[0]?.payload;
              return `t=${row?.t}s${row?.edit ? " · operator edit" : ""}`;
            }}
          />
          <Line type="monotone" dataKey="p" stroke="#ff5d6c" dot={{ r: 2 }} name="flood %" />
          <Line type="monotone" dataKey="rain" stroke="#5ce1ff" dot={{ r: 2 }} name="rain mm" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
