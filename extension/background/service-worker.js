// Service worker entry — wires modules. Connection loop lands in T009.
import { markConnected } from "./socket.js";

chrome.runtime.onInstalled.addListener(() => {
  markConnected(false);
});

chrome.runtime.onStartup.addListener(() => {
  markConnected(false);
});
