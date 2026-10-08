/** Single timestamp formatter for the whole UI — always Asia/Kolkata (IST).
 *
 * Backend timestamps are ISO strings, often UTC without a "Z" suffix. A naive
 * ISO string is treated as UTC so the roster and the feed never disagree. */
const TZ = "Asia/Kolkata";

const timeFmt = new Intl.DateTimeFormat("en-IN", { timeZone: TZ, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const dateTimeFmt = new Intl.DateTimeFormat("en-IN", { timeZone: TZ, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

export function toDate(value) {
  if (value == null || value === "") return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value === "number") return new Date(value < 1e12 ? value * 1000 : value);
  const s = String(value);
  const naiveIso = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s);
  const d = new Date(naiveIso ? `${s}Z` : s);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "18:18:05 IST" */
export function formatTimeIST(value, fallback = "—") {
  const d = toDate(value);
  return d ? `${timeFmt.format(d)} IST` : fallback;
}

/** "24 Sept, 18:18:05 IST" */
export function formatDateTimeIST(value, fallback = "—") {
  const d = toDate(value);
  return d ? `${dateTimeFmt.format(d)} IST` : fallback;
}
