/**
 * Shared WebSocket to backend (proxied via Vite /ws → :8000).
 * On app.voyamindai.online, connects to api.voyamindai.online/ws.
 * Singleton avoids Strict Mode double-mount spam and duplicate sockets
 * from SimulationExecution + useLivePipeline.
 */

import { resolveWsUrl } from "./apiOrigin.js";

const listeners = new Set();
const statusListeners = new Set();

let ws = null;
let reconnectTimer = null;
let heartbeat = null;
let intentionalClose = false;
let tries = 0;
let refCount = 0;

function wsUrl() {
  return resolveWsUrl();
}

function setStatus(status) {
  statusListeners.forEach((fn) => {
    try {
      fn(status);
    } catch {
      /* ignore */
    }
  });
}

function clearTimers() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (heartbeat) {
    clearInterval(heartbeat);
    heartbeat = null;
  }
}

function scheduleReconnect() {
  if (intentionalClose || refCount <= 0) return;
  clearTimers();
  const delay = Math.min(15000, 800 * 2 ** Math.min(tries, 4));
  tries += 1;
  reconnectTimer = setTimeout(openSocket, delay);
}

function openSocket() {
  if (intentionalClose || refCount <= 0) return;
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  clearTimers();
  let socket;
  try {
    socket = new WebSocket(wsUrl());
  } catch {
    setStatus("disconnected");
    scheduleReconnect();
    return;
  }
  ws = socket;
  setStatus("connecting");

  socket.onopen = () => {
    if (ws !== socket) return;
    tries = 0;
    setStatus("connected");
    heartbeat = setInterval(() => {
      if (ws === socket && socket.readyState === WebSocket.OPEN) {
        try {
          socket.send("ping");
        } catch {
          /* ignore */
        }
      }
    }, 12000);
  };

  socket.onmessage = (ev) => {
    if (ws !== socket) return;
    let data;
    try {
      data = JSON.parse(ev.data);
    } catch {
      return;
    }
    listeners.forEach((fn) => {
      try {
        fn(data);
      } catch {
        /* ignore */
      }
    });
  };

  socket.onerror = () => {
    if (ws !== socket) return;
    setStatus("disconnected");
  };

  socket.onclose = () => {
    if (ws === socket) ws = null;
    clearInterval(heartbeat);
    heartbeat = null;
    setStatus("disconnected");
    scheduleReconnect();
  };
}

function acquire() {
  refCount += 1;
  intentionalClose = false;
  if (refCount === 1) {
    // Defer open so React Strict Mode unmount can cancel before CONNECTING
    reconnectTimer = setTimeout(openSocket, 0);
  } else if (!ws || ws.readyState === WebSocket.CLOSED) {
    openSocket();
  }
}

function release() {
  refCount = Math.max(0, refCount - 1);
  if (refCount > 0) return;
  intentionalClose = true;
  clearTimers();
  const sock = ws;
  ws = null;
  if (!sock) return;
  sock.onopen = null;
  sock.onmessage = null;
  sock.onerror = null;
  sock.onclose = null;
  // Only close if already open — avoid "closed before established" console noise
  if (sock.readyState === WebSocket.OPEN) {
    try {
      sock.close();
    } catch {
      /* ignore */
    }
  } else if (sock.readyState === WebSocket.CONNECTING) {
    sock.addEventListener("open", () => {
      try {
        sock.close();
      } catch {
        /* ignore */
      }
    });
  }
}

/**
 * Subscribe to hub events. Returns unsubscribe.
 * Multiple callers share one socket.
 */
export function connectSocket(onEvent, onStatus) {
  if (typeof onEvent === "function") listeners.add(onEvent);
  if (typeof onStatus === "function") statusListeners.add(onStatus);

  acquire();

  return () => {
    if (typeof onEvent === "function") listeners.delete(onEvent);
    if (typeof onStatus === "function") statusListeners.delete(onStatus);
    release();
  };
}
