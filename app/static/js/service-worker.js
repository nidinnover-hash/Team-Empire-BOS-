/**
 * Nidin BOS — Service Worker
 * Strategy: cache-first for static assets, network-first for API/HTML.
 */

'use strict';

var CACHE_NAME = 'nidin-bos-v1';

// Static assets to pre-cache on install
var PRECACHE_URLS = [
  '/',
  '/static/css/shared.css',
  '/static/css/theme.css',
  '/static/css/dashboard.css',
  '/static/js/ui-utils.js',
  '/static/favicon.svg',
  '/static/manifest.json',
];

// ── Install ───────────────────────────────────────────────────────────────────

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(PRECACHE_URLS);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

// ── Activate ──────────────────────────────────────────────────────────────────

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys
          .filter(function (key) { return key !== CACHE_NAME; })
          .map(function (key) { return caches.delete(key); })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

// ── Fetch ─────────────────────────────────────────────────────────────────────

self.addEventListener('fetch', function (event) {
  var url = new URL(event.request.url);

  // Never intercept API calls, auth, or non-GET requests
  if (
    event.request.method !== 'GET' ||
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/web/login') ||
    url.pathname.startsWith('/web/logout')
  ) {
    return;
  }

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(function (cached) {
        if (cached) return cached;
        return fetch(event.request).then(function (response) {
          if (response && response.status === 200) {
            var clone = response.clone();
            caches.open(CACHE_NAME).then(function (cache) {
              cache.put(event.request, clone);
            });
          }
          return response;
        });
      })
    );
    return;
  }

  // HTML pages: network-first, fallback to cache
  event.respondWith(
    fetch(event.request).then(function (response) {
      if (response && response.status === 200) {
        var clone = response.clone();
        caches.open(CACHE_NAME).then(function (cache) {
          cache.put(event.request, clone);
        });
      }
      return response;
    }).catch(function () {
      return caches.match(event.request).then(function (cached) {
        return cached || caches.match('/');
      });
    })
  );
});
