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

    if (includeAuth && !headers.Authorization) {
      var token = opts.token || (await getApiToken());
      if (!token) throw new Error("session_expired");
      headers.Authorization = "Bearer " + token;
    }
    if (includeCsrf && !headers["X-CSRF-Token"]) {
      var csrf = getCsrfToken();
      if (csrf) headers["X-CSRF-Token"] = csrf;
    }

    var response = await fetch(path, {
      method: method,
      headers: headers,
      body: opts.body,
    });

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

