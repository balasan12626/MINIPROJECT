/**
 * Resolve HTTP API origin and WebSocket base.
 * Local Vite proxies /api and /ws → backend.
 * Production app host (app.voyamindai.online) has no working /api proxy —
 * talk to api.voyamindai.online directly.
 */
export function resolveApiOrigin() {
  const fromEnv = String(import.meta.env.VITE_API_BASE || "").trim().replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  if (typeof window === "undefined") return "";
  const host = window.location.hostname || "";
  if (host === "app.voyamindai.online" || host === "voyamindai.online" || host === "www.voyamindai.online") {
    return "https://api.voyamindai.online";
  }
  return "";
}

export function apiUrl(path) {
  const base = resolveApiOrigin();
  const p = path.startsWith("/") ? path : `/${path}`;
  return base ? `${base}${p}` : p;
}

export function resolveWsUrl() {
  const fromEnv = String(import.meta.env.VITE_WS_BASE || "").trim().replace(/\/$/, "");
  if (fromEnv) {
    return fromEnv.includes("/ws") ? fromEnv : `${fromEnv}/ws`;
  }
  const api = resolveApiOrigin();
  if (api) {
    const u = new URL(api);
    const proto = u.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${u.host}/ws`;
  }
  if (typeof window === "undefined") return "/ws";
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  let host = window.location.host;
  if (host.startsWith("localhost")) {
    host = host.replace("localhost", "127.0.0.1");
  }
  return `${proto}://${host}/ws`;
}
