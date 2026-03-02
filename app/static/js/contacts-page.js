(async function () {
  var token = await window.__bootPromise;
  var esc = function (value) {
    var text = String(value == null ? "" : value);
    if (window.PCUI && window.PCUI.escapeHtml) return window.PCUI.escapeHtml(text);
    return text.replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  };
  var headers = function () {
    return { Authorization: "Bearer " + token, "Content-Type": "application/json" };
  };
  var askInput = async function (title, message, defaultValue) {
    if (window.PCUI && window.PCUI.promptText) return window.PCUI.promptText(title, message, defaultValue);
    return window.prompt(message || "", defaultValue || "");
  };

  async function loadContacts() {
    var response = await fetch("/api/v1/contacts?limit=200", { headers: headers() });
    if (!response.ok) return;
    var items = await response.json();
    document.getElementById("k-total").textContent = String(items.length);
    document.getElementById("k-biz").textContent = String(items.filter(function (item) { return item.relationship === "business"; }).length);
    document.getElementById("k-per").textContent = String(items.filter(function (item) { return item.relationship === "personal"; }).length);

    var body = document.getElementById("tbody");
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="5" style="text-align:center;opacity:.5">No contacts yet</td></tr>';
      return;
    }

    body.innerHTML = items.map(function (item) {
      var name = esc(item.name || "--");
      var email = esc(item.email || "--");
      var company = esc(item.company || "--");
      var phone = esc(item.phone || "--");
      var relationship = esc(item.relationship || "unknown");
      return "<tr><td>" + name + "</td><td>" + email + "</td><td>" + company + "</td><td><span class=\"badge\">" + relationship + "</span></td><td>" + phone + "</td></tr>";
    }).join("");
  }

  var addButton = document.getElementById("add-btn");
  if (addButton) {
    addButton.onclick = async function () {
      var name = await askInput("New Contact", "Contact name:", "");
      if (!name) return;
      var email = await askInput("New Contact", "Email (optional):", "");
      email = email || undefined;
      await fetch("/api/v1/contacts", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ name: name, email: email }),
      });
      await loadContacts();
    };
  }

  await loadContacts();
  if (typeof lucide !== "undefined") {
    lucide.createIcons();
  }
})();
