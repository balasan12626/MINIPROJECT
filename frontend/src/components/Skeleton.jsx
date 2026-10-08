/** Loading placeholders for the scenario output area.
 *
 * The codebase had no skeleton vocabulary — only `.run-spinner`, `.kpi-loading`
 * and the blocking `.page-loader` overlay. These reuse the existing panel /
 * kpi shells so a loading box occupies exactly the space its real content
 * will, which is what stops the page jumping when results land.
 */

export function SkeletonLine({ w = "100%", h = 12 }) {
  return <span className="skel-line" style={{ width: w, height: h }} aria-hidden />;
}

/** Stand-in for a KpiCard while its step is running. */
export function SkeletonKpi({ label }) {
  return (
    <div className="panel kpi kpi-card skel-card" aria-busy="true">
      <div className="label">{label}</div>
      <SkeletonLine w="62%" h={26} />
      <SkeletonLine w="44%" h={10} />
    </div>
  );
}

/** Stand-in for a full output panel. `lines` shapes the body. */
export function SkeletonPanel({ title, lines = 4, tall = false }) {
  return (
    <div className="panel skel-card" aria-busy="true">
      <div className="panel-head">
        <h3>{title}</h3>
        <span className="kpi-loading">
          <span className="run-spinner" />
          LOADING
        </span>
      </div>
      {tall ? (
        <div className="skel-block" aria-hidden />
      ) : (
        <div className="skel-lines">
          {Array.from({ length: lines }, (_, i) => (
            <SkeletonLine key={i} w={`${92 - i * 11}%`} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Stand-in for a results table. */
export function SkeletonTable({ title, rows = 5 }) {
  return (
    <div className="panel skel-card" aria-busy="true">
      <div className="panel-head">
        <h3>{title}</h3>
        <span className="kpi-loading">
          <span className="run-spinner" />
          LOADING
        </span>
      </div>
      <div className="skel-lines">
        {Array.from({ length: rows }, (_, i) => (
          <SkeletonLine key={i} h={16} />
        ))}
      </div>
    </div>
  );
}

export default SkeletonPanel;
