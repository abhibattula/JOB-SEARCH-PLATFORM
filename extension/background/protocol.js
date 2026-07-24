// Bridge protocol constants + envelope helpers. The Python side
// (engine/autofill/ext_protocol.py) is the authoritative schema; this file
// only names message types and validates envelopes enough to route them.
export const PROTOCOL_V = 1;

export const EXT_TO_APP = Object.freeze([
  "hello", "tab_opened", "fields", "fill_result", "page_event",
  "fill_here", "pong",
]);

export const APP_TO_EXT = Object.freeze([
  "hello_ok", "error", "ping", "open_tab", "close_tab",
  "watch_start", "watch_stop", "fill", "overlay_state",
]);

let seq = 0;

export function envelope(type, payload = {}) {
  return { v: PROTOCOL_V, type, seq: ++seq, ...payload };
}

export function validEnvelope(msg) {
  return (
    msg !== null && typeof msg === "object" &&
    msg.v === PROTOCOL_V && typeof msg.type === "string"
  );
}

// Logging helper — the ONLY sanctioned log call sites for bridge traffic.
// Structurally drops fill values so secrets can never reach the console
// (constitution: passwords never logged extension-side).
export function logSafe(label, msg) {
  if (!msg || typeof msg !== "object") { return; }
  const clone = { ...msg };
  if (Array.isArray(clone.items)) {
    clone.items = clone.items.map((item) => {
      const { value, ...rest } = item;
      return rest;
    });
  }
  console.debug(`[je] ${label}`, clone);
}
