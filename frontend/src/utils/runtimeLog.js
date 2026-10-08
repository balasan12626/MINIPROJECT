/** Global runtime diagnostics, installed once from main.jsx.
 *
 * - Uncaught errors and unhandled promise rejections are logged with a clear
 *   prefix (React render errors are logged by ErrorBoundary).
 * - A low-memory warning is printed when the tab's JS heap nears its limit.
 *   (Chromium-only API; this machine has 8 GB RAM, and a tab killed for lack
 *   of memory shows as "STATUS_BREAKPOINT" / "page is having a problem".) */

const PREFIX = "[AquaSentinel]";
const HEAP_WARN_RATIO = 0.7;
const HEAP_CHECK_MS = 15000;

export function installRuntimeLogging() {
  if (typeof window === "undefined" || window.__aquaRuntimeLog) return;
  window.__aquaRuntimeLog = true;

  window.addEventListener("error", (e) => {
    // Resource load failures (img/script) arrive here with no `error` object.
    if (e.error || e.message) {
      console.error(`${PREFIX} Uncaught error: ${e.message}`, e.filename ? `at ${e.filename}:${e.lineno}:${e.colno}` : "", e.error || "");
    }
  });

  window.addEventListener("unhandledrejection", (e) => {
    const r = e.reason;
    console.error(`${PREFIX} Unhandled promise rejection: ${r?.message || r}`, r);
  });

  const mem = window.performance?.memory;
  if (mem && typeof mem.jsHeapSizeLimit === "number") {
    let warned = false;
    window.setInterval(() => {
      const used = mem.usedJSHeapSize / mem.jsHeapSizeLimit;
      if (used >= HEAP_WARN_RATIO && !warned) {
        warned = true;
        console.warn(
          `${PREFIX} Low memory: this tab is using ${Math.round(mem.usedJSHeapSize / 1e6)} MB ` +
            `(${Math.round(used * 100)}% of its limit). Close other tabs/apps if the page becomes slow.`
        );
      } else if (used < HEAP_WARN_RATIO * 0.8) {
        warned = false;
      }
    }, HEAP_CHECK_MS);
  }
}
