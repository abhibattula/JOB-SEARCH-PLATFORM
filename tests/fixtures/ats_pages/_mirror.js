// Mirrors every real DOM value change back to the test server — the
// integration suite's ground truth for "did the value actually land".
document.addEventListener("input", function (e) {
  var el = e.target;
  if (!el || !el.name) { return; }
  fetch("/echo", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name: el.name, value: el.value || (el.checked ? "on" : "")}),
  });
});
document.addEventListener("change", function (e) {
  var el = e.target;
  if (!el || !el.name) { return; }
  fetch("/echo", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name: el.name, value: el.value || (el.checked ? "on" : "")}),
  });
});
