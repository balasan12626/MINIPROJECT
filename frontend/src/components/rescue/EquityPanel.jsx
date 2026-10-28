import { memo } from "react";

const n = (v) => (v == null ? "—" : v);

function GroupTable({ title, rows }) {
  if (!rows?.length) return null;
  return (
    <div className="table-wrap">
      <table className="data-table">
        <caption>{title}</caption>
        <thead>
          <tr>
            <th>Group</th>
            <th>Safe / total</th>
            <th>To pickup p50 / p90</th>
            <th>To safety p50 / p90</th>
            <th>Still waiting (longest)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((g) => (
            <tr key={g.group} className={g.flag ? "is-flagged" : ""}>
              <td>
                {g.flag ? "⚠ " : ""}
                {g.group}
              </td>
              <td>
                {g.served}/{g.people}
              </td>
              <td>
                {n(g.pickup_p50)} / {n(g.pickup_p90)}
              </td>
              <td>
                {n(g.safe_p50)} / {n(g.safe_p90)}
              </td>
              <td>
                {g.still_waiting}
                {g.longest_wait_min != null ? ` (${g.longest_wait_min} min)` : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** F14 — who waits longer, by vulnerability and by K-means cluster. Every
 * number comes from equity_board() over the stage machine's timestamps. */
function EquityPanel({ equity, title = "Fairness — who waits longer?" }) {
  if (!equity) return null;
  const o = equity.overall || {};
  return (
    <div className="panel equity-panel">
      <div className="panel-head">
        <h3>{title}</h3>
        <span className={`badge ${equity.flagged?.length ? "warn" : "live"}`}>
          {equity.flagged?.length ? `${equity.flagged.length} group(s) flagged` : "no group flagged"}
        </span>
      </div>
      <p className="hint">
        Overall: {o.served}/{o.people} safe · median {n(o.safe_p50)} min, p90 {n(o.safe_p90)} min to safety ({equity.units}).{" "}
        {equity.rule}.
        {equity.flagged?.length ? ` Flagged: ${equity.flagged.join(", ")}.` : ""}
      </p>
      <GroupTable title="By vulnerability" rows={equity.by_vulnerability} />
      <GroupTable title="By area (K-means cluster)" rows={equity.by_cluster} />
    </div>
  );
}

export default memo(EquityPanel);
