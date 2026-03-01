(async function () {
  var token = await window.__bootPromise;
  var headers = function () {
    return { Authorization: "Bearer " + token, "Content-Type": "application/json" };
  };

  try {
    var response = await fetch("/api/v1/clone/memory/stats", { headers: headers() });
    if (response.ok) {
      var payload = await response.json();
      document.getElementById("k-total").textContent = String(payload.total_memories || 0);
    }
  } catch (_error) {
    // no-op
  }

  if (typeof lucide !== "undefined") {
    lucide.createIcons();
  }
})();
