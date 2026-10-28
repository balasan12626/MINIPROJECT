/* F15 — offline shell for the citizen phone pages (/sos, /safe).
 *
 * Scope is deliberately small:
 *  - navigations to /sos and /safe: network first, fall back to the cached
 *    app shell (index.html) so the page opens without signal;
 *  - hashed build files under /assets/: cache first (file names change on
 *    every build, so a cached copy is never stale);
 *  - everything else — /api, /ws, map tiles, other pages — is not touched.
 * Live data (/api) is never cached: an SOS made offline is kept by the page's
 * own outbox (localStorage) and sent when the phone is back online.
 */
const VERSION = "aq-phone-v1";
const SHELL = "/index.html";
const PHONE = /^\/(sos|safe)\/?$/;
const MAX_ASSETS = 80;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(VERSION)
      .then((c) => c.add(new Request(SHELL, { cache: "reload" })))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

async function trim(cache) {
  const keys = (await cache.keys()).filter((r) => new URL(r.url).pathname.startsWith("/assets/"));
  for (let i = 0; i < keys.length - MAX_ASSETS; i += 1) await cache.delete(keys[i]);
}

async function cacheAsset(url) {
  const cache = await caches.open(VERSION);
  if (await cache.match(url)) return;
  const res = await fetch(url);
  if (res.ok) {
    await cache.put(url, res);
    await trim(cache);
  }
}

// The page sends the build files it already loaded (they were fetched before
// this worker took control), so the first visit is enough to work offline.
self.addEventListener("message", (event) => {
  const urls = (event.data && event.data.type === "cache-assets" && event.data.urls) || [];
  event.waitUntil(
    Promise.all(
      urls
        .filter((u) => new URL(u, self.location.origin).origin === self.location.origin)
        .filter((u) => new URL(u, self.location.origin).pathname.startsWith("/assets/"))
        .map((u) => cacheAsset(u).catch(() => undefined))
    )
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (req.mode === "navigate" && PHONE.test(url.pathname)) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(VERSION).then((c) => c.put(SHELL, copy));
          }
          return res;
        })
        .catch(() => caches.match(SHELL).then((hit) => hit || Response.error()))
    );
    return;
  }

  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            if (res.ok) {
              const copy = res.clone();
              caches.open(VERSION).then((c) => c.put(req, copy).then(() => trim(c)));
            }
            return res;
          })
      )
    );
  }
});
