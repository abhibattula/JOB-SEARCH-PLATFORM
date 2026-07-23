// Tab + frame routing. Stateless by design: the map is rebuilt from
// chrome.tabs on SW restart; durable truth lives in the Python app.
// Filled in during T009.
export const watched = new Map(); // tabId -> {jobId|null}

export async function openTab(url) {
  const tab = await chrome.tabs.create({ url, active: true });
  return tab.id;
}

export async function closeTab(tabId) {
  try { await chrome.tabs.remove(tabId); } catch (_e) { /* already gone */ }
  watched.delete(tabId);
}
