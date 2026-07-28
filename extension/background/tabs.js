// Tab + frame routing between the app's commands and content scripts.
// Stateless across SW restarts: the watched map is rebuilt from incoming
// commands; the durable queue truth lives in the Python app.
import { send } from "./socket.js";

export const watched = new Map(); // tabId -> {jobId|null}

// 016 (T008): the watched set survives MV3 worker restarts — an
// amnesiac worker used to answer watch_state{watched:false} and the tab
// went permanently quiet until the next socket reconnect.
function persistWatched() {
  chrome.storage.session
    .set({ watchedTabs: Array.from(watched.keys()) })
    .catch(() => {});
}

export async function restoreWatched() {
  try {
    const stored = await chrome.storage.session.get("watchedTabs");
    for (const tabId of stored.watchedTabs || []) {
      if (!watched.has(tabId)) { watched.set(tabId, { jobId: null }); }
    }
  } catch (_e) { /* session storage unavailable — degrade to old behavior */ }
}

export async function openTab(reqId, jobId, url) {
  const tab = await chrome.tabs.create({ url, active: true });
  send({ v: 1, type: "tab_opened", seq: 0, req_id: reqId, tab_id: tab.id });
}

export async function closeTab(tabId) {
  watched.delete(tabId);
  persistWatched();
  try { await chrome.tabs.remove(tabId); } catch (_e) { /* already gone */ }
}

export function watchStart(tabId, jobId) {
  watched.set(tabId, { jobId });
  persistWatched();
  // 016 (T015): adhoc (popup fill-here, job -2) watches never auto-open
  // the application form — only queue-driven ones do.
  broadcastToTab(tabId, { type: "watch", adhoc: jobId === -2 });
}

export function watchStop(tabId) {
  watched.delete(tabId);
  persistWatched();
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
    persistWatched();
    send({ v: 1, type: "page_event", seq: 0, tab_id: tabId, kind: "tab_closed" });
  }
});

// 016 (T008, R4): a tab opened FROM a watched tab is where the real form
// lives (embedded boards open applications in a child tab). Report it —
// the app transfers the watch and answers with watch_start for the child.
chrome.tabs.onCreated.addListener((tab) => {
  if (tab.openerTabId !== undefined && watched.has(tab.openerTabId)) {
    send({ v: 1, type: "child_tab", seq: 0, tab_id: tab.id,
           opener_tab_id: tab.openerTabId });
  }
});

chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (watched.has(tabId) && info.status === "loading" && info.url) {
    send({ v: 1, type: "page_event", seq: 0, tab_id: tabId,
           kind: "nav", url: info.url });
  }
});
