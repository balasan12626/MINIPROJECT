/** Feed helpers shared by the timeline, the agent conversation and any other
 * append-only list on the live pages.
 *
 * `collapseFeed` folds identical consecutive entries into one row with a
 * count ("Flood probability 95% ×12") and keeps only the newest `cap` rows,
 * so a long run never grows the DOM without bound. */
export function collapseFeed(items, { key = (x) => x, cap = 50 } = {}) {
  const out = [];
  for (const item of items || []) {
    const k = key(item);
    const prev = out[out.length - 1];
    if (prev && prev.key === k) {
      prev.count += 1;
      prev.last = item;
    } else {
      out.push({ key: k, first: item, last: item, count: 1 });
    }
  }
  return out.length > cap ? out.slice(-cap) : out;
}

/** Evenly thin a long series down to at most `max` points (always keeps the
 * first and last point, so the chart's range and latest value are exact). */
export function decimate(rows, max = 200) {
  if (!Array.isArray(rows) || rows.length <= max) return rows || [];
  const step = (rows.length - 1) / (max - 1);
  const out = new Array(max);
  for (let i = 0; i < max; i += 1) out[i] = rows[Math.round(i * step)];
  return out;
}

/** Trailing throttle: calls `fn` with the latest args at most once per `ms`.
 * `cancel()` drops a pending call — call it on unmount. */
export function createThrottle(fn, ms) {
  let last = 0;
  let timer = null;
  let args = null;
  const run = () => {
    timer = null;
    last = Date.now();
    const a = args;
    args = null;
    fn(...(a || []));
  };
  const throttled = (...next) => {
    args = next;
    if (timer) return;
    timer = setTimeout(run, Math.max(0, last + ms - Date.now()));
  };
  throttled.cancel = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    args = null;
  };
  return throttled;
}
