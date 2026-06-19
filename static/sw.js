/* Minimal service worker: cache the static shell, stay out of the way for
   everything dynamic (POST /calculate, report downloads, navigations). */
const CACHE = "allora-density-v3";
const SHELL = [
  "/",
  "/static/css/brand.css",
  "/static/js/app.js",
  "/static/js/htmx.min.js",
  "/static/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/assets/logos/allora_logo_white.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const { request } = e;
  // Only handle GETs for static/asset files; let the network own the rest.
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.pathname.startsWith("/static/") || url.pathname.startsWith("/assets/")) {
    // Network-first: fresh assets when online, cached fallback when offline.
    e.respondWith(
      fetch(request).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(request, copy));
        return res;
      }).catch(() => caches.match(request))
    );
  }
});
