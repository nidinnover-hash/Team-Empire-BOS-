/* Lightweight chart helpers (no external dependency). */
(function () {
  "use strict";

  function toNums(values) {
    return (Array.isArray(values) ? values : []).map(function (v) {
      var n = Number(v);
      return Number.isFinite(n) ? n : 0;
    });
  }

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function pointsFor(values, width, height, pad, minV, maxV) {
    var n = values.length;
    if (!n) return "";
    var w = Math.max(1, width - pad * 2);
    var h = Math.max(1, height - pad * 2);
    var range = Math.max(1e-9, maxV - minV);
    var step = n > 1 ? w / (n - 1) : 0;
    var out = [];
    for (var i = 0; i < n; i++) {
      var x = pad + i * step;
      var y = pad + (maxV - values[i]) * (h / range);
      out.push((Math.round(x * 100) / 100) + "," + (Math.round(y * 100) / 100));
    }
    return out.join(" ");
  }

  function renderSparkline(host, values, opts) {
    if (!host) return;
    var options = opts || {};
    var series = toNums(values);
    if (!series.length) {
      host.innerHTML = '<div class="empty" style="padding:.4rem 0">No trend data</div>';
      return;
    }
    var width = Number(options.width || 240);
    var height = Number(options.height || 56);
    var pad = Number(options.pad || 3);
    var minV = Math.min.apply(null, series);
    var maxV = Math.max.apply(null, series);
    if (minV === maxV) {
      minV = minV - 1;
      maxV = maxV + 1;
    }
    var line = pointsFor(series, width, height, pad, minV, maxV);
    var area = line + " " + (width - pad) + "," + (height - pad) + " " + pad + "," + (height - pad);
    var stroke = options.stroke || "var(--brand, #0a84ff)";
    var fill = options.fill || "rgba(10,132,255,0.12)";
    host.innerHTML =
      '<svg viewBox="0 0 ' + width + " " + height + '" preserveAspectRatio="none" role="img" aria-label="' + esc(options.ariaLabel || "trend") + '">' +
      '<polygon points="' + area + '" fill="' + fill + '"></polygon>' +
      '<polyline points="' + line + '" fill="none" stroke="' + stroke + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></polyline>' +
      "</svg>";
  }

  function renderLineChart(host, config) {
    if (!host) return;
    var cfg = config || {};
    var series = Array.isArray(cfg.series) ? cfg.series : [];
    if (!series.length) {
      host.innerHTML = '<div class="empty" style="padding:.6rem 0">No chart data</div>';
      return;
    }
    var normalized = series.map(function (s, idx) {
      return {
        name: s.name || ("Series " + (idx + 1)),
        color: s.color || "var(--brand, #0a84ff)",
        values: toNums(s.values),
      };
    }).filter(function (s) { return s.values.length > 0; });
    if (!normalized.length) {
      host.innerHTML = '<div class="empty" style="padding:.6rem 0">No chart data</div>';
      return;
    }

    var width = Number(cfg.width || 560);
    var height = Number(cfg.height || 180);
    var pad = Number(cfg.pad || 14);
    var all = [];
    normalized.forEach(function (s) { all = all.concat(s.values); });
    var minV = Math.min.apply(null, all);
    var maxV = Math.max.apply(null, all);
    if (minV === maxV) {
      minV = minV - 1;
      maxV = maxV + 1;
    }

    var grid = "";
    for (var i = 0; i < 4; i++) {
      var y = pad + ((height - pad * 2) * i / 3);
      grid += '<line x1="' + pad + '" y1="' + y + '" x2="' + (width - pad) + '" y2="' + y + '" stroke="var(--line-soft, #e6ebf2)" stroke-width="1"></line>';
    }

    var polylines = normalized.map(function (s) {
      var pts = pointsFor(s.values, width, height, pad, minV, maxV);
      var parts = pts.split(" ");
      var last = parts.length ? parts[parts.length - 1].split(",") : [pad, height - pad];
      return (
        '<polyline points="' + pts + '" fill="none" stroke="' + s.color + '" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"></polyline>' +
        '<circle cx="' + last[0] + '" cy="' + last[1] + '" r="2.8" fill="' + s.color + '"></circle>'
      );
    }).join("");

    var legend = normalized.map(function (s) {
      return '<span style="display:inline-flex;align-items:center;gap:.35rem;margin-right:.8rem;font-size:.72rem;color:var(--text-muted)">' +
        '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + s.color + '"></span>' +
        esc(s.name) +
        "</span>";
    }).join("");

    host.innerHTML =
      '<div style="display:flex;justify-content:space-between;align-items:center;margin:0 0 .45rem 0">' +
      '<div style="font-size:.75rem;color:var(--text-faint)">' + esc(cfg.caption || "") + "</div>" +
      '<div>' + legend + "</div>" +
      "</div>" +
      '<svg viewBox="0 0 ' + width + " " + height + '" preserveAspectRatio="none" role="img" aria-label="' + esc(cfg.ariaLabel || "line chart") + '">' +
      grid + polylines +
      "</svg>";
  }

  window.PCChartsLite = {
    renderSparkline: renderSparkline,
    renderLineChart: renderLineChart,
  };
})();

