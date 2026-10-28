import { memo } from "react";

const f1 = (v) => (v == null ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 1 }));

/** F28 — supply runs from state.supply: each shelter's daily need at Sphere
 * rates for the people delivered there this run, stock left, and the
 * (assumed, labelled) truck fleet. Renders nothing when supply runs are off. */
function SupplyPanel({ supply }) {
  if (!supply) return null;
  const shelters = supply.shelters || [];
  const trucks = supply.trucks || [];
  return (
    <div className="panel supply-panel">
      <div className="panel-head">
        <h3>Food &amp; water supply runs</h3>
        <span className="badge sim">assumed fleet</span>
      </div>
      <p className="hint">
        {supply.rates_source}. Labelled assumptions — {supply.assumed}.
      </p>
      {shelters.length ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Shelter</th>
                <th>People delivered</th>
                <th>Water / day</th>
                <th>Food / day</th>
                <th>Stock left</th>
                <th>Delivered</th>
                <th>Truck on the way</th>
              </tr>
            </thead>
            <tbody>
              {shelters.map((s) => (
                <tr key={s.name} className={s.hours_of_stock_left != null && s.hours_of_stock_left < 12 ? "is-low" : ""}>
                  <td>{s.name}</td>
                  <td>{s.people}</td>
                  <td>{f1(s.need_water_l_per_day)} L</td>
                  <td>{f1(s.need_food_kcal_per_day)} kcal</td>
                  <td>{s.hours_of_stock_left != null ? `${f1(s.hours_of_stock_left)} h` : "—"}</td>
                  <td>{f1(s.delivered_person_days)} person-days</td>
                  <td>{s.incoming?.length ? s.incoming.join(", ") : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="hint">No one has been delivered to a shelter yet, so there is no need to supply.</p>
      )}
      <ul className="supply-trucks">
        {trucks.map((t) => (
          <li key={t.name}>
            🚚 <b>{t.name}</b> ({t.home}) —{" "}
            {t.leg ? `driving to ${t.leg.to}, ${f1(t.leg.km)} km by road` : "idle"} · {t.trips} trip(s)
          </li>
        ))}
      </ul>
    </div>
  );
}

export default memo(SupplyPanel);
