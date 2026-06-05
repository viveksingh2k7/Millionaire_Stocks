/* ─────────────────────────────────────────────────────────────
   Millionaire Stocks — Service Worker
   Cache strategy:
     • Static shell  → cache-first
     • Data JSON     → network-first with cache fallback
     • CDN assets    → network-first with cache fallback
   Bump CACHE_NAME version on every static asset change.
───────────────────────────────────────────────────────────── */
const CACHE_NAME    = 'ms-stocks-v3';   // bumped: India NSE market added
const DATA_CACHE    = 'ms-stocks-data-v1';

const STATIC_ASSETS = [
  './index.html',
  './manifest.json',
  './icons/icon-48.png',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon.svg',
  './icons/icon-maskable.svg',
];

const DATA_ASSETS = [
  './signals.json',
  './portfolio.json',
  './trade_log.json',
  './prices.json',
  './india_stocks.json',
];

const CDN_ASSETS = [
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js',
  'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap',
];

/* ── Install: cache static shell ───────────────────────────── */
self.addEventListener('install', e => {
  e.waitUntil(
    Promise.all([
      caches.open(CACHE_NAME).then(c => c.addAll(STATIC_ASSETS)),
      caches.open(CACHE_NAME).then(c =>
        Promise.allSettled(CDN_ASSETS.map(url =>
          fetch(url).then(res => { if (res.ok) c.put(url, res); })
        ))
      ),
    ]).then(() => self.skipWaiting())
  );
});

/* ── Activate: remove old caches ──────────────────────────── */
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== CACHE_NAME && k !== DATA_CACHE)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

/* ── Fetch ────────────────────────────────────────────────── */
self.addEventListener('fetch', e => {
  const { request } = e;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') return;

  // ── Data JSON files: network-first (always try to get fresh data)
  if (DATA_ASSETS.some(d => url.pathname.endsWith(d.replace('./', '/')))) {
    e.respondWith(
      fetch(request)
        .then(res => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(DATA_CACHE).then(c => c.put(request, clone));
          }
          return res;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // ── CDN assets: network-first with cache fallback
  if (url.hostname !== self.location.hostname) {
    e.respondWith(
      fetch(request)
        .then(res => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE_NAME).then(c => c.put(request, clone));
          }
          return res;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // ── Local static assets: cache-first
  e.respondWith(
    caches.match(request).then(cached => {
      if (cached) return cached;
      return fetch(request).then(res => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(c => c.put(request, clone));
        }
        return res;
      });
    })
  );
});
