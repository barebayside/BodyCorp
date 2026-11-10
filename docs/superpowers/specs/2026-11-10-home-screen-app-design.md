# Home-screen app and phone notifications — design and wiring

2026-11-10 · Decision: NEXT.md item 0b (Edward: a home-screen web app, no App Store or Google Play).
Status: the parts are built and tested; **nothing is wired into the portal yet.** This file says exactly
what to change in `portal.html`, `portal.js`, `main.py`, `store.py` and the senders to switch it on.

## What it is, in plain words

- A resident opens the portal on their phone and gets a quiet line: "Add Alatai to your Home Screen".
  On iPhone it shows the steps (Share, then Add to Home Screen); on Android it's one tap.
- From the Home Screen the portal opens full-screen with Alatai's icon and colours, starts fast, and
  shows "You're offline" instead of a browser error when there's no signal.
- Once it's on the Home Screen, the person can tap "Turn on notifications". After that their phone buzzes
  when something needs them. **Email still goes out every time**: notifications are a nudge, not the record.
- iPhone needs iOS 16.4 or later and the app added to the Home Screen first; notifications don't exist in
  a Safari tab. Android works in Chrome straight away, installed or not.

## Built (new files only)

| File | What it is |
|---|---|
| `catalyst/client/sw.js` | Service worker: keeps a copy of the app's files, offline screen, shows pushes, opens the right screen on tap. Never touches `/server/`. |
| `catalyst/client/manifest-altai.webmanifest` | Alatai's app card: "Alatai on the Park" / "Alatai", Canopy `#243B2F`, Paper `#F9F7EF`, start `portal.html?b=altai`. |
| `catalyst/client/icons/altai-*.png` | 512, 192, 180 (iPhone), 32 (tab), maskable-512 (Android shapes), badge-96 (status bar, white). A light Newsreader "A" in front of an olive fig crown on Canopy. |
| `catalyst/client/icons/product-*.png` | The same set for the product: a front-door arch on Ink. Used by any building without its own. |
| `catalyst/functions/bodycorp_api/push.py` | Web Push sender (RFC 8291 encryption + RFC 8292 VAPID, `cryptography` only) and the subscribe/unsubscribe logic. |
| `tests/test_push.py` | 19 tests, including RFC 8291's own worked example byte for byte. |

Checked in Chromium against a local copy: manifest has no errors and is installable, a push shows the
right title, body, icon and link, the kept page opens with the server stopped, an unseen page gets the
offline screen, and nothing under `/server/` is ever kept.

