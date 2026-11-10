/* BodyCorp home-screen app: the service worker.

   Lives at /app/sw.js, so it looks after everything under /app/ (every building's portal).
   It does three things:
   1. Keeps a copy of the app's own files (page, styles, script, icons) so the app opens on a
      bad connection, and shows a plain "You're offline" page when there's no copy and no signal.
      The page is always fetched fresh first (so a deploy shows up at once); the copy is the fallback.
   2. Never keeps anything from /server/ (requests, documents, sign-in): those are private and live.
   3. Shows phone notifications (Web Push) and opens the right screen when one is tapped.

   Bump VERSION when the list of SHELL files changes; old copies are cleared on the next start. */

const VERSION = "v1";
const CACHE = "bodycorp-shell-" + VERSION;
const FONT_CACHE = "bodycorp-fonts-" + VERSION;
const SHELL = ["portal.html", "portal.css", "portal.js", "icons/product-192.png", "icons/product-badge-96.png"];
const NETWORK_WAIT_MS = 3500;   // a slow page start falls back to the kept copy after this

const OFFLINE_HTML = `<!doctype html>
<html lang="en-AU"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#243B2F"><title>You're offline</title>
<style>
  :root { --brand:#243B2F; --paper:#F9F7EF; --ink:#22272B; --muted:#5b625e; }
  * { box-sizing: border-box; }
  html, body { margin: 0; min-height: 100%; }
  body { background: var(--paper); color: var(--ink); font: 400 16.5px/1.6 "Hanken Grotesk", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  header { background: var(--brand); color: var(--paper); padding: 26px 20px 22px; }
  header span { font: 300 26px/1.1 "Newsreader", Georgia, serif; }
  main { max-width: 640px; padding: 32px 20px; }
  h1 { font: 300 34px/1.1 "Newsreader", Georgia, serif; color: var(--brand); margin: 0 0 12px; }
  p { color: var(--muted); margin: 8px 0; }
  button { margin-top: 20px; background: var(--brand); color: var(--paper); border: 0; border-radius: 3px;
           font: 600 15px/1 "Hanken Grotesk", system-ui, sans-serif; padding: 16px 24px; cursor: pointer; }
</style></head>
<body><header><span>Building portal</span></header>
<main><h1>You're offline</h1>
<p>This phone isn't connected to the internet just now, so the portal can't load.</p>
<p>Your requests and messages are safe. Try again when you have signal or Wi-Fi.</p>
<button type="button" onclick="location.reload()">Try again</button></main></body></html>`;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => Promise.all(SHELL.map((path) =>
        // One missing file must not stop the app installing.
        cache.add(new Request(path, { cache: "reload" })).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names
        .filter((name) => name.startsWith("bodycorp-") && name !== CACHE && name !== FONT_CACHE)
        .map((name) => caches.delete(name))))
      .then(() => self.clients.claim())
  );
});

function isPrivate(url) {
  // Anything the server answers, and Catalyst's own sign-in paths: never kept, never touched.
  return url.pathname.includes("/server/") || url.pathname.includes("/__catalyst/") ||
         url.pathname.includes("/baas/") || url.pathname.includes("/accounts/");
}

function offlinePage() {
  return new Response(OFFLINE_HTML, { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } });
}

function withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("slow")), ms);
    promise.then((value) => { clearTimeout(timer); resolve(value); },
                 (error) => { clearTimeout(timer); reject(error); });
  });
}

// Fresh from the network first, keep a copy; if the network fails or is slow, the copy; else offline.
async function networkFirst(request, isPage) {
  const cache = await caches.open(CACHE);
  const fetching = fetch(request).then((response) => {
    if (response && response.ok && response.type === "basic") {
      cache.put(request, response.clone()).catch(() => null);
    }
    return response;
  });
  try {
    return await withTimeout(fetching, NETWORK_WAIT_MS);
  } catch (error) {
    // ignoreSearch: portal.html?b=altai and ?b=other share one kept page; portal.js reads b.
    const kept = await cache.match(request, { ignoreSearch: true });
    if (kept) return kept;
    try { return await fetching; } catch (_) { /* fall through */ }
    return isPage ? offlinePage() : Response.error();
  }
}

// Google Fonts: kept once, used forever (the files never change at a given address).
async function fontFirst(request) {
  const cache = await caches.open(FONT_CACHE);
  const kept = await cache.match(request);
  if (kept) return kept;
  try {
    const response = await fetch(request);
    if (response && (response.ok || response.type === "opaque")) cache.put(request, response.clone()).catch(() => null);
    return response;
  } catch (error) {
    return Response.error();
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com") {
    event.respondWith(fontFirst(request));
    return;
  }
  if (url.origin !== self.location.origin || isPrivate(url)) return;   // the browser handles it, nothing kept
  if (!url.pathname.startsWith(new URL(self.registration.scope).pathname)) return;

  const isPage = request.mode === "navigate";
  event.respondWith(networkFirst(request, isPage));
});

// ---------- phone notifications ----------

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (error) {
    data = { body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "Building portal";
  const options = {
    body: data.body || "There's something new for you in the portal.",
    icon: data.icon || "icons/product-192.png",
    badge: data.badge || "icons/product-badge-96.png",
    tag: data.tag || undefined,        // a newer push for the same building replaces the older one
    renotify: Boolean(data.tag),
    data: { url: data.url || "portal.html" },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || "portal.html",
                         self.registration.scope).href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const path = new URL(target).pathname;
    const open = windows.find((client) => new URL(client.url).pathname === path) ||
                 windows.find((client) => client.url.startsWith(self.registration.scope));
    if (open) {
      await open.focus();
      if (open.url !== target) {
        // navigate() only works on a window this worker looks after; otherwise ask the page to go there.
        try { await open.navigate(target); } catch (error) { open.postMessage({ type: "open", url: target }); }
      }
      return;
    }
    await self.clients.openWindow(target);
  })());
});

// The push service replaced this phone's subscription (rare). The page re-sends its
// subscription every time it opens, so nothing to do here except keep the new one alive.
self.addEventListener("pushsubscriptionchange", (event) => {
  const old = event.oldSubscription;
  if (!old || !old.options) return;
  event.waitUntil(self.registration.pushManager.subscribe(old.options).catch(() => null));
});
