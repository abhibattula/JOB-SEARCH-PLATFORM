// Popup: connection status + "Fill this page" + recovery pairing.
// 015 (FR-011): never a dead control — every disconnected state names its
// reason in plain language and offers a retry; the Fill button explains
// instead of silently doing nothing.
"use strict";

const CLOSE_REASONS = {
  4401: "The app rejected the pairing (stale pairing — the app restarted, " +
        "or the wrong folder is loaded). Press Connect now; if it keeps " +
        "failing, remove the extension and Load unpacked again from the " +
        "exact folder shown in the app's Companion page.",
  4426: "This companion is older than the app. Open the extensions page " +
        "and click the ↻ reload icon on the Job Engine Companion card.",
};

function describe(resp) {
  if (resp && resp.connected) {
    return { ok: true, text: "Connected to Job Engine" };
  }
  const la = resp && resp.lastAttempt;
  if (!la) {
    return { ok: false, text: "Companion starting… press Connect now " +
                              "if this doesn't change." };
  }
  switch (la.stage) {
    case "no-pairing":
      return { ok: false, text: "Pairing file missing — load the exact " +
        "folder shown in the app's Companion page, or paste a recovery " +
        "code below." };
    case "identity-failed":
      return { ok: false, text: "App not running — open Job Engine, " +
        "then press Connect now." +
        (la.port ? " (tried port " + la.port + ")" : "") };
    case "ws-error":
      return { ok: false, text: "Couldn't reach the app on port " + la.port +
        " — is Job Engine running?" };
    case "closed":
      return { ok: false, text: CLOSE_REASONS[la.code] ||
        ("Connection closed (code " + la.code + ") — press Connect now.") };
    case "connected":
      return { ok: false, text: "Reconnecting…" };
    default:
      return { ok: false, text: "Not connected yet — press Connect now." };
  }
}

async function status() {
  try {
    return await chrome.runtime.sendMessage({ type: "status?" });
  } catch (_e) {
    return null;
  }
}

function render(resp) {
  const dot = document.getElementById("dot");
  const text = document.getElementById("status-text");
  const reason = document.getElementById("reason");
  const d = describe(resp);
  dot.classList.toggle("on", d.ok);
  text.textContent = d.ok ? "Connected to Job Engine" : "Not connected";
  reason.textContent = d.ok
    ? "Fills happen in this browser — you still click every submit."
    : d.text;
}

async function refresh() {
  render(await status());
}

document.getElementById("fill-here").addEventListener("click", async () => {
  const resp = await status();
  if (!resp || !resp.connected) {
    document.getElementById("reason").textContent =
      "Can't fill: " + describe(resp).text;
    return; // stay open so the reason is readable — never a silent no-op
  }
  await chrome.runtime.sendMessage({ type: "fill_here!" });
  window.close();
});

document.getElementById("connect-now").addEventListener("click", async () => {
  document.getElementById("reason").textContent = "Connecting…";
  await chrome.runtime.sendMessage({ type: "connect!" }).catch(() => {});
  setTimeout(refresh, 900);
});

document.getElementById("recovery-save").addEventListener("click", async () => {
  const code = document.getElementById("recovery-code").value.trim();
  if (code) {
    await chrome.runtime.sendMessage({ type: "recovery_pair!", code });
    setTimeout(refresh, 900);
  }
});

refresh();
setInterval(refresh, 2000);
