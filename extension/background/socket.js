// WebSocket link to the local app. Pairing comes from pairing.json, which
// the app rewrites at every launch (unpacked extensions re-read packaged
// files from disk on each fetch). Full logic lands in T009; this skeleton
// keeps the badge honest and the module importable.
import { setConnected } from "./badge.js";

export const state = { ws: null, connected: false };

export async function readPairing() {
  try {
    const resp = await fetch(chrome.runtime.getURL("pairing.json"));
    return await resp.json(); // {port, secret, app_id}
  } catch (_e) {
    return null; // app has never run / folder not stamped yet
  }
}

export function markConnected(connected) {
  state.connected = connected;
  setConnected(connected);
}
