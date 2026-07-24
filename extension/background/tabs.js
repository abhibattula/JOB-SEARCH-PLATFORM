// Tab + frame routing between the app's commands and content scripts.
// Stateless across SW restarts: the watched map is rebuilt from incoming
// commands; the durable queue truth lives in the Python app.
import { send } from "./socket.js";

export const watched = new Map(); // tabId -> {jobId|null}

export async function openTab(reqId, jobId, url) {
  const tab = await chrome.tabs.create({ url, active: true });
  send({ v: 1, type: "tab_opened", seq: 0, req_id: reqId, tab_id: tab.id });
}

export async function closeTab(tabId) {
  watched.delete(tabId);
  try { await chrome.tabs.remove(tabId); } catch (_e) { /* already gone */ }
}

export function watchStart(tabId, jobId) {
  watched.set(tabId, { jobId });
  broadcastToTab(tabId, { type: "watch" });
}

export function watchStop(tabId) {
  watched.delete(tabId);
  broadcastToTab(tabId, { type: "unwatch" });
}

// Deliver an app→content instruction. Fills are routed to the exact frame
// that reported the fields (cross-origin iframes each fill their own DOM);
// overlay_state goes to the top frame only.
export function toContent(tabId, message, frameId) {
  const options = frameId === undefined ? undefined : { frameId };
  chrome.tabs.sendMessage(tabId, message, options).catch(() => {
    // no content script yet (page still loading) — the next scan re-syncs
  });
}

function broadcastToTab(tabId, message) {
  chrome.tabs.sendMessage(tabId, message).catch(() => {});
}

// Relay content-script events (fields / fill_result / page_event / fill_here)
// up to the app, tagging the originating frame.
export function relayFromContent(tabId, frameId, msg) {
  const withRoute = { ...msg, tab_id: tabId };
  if (frameId !== undefined && msg.type === "fields") {
    withRoute.frame_id = frameId;
  }
  if (frameId !== undefined && msg.type === "fill_result") {
    withRoute.frame_id = frameId;
  }
  send({ v: 1, seq: 0, ...withRoute });
}

// A closed tab must tell the app so the queue can mark itself interrupted.
chrome.tabs.onRemoved.addListener((tabId) => {
  if (watched.has(tabId)) {
    watched.delete(tabId);
    send({ v: 1, type: "page_event", seq: 0, tab_id: tabId, kind: "tab_closed" });
  }
});

chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (watched.has(tabId) && info.status === "loading" && info.url) {
    send({ v: 1, type: "page_event", seq: 0, tab_id: tabId,
           kind: "nav", url: info.url });
  }
});
