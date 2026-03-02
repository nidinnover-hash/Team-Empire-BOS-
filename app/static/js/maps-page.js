/* Maps & Location Tracking — Nidin BOS */
(function () {
  "use strict";

  let TOKEN = null;
  let map = null;
  let markers = [];
  let refreshTimer = null;
  const REFRESH_INTERVAL = 30000; // 30s
  const HISTORY_LIMIT = 50;
  let historyOffset = 0;
  let gpsWatchId = null;

  /* ── Bootstrap ── */
  async function boot() {
    if (window.__bootPromise) {
      TOKEN = await window.__bootPromise;
    }
    initTabs();
    initMap();
    loadActiveLocations();
    loadCheckins();
    loadHistory();
    loadConsentStatus();
    loadAllConsent();
    bindEvents();
    refreshTimer = setInterval(loadActiveLocations, REFRESH_INTERVAL);
  }

  /* ── Tabs ── */
  function initTabs() {
    document.querySelectorAll(".tab").forEach(function (btn) {
      btn.addEventListener("click", function () {
        document.querySelectorAll(".tab").forEach(function (t) {
          t.classList.remove("active");
          t.setAttribute("aria-selected", "false");
        });
        document.querySelectorAll(".tab-panel").forEach(function (p) {
          p.classList.remove("active");
        });
        btn.classList.add("active");
        btn.setAttribute("aria-selected", "true");
        var panel = document.getElementById("panel-" + btn.dataset.tab);
        if (panel) panel.classList.add("active");
      });
    });
  }

  /* ── Map ── */
  function initMap() {
    map = L.map("map-container").setView([25.2048, 55.2708], 10); // default: Dubai
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);
  }

  function clearMarkers() {
    markers.forEach(function (m) { map.removeLayer(m); });
    markers = [];
  }

  function placeMarker(loc) {
    var marker = L.marker([loc.latitude, loc.longitude]).addTo(map);
    var popup = '<div class="loc-popup">' +
      '<strong>' + esc(loc.employee_name || "Employee #" + loc.employee_id) + '</strong>' +
      (loc.role ? '<div>' + esc(loc.role) + '</div>' : '') +
      (loc.address ? '<div>' + esc(loc.address) + '</div>' : '') +
      '<div class="sub">' + esc(loc.source || '') + ' · ' + fmtTime(loc.last_seen || loc.created_at) + '</div>' +
      (loc.accuracy_m ? '<div class="sub">Accuracy: ' + loc.accuracy_m + 'm</div>' : '') +
      '</div>';
    marker.bindPopup(popup);
    markers.push(marker);
    return marker;
  }

  /* ── API helpers ── */
  function hdrs() {
    var h = { "Content-Type": "application/json" };
    if (TOKEN) h["Authorization"] = "Bearer " + TOKEN;
    return h;
  }

  async function api(method, path, body) {
    var opts = { method: method, headers: hdrs() };
    if (body) opts.body = JSON.stringify(body);
    var r = await fetch("/api/v1" + path, opts);
    if (!r.ok) {
      var err = await r.json().catch(function () { return { detail: r.statusText }; });
      throw new Error(err.detail || r.statusText);
    }
    return r.json();
  }

  /* ── Load active locations ── */
  async function loadActiveLocations() {
    try {
      var locs = await api("GET", "/locations/active");
      clearMarkers();
      var kActive = 0;
      var totalAcc = 0;
      var accCount = 0;
      locs.forEach(function (loc) {
        placeMarker(loc);
        kActive++;
        if (loc.accuracy_m) { totalAcc += loc.accuracy_m; accCount++; }
      });
      setText("k-active", kActive);
      setText("k-tracked", locs.length);
      setText("k-accuracy", accCount > 0 ? Math.round(totalAcc / accCount) + "m" : "—");
      if (locs.length > 0) {
        var group = L.featureGroup(markers);
        map.fitBounds(group.getBounds().pad(0.1));
      }
    } catch (e) {
      console.warn("Failed to load locations:", e.message);
    }
  }

  /* ── Check-ins ── */
  async function loadCheckins() {
    try {
      var rows = await api("GET", "/locations/checkins?limit=50");
      var tb = document.getElementById("checkins-body");
      if (!rows.length) {
        tb.innerHTML = '<tr><td colspan="6" class="empty">No check-ins yet</td></tr>';
        setText("k-checkins", 0);
        return;
      }
      var today = new Date().toISOString().slice(0, 10);
      var todayCount = 0;
      tb.innerHTML = "";
      rows.forEach(function (r) {
        if (r.created_at && r.created_at.slice(0, 10) === today) todayCount++;
        var tr = document.createElement("tr");
        tr.innerHTML =
          '<td>' + esc(String(r.employee_id)) + '</td>' +
          '<td>' + esc(r.checkin_type) + '</td>' +
          '<td>' + esc(r.place_name || '—') + '</td>' +
          '<td>' + esc(r.notes || '—') + '</td>' +
          '<td>' + fmtTime(r.created_at) + '</td>' +
          '<td>' + (r.checked_out_at ? '<span class="sub">Checked out</span>' :
            '<button class="btn sm" data-checkout="' + r.id + '" type="button">Check Out</button>') + '</td>';
        tb.appendChild(tr);
      });
      setText("k-checkins", todayCount);

      tb.querySelectorAll("[data-checkout]").forEach(function (btn) {
        btn.addEventListener("click", function () { doCheckout(btn.dataset.checkout); });
      });
    } catch (e) {
      console.warn("Failed to load checkins:", e.message);
    }
  }

  async function doCheckin() {
    var statusEl = document.getElementById("checkin-status");
    statusEl.textContent = "Getting location...";
    statusEl.className = "status";

    if (!navigator.geolocation) {
      statusEl.textContent = "Geolocation not supported by your browser.";
      statusEl.className = "status err";
      return;
    }

    navigator.geolocation.getCurrentPosition(
      async function (pos) {
        try {
          var body = {
            employee_id: null, // server will use actor's employee_id
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
            place_name: document.getElementById("checkin-place").value || null,
            notes: document.getElementById("checkin-notes").value || null,
            checkin_type: document.getElementById("checkin-type").value,
          };
          await api("POST", "/locations/checkin", body);
          statusEl.textContent = "Checked in successfully!";
          statusEl.className = "status ok";
          loadCheckins();
          loadActiveLocations();
        } catch (e) {
          statusEl.textContent = "Check-in failed: " + e.message;
          statusEl.className = "status err";
        }
      },
      function (err) {
        statusEl.textContent = "Location error: " + err.message;
        statusEl.className = "status err";
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  async function doCheckout(checkinId) {
    try {
      await api("POST", "/locations/checkin/" + checkinId + "/checkout");
      loadCheckins();
      if (window.showToast) window.showToast("Checked out", "ok");
    } catch (e) {
      if (window.showToast) window.showToast("Checkout failed: " + e.message, "err");
    }
  }

  /* ── History ── */
  async function loadHistory() {
    try {
      var params = "?limit=" + HISTORY_LIMIT + "&offset=" + historyOffset;
      var empId = document.getElementById("hist-employee").value;
      if (empId) params += "&employee_id=" + empId;
      var src = document.getElementById("hist-source").value;
      if (src) params += "&source=" + src;
      var from = document.getElementById("hist-from").value;
      if (from) params += "&date_from=" + from + "T00:00:00";
      var to = document.getElementById("hist-to").value;
      if (to) params += "&date_to=" + to + "T23:59:59";

      var rows = await api("GET", "/locations/history" + params);
      var tb = document.getElementById("history-body");
      if (!rows.length) {
        tb.innerHTML = '<tr><td colspan="7" class="empty">No history records</td></tr>';
        return;
      }
      tb.innerHTML = "";
      rows.forEach(function (r) {
        var tr = document.createElement("tr");
        tr.innerHTML =
          '<td>' + esc(String(r.employee_id)) + '</td>' +
          '<td>' + r.latitude.toFixed(6) + '</td>' +
          '<td>' + r.longitude.toFixed(6) + '</td>' +
          '<td>' + esc(r.source) + '</td>' +
          '<td>' + (r.accuracy_m ? r.accuracy_m + 'm' : '—') + '</td>' +
          '<td>' + esc(r.address || '—') + '</td>' +
          '<td>' + fmtTime(r.created_at) + '</td>';
        tb.appendChild(tr);
      });

      var page = Math.floor(historyOffset / HISTORY_LIMIT) + 1;
      setText("hist-page-info", "Page " + page);
      document.getElementById("hist-prev-btn").disabled = historyOffset === 0;
      document.getElementById("hist-next-btn").disabled = rows.length < HISTORY_LIMIT;
    } catch (e) {
      console.warn("Failed to load history:", e.message);
    }
  }

  /* ── Consent ── */
  async function loadConsentStatus() {
    try {
      // Try to get own consent — might fail if user has no employee record
      var data = await api("GET", "/locations/consent?employee_id=0");
      document.getElementById("consent-toggle").checked = data.consent || false;
    } catch (_) {
      // silently ignore — user may not have employee record
    }
  }

  async function loadAllConsent() {
    try {
      var rows = await api("GET", "/locations/consent/all");
      var tb = document.getElementById("consent-body");
      if (!rows.length) {
        tb.innerHTML = '<tr><td colspan="3" class="empty">No employees found</td></tr>';
        return;
      }
      tb.innerHTML = "";
      rows.forEach(function (r) {
        var tr = document.createElement("tr");
        tr.innerHTML =
          '<td>' + esc(String(r.employee_id)) + '</td>' +
          '<td>' + esc(r.name || '—') + '</td>' +
          '<td>' + (r.consent ? 'Yes' : 'No') + '</td>';
        tb.appendChild(tr);
      });
    } catch (_) {
      // silently ignore — user may not have ADMIN role
    }
  }

  async function toggleConsent() {
    var el = document.getElementById("consent-toggle");
    var statusEl = document.getElementById("consent-status");
    try {
      await api("PATCH", "/locations/consent", { employee_id: 0, consent: el.checked });
      statusEl.textContent = el.checked ? "Tracking enabled" : "Tracking disabled";
      statusEl.className = "status ok";
    } catch (e) {
      statusEl.textContent = "Failed: " + e.message;
      statusEl.className = "status err";
      el.checked = !el.checked;
    }
  }

  /* ── GPS Tracking ── */
  function startGpsTracking() {
    var btn = document.getElementById("start-tracking-btn");
    if (gpsWatchId !== null) {
      navigator.geolocation.clearWatch(gpsWatchId);
      gpsWatchId = null;
      btn.textContent = "Start GPS";
      btn.classList.remove("active-tracking");
      if (window.showToast) window.showToast("GPS tracking stopped", "ok");
      return;
    }

    if (!navigator.geolocation) {
      if (window.showToast) window.showToast("Geolocation not supported", "err");
      return;
    }

    btn.textContent = "Stop GPS";
    btn.classList.add("active-tracking");
    if (window.showToast) window.showToast("GPS tracking started", "ok");

    gpsWatchId = navigator.geolocation.watchPosition(
      async function (pos) {
        try {
          await api("POST", "/locations/track", {
            employee_id: null,
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
            accuracy_m: pos.coords.accuracy ? Math.round(pos.coords.accuracy) : null,
            altitude_m: pos.coords.altitude ? Math.round(pos.coords.altitude) : null,
            source: "gps",
          });
        } catch (e) {
          console.warn("GPS track failed:", e.message);
        }
      },
      function (err) {
        console.warn("GPS error:", err.message);
        if (window.showToast) window.showToast("GPS error: " + err.message, "err");
      },
      { enableHighAccuracy: true, maximumAge: 15000, timeout: 10000 }
    );
  }

  /* ── Events ── */
  function bindEvents() {
    document.getElementById("refresh-map-btn").addEventListener("click", loadActiveLocations);
    document.getElementById("start-tracking-btn").addEventListener("click", startGpsTracking);
    document.getElementById("checkin-btn").addEventListener("click", doCheckin);
    document.getElementById("consent-toggle").addEventListener("change", toggleConsent);

    document.getElementById("hist-search-btn").addEventListener("click", function () {
      historyOffset = 0;
      loadHistory();
    });
    document.getElementById("hist-prev-btn").addEventListener("click", function () {
      historyOffset = Math.max(0, historyOffset - HISTORY_LIMIT);
      loadHistory();
    });
    document.getElementById("hist-next-btn").addEventListener("click", function () {
      historyOffset += HISTORY_LIMIT;
      loadHistory();
    });
  }

  /* ── Helpers ── */
  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  function setText(id, val) {
    var el = document.getElementById(id);
    if (el) el.textContent = String(val);
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  /* ── Init ── */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
