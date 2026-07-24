// Service worker entry: owns the socket, routes app↔content messages.
import { setConnected } from "./badge.js";
import {
  armWatchdog, connect, onWatchdogTick, send, startKeepalive, state,
  WATCHDOG_ALARM,
} from "./socket.js";
import {
  openTab, closeTab, watchStart, watchStop, toContent, relayFromContent,
  watched,
} from "./tabs.js";

setConnected(false);

// Registered at TOP LEVEL so Chrome knows to spin this worker back up when
// the alarm fires — this is what makes the companion survive the ~30s idle
// termination that killed v1.0.0's connection permanently.
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === WATCHDOG_ALARM) { onWatchdogTick(); }
});

// App → extension commands arrive on the socket.
state.onMessage = (msg) => {
  switch (msg.type) {
    case "open_tab": openTab(msg.req_id, msg.job_id, msg.url); break;
    case "close_tab": closeTab(msg.tab_id); break;
    case "watch_start": watchStart(msg.tab_id, msg.job_id); break;
    case "watch_stop": watchStop(msg.tab_id); break;
    case "fill": toContent(msg.tab_id, { type: "fill", items: msg.items },
                           msg.frame_id); break;
    case "overlay_state": toContent(msg.tab_id, { type: "overlay_state",
                                                  summary: msg.summary }, 0); break;
    // 012 discovery: score/save replies go to the requesting tab's top frame.
    case "score_result": toContent(msg.tab_id, { ...msg, type: "score_result" }, 0);
      break;
    case "save_result": toContent(msg.tab_id, { ...msg, type: "save_result" }, 0);
      break;
    default: break;
  }
};

// Content scripts → app (fields, fill_result, page_event, fill_here).
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // Popup status query
  if (msg && msg.type === "status?") {
    sendResponse({ connected: state.connected });
    return true;
  }
  if (msg && msg.type === "fill_here!") {
    // popup asked to fill the active tab; find it and relay
    chrome.tabs.query({ active: true, currentWindow: true }).then((tabs) => {
      const tab = tabs[0];
      if (tab) {
        send({ v: 1, type: "fill_here", seq: 0, tab_id: tab.id,
               url: tab.url || "", title: tab.title || "" });
      }
    });
    return false;
  }
  if (msg && msg.type === "recovery_pair!") {
    // "port:secret" pasted in the popup
    const [port, secret] = String(msg.code || "").split(":");
    if (port && secret) {
      state.recoveryPairing = { port: Number(port), secret };
      connect();
    }
    return false;
  }
  // A content script announcing it's loaded — tell it whether its tab is
  // being watched (closes the watch_start-before-inject race).
  if (sender.tab && msg && msg._je_ready) {
    chrome.tabs.sendMessage(
      sender.tab.id,
      { type: "watch_state", watched: watched.has(sender.tab.id) },
      sender.frameId !== undefined ? { frameId: sender.frameId } : undefined,
    ).catch(() => {});
    return false;
  }
  // From a content script (has sender.tab)
  if (sender.tab && msg && msg._je) {
    relayFromContent(sender.tab.id, sender.frameId, msg.payload);
  }
  return false;
});

// Also re-arm on install/browser start so the alarm exists even if this
// worker never ran otherwise.
chrome.runtime.onInstalled.addListener(() => { armWatchdog(); connect(); });
chrome.runtime.onStartup.addListener(() => { armWatchdog(); connect(); });

// Runs on EVERY worker startup (including alarm-triggered wakes): make sure
// the watchdog exists, then try to connect immediately.
armWatchdog();
startKeepalive();
connect();
