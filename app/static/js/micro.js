/**
 * Nidin BOS — Micro-interactions module
 *
 * Provides:
 *  - countUp()          Animate numbers from 0 to target
 *  - skeletonLoad()     Show skeleton placeholders, swap to real content
 *  - staggerIn()        Trigger staggered entrance on dynamically added items
 *  - flashRow()         Highlight a row after create/update
 *  - emptyState()       Render a rich empty placeholder
 *  - pageTransition()   Navigate with View Transition API (fallback: instant)
 */
(function () {
  "use strict";

  /* ════════════════════════════════════════════════════════════════════════
     COUNT-UP — Animate a number from 0 to its target value
     Usage:
       <span data-count-to="1234" data-count-prefix="$">0</span>
       Then call:  Micro.countUp()          — all [data-count-to] on page
                   Micro.countUp(container)  — scoped to a container
     ════════════════════════════════════════════════════════════════════════ */
  function countUp(scope) {
    var root = scope || document;
    var els = root.querySelectorAll("[data-count-to]");
    if (!els.length) return;

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        if (el.dataset.counted) return;
        el.dataset.counted = "1";
        observer.unobserve(el);
        _animateNumber(el);
      });
    }, { threshold: 0.2 });

    els.forEach(function (el) { observer.observe(el); });
  }

  function _animateNumber(el) {
    var target = parseFloat(el.dataset.countTo) || 0;
    var prefix = el.dataset.countPrefix || "";
    var suffix = el.dataset.countSuffix || "";
    var decimals = (el.dataset.countDecimals !== undefined)
      ? parseInt(el.dataset.countDecimals, 10)
      : (target % 1 !== 0 ? 2 : 0);
    var duration = parseInt(el.dataset.countDuration, 10) || 800;
    var start = performance.now();

    function tick(now) {
      var elapsed = now - start;
      var progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      var eased = 1 - Math.pow(1 - progress, 3);
      var current = target * eased;
      el.textContent = prefix + _formatNumber(current, decimals) + suffix;
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function _formatNumber(n, decimals) {
    var fixed = n.toFixed(decimals);
    // Add thousands separator
    var parts = fixed.split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return parts.join(".");
  }

  /* ════════════════════════════════════════════════════════════════════════
     SKELETON LOAD — Show skeletons, then swap to real content
     Usage:
       var done = Micro.skeletonLoad(container, { rows: 5, style: 'list' });
       // ... fetch data ...
       done();  // removes skeletons
     Styles: 'list' | 'kpi' | 'card' | 'table'
     ════════════════════════════════════════════════════════════════════════ */
  function skeletonLoad(container, options) {
    if (!container) return function () {};
    var opts = options || {};
    var count = opts.rows || 4;
    var style = opts.style || "list";

    var html = "";
    for (var i = 0; i < count; i++) {
      if (style === "list") {
        html +=
          '<div class="skeleton skel-row">' +
            '<div class="skeleton skel-circle"></div>' +
            '<div style="flex:1">' +
              '<div class="skeleton skel-line medium"></div>' +
              '<div class="skeleton skel-line short"></div>' +
            '</div>' +
          '</div>';
      } else if (style === "kpi") {
        html += '<div class="skeleton skel-kpi"></div>';
      } else if (style === "card") {
        html += '<div class="skeleton skel-card"></div>';
      } else if (style === "table") {
        html +=
          '<div class="skeleton skel-row">' +
            '<div class="skeleton skel-line" style="width:20%"></div>' +
            '<div class="skeleton skel-line" style="width:35%"></div>' +
            '<div class="skeleton skel-line" style="width:15%"></div>' +
            '<div class="skeleton skel-line short"></div>' +
          '</div>';
      }
    }

    var wrapper = document.createElement("div");
    wrapper.className = "skeleton-container stagger-fade";
    wrapper.innerHTML = html;
    container.innerHTML = "";
    container.appendChild(wrapper);

    // Return a cleanup function
    return function () {
      if (wrapper.parentNode) wrapper.remove();
    };
  }

  /* ════════════════════════════════════════════════════════════════════════
     STAGGER IN — Apply staggered entrance to dynamically inserted items
     Usage:  Micro.staggerIn(container)
     Items must already be in the DOM. Adds animation classes.
     ════════════════════════════════════════════════════════════════════════ */
  function staggerIn(container) {
    if (!container) return;
    var children = container.children;
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      child.style.opacity = "0";
      child.style.animation =
        "enter-up 0.4s cubic-bezier(0.16, 1, 0.3, 1) " +
        Math.min(i * 0.04, 0.4) + "s both";
    }
  }

  /* ════════════════════════════════════════════════════════════════════════
     FLASH ROW — Highlight a row briefly after create/update
     Usage:  Micro.flashRow(element)
     ════════════════════════════════════════════════════════════════════════ */
  function flashRow(el) {
    if (!el) return;
    el.classList.remove("row-flash");
    // Force reflow to restart animation
    void el.offsetWidth;
    el.classList.add("row-flash");
    el.addEventListener("animationend", function () {
      el.classList.remove("row-flash");
    }, { once: true });
  }

  /* ════════════════════════════════════════════════════════════════════════
     EMPTY STATE — Render a rich empty placeholder
     Usage:
       Micro.emptyState(container, {
         icon: 'inbox',          // Lucide icon name
         title: 'No tasks yet',
         desc: 'Create your first task to get started.',
         action: { label: 'New Task', onclick: fn }
       })
     ════════════════════════════════════════════════════════════════════════ */
  function emptyState(container, options) {
    if (!container) return;
    var opts = options || {};
    var icon = opts.icon || "inbox";
    var title = opts.title || "Nothing here yet";
    var desc = opts.desc || "";

    var html =
      '<div class="empty-state">' +
        '<div class="empty-state-icon"><i data-lucide="' + _escHtml(icon) + '"></i></div>' +
        '<div class="empty-state-title">' + _escHtml(title) + '</div>' +
        (desc ? '<div class="empty-state-desc">' + _escHtml(desc) + '</div>' : '') +
        (opts.action
          ? '<div class="empty-state-action"><button class="btn primary sm" type="button">' +
            _escHtml(opts.action.label || "Get Started") + '</button></div>'
          : '') +
      '</div>';

    container.innerHTML = html;

    // Render lucide icon
    if (window.lucide && window.lucide.createIcons) {
      window.lucide.createIcons({ nodes: container.querySelectorAll("[data-lucide]") });
    }

    // Bind action button
    if (opts.action && opts.action.onclick) {
      var btn = container.querySelector(".empty-state-action button");
      if (btn) btn.addEventListener("click", opts.action.onclick);
    }
  }

  /* ════════════════════════════════════════════════════════════════════════
     PAGE TRANSITION — Navigate with View Transition API
     Usage:  Micro.navigate('/web/tasks')
     Falls back to normal navigation if API unsupported.
     ════════════════════════════════════════════════════════════════════════ */
  function navigate(url) {
    if (document.startViewTransition) {
      document.startViewTransition(function () {
        window.location.href = url;
      });
    } else {
      window.location.href = url;
    }
  }

  /* ════════════════════════════════════════════════════════════════════════
     AUTO-INIT — Run on page load
     ════════════════════════════════════════════════════════════════════════ */
  function init() {
    // Auto count-up all [data-count-to] elements
    countUp();

    // Intercept sidebar links for page transitions
    var sidebarLinks = document.querySelectorAll(".sb-item[href]");
    sidebarLinks.forEach(function (link) {
      if (link.target === "_blank") return;
      link.addEventListener("click", function (e) {
        if (e.ctrlKey || e.metaKey || e.shiftKey) return;
        if (!document.startViewTransition) return; // let browser handle
        e.preventDefault();
        navigate(link.href);
      });
    });
  }

  function _escHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Run init on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }

  // Export
  window.Micro = {
    countUp: countUp,
    skeletonLoad: skeletonLoad,
    staggerIn: staggerIn,
    flashRow: flashRow,
    emptyState: emptyState,
    navigate: navigate,
  };
})();
