// Small service worker: makes the app installable and shows a friendly offline page
// instead of the browser's error. No background sync or push.
const CACHE_NAME = "growth-planner-v2";
const OFFLINE_URL = "/offline/";
const PRECACHE = [
  OFFLINE_URL,
  "/static/manifest.json",
  "/static/css/app.css",
  "/static/js/app.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/favicon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    // Precache one by one so a single missing file can't break the whole install.
    caches.open(CACHE_NAME)
      .then((cache) => Promise.all(PRECACHE.map((url) => cache.add(url).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  // Pages: network first (logged-in content must be fresh); offline page as the fallback.
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }

  // Our own static files: serve from cache instantly, refresh in the background
  // (stale-while-revalidate), so a CSS/JS update shows up on the next visit.
  if (url.origin === self.location.origin && url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) =>
        cache.match(request).then((cached) => {
          const network = fetch(request).then((response) => {
            if (response && response.ok) cache.put(request, response.clone());
            return response;
          }).catch(() => cached);
          return cached || network;
        })
      )
    );
  }
});
