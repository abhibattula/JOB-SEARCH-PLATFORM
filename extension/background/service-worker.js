// Service worker entry: owns the socket, routes app↔content messages.
import { setConnected } from "./badge.js";
import {
  armWatchdog, connect, onWatchdogTick, readPairing, send, startKeepalive,
  state, WATCHDOG_ALARM,
} from "./socket.js";
import {
  openTab, closeTab, watchStart, watchStop, toContent, relayFromContent,
  restoreWatched, watched,
} from "./tabs.js";

setConnected(false);

// 016 (T008): rebuild the watched set on EVERY worker start — content
// scripts probing an awake-but-amnesiac worker must not go dormant.
restoreWatched();

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
    // 017 (C12): the app has sent `rescan` from three call sites since 016,
    // but nothing ever handled it — it fell through to `default:` and every
    // draft-ready push and Fill again waited on the 2 s safety poll instead.
    // Broadcast to every watched tab's top frame; the content script decides.
    case "rescan":
      watched.forEach((_entry, tabId) => {
        toContent(tabId, { type: "rescan", reason: msg.reason || "" }, 0);
      });
      break;
    // 016 (T010): app-side refusals (e.g. busy) are STORED so the popup can
    // show them — this used to hit `default:` and vanish (RC4).
    case "error":
      chrome.storage.session.set({
        lastError: { code: msg.code || "", message: msg.message || "",
                     at: Date.now() },
      }).catch(() => {});
      break;
    default: break;
  }
};

// Content scripts → app (fields, fill_result, page_event, fill_here).
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // Popup status query — includes the last connection-attempt record (015)
  // so the popup can explain WHY it isn't connected. A freshly-woken worker
  // has blank memory; fall back to the storage.session mirror.
  if (msg && msg.type === "status?") {
    chrome.storage.session.get(["lastAttempt", "lastError"])
      .then((stored) => sendResponse({
        connected: state.connected,
        lastAttempt: state.lastAttempt || stored.lastAttempt || null,
        lastError: stored.lastError || null,
      }))
      .catch(() => sendResponse({ connected: state.connected,
                                  lastAttempt: state.lastAttempt || null,
                                  lastError: null }));
    return true;
  }
  // Popup asked for an immediate reconnect attempt (015: "Connect now")
  if (msg && msg.type === "connect!") {
    connect();
    sendResponse({ ok: true });
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
    // 016 (T015): carry the watch ORIGIN too — content scripts usually
    // start via this probe (the watch_start broadcast races injection),
    // and only queue-driven watches may auto-open the application form.
    // Restored watches (jobId unknown) stay conservative: adhoc.
    const entry = watched.get(sender.tab.id);
    chrome.tabs.sendMessage(
      sender.tab.id,
      { type: "watch_state", watched: watched.has(sender.tab.id),
        adhoc: !entry || entry.jobId == null || entry.jobId === -2 },
      sender.frameId !== undefined ? { frameId: sender.frameId } : undefined,
    ).catch(() => {});
    return false;
  }
  // 017 (C9, FR-029): fetch an app file on the content script's behalf.
  // Only the service worker holds host_permissions for 127.0.0.1 — a
  // content-script fetch of the app's relative url resolves against the job
  // board, where Greenhouse answers with its own HTML and status 200, so an
  // HTML page was being attached as the applicant's resume.
  if (sender.tab && msg && msg._je_file) {
    (async () => {
      try {
        const pairing = await readPairing();
        if (!pairing || !pairing.port) {
          return { ok: false, error: "no_pairing" };
        }
        const url = "http://127.0.0.1:" + pairing.port + msg.path;
        const resp = await fetch(url);
        if (!resp.ok) { return { ok: false, error: "http_" + resp.status }; }
        const buffer = await resp.arrayBuffer();
        const bytes = new Uint8Array(buffer);
        let binary = "";
        for (let i = 0; i < bytes.length; i += 1) {
          binary += String.fromCharCode(bytes[i]);
        }
        return {
          ok: true,
          name: "",
          mime: resp.headers.get("content-type") || "",
          size: bytes.length,
          bytes: btoa(binary),
        };
      } catch (e) {
        return { ok: false, error: String(e && e.message ? e.message : e) };
      }
    })().then(sendResponse);
    return true;  // async reply
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
