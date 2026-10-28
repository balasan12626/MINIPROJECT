import { memo, useEffect, useState } from "react";
import { getJson } from "../../services/api.js";

/** One stored, script-generated result (GET /api/benchmark/stored/{name}).
 * Never computed in the browser or in a request — the card only shows the file,
 * or the command that generates it. `children(data)` renders the body. */
function StoredResultCard({ name, title, children, perCity = true }) {
  const [city, setCity] = useState(null);
  const [data, setData] = useState(undefined);
  useEffect(() => {
    let alive = true;
    const q = perCity && city ? `?city=${encodeURIComponent(city)}` : "";
    getJson(`/api/benchmark/stored/${name}${q}`).then((d) => alive && setData(d));
    return () => {
      alive = false;
    };
  }, [name, city, perCity]);
  const missing = data && data.available === false;
  return (
    <div className="panel stored-result">
      <div className="panel-head">
        <h3>{title}</h3>
        {perCity && data?.available_cities?.length ? (
          <select aria-label={`${title} city`} value={data.city || city || ""} onChange={(e) => setCity(e.target.value)}>
            {data.available_cities.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      {data === undefined ? <p className="hint">Loading…</p> : null}
      {missing ? <p className="hint">{String(data.message || "Not generated yet").replace(/^DATA UNAVAILABLE: /, "")}</p> : null}
      {data && !missing ? children(data) : null}
    </div>
  );
}

export default memo(StoredResultCard);
