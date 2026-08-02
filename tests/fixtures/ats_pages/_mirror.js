// Mirrors every real DOM value change back to the test server — the
// integration suite's ground truth for "did the value actually land".
//
// 020: a rich-text editor has neither .name nor .value, so a contenteditable
// cover letter was invisible to this mirror exactly as it was invisible to
// the scanner. Such an element opts in with data-echo-name and reports its
// innerText instead. Every existing fixture is unaffected.
function __jeEchoPayload(el) {
  if (!el) { return null; }
  if (el.name) {
    return { name: el.name, value: el.value || (el.checked ? "on" : "") };
  }
  var node = el.closest ? el.closest("[data-echo-name]") : null;
  if (node) {
    return { name: node.getAttribute("data-echo-name"),
             value: (node.innerText || node.textContent || "").trim() };
  }
  return null;
}

function __jeEcho(e) {
  var payload = __jeEchoPayload(e.target);
  if (!payload) { return; }
  fetch("/echo", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
}

document.addEventListener("input", __jeEcho);
document.addEventListener("change", __jeEcho);