**Why not pywebpush:** Catalyst's deploy runs `pip install --platform manylinux2014_x86_64
--only-binary=:all:`. pywebpush needs `http-ece`, which has no wheel, so the deploy would fail.
`cryptography==43.0.3` does have the right wheel (cp39-abi3 manylinux2014) and is all `push.py` needs.

## Switch-on steps (coordinator)

### 1. Back end

1. `requirements.txt`: add `cryptography==43.0.3` (newer versions may only ship wheels the deploy's
   `--platform manylinux2014_x86_64` can't take). Locally: `py -3.9 -m pip install cryptography==43.0.3`
   (already installed on this PC).
2. `store.py`: add the table (it already exists in Catalyst, Development):
   ```python
   PUSH_SUBS = "Push_Subs"
   # Web Push devices (2026-11-10). "Keys" is a reserved word in the Data Store, hence Sub_Keys.
   PUSH_SUBS: {"required": ("User_Id", "Building_Id", "Endpoint", "Sub_Keys"), "unique": (),
               "sizes": {"Endpoint": TEXT_MAX, "Sub_Keys": TEXT_MAX, "User_Agent": 255}},
   ```
   and add `"Endpoint", "Sub_Keys"` to `_TEXT`. (`push.py` reads `store.PUSH_SUBS` when it exists.)
   Once it's in SCHEMA the fake store has the table; the `db` fixture in `test_push.py` still works.
3. `failures.py` docstring KINDS: add `push   a phone notification couldn't be delivered (host + status only)`.
4. Env vars in `catalyst-config.json` (git-ignored) and the example file (placeholders):
   `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` = `mailto:edward@barebaysidelabs.com`.
   The real keys are in the session scratchpad `vapid.json`, not in the repo. **The same keys must go on
   the live copy at go-live**: new keys would silently orphan every phone that subscribed on the test copy
   (they'd need to turn notifications on again).
5. Routes in `main.py` (ROUTES table and the route map docstring):

   | Route | Who | Body / query | Answer |
   |---|---|---|---|
   | `GET /push/key` | public | `b` | `{ok, key}` (`push.public_key()`, `""` = not set up, so the page hides the button) |
   | `POST /push/subscribe` | signed in, belongs to the building (any approved unit or any role) | `{b, subscription: {endpoint, keys: {p256dh, auth}}}` (exactly `PushSubscription.toJSON()`) | `{ok, subscribed: true}` |
   | `DELETE /push/subscribe` | signed in | `{b, endpoint}` | `{ok, subscribed: false, removed}` |

   Handlers: `push.subscribe(c.db, building, user, c.body, c.headers.get("User-Agent", ""))` and
   `push.unsubscribe(c.db, building, user, c.body)`. Both raise `ApiError` 400 for a bad subscription.
   Someone signed in but not in the building: 403, same as the other building-scoped routes.
   `main.handler` merges query args into the body, so if Catalyst drops a DELETE body on the test copy,
   send `endpoint` in the query string; if DELETE itself is refused, add `POST /push/unsubscribe` instead.
6. Building brand: `push.message` uses `brand.app_icon` and `brand.app_badge` (relative paths), else the
   product icons. `admin._clean_brand` only keeps whitelisted keys, so either add
   `app_manifest`, `app_icon`, `app_badge`, `apple_touch` there (accept only `^icons/[a-z0-9-]+\.png$` and
   `^manifest-[a-z0-9-]+\.webmanifest$`), or write them straight into Alatai's Buildings row. Alatai's:
   `{"app_manifest": "manifest-altai.webmanifest", "app_icon": "icons/altai-192.png",
   "app_badge": "icons/altai-badge-96.png", "apple_touch": "icons/altai-180.png"}`.
   `buildings.public` already sends `brand`, so the page gets them with no other change.

### 2. Which events push (and to whom)

Same people as the email, sent right after it, one short line. Links are relative (`portal.html?b=<slug>#/...`)
so they open inside the installed app. `push.send` and `push.send_to_emails` never raise and log their own
failures, so they can't break the action. Use `push.send(db, building, user_ids, title, body, url)` when you
have user ids, `push.send_to_emails(...)` beside an existing `mailer.send`.

| Event | Where (beside the email) | To | Title / body / link |
|---|---|---|---|
| New request | `cases._email_handlers` (after the loop over `deadlines.handler_emails`) | the case's handlers | building name / "New request ALT-0042: <title>" (lead with the deadline when one is near, e.g. "Decide by 14 Nov: …") / `#/case/<id>` |
| Resident replies on a request | same `_email_handlers` call path | handlers | building name / "ALT-0042: the resident replied" / `#/case/<id>` |
| Reply, status change or decision to the resident | `cases._email_resident`, and `pipeline.send_button_email` when `to == "resident"` | `row["User_Id"]` | building name / "ALT-0042: <heading>" (e.g. "Decision made") / `#/request/<id>` |
| Stage button emails to the committee / manager | `pipeline.send_button_email` (other `to` values, via `recipients(...)`) | those recipients | building name / subject / `#/case/<id>` |
| Vote opened (outside a meeting) | `votes._send_notice`, after the committee loop | `committee.committee_ids(db, building)` (not the owners' advice: email only) | building name / "Committee vote: closes <date>" / `#/vote/<id>` |
| Task due or overdue | `deadlines.remind`, after each digest `mailer.send` | that digest's address | building name / "<n> item(s) due soon or overdue" / `#/tasks` (tasks only) or `#/inbox/due` |

Not pushed (email only, to keep the phone quiet): sign-in codes, notices, minutes, owners' advice, the
daily self-check. A sign-up waiting for an approver is a good later addition (`people.py`, `#/approvals`).

### 3. `portal.html` `<head>` (after the stylesheet link)

```html
<link rel="manifest" id="app-manifest" href="">
<link rel="apple-touch-icon" id="app-touch-icon" href="icons/product-180.png">
<link rel="icon" type="image/png" sizes="32x32" id="app-favicon" href="icons/product-32.png">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" id="app-title" content="Portal">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
```

`portal.html` serves every building, so the manifest is chosen by `portal.js` from the building's brand
(below). An empty `href` means "no app card yet", which is right for a building without one. Safari reads
these tags when Share is tapped and Chrome reads the manifest link when it changes, so setting them from
script works on both.

### 4. `portal.js`

**a. In `applyBrand(building)`, after the colours:**
```js
const app = brandOf(building);
const setHref = (id, value) => { const el = document.getElementById(id); if (el && value) el.setAttribute("href", value); };
if (app.app_manifest) setHref("app-manifest", app.app_manifest);
setHref("app-touch-icon", app.apple_touch);
setHref("app-favicon", app.app_icon && app.app_icon.replace(/-192\.png$/, "-32.png"));
const title = document.getElementById("app-title");
if (title && building && building.name) title.setAttribute("content", building.name.replace(/ on the Park$/, ""));
```
(Short name: better to add `app_short_name` to the brand than to trim; the manifest already says "Alatai".)

**b. Register the service worker (once, at start-up):**
```js
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js", { scope: "./" }).catch(() => { /* app still works without it */ });
  });
  // A tapped notification when the open window isn't controlled by the worker: go where it says.
  navigator.serviceWorker.addEventListener("message", (event) => {
    if (event.data && event.data.type === "open" && event.data.url) location.href = event.data.url;
  });
}
```

**c. Helpers:**
```js
const INSTALL_DISMISSED = "bodycorp_install_dismissed";
const isStandalone = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
const isIPhone = () => /iphone|ipad|ipod/i.test(navigator.userAgent) ||
  (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);   // iPadOS says "Mac"
const canPush = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

let installPrompt = null;   // Android/Chrome hands this over once; we show our own button instead of its bar
window.addEventListener("beforeinstallprompt", (event) => { event.preventDefault(); installPrompt = event; drawAppRow(); });
window.addEventListener("appinstalled", () => { installPrompt = null; drawAppRow(); });

function urlKey(base64url) {
  const pad = "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob((base64url + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

async function sendSubscription(sub) {
  await api(withB("/push/subscribe"), { body: { b: state.b, subscription: sub.toJSON() } });
}

async function turnOnNotifications() {          // ONLY ever called from a tap
  const { key } = await api(withB("/push/key"));
  if (!key) throw new Error("Notifications aren't set up yet.");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") { drawAppRow(); return; }
  const reg = await navigator.serviceWorker.ready;
  const sub = (await reg.pushManager.getSubscription()) ||
              (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlKey(key) }));
  await sendSubscription(sub);
  drawAppRow();
}

// On every signed-in start: if notifications are on, re-send the subscription so the server stays current
// (phones change it now and then; the server also moves a shared phone to whoever signed in last).
async function refreshSubscription() {
  if (!canPush() || Notification.permission !== "granted") return;
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) await sendSubscription(sub);
  } catch (e) { /* email still reaches them */ }
}
```
Call `refreshSubscription()` after `loadMe()` succeeds.

**d. Sign-out**, in `signOut()` before `/auth/logout` (the session is still valid):
```js
try {
  const reg = canPush() && await navigator.serviceWorker.getRegistration();
  const sub = reg && await reg.pushManager.getSubscription();
  if (sub) await api(withB("/push/subscribe", { endpoint: sub.endpoint }), { method: "DELETE", body: { b: state.b, endpoint: sub.endpoint } });
} catch (e) { /* signing out anyway */ }
```
(Keep the browser's subscription: the next person to sign in on that phone re-sends it as theirs.)

**e. The row itself** — `drawAppRow()` fills a `<div id="app-row">` on the home screen (resident and staff),
as one hairline row in the existing style (small uppercase label, one sentence, an underlined text link; no
pop-up, no pill, not the screen's filled button). What it shows, in order:

| Situation | Label · line · link |
|---|---|
| Not installed, Android/Chrome, `installPrompt` set | ON YOUR PHONE · Add Alatai to your Home Screen. · **Add** → `installPrompt.prompt()` |
| Not installed, iPhone/iPad (Safari, or Chrome/Edge on iOS 16.4+) | ON YOUR PHONE · Add Alatai to your Home Screen: tap **Share** (the square with the arrow), then **Add to Home Screen**, then **Add**. Then open it from there. · **Done** (dismiss) |
| Not installed, iPhone, inside another app's browser (Gmail, Facebook) | Open this page in Safari to add it to your Home Screen. |
| Not installed, desktop | nothing |
| Installed (or Android without install) and `canPush()` and permission `default` | NOTIFICATIONS · Get a message on this phone when something needs you. · **Turn on** → `turnOnNotifications()` |
| Permission `granted` | nothing (or a quiet "Notifications are on for this phone.") |
| Permission `denied` | NOTIFICATIONS · Turned off for this app. iPhone: Settings → Notifications → Alatai. Android: hold the app icon → App info → Notifications. |

Rules: never call `Notification.requestPermission()` on page load, only from the "Turn on" tap (iPhone
refuses it otherwise, and Chrome hides the prompt for pages that ask unasked). On iPhone show the
notifications line **only when `isStandalone()`**: in a Safari tab `PushManager` doesn't exist, so offer
Add to Home Screen first. "Done"/dismiss stores `INSTALL_DISMISSED` via `local.set` and hides the install
line for 30 days; the notifications line can't be dismissed while permission is `default` but stays one
quiet row. When `GET /push/key` returns `""` (keys not set on that copy), don't show the notifications line.

### 5. Deploy and prove it

1. Tests: `py -3.9 -m pytest -q tests`.
2. `catalyst deploy --only functions` then `--only client` (test copy). Check `GET /server/bodycorp_api/`
   is `{ok:true}`, `GET /push/key?b=altai` returns the key, and that `manifest-altai.webmanifest` and
   `sw.js` load from `/app/` (the browser takes a manifest with any content type; if the service worker
   is refused for its type, that's a hosting problem to raise).
3. Real phones (NEXT.md 0b go-live check): an iPhone on iOS 16.4+ and an Android.
   Add to Home Screen → open from the icon (full-screen, Alatai icon, green bar) → sign in → Turn on → from a
   second account lodge a request to a handler on that phone → the phone buzzes → tapping it opens the
   request. Airplane mode → open the app → it opens (kept copy) or says "You're offline", never a browser
   error. Sign out → lodge again → no buzz on that phone.
4. Bump `VERSION` in `sw.js` whenever its `SHELL` list changes. Ordinary deploys don't need it: the page and
   its files are always fetched fresh first.
