import { createContext, useContext, useEffect, useRef, useSyncExternalStore } from "react";
import { fetchSimState } from "../../services/api.js";
import { connectSocket } from "../../services/ws.js";

/** Tiny external store for the /simulation run view.
 *
 * One feed (`useSimFeed`) owns every request to /api/simulation/state and the
 * websocket subscription. Sections read narrow slices with `useSim*` selectors,
 * so a state update only re-renders the sections whose slice actually changed.
 *
 * Incoming states are structurally shared with the previous one
 * (`replaceEqualDeep`): unchanged sub-trees keep their identity, which is what
 * makes the selectors and React.memo effective. */

export const POLL_MS = 2000;
export const MIN_COMMIT_GAP_MS = 1000;

function isPlain(v) {
  return v !== null && typeof v === "object" && Object.getPrototypeOf(v) === Object.prototype;
}

export function replaceEqualDeep(prev, next) {
  if (prev === next) return prev;
  if (Array.isArray(prev) && Array.isArray(next)) {
    let same = prev.length === next.length;
    const out = new Array(next.length);
    for (let i = 0; i < next.length; i += 1) {
      out[i] = replaceEqualDeep(prev[i], next[i]);
      if (out[i] !== prev[i]) same = false;
    }
    return same ? prev : out;
  }
  if (isPlain(prev) && isPlain(next)) {
    const keys = Object.keys(next);
    let same = keys.length === Object.keys(prev).length;
    const out = {};
    for (const k of keys) {
      out[k] = replaceEqualDeep(prev[k], next[k]);
      if (out[k] !== prev[k] || !(k in prev)) same = false;
    }
    return same ? prev : out;
  }
  return next;
}

function isSoftFailure(d) {
  return Boolean(d && d.available === false && d.message);
}

