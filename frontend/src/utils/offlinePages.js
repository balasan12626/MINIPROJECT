/** F15 — register the small service worker (public/sw.js) that lets the
 * citizen phone pages (/sos, /safe) open without signal. Production builds
 * only: in dev it would cache Vite's modules and fight hot reload. */
export function registerPhoneOffline({ enabled = import.meta.env.PROD } = {}) {
  if (!enabled || typeof navigator === "undefined" || !("serviceWorker" in navigator)) return false;
  navigator.serviceWorker
    .register("/sw.js")
    .then(() => navigator.serviceWorker.ready)
    .then((reg) => {
      // build files already loaded before the worker took control
      const urls =
        typeof performance !== "undefined" && performance.getEntriesByType
          ? performance
              .getEntriesByType("resource")
              .map((e) => e.name)
              .filter((u) => u.includes("/assets/"))
          : [];
      urls.push(...[...document.querySelectorAll('script[src*="/assets/"], link[href*="/assets/"]')].map((el) => el.src || el.href));
      reg.active?.postMessage({ type: "cache-assets", urls: [...new Set(urls)] });
    })
    .catch(() => {
      /* no service worker (private mode / http): pages still work online */
    });
  return true;
}
