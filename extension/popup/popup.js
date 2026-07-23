// Popup: connection status + "Fill this page" + recovery pairing.
// Wired to the service worker in T009/T012.
"use strict";

async function refresh() {
  const dot = document.getElementById("dot");
  const text = document.getElementById("status-text");
  const fillBtn = document.getElementById("fill-here");
  try {
    const resp = await chrome.runtime.sendMessage({ type: "status?" });
    const connected = Boolean(resp && resp.connected);
    dot.classList.toggle("on", connected);
    text.textContent = connected
      ? "Connected to Job Engine"
      : "App not running — open Job Engine";
    fillBtn.disabled = !connected;
  } catch (_e) {
    text.textContent = "Companion starting…";
  }
}

document.getElementById("fill-here").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: "fill_here!" });
  window.close();
});

document.getElementById("recovery-save").addEventListener("click", async () => {
  const code = document.getElementById("recovery-code").value.trim();
  if (code) {
    await chrome.runtime.sendMessage({ type: "recovery_pair!", code });
  }
});

refresh();