export function createSimStore() {
  let state = { sim: null, progress: null, connIssue: "", explain: { data: null, loading: false, error: null } };
  const listeners = new Set();
  const emit = () => listeners.forEach((l) => l());

  const store = {
    getState: () => state,
    subscribe(l) {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    /** Commit a full state (or an updater). Soft network fallbacks are ignored
     * so a good run is never wiped by a transient error payload. */
    ingest({ sim: rawSim, progress: rawProgress } = {}) {
      let sim = state.sim;
      let progress = state.progress;
      if (rawSim !== undefined) {
        const raw = typeof rawSim === "function" ? rawSim(state.sim) : rawSim;
        if (raw && !isSoftFailure(raw)) {
          sim = replaceEqualDeep(state.sim, raw);
          if (raw.progress) progress = replaceEqualDeep(progress, raw.progress);
        }
      }
      if (rawProgress) progress = replaceEqualDeep(progress, rawProgress);
      if (sim === state.sim && progress === state.progress) return;
      state = { ...state, sim, progress };
      emit();
    },
    setSim(next) {
      store.ingest({ sim: next });
    },
    setConnIssue(msg) {
      const m = msg || "";
      if (m === state.connIssue) return;
      state = { ...state, connIssue: m };
      emit();
    },
    /** explain-v2 result for the current rain value (see ExplainController). */
    setExplain(patch) {
      state = { ...state, explain: { ...state.explain, ...patch } };
      emit();
    },
    /** Replaced by the live feed; manual "Retry now". */
    refresh: () => {},
    /** Replaced by ExplainController; the XAI panel's Retry. */
    retryExplain: () => {},
  };
  return store;
}

/** People still moving through the backend's rescue stage machine. The
 * backend advances a person only when the state is read, so polling has to
 * continue after the engine completes until every row reaches "rescued". */
export function rescueInProgress(sim) {
  return (sim?.contact_log || []).some((r) => r && (r.ops_status || "queued") !== "rescued");
}

export function shouldKeepPolling(sim) {
  if (!sim) return true;
  const status = sim.current?.run_status ?? sim.status;
  if (status === "running") return true;
  if (status === "completed") return rescueInProgress(sim);
  return false;
}

/** The single live feed for a run view. Rules:
 *  - poll every 2 s only while the run is live (running, or completed with
 *    rescues still advancing); zero periodic requests afterwards;
 *  - a websocket `simulation_state` carries the full state, so it replaces a
 *    poll instead of triggering one;
 *  - ≤ 1 store commit per second, whatever the event rate;
 *  - nothing while the tab is hidden; catch up on return;
 *  - every timer and the socket are released on unmount. */
export function useSimFeed(store) {
  useEffect(() => {
    let disposed = false;
    let pollTimer = null;
    let commitTimer = null;
    let refreshTimer = null;
    let inflight = false;
    let failStreak = 0;
    let lastDataAt = 0;
    let lastFetchAt = 0;
    let lastCommitAt = 0;
    let pendingSim = null;
    let pendingProgress = null;
    let pendingConversation = null;

    const hidden = () => typeof document !== "undefined" && document.hidden;
    const currentSim = () => pendingSim || store.getState().sim;

    function flush() {
      commitTimer = null;
      if (disposed || hidden()) return;
      lastCommitAt = Date.now();
      const simNext = pendingSim;
      const conv = pendingConversation;
      const prog = pendingProgress;
      pendingSim = null;
      pendingConversation = null;
      pendingProgress = null;
      let sim;
      if (simNext) sim = conv && !simNext.conversation ? { ...simNext, conversation: conv } : simNext;
      else if (conv) sim = (prev) => ({ ...(prev || {}), conversation: conv });
      store.ingest({ sim, progress: prog || undefined });
    }

    function scheduleCommit() {
      if (commitTimer || disposed) return;
      commitTimer = setTimeout(flush, Math.max(0, lastCommitAt + MIN_COMMIT_GAP_MS - Date.now()));
    }

    function receive(d) {
      lastDataAt = Date.now();
      pendingSim = d;
      scheduleCommit();
      schedulePoll();
    }

    function fail(msg) {
      failStreak += 1;
      if (failStreak >= 5) store.setConnIssue(msg);
    }

    async function pull() {
      if (inflight || disposed) return;
      inflight = true;
      lastFetchAt = Date.now();
      try {
        const d = await fetchSimState();
        if (disposed) return;
        if (isSoftFailure(d)) {
          fail(d.message || "Backend is not returning simulation state.");
        } else if (d) {
          failStreak = 0;
          store.setConnIssue("");
          receive(d);
        }
      } catch (err) {
        if (!disposed) fail(err?.message || "Lost connection to the backend.");
      } finally {
        inflight = false;
        if (!disposed) schedulePoll();
      }
    }

    function schedulePoll() {
      if (disposed || pollTimer || hidden()) return;
      if (!shouldKeepPolling(currentSim())) return;
      const gap = failStreak > 3 ? Math.min(15000, POLL_MS * 2 ** Math.min(failStreak - 3, 3)) : POLL_MS;
      const wait = Math.max(0, Math.max(lastDataAt, lastFetchAt) + gap - Date.now());
      pollTimer = setTimeout(() => {
        pollTimer = null;
        if (disposed || hidden()) return;
        // A websocket state arrived meanwhile — this poll is not needed yet.
        if (failStreak === 0 && Date.now() - lastDataAt < POLL_MS - 50) {
          schedulePoll();
          return;
        }
        pull();
      }, wait);
    }

    /** A discrete event (not a full state) — make sure fresh state follows
     * within ~1 s, unless a websocket state beats us to it. */
    function requestRefresh() {
      if (refreshTimer || disposed) return;
      const askedAt = Date.now();
      refreshTimer = setTimeout(() => {
        refreshTimer = null;
        if (disposed || hidden() || lastDataAt >= askedAt) return;
        pull();
      }, MIN_COMMIT_GAP_MS);
    }

    store.refresh = () => pull();

    const stopSocket = connectSocket((ev) => {
      if (!ev || disposed) return;
      if (ev.type === "simulation_state" && ev.payload && typeof ev.payload === "object" && ev.payload.status) {
        receive(ev.payload);
      } else if (ev.type === "pipeline_progress" && ev.payload?.mode === "simulation") {
        pendingProgress = ev.payload;
        scheduleCommit();
      } else if (ev.type === "agent_talk" && ev.payload && (ev.payload.mode || "simulation") === "simulation") {
        pendingConversation = ev.payload;
        scheduleCommit();
      } else if (ev.type === "simulation_event") {
        requestRefresh();
      }
    });

    // User actions (pause/resume/reset/override) commit straight into the
    // store; restart the poller if one of them made the run live again.
    const unsubscribe = store.subscribe(() => schedulePoll());

    const onVisibility = () => {
      if (hidden()) {
        if (pollTimer) clearTimeout(pollTimer);
        pollTimer = null;
        return;
      }
      if (pendingSim || pendingProgress || pendingConversation) scheduleCommit();
      schedulePoll();
    };
    if (typeof document !== "undefined") document.addEventListener("visibilitychange", onVisibility);

    pull();

    return () => {
      disposed = true;
      if (pollTimer) clearTimeout(pollTimer);
      if (commitTimer) clearTimeout(commitTimer);
      if (refreshTimer) clearTimeout(refreshTimer);
      unsubscribe();
      stopSocket();
      store.refresh = () => {};
      if (typeof document !== "undefined") document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [store]);
}

const SimStoreContext = createContext(null);
export const SimStoreProvider = SimStoreContext.Provider;

export function useSimStore() {
  return useContext(SimStoreContext);
}

function shallowEqual(a, b) {
  if (a === b) return true;
  if (!a || !b || typeof a !== "object" || typeof b !== "object") return false;
  const ka = Object.keys(a);
  if (ka.length !== Object.keys(b).length) return false;
  for (const k of ka) if (!Object.is(a[k], b[k])) return false;
  return true;
}

/** Subscribe to a slice of `{ sim, progress, connIssue, explain }`. The selector may
 * return a fresh object of stable parts — it is compared shallowly, so the
 * component re-renders only when one of those parts changes. */
export function useSim(selector) {
  const store = useSimStore();
  const cache = useRef(undefined);
  const get = () => {
    const next = selector(store.getState());
    if (cache.current !== undefined && shallowEqual(cache.current, next)) return cache.current;
    cache.current = next;
    return next;
  };
  return useSyncExternalStore(store.subscribe, get, get);
}
