import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { buildEventFeed, deriveRescueOps, serverClockOffset } from "../state/rescueOps.js";
import { collapseFeed } from "../utils/feed.js";

/** Newest-first feed, identical consecutive rows folded (×N), capped at 50. */
function collapsedFeed(sim) {
  const chronological = buildEventFeed(sim, 300).reverse();
  return collapseFeed(chronological, {
    key: (e) => `${e.kind}|${e.stage || ""}|${e.who}|${e.text}`,
    cap: 50,
  })
    .map((g) => ({ ...g.last, count: g.count }))
    .reverse();
}

/** Live rescue-operations view model.
 *
 * Re-derives once per backend poll (~1.2 s). It deliberately does NOT hold a
 * per-frame position: smooth movement is done inside each marker with
 * requestAnimationFrame + marker.setLatLng(), so a 60 fps animation causes
 * zero React re-renders. See components/rescue/LiveRescueMap.jsx.
 *
 * `paused` freezes the VIEW only — polling and animation stop, the backend run
 * is untouched. The backend's own pause/resume is not used because
 * SimulationEngine.resume() re-enters _loop() and re-runs _ingest_citizens(),
 * which wipes every person's in-flight progress.
 */
export function useRescueOps(sim) {
  const [paused, setPaused] = useState(false);
  // Frozen snapshot taken at the moment of pausing, so the view holds still.
  const frozenRef = useRef(null);

  // The clock offset must be STABLE. Recomputing `newest - Date.now()` every
  // poll makes `Date.now() + offset` collapse to `newest`, so the derived
  // "now" never advances and every unit freezes mid-leg. Keep the largest
  // correction observed instead: that is the real "server is ahead by X".
  const offsetRef = useRef(0);

  const live = useMemo(() => {
    const seen = serverClockOffset(sim, Date.now());
    if (seen > offsetRef.current) offsetRef.current = seen;
    const offset = offsetRef.current;
    return {
      offset,
      ops: deriveRescueOps(sim, Date.now() + offset),
      feed: collapsedFeed(sim),
    };
  }, [sim]);

  useEffect(() => {
    if (paused) frozenRef.current = live;
    else frozenRef.current = null;
    // Only re-freeze when the pause flag flips, not on every poll.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paused]);

  const view = paused && frozenRef.current ? frozenRef.current : live;

  const toggle = useCallback(() => setPaused((p) => !p), []);

  return { ...view, paused, setPaused, togglePaused: toggle };
}

/** Tracks which people just changed stage, so a row can flash exactly once.
 *
 * `sim.citizens` is a fresh array identity on every poll, so a naive effect
 * dependency fires 1.2×/s. The backend's `ops_stage_at` is the authoritative
 * "this stage began at" stamp, so we key on it: the flash is idempotent across
 * polls and survives a remount.
 */
export function useStageChanges(people, windowMs = 2600) {
  const seenRef = useRef(new Map());
  const flashedAtRef = useRef(new Map());
  const [, bump] = useState(0);

  useEffect(() => {
    const seen = seenRef.current;
    const now = Date.now();
    let any = false;
    for (const p of people) {
      const token = `${p.stage}@${p.stageStartedAt ?? 0}`;
      const prev = seen.get(p.key);
      if (prev !== undefined && prev !== token) {
        flashedAtRef.current.set(p.key, now);
        any = true;
      }
      seen.set(p.key, token);
    }
    if (!any) return undefined;
    // One timer to re-render once the window closes. Expiry is stored as a
    // timestamp rather than relying on this timer surviving — the 1.2 s poll
    // re-renders anyway, and an earlier version lost every un-flash because
    // the effect cleanup cancelled the pending timer on the next poll.
    const t = window.setTimeout(() => bump((n) => n + 1), windowMs + 60);
    return () => window.clearTimeout(t);
  }, [people, windowMs]);

  const now = Date.now();
  const flashing = new Set();
  for (const [key, at] of flashedAtRef.current) {
    if (now - at < windowMs) flashing.add(key);
    else flashedAtRef.current.delete(key);
  }
  return flashing;
}

/** "New SOS · <name> · <people> people" toasts.
 *
 * The first non-empty roster of a run is the scenario's own SOS list, so it
 * only seeds the seen-set; any person that appears after that (SEND SOS, the
 * voice agent, an SOS arriving mid-run) raises one toast. Keyed on
 * citizen_name, which the backend keeps unique. */
export function useNewSosToasts(runId, people, ttlMs = 4500) {
  const seenRef = useRef({ runId: undefined, keys: null });
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    const seen = seenRef.current;
    if (seen.runId !== runId) {
      seenRef.current = { runId, keys: null };
    }
    const cur = seenRef.current;
    if (!people.length) return;
    if (cur.keys === null) {
      cur.keys = new Set(people.map((p) => p.key));
      return;
    }
    const fresh = people.filter((p) => !cur.keys.has(p.key));
    if (!fresh.length) return;
    for (const p of fresh) cur.keys.add(p.key);
    const now = Date.now();
    setToasts((prev) => [
      ...prev,
      ...fresh.map((p) => ({ id: `${p.key}@${now}`, key: p.key, name: p.name, people: p.people, at: now })),
    ]);
  }, [runId, people]);

  useEffect(() => {
    if (!toasts.length) return undefined;
    const oldest = Math.min(...toasts.map((t) => t.at));
    const t = window.setTimeout(
      () => setToasts((prev) => prev.filter((x) => Date.now() - x.at < ttlMs)),
      Math.max(50, oldest + ttlMs - Date.now())
    );
    return () => window.clearTimeout(t);
  }, [toasts, ttlMs]);

  const dismiss = useCallback((id) => setToasts((prev) => prev.filter((t) => t.id !== id)), []);
  return { toasts, dismiss };
}
