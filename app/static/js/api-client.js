(function () {
  var tokenPromise = null;

  function getCsrfToken() {
    var pair = document.cookie.split("; ").find(function (c) {
      return c.startsWith("pc_csrf=");
    });
    return pair ? decodeURIComponent(pair.split("=")[1]) : "";
  }

  async function getApiToken() {
    if (!tokenPromise) {
      tokenPromise = fetch("/web/api-token")
        .then(function (r) {
          if (!r.ok) throw new Error("session_expired");
          return r.json();
        })
        .then(function (d) {
          return d.token || null;
        })
        .catch(function (err) {
          tokenPromise = null;
          throw err;
        });
    }
    return tokenPromise;
  }

  async function safeFetchJson(path, options) {
    var opts = options || {};
    var method = opts.method || "GET";
    var includeAuth = opts.auth === true;
    var includeCsrf = opts.csrf === true;
    var headers = opts.headers || {};
    var externalSignal = opts.signal || null;

    if (includeAuth && !headers.Authorization) {
      var token = opts.token || (await getApiToken());
      if (!token) throw new Error("session_expired");
      headers.Authorization = "Bearer " + token;
    }
    if (includeCsrf && !headers["X-CSRF-Token"]) {
      var csrf = getCsrfToken();
      if (csrf) headers["X-CSRF-Token"] = csrf;
    }

    var retries = typeof opts.retries === "number" ? opts.retries : 1;
    var timeoutMs = typeof opts.timeoutMs === "number" ? opts.timeoutMs : 15000;
    var response = null;
    var lastErr = null;
    for (var attempt = 0; attempt <= retries; attempt++) {
      var controller = new AbortController();
      var onExternalAbort = null;
      if (externalSignal) {
        if (externalSignal.aborted) controller.abort();
        else {
          onExternalAbort = function () { controller.abort(); };
          externalSignal.addEventListener("abort", onExternalAbort, { once: true });
        }
      }
      var timer = setTimeout(function () { controller.abort(); }, timeoutMs);
      try {
        response = await fetch(path, {
          method: method,
          headers: headers,
          body: opts.body,
          signal: controller.signal,
        });
        clearTimeout(timer);
        if (externalSignal && onExternalAbort) externalSignal.removeEventListener("abort", onExternalAbort);
        if (response.status >= 500 && attempt < retries) {
          await new Promise(function (r) { setTimeout(r, 250 * (attempt + 1)); });
          continue;
        }
        break;
      } catch (e) {
        clearTimeout(timer);
        if (externalSignal && onExternalAbort) externalSignal.removeEventListener("abort", onExternalAbort);
        lastErr = e;
        if (attempt >= retries) throw e;
        await new Promise(function (r) { setTimeout(r, 250 * (attempt + 1)); });
      }
    }
    if (!response && lastErr) throw lastErr;

    var body = await response.json().catch(function () {
      return {};
    });
    if (!response.ok) {
      var detail = body && body.detail ? body.detail : ("Request failed (" + response.status + ")");
      var err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      err.status = response.status;
      err.body = body;
      throw err;
    }
    return body;
  }

  window.PCAPI = {
    getCsrfToken: getCsrfToken,
    getApiToken: getApiToken,
    safeFetchJson: safeFetchJson,
  };
})();
