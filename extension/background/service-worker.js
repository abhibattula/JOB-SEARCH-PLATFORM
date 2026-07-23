// Service worker entry: owns the socket, routes app↔content messages.
import { setConnected } from "./badge.js";
import { connect, startKeepalive, state, send } from "./socket.js";
import {
  openTab, closeTab, watchStart, watchStop, toContent, relayFromContent,
  watched,
} from "./tabs.js";

setConnected(false);

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
  // From a content script (has sender.tab)
  if (sender.tab && msg && msg._je) {
    relayFromContent(sender.tab.id, sender.frameId, msg.payload);
  }
  return false;
});

startKeepalive();
connect();
