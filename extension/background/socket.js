// WebSocket link to the local Job Engine app.
//
// Pairing: the app owns this extension folder and rewrites pairing.json at
// every launch with the current port + secret. Unpacked extensions re-read
// packaged files from disk on each fetch, so we pick up a new port/secret
// on every connect attempt with no reload and no user action.
//
// Keepalive: since Chrome 116, WebSocket traffic resets the service-worker
// idle timer, so a 20s ping keeps this worker (and the socket) alive.
import { setConnected } from "./badge.js";
import { logSafe, validEnvelope } from "./protocol.js";

const PING_MS = 20000;
const BACKOFF_MIN_MS = 1000;
const BACKOFF_MAX_MS = 30000;

export const state = {
  ws: null,
  connected: false,
  backoff: BACKOFF_MIN_MS,
  onMessage: null, // set by service-worker.js
  recoveryPairing: null, // {port, secret} entered in the popup, optional
};

export async function readPairing() {
  // Recovery pairing (user pasted a code because they moved the folder)
  // wins over the on-disk file.
  if (state.recoveryPairing) { return state.recoveryPairing; }
  try {
    const resp = await fetch(chrome.runtime.getURL("pairing.json"));
    return await resp.json(); // {port, secret, app_id, protocol_v}
  } catch (_e) {
    return null; // app has never run / folder not stamped yet
  }
}

function markConnected(connected) {
  state.connected = connected;
  setConnected(connected);
}

export function send(payload) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    logSafe("→", payload);
    state.ws.send(JSON.stringify(payload));
    return true;
  }
  return false;
}

async function verifyIdentity(port) {
  // Confirm this really is the app before presenting the secret.
  try {
    const resp = await fetch(`http://127.0.0.1:${port}/api/bridge/info`);
    const info = await resp.json();
    return info && info.app_id === "jobengine";
  } catch (_e) {
    return false;
  }
}

export async function connect() {
  const pairing = await readPairing();
  if (!pairing || !pairing.port) {
    scheduleReconnect();
    return;
  }
  if (!(await verifyIdentity(pairing.port))) {
    scheduleReconnect();
    return;
  }

  let ws;
  try {
    ws = new WebSocket(`ws://127.0.0.1:${pairing.port}/ws/ext`);
  } catch (_e) {
    scheduleReconnect();
    return;
  }
  state.ws = ws;

  ws.addEventListener("open", () => {
    ws.send(JSON.stringify({
      v: 1, type: "hello", seq: 1,
      secret: pairing.secret,
      version: chrome.runtime.getManifest().version,
      chrome_version: (navigator.userAgent.match(/Chrome\/(\d+)/) || [])[1] || "",
    }));
  });

  ws.addEventListener("message", (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch (_e) { return; }
    if (!validEnvelope(msg)) { return; }
    logSafe("←", msg);
    if (msg.type === "hello_ok") {
      markConnected(true);
      state.backoff = BACKOFF_MIN_MS;
      return;
    }
    if (msg.type === "ping") { send({ v: 1, type: "pong", seq: 0 }); return; }
    if (state.onMessage) { state.onMessage(msg); }
  });

  ws.addEventListener("close", () => {
    markConnected(false);
    state.ws = null;
    scheduleReconnect();
  });
  ws.addEventListener("error", () => {
    try { ws.close(); } catch (_e) { /* ignore */ }
  });
}

function scheduleReconnect() {
  const delay = state.backoff;
  state.backoff = Math.min(state.backoff * 2, BACKOFF_MAX_MS);
  setTimeout(connect, delay);
}

export function startKeepalive() {
  // A ping every 20s doubles as the SW-alive heartbeat and the liveness
  // signal the app uses to choose the extension backend.
  setInterval(() => {
    if (state.connected) { send({ v: 1, type: "ping", seq: 0 }); }
  }, PING_MS);
}
