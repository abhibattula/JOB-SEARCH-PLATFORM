// Bridge protocol constants + envelope helpers. The Python side
// (engine/autofill/ext_protocol.py) is the authoritative schema; this file
// only names message types and validates envelopes enough to route them.
export const PROTOCOL_V = 1;

export const EXT_TO_APP = Object.freeze([
  "hello", "tab_opened", "fields", "fill_result", "page_event",
  "fill_here", "pong", "score_request", "save_job", "scan_error",
  "child_tab", "fill_again", "answer_question", "apply_here",
  "session_control",
  // 019
  "credential_save", "advance_result",
]);

export const APP_TO_EXT = Object.freeze([
  "hello_ok", "error", "ping", "open_tab", "close_tab",
  "watch_start", "watch_stop", "fill", "overlay_state", "answers",
  "score_result", "save_result", "rescan",
  // 019
  "advance_step",
]);

// 019: message fields that carry a credential. Dropped structurally before
// anything reaches the console — a password must never be one console.debug
// away from the page's own devtools.
const SECRET_FIELDS = Object.freeze(["password", "secret", "email"]);

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
  // 019: credential_save carries a real password. Strip by NAME, not by
  // message type, so a future message that reuses the field name is
  // covered the moment it exists rather than the moment someone remembers.
  for (const field of SECRET_FIELDS) {
    if (field in clone) { clone[field] = "•••"; }
  }
  console.debug(`[je] ${label}`, clone);
}
