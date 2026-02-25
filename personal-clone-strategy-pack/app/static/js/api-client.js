(function () {
  var tokenPromise = null;
  var tokenFetchedAt = 0;
  var TOKEN_TTL_MS = 7 * 60 * 60 * 1000; // 7 hours (server token lasts 8h)

  function getCsrfToken() {
    var pair = document.cookie.split("; ").find(function (c) {
      return c.startsWith("pc_csrf=");
    });
    return pair ? decodeURIComponent(pair.split("=").slice(1).join("=")) : "";
  }

  function _clearToken() {
    tokenPromise = null;
    tokenFetchedAt = 0;
  }

  async function getApiToken() {
    var now = Date.now();
    if (tokenPromise && (now - tokenFetchedAt) < TOKEN_TTL_MS) {
      return tokenPromise;
    }
    _clearToken();
    tokenFetchedAt = now;
    tokenPromise = fetch("/web/api-token")
      .then(function (r) {
        if (!r.ok) {
          if (r.status === 401) window.location.href = "/web/login";
          throw new Error("session_expired");
        }
        return r.json();
      })
      .then(function (d) {
        return d.token || null;
      })
      .catch(function (err) {
        _clearToken();
        throw err;
      });
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
      if (response.status === 401) {
        _clearToken();
        window.location.href = "/web/login";
      }
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
