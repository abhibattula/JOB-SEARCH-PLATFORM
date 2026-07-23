// Connection badge: green dot connected, gray otherwise.
export function setConnected(connected) {
  chrome.action.setBadgeText({ text: "●" });
  chrome.action.setBadgeBackgroundColor({
    color: connected ? "#1a7f37" : "#8b949e",
  });
  chrome.action.setTitle({
    title: connected
      ? "Job Engine Companion — connected"
      : "Job Engine Companion — app not running",
  });
}
