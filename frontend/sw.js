/* GullyScore app-shell service worker.
 *
 * Static assets are cache-first; API GETs are network-first with a cached
 * fallback so a scorekeeper can reopen the app offline. Mutations are never
 * cached or replayed here; the scoring queue lives in the page (localStorage)
 * with server-side idempotency keys.
 */
const CACHE = "gullyscore-shell-v5-4";
const SHELL = [
  "/",
  "/index.html",
  "/pages/live.html",
  "/pages/matches.html",
  "/pages/match-type.html",
  "/pages/setup-turf.html",
  "/pages/setup-t20.html",
  "/pages/setup-custom.html",
  "/pages/series-new.html",
  "/pages/series.html",
  "/pages/scorecard.html",
  "/pages/stats.html",
  "/pages/settings.html",
  "/pages/login.html",
  "/css/app.css",
  "/config.js",
  "/js/api.js",
  "/js/dom.js",
  "/js/prefs.js",
  "/js/theme.js",
  "/js/pwa.js",
  "/js/offline.js",
  "/js/home.js",
  "/js/live.js",
  "/js/matches.js",
  "/js/scorecard.js",
  "/js/series-new.js",
  "/js/series.js",
  "/js/settings.js",
  "/js/login.js",
  "/js/setup.js",
  "/js/static-page.js",
  "/components/shell.js",
  "/components/ui.js",
  "/manifest.webmanifest",
  "/icons/icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      Promise.allSettled(SHELL.map((url) => cache.add(new Request(url, { cache: "reload" })))),
    ),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("sync", (event) => {
  if (event.tag !== "gully-score-sync") return;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      clients.forEach((client) => client.postMessage({ type: "GULLY_SYNC_REQUEST" }));
    }),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request)),
    );
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(async () => (await caches.match(request)) || caches.match("/index.html")),
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ||
        fetch(request).then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        }),
    ),
  );
});
