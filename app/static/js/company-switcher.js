/**
 * Company Module Switcher — persists selected company context in localStorage.
 * Exposes window.BOS_COMPANY for other scripts to read.
 */
(function () {
  "use strict";
  var STORAGE_KEY = "bos_active_company";
  var btn = document.getElementById("company-switcher-btn");
  var dropdown = document.getElementById("company-dropdown");
  var nameEl = document.getElementById("company-current");
  if (!btn || !dropdown) return;

  var current = localStorage.getItem(STORAGE_KEY) || "all";
  window.BOS_COMPANY = current;

  function setActive(company) {
    current = company;
    window.BOS_COMPANY = company;
    localStorage.setItem(STORAGE_KEY, company);
    var options = dropdown.querySelectorAll(".sb-company-option");
    options.forEach(function (opt) {
      var isActive = opt.dataset.company === company;
      opt.classList.toggle("active", isActive);
      if (isActive && nameEl) nameEl.textContent = opt.textContent;
    });
    close();
    // Dispatch event for other scripts to react
    document.dispatchEvent(new CustomEvent("bos:company-changed", { detail: { company: company } }));
  }

  function toggle() {
    var isOpen = dropdown.classList.contains("open");
    if (isOpen) close();
    else open();
  }

  function open() {
    dropdown.classList.add("open");
    btn.setAttribute("aria-expanded", "true");
  }

  function close() {
    dropdown.classList.remove("open");
    btn.setAttribute("aria-expanded", "false");
  }

  // Init: set the active state from localStorage
  setActive(current);

  btn.addEventListener("click", function (e) {
    e.stopPropagation();
    toggle();
  });

  dropdown.addEventListener("click", function (e) {
    var opt = e.target.closest(".sb-company-option");
    if (opt) setActive(opt.dataset.company);
  });

  // Close on outside click
  document.addEventListener("click", function (e) {
    if (!btn.contains(e.target) && !dropdown.contains(e.target)) {
      close();
    }
  });
})();
