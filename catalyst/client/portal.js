// The whole portal on one page, routed by the part of the address after "#".
// The building comes from ?b=<code>. Everything is checked again by the bodycorp_api
// function; the page only hides what a person can't use. Every reply must carry
// ok: true or it is treated as a failure.

"use strict";

const API = "/server/bodycorp_api";
const TOKEN_KEY = "bodycorp_token";
const MAX_FILE = 5 * 1024 * 1024;
const DRAFT_TEXT = "Draft — to be checked against the building's CMS and by-laws";
const GUIDANCE_TEXT = "Steps are guidance, checked by your advisors.";

const STATUSES = ["new", "in_progress", "waiting_on_resident", "with_committee", "decided", "closed"];
const STATUS_RESIDENT = {
  new: "Received", in_progress: "Being worked on", waiting_on_resident: "Waiting on you",
  with_committee: "With the committee", decided: "Decided", closed: "Closed",
};
const STATUS_STAFF = {
  new: "New", in_progress: "In progress", waiting_on_resident: "Waiting on resident",
  with_committee: "With the committee", decided: "Decided", closed: "Closed",
};
const OUTCOMES = {
  approved: "Approved", approved_with_conditions: "Approved with conditions", refused: "Refused",
  deemed_approved: "Treated as approved (no decision in time)", not_agreed: "Treated as not agreed (no decision in time)",
};
const ROLES = {
  chair: "Chair", secretary: "Secretary", treasurer: "Treasurer", member: "Committee member (votes)",
  committee: "Committee (no vote)", manager: "Building manager", approver: "Approver", admin: "Admin",
};
const POSITIONS = { chair: "Chair", secretary: "Secretary", treasurer: "Treasurer", member: "Ordinary members", committee: "Committee (no vote)" };
const HOW = { present: "In person", electronic: "Phone or video", proxy: "By proxy", absent: "Absent" };
const VOTE_WORDS = { yes: "Yes", no: "No", abstain: "Abstain", conflict: "Conflict declared" };
const TO_WHO = { resident: "the resident", committee: "the committee", voting: "the voting members", manager: "the building manager" };
const HANDLERS = { committee: "Committee", manager: "Building manager" };
const CLAIM_STATUS = { pending: "Waiting", approved: "Approved", rejected: "Not approved", removed: "Removed" };
const EVENT_KINDS = { created: "Request sent", status: "Status changed", step: "Step updated", decision: "Decision recorded", decided: "Decision recorded", action: "Step taken", vote: "Vote" };
const DOC_KINDS = ["Minutes", "By-laws", "CMS", "Notice of meeting", "Insurance", "Other"];

const state = {
  b: "", building: null, units: [], me: null, topics: null,
  email: "", flash: "", signinNote: "",
};

// ------------------------------------------------------------------ small helpers

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const enc = encodeURIComponent;

function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"'`]/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;", "`": "&#96;",
  }[c]));
}

const lines = (text) => esc(text).replace(/\r?\n/g, "<br>");
const isTrue = (v) => v === true || v === 1 || v === "true" || v === "1";
const num = (v) => (v === null || v === undefined || v === "" || !isFinite(Number(v)) ? null : Number(v));

function parseMaybe(v, fallback) {
  if (typeof v !== "string") return v == null ? fallback : v;
  try { return JSON.parse(v); } catch (e) { return fallback; }
}

// localStorage can throw (private windows, blocked storage); keep a copy in memory too.
const memory = {};
const local = {
  get(k) { try { const v = localStorage.getItem(k); if (v !== null) return v; } catch (e) { /* fall through */ } return memory[k] || null; },
  set(k, v) { memory[k] = v; try { localStorage.setItem(k, v); } catch (e) { /* memory only */ } },
  remove(k) { delete memory[k]; try { localStorage.removeItem(k); } catch (e) { /* ignore */ } },
};

// Catalyst ROWIDs are bigger than JavaScript can hold exactly, so long numbers
// in a reply are kept as strings and sent back exactly as they came.
function quoteBigInts(text) {
  let out = "";
  let i = 0;
  let inString = false;
  while (i < text.length) {
    const c = text[i];
    if (inString) {
      if (c === "\\") { out += c + (text[i + 1] || ""); i += 2; continue; }
      if (c === '"') inString = false;
      out += c; i++; continue;
    }
    if (c === '"') { inString = true; out += c; i++; continue; }
    if ((c >= "0" && c <= "9") || c === "-") {
      let j = i + 1;
      while (j < text.length && /[0-9.eE+-]/.test(text[j])) j++;
      const token = text.slice(i, j);
      out += /^-?\d{16,}$/.test(token) ? '"' + token + '"' : token;
      i = j; continue;
    }
    out += c; i++;
  }
  return out;
}

function parseUtc(s) {
  if (!s) return null;
  const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/);
  if (m) return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0)));
  const d = new Date(s);
  return isNaN(d) ? null : d;
}

function timeZone() {
  const b = state.building || {};
  return b.timezone || (b.settings && b.settings.timezone) || "Australia/Brisbane";
}

function fmtDate(s) {
  const d = parseUtc(s);
  if (!d) return "";
  try { return d.toLocaleDateString("en-AU", { timeZone: timeZone(), day: "numeric", month: "short", year: "numeric" }); }
  catch (e) { return d.toDateString(); }
}

function fmtWhen(s) {
  const d = parseUtc(s);
  if (!d) return "";
  try {
    return d.toLocaleString("en-AU", { timeZone: timeZone(), day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
  } catch (e) { return d.toString(); }
}

function daysText(v) {
  const n = num(v);
  if (n === null) return "";
  if (n < 0) return (-n === 1 ? "1 day" : -n + " days") + " overdue";
  if (n === 0) return "Due today";
  return (n === 1 ? "1 day" : n + " days") + " left";
}

const isUrgent = (v) => num(v) !== null && num(v) <= 3;
const isFinished = (c) => c.status === "decided" || c.status === "closed";

function takeFlash() {
  const f = state.flash;
  state.flash = "";
  return f ? `<p class="okmsg" role="status">${esc(f)}</p>` : "";
}

// ------------------------------------------------------------------ server

class Quiet extends Error {}   // already handled (e.g. sent back to sign-in); show nothing

function withB(path, params) {
  const q = new URLSearchParams({ b: state.b });
  Object.entries(params || {}).forEach(([k, v]) => q.set(k, v));
  return path + "?" + q.toString();
}

function authHeaders() {
  const token = local.get(TOKEN_KEY);
  // Catalyst's gateway rejects any Authorization header, so the session goes in X-Session.
  return token ? { "X-Session": token } : {};
}

async function api(path, opts = {}) {
  const hasBody = opts.body !== undefined;
  const method = opts.method || (hasBody ? "POST" : "GET");
  const headers = authHeaders();
  if (hasBody) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(API + path, { method, headers, body: hasBody ? JSON.stringify(opts.body) : undefined });
  } catch (e) {
    throw new Error("Can't reach the server. Check your connection and try again.");
  }
  let data = null;
  try { data = JSON.parse(quoteBigInts(await res.text())); } catch (e) { data = null; }
  if (res.status === 401 && !path.startsWith("/auth/")) {
    signOutHere("Please sign in again.");
    throw new Quiet("signed out");
  }
  if (!data || data.ok !== true) {
    const err = new Error((data && (data.error || data.message)) || "Something went wrong. Please try again.");
    err.status = res.status;
    throw err;
  }
  return data;
}

// Files come back as bytes, fetched with the X-Session header and turned into a blob.
async function fetchBlob(path) {
  let res;
  try { res = await fetch(API + path, { headers: authHeaders() }); }
  catch (e) { throw new Error("Can't reach the server. Check your connection and try again."); }
  if (res.status === 401) { signOutHere("Please sign in again."); throw new Quiet("signed out"); }
  const type = res.headers.get("Content-Type") || "";
  if (type.includes("application/json")) {
    let data = null;
    try { data = JSON.parse(quoteBigInts(await res.text())); } catch (e) { data = null; }
    if (data && data.ok === true && data.data) {   // in case the file is sent as base64 JSON
      const bytes = Uint8Array.from(atob(data.data), (ch) => ch.charCodeAt(0));
      return new Blob([bytes], { type: data.type || "application/octet-stream" });
    }
    throw new Error((data && data.error) || "That file couldn't be opened.");
  }
  if (!res.ok) throw new Error("That file couldn't be opened.");
  return res.blob();
}

function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name || "file";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

function fileOk(file) {
  const type = file.type || "";
  return type.startsWith("image/") || type === "application/pdf" || /\.(pdf|jpe?g|png|gif|webp|heic|heif)$/i.test(file.name);
}

function guessType(name) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  return {
    pdf: "application/pdf", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", gif: "image/gif",
    webp: "image/webp", heic: "image/heic", heif: "image/heif",
    doc: "application/msword", docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  }[ext] || "application/octet-stream";
}

function readBase64(file) {
  return new Promise((resolve, reject) => {
    if (file.size > MAX_FILE) { reject(new Error(`"${file.name}" is over 5 MB. Try a smaller file.`)); return; }
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = () => reject(new Error(`"${file.name}" couldn't be read.`));
    reader.readAsDataURL(file);
  });
}

// Run one action from a button: disable it, show any error in errorEl.
async function busy(button, errorEl, work) {
  if (errorEl) errorEl.textContent = "";
  const label = button ? button.textContent : "";
  if (button) { button.disabled = true; button.textContent = "One moment…"; }
  try {
    await work();
  } catch (e) {
    if (!(e instanceof Quiet) && errorEl) errorEl.textContent = e.message;
  } finally {
    if (button && button.isConnected) { button.disabled = false; button.textContent = label; }
  }
}

// Ask for a second tap before anything that removes or deletes.
function confirmTap(button, armedLabel, action) {
  const label = button.textContent;
  button.addEventListener("click", () => {
    if (button.dataset.armed) {
      delete button.dataset.armed;
      button.classList.remove("armed");
      button.textContent = label;
      action();
      return;
    }
    button.dataset.armed = "1";
    button.classList.add("armed");
    button.textContent = armedLabel;
    setTimeout(() => {
      if (button.dataset.armed) { delete button.dataset.armed; button.classList.remove("armed"); button.textContent = label; }
    }, 4000);
  });
}

// ------------------------------------------------------------------ branding and chrome

const isColour = (c) => typeof c === "string" && /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(c.trim());

function longHex(c) {
  c = c.trim();
  return c.length === 4 ? "#" + c[1] + c[1] + c[2] + c[2] + c[3] + c[3] : c;
}

function isLight(hex) {
  const h = longHex(hex).slice(1);
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.45;
}

function brandOf(building) {
  return parseMaybe((building || {}).brand, {}) || {};
}

function applyBrand(building) {
  state.building = building || {};
  const brand = brandOf(building);
  const root = document.documentElement.style;
  if (isColour(brand.primary)) {
    root.setProperty("--brand", brand.primary.trim());
    root.setProperty("--on-brand", isLight(brand.primary) ? "#22272B" : "#F9F7EF");
    const meta = $('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", brand.primary.trim());
  }
  if (isColour(brand.accent)) root.setProperty("--accent", brand.accent.trim());

  const name = building.name || "Building portal";
  $("#bname").textContent = name;
  document.title = building.name ? building.name : "Building portal";

  const logo = $("#logo");
  const url = typeof brand.logo_url === "string" ? brand.logo_url.trim() : "";
  if (/^(https:\/\/|\/)/i.test(url)) { logo.src = url; logo.alt = ""; logo.hidden = false; }
  else { logo.hidden = true; logo.removeAttribute("src"); }

  // Optional canopy strip: the building's photo printed in its own two colours behind the name.
  const header = $("header.top");
  const banner = $("#banner");
  const bannerImg = $("#banner-img");
  const bannerUrl = typeof brand.banner_url === "string" ? brand.banner_url.trim() : "";
  const showBanner = (on) => { banner.hidden = !on; header.classList.toggle("has-banner", on); };
  if (/^(https:\/\/|\/)/i.test(bannerUrl)) {
    bannerImg.onerror = () => showBanner(false);
    if (bannerImg.getAttribute("src") !== bannerUrl) bannerImg.src = bannerUrl;
    showBanner(true);
  } else {
    bannerImg.onerror = null;
    bannerImg.removeAttribute("src");
    showBanner(false);
  }

  const foot = [brand.footer || building.name, building.scheme_no].filter(Boolean).join(" · ");
  $("#foot-line").textContent = foot;
  $("#foot-sep").hidden = !foot;
}

function approvedUnits() {
  return state.me ? state.me.memberships.filter((m) => m.status === "approved") : [];
}

function isStaff() {
  const c = state.me.can;
  return c.handle || c.approve || c.admin;
}

function canHandleCase(c) {
  const roles = state.me.roles;
  return roles.includes("admin") || roles.includes(c.handler);
}

function drawChrome() {
  const me = state.me;
  const nav = $("#nav");
  if (!me) {
    nav.hidden = true; nav.textContent = ""; $("#who").textContent = "";
    return;
  }
  $("#who").textContent = me.user.name || me.user.email || "";
  const c = me.can;
  const items = [];
  if (approvedUnits().length || isStaff()) items.push(["#/home", "Home"]);
  if (c.handle) items.push(["#/board", "Board"]);
  if (c.committee) items.push(["#/votes", "Votes"], ["#/meetings", "Meetings"], ["#/tasks", "Tasks"]);
  if (c.approve) items.push(["#/approvals", "Approvals"], ["#/members", "Members"]);
  if (c.handle) items.push(["#/notices", "Notices"], ["#/docs", "Documents"]);
  if (c.admin) items.push(["#/settings", "Settings"]);
  nav.innerHTML = items.map(([href, text]) => `<a href="${href}" data-nav="${href}">${esc(text)}</a>`).join("")
    + `<button type="button" class="nav-out" id="signout">Sign out</button>`;
  nav.hidden = false;
  $("#signout").addEventListener("click", signOut);
  markNav();
}

function markNav() {
  let h = location.hash;
  if (h.startsWith("#/case/") || h.startsWith("#/inbox") || h === "#/committee") h = "#/board";
  if (h.startsWith("#/vote/")) h = "#/votes";
  if (h.startsWith("#/meeting/") || h.startsWith("#/minutes/")) h = "#/meetings";
  if (h.startsWith("#/new") || h.startsWith("#/request/")) h = "#/home";
  $$("#nav a").forEach((a) => {
    const on = h === a.dataset.nav || h.startsWith(a.dataset.nav + "/");
    a.classList.toggle("on", on);
    if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
}

// One live countdown at a time; drawing a new screen stops the old one.
let ticker = null;

function draw(html) {
  if (ticker) { clearInterval(ticker); ticker = null; }
  const v = $("#view");
  v.innerHTML = html;
  window.scrollTo(0, 0);
  return v;
}

function drawLoading() { draw('<p class="muted loading">Loading…</p>'); }

function drawError(message) {
  draw(`<section class="card narrow">
    <h1>That didn't work</h1>
    <p>${esc(message)}</p>
    <button class="btn" id="retry" type="button">Try again</button>
  </section>`);
  $("#retry").addEventListener("click", route);
}

async function loadMe() {
  const r = await api(withB("/me"));
  const roles = (r.roles || []).map((x) => (typeof x === "string" ? x : x && x.role)).filter(Boolean);
  const can = r.can || {};
  const admin = !!can.admin || roles.includes("admin");
  state.me = {
    user: r.user || {},
    roles,
    memberships: r.memberships || [],
    can: {
      submit: !!can.submit, handle: !!can.handle || admin, approve: !!can.approve || admin,
      admin, owner: !!can.owner, committee: !!(r.committee && r.committee.committee) || admin,
    },
    committee: r.committee || {},
  };
  drawChrome();
}

async function loadTopics() {
  if (!state.topics) {
    const r = await api(withB("/topics"));
    state.topics = (r.topics || []).map((t) => ({ ...t, fields: parseMaybe(t.fields, []) || [] }));
  }
  return state.topics;
}

function signOutHere(note) {
  local.remove(TOKEN_KEY);
  state.me = null;
  state.topics = null;
  state.signinNote = note || "";
  drawChrome();
  go("#/signin");
}

async function signOut() {
  try { await api("/auth/logout", { body: {} }); } catch (e) { /* signed out here either way */ }
  signOutHere("You're signed out.");
}

// ------------------------------------------------------------------ routing

const ROUTES = [
  { re: /^#\/signin$/, view: viewSignin, open: true },
  { re: /^#\/code$/, view: viewCode, open: true },
  { re: /^#\/name$/, view: viewName, setup: true },
  { re: /^#\/claim$/, view: viewClaim, setup: true },
  { re: /^#\/waiting$/, view: viewWaiting, setup: true },
  { re: /^#\/home$/, view: viewHome },
  { re: /^#\/new$/, view: viewTopics, need: "submit" },
  { re: /^#\/new\/(.+)$/, view: viewNewRequest, need: "submit" },
  { re: /^#\/request\/(.+)$/, view: viewRequest },
  { re: /^#\/inbox(?:\/(due|closed))?$/, view: viewInbox, need: "handle", wide: true },
  { re: /^#\/case\/(.+)$/, view: viewCase, need: "handle", wide: true },
  { re: /^#\/board$/, view: viewBoard, need: "handle", wide: true },
  { re: /^#\/votes$/, view: viewVotes, need: "committee" },
  { re: /^#\/vote\/(.+)$/, view: viewVote, need: "committee" },
  { re: /^#\/meetings$/, view: viewMeetings, need: "committee" },
  { re: /^#\/meeting\/(.+)$/, view: viewMeeting, need: "committee", wide: true },
  { re: /^#\/minutes\/(.+)$/, view: viewMinutes, need: "committee" },
  { re: /^#\/tasks(?:\/(all))?$/, view: viewTasks, need: "committee" },
  { re: /^#\/committee$/, view: viewCommittee, need: "committee", wide: true },
  { re: /^#\/approvals$/, view: viewApprovals, need: "approve" },
  { re: /^#\/members$/, view: viewMembers, need: "approve", wide: true },
  { re: /^#\/notices$/, view: viewNotices, need: "handle" },
  { re: /^#\/docs$/, view: viewDocs, need: "handle" },
  { re: /^#\/settings$/, view: viewSettings, need: "admin" },
];

let seq = 0;   // each route() call gets a number; a slower, older one stops drawing

function go(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

function gate(found, hash) {
  const me = state.me;
  if (!me.user.name && hash !== "#/name") return "#/name";
  const resident = approvedUnits().length > 0;
  if (!isStaff() && !resident) {
    if (found.r.setup) return null;
    return me.memberships.some((m) => m.status === "pending") ? "#/waiting" : "#/claim";
  }
  if (found.r.need && !me.can[found.r.need]) return "#/home";
  if (hash === "#/home" && !resident && me.can.handle) return "#/board";
  return null;
}

async function route(retry) {
  if (retry && retry.type) retry = false;   // called as an event handler
  const t = ++seq;
  const hash = location.hash;
  const token = local.get(TOKEN_KEY);
  let found = null;
  for (const r of ROUTES) {
    const m = hash.match(r.re);
    if (m) { found = { r, args: m.slice(1) }; break; }
  }
  if (!found) { go(token ? "#/home" : "#/signin"); return; }

  document.body.classList.toggle("wide", !!found.r.wide);
  if (found.r.open) { markNav(); found.r.view(t); return; }
  if (!token) { go("#/signin"); return; }

  if (!state.me) {
    drawLoading();
    try { await loadMe(); } catch (e) { if (!(e instanceof Quiet) && t === seq) drawError(e.message); return; }
    if (t !== seq) return;
  }
  const redirect = gate(found, hash);
  if (redirect && redirect !== hash) { go(redirect); return; }
  markNav();
  try {
    await found.r.view(t, ...found.args);
  } catch (e) {
    if (e instanceof Quiet || t !== seq) return;
    if (e.status === 403 && !retry) {
      // Access changed (e.g. removed or still waiting): reload who we are and go where they belong.
      state.me = null;
      route(true);
      return;
    }
    drawError(e.message);
  }
}

// ------------------------------------------------------------------ which building

function viewWhichBuilding(message) {
  document.body.classList.remove("wide");
  draw(`<section class="card narrow">
    <h1>Which building?</h1>
    ${message ? `<p class="error" role="alert">${esc(message)}</p>` : ""}
    <form id="f">
      <label for="code">Building code</label>
      <input id="code" autocomplete="off" autocapitalize="none" spellcheck="false" required>
      <button class="btn block" type="submit">Go to my building</button>
    </form>
  </section>`);
  $("#f").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const code = $("#code").value.trim().toLowerCase();
    if (code) location.href = "portal.html?b=" + enc(code);
  });
}

// ------------------------------------------------------------------ sign in

function viewSignin() {
  const note = state.signinNote;
  state.signinNote = "";
  draw(`<section class="card narrow">
    <h1>Sign in</h1>
    ${note ? `<p class="okmsg" role="status">${esc(note)}</p>` : ""}
    <p class="lead">We'll email you a 6-digit code.</p>
    <form id="f" novalidate>
      <label for="email">Your email</label>
      <input id="email" type="email" autocomplete="email" inputmode="email" required value="${esc(state.email)}">
      <p class="error" role="alert"></p>
      <button class="btn block" type="submit">Email me a code</button>
    </form>
  </section>`);
  const f = $("#f");
  f.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const err = $(".error", f);
    const email = $("#email").value.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { err.textContent = "Check your email address."; return; }
    busy($("button", f), err, async () => {
      await api("/auth/start", { body: { email, b: state.b } });
      state.email = email;
      go("#/code");
    });
  });
}

function viewCode() {
  if (!state.email) { go("#/signin"); return; }
  draw(`<section class="card narrow">
    <h1>Check your email</h1>
    <p class="lead">We sent a code to <b>${esc(state.email)}</b>.</p>
    <form id="f" novalidate>
      <label for="code">6-digit code</label>
      <input id="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" class="code-input">
      <p class="error" role="alert"></p>
      <button class="btn block" type="submit">Sign in</button>
    </form>
    <p class="okmsg" id="resent" role="status" hidden>New code sent.</p>
    <div class="link-row">
      <button type="button" class="linkbtn" id="resend">Send a new code</button>
      <a href="#/signin">Use a different email</a>
    </div>
  </section>`);
  const f = $("#f");
  const err = $(".error", f);
  $("#code").focus();
  f.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const code = $("#code").value.replace(/\D/g, "");
    if (code.length !== 6) { err.textContent = "Enter the 6 numbers from the email."; return; }
    busy($("button", f), err, async () => {
      const r = await api("/auth/verify", { body: { email: state.email, code } });
      if (!r.token) throw new Error("Sign-in failed. Please try again.");
      local.set(TOKEN_KEY, r.token);
      state.me = null;
      state.topics = null;
      go("#/home");
    });
  });
  $("#resend").addEventListener("click", (ev) => {
    $("#resent").hidden = true;
    busy(ev.currentTarget, err, async () => {
      await api("/auth/start", { body: { email: state.email, b: state.b } });
      $("#resent").hidden = false;
    });
  });
}

// ------------------------------------------------------------------ joining

function viewName() {
  draw(`<section class="card narrow">
    <h1>What's your name?</h1>
    <form id="f">
      <label for="name">Full name</label>
      <input id="name" autocomplete="name" required maxlength="120" value="${esc(state.me.user.name || "")}">
      <p class="error" role="alert"></p>
      <button class="btn block" type="submit">Save name</button>
    </form>
  </section>`);
  const f = $("#f");
  f.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const name = $("#name").value.trim();
    const err = $(".error", f);
    if (!name) { err.textContent = "Please enter your name."; return; }
    busy($("button", f), err, async () => {
      const r = await api("/me/name", { body: { name } });
      state.me.user = r.user || { ...state.me.user, name };
      drawChrome();
      go("#/home");
    });
  });
}

function viewClaim() {
  const units = state.units || [];
  const taken = new Map(state.me.memberships
    .filter((m) => m.status === "pending" || m.status === "approved")
    .map((m) => [String(m.unit_id), m.status]));
  const rows = units.map((u) => {
    const status = taken.get(String(u.id));
    const label = esc(u.label);
    return `<div class="unit-row${status ? " taken" : ""}" data-find="${esc(String(u.label).toLowerCase())}">
      <label class="check"><input type="checkbox" data-unit="${esc(u.id)}"${status ? " disabled" : ""}><span>${label}</span></label>
      ${status
        ? `<span class="muted small">${status === "approved" ? "Yours" : "Waiting"}</span>`
        : `<select data-rel="${esc(u.id)}" aria-label="Owner or tenant, ${label}"><option value="owner">Owner</option><option value="tenant">Tenant</option></select>`}
    </div>`;
  }).join("");
  const anyMembership = state.me.memberships.length > 0;
  draw(`<section class="card">
    <h1>Which units are yours?</h1>
    <p class="lead">Tick each one. Say if you own or rent it.</p>
    ${units.length > 12 ? `<label for="find" class="sr-only">Find your unit</label><input id="find" type="search" placeholder="Find your unit" autocomplete="off">` : ""}
    <div class="unit-list">${rows || '<p class="muted pad">No units are set up yet.</p>'}</div>
    <p class="error" role="alert"></p>
    <button class="btn block" id="send" type="button">Send for approval</button>
    ${anyMembership ? '<p class="link-row"><a href="#/home">Back</a></p>' : ""}
  </section>`);
  const find = $("#find");
  if (find) {
    find.addEventListener("input", () => {
      const q = find.value.trim().toLowerCase();
      $$(".unit-row").forEach((row) => { row.hidden = q && !row.dataset.find.includes(q); });
    });
  }
  $("#send").addEventListener("click", (ev) => {
    const err = $(".error");
    const claims = $$("input[data-unit]:checked").map((cb) => {
      const unit = units.find((u) => String(u.id) === cb.dataset.unit);
      const rel = $(`select[data-rel="${CSS.escape(cb.dataset.unit)}"]`);
      return { unit_id: unit ? unit.id : cb.dataset.unit, relation: rel ? rel.value : "owner" };
    });
    if (!claims.length) { err.textContent = "Tick at least one unit."; return; }
    busy(ev.currentTarget, err, async () => {
      await api("/claims", { body: { b: state.b, claims } });
      await loadMe();
      state.flash = "Sent for approval.";
      go(approvedUnits().length ? "#/home" : "#/waiting");
    });
  });
}

function viewWaiting() {
  const flash = takeFlash();
  const list = state.me.memberships.map((m) => `<li><b>${esc(m.unit_label)}</b> · ${esc(m.relation === "tenant" ? "Tenant" : "Owner")} · ${esc(CLAIM_STATUS[m.status] || m.status)}</li>`).join("");
  draw(`${flash}<section class="card narrow">
    <h1>Waiting for approval</h1>
    <p class="lead">We're checking your units against the roll.<br>We'll email you when you're in.</p>
    ${list ? `<ul class="plain">${list}</ul>` : ""}
    <p class="error" role="alert"></p>
    <div class="actions">
      <button class="btn" id="again" type="button">Check again</button>
      <a class="btn secondary" href="#/claim">Add another unit</a>
    </div>
  </section>`);
  $("#again").addEventListener("click", (ev) => {
    busy(ev.currentTarget, $(".error"), async () => {
      await loadMe();
      if (approvedUnits().length) { state.flash = "You're in."; go("#/home"); }
      else { state.flash = "Still waiting. We'll email you."; route(); }
    });
  });
}

// ------------------------------------------------------------------ resident home

function noticesHtml(notices) {
  if (!notices.length) return '<p class="muted">No notices right now.</p>';
  return notices.map((n) => `<article class="notice">
    <h3>${esc(n.title)}</h3>
    <p class="muted small">${esc(fmtDate(n.created || n.created_at))}${n.audience === "owners" ? ' · <span class="label">Owners only</span>' : ""}</p>
    <p>${lines(n.body)}</p>
  </article>`).join("");
}

function requestRowsHtml(cases, href) {
  if (!cases.length) return '<p class="muted">No requests yet.</p>';
  return `<div class="rows">${cases.map((c) => {
    const due = isFinished(c) ? "" : daysText(c.days_left);
    return `<a class="row" href="${href}${enc(c.id)}">
      <span class="ref">${esc(c.ref)}</span>
      <span class="due${!isFinished(c) && isUrgent(c.days_left) ? " late" : ""}">${esc(due)}</span>
      <span class="title">${esc(c.title)}</span>
      <span class="status">${esc(STATUS_RESIDENT[c.status] || c.status_label || c.status)}</span>
      <span class="unit">${esc(c.unit_label || "")}</span>
    </a>`;
  }).join("")}</div>`;
}

function docsHtml(docs, manage) {
  if (!docs.length) return '<p class="muted">No documents yet.</p>';
  return `<div class="doc-list">${docs.map((d) => `<div class="doc-row">
    <div class="grow"><b>${esc(d.title)}</b>
      <span class="muted small">${esc(d.category || "")}${d.audience === "owners" ? " · Owners only" : ""}${d.created ? " · " + esc(fmtDate(d.created)) : ""}</span></div>
    <button type="button" class="btn small secondary" data-doc="${esc(d.id)}" data-name="${esc(d.file_name || d.title)}">Download</button>
    ${manage ? `<button type="button" class="btn small danger" data-del-doc="${esc(d.id)}">Delete</button>` : ""}
    <p class="error"></p>
  </div>`).join("")}</div>`;
}

function wireDocDownloads(root) {
  $$("[data-doc]", root).forEach((btn) => {
    btn.addEventListener("click", () => {
      const err = $(".error", btn.closest(".doc-row"));
      busy(btn, err, async () => {
        const blob = await fetchBlob(withB("/docs/file", { id: btn.dataset.doc }));
        saveBlob(blob, btn.dataset.name);
      });
    });
  });
}

async function fill(t, selector, load, render) {
  try {
    const html = render(await load());
    if (t === seq && $(selector)) $(selector).innerHTML = html;
  } catch (e) {
    if (!(e instanceof Quiet) && t === seq && $(selector)) $(selector).innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

async function viewHome(t) {
  const me = state.me;
  const units = approvedUnits();
  const first = (me.user.name || "").split(" ")[0];
  const canRead = units.length > 0 || me.can.handle;
  draw(`${takeFlash()}
    <h1 class="hello">Hi ${esc(first || "there")}</h1>
    ${units.length ? `<p class="muted">${units.map((u) => esc(u.unit_label)).join(" · ")}</p>` : ""}
    ${me.can.submit ? `<div class="actions">
      <a class="btn" href="#/new">New request</a>
      <a class="btn secondary" id="accident" href="#/new" hidden>Report an accident</a>
    </div>` : ""}
    ${canRead ? '<section class="card"><h2>Notices</h2><div id="notices"><p class="muted">Loading…</p></div></section>' : ""}
    ${me.can.submit || units.length ? '<section class="card"><h2>My requests</h2><div id="mine"><p class="muted">Loading…</p></div></section>' : ""}
    ${canRead ? '<section class="card"><h2>Documents</h2><div id="docs"><p class="muted">Loading…</p></div></section>' : ""}
    ${!canRead && me.can.approve ? '<section class="card"><h2>Your jobs</h2><div class="actions"><a class="btn" href="#/approvals">Approvals</a><a class="btn secondary" href="#/members">Members</a></div></section>' : ""}
    <p class="link-row small"><a href="#/claim">Add another unit</a></p>`);

  const jobs = [];
  if (canRead) {
    jobs.push(fill(t, "#notices", async () => (await api(withB("/notices"))).notices || [], noticesHtml));
    jobs.push(fill(t, "#docs", async () => (await api(withB("/docs"))).docs || [], (docs) => docsHtml(docs, false))
      .then(() => { if (t === seq && $("#docs")) wireDocDownloads($("#docs")); }));
  }
  if ($("#mine")) {
    jobs.push(fill(t, "#mine", async () => (await api(withB("/cases", { scope: "mine" }))).cases || [],
      (cases) => requestRowsHtml(cases, "#/request/")));
  }
  if (me.can.submit) {
    jobs.push(loadTopics().then((topics) => {
      const accident = topics.find((tp) => /accident|incident/i.test(tp.key + " " + tp.label));
      const link = $("#accident");
      if (accident && link && t === seq) { link.href = "#/new/" + enc(accident.key); link.hidden = false; }
    }).catch(() => { /* the shortcut just stays hidden */ }));
  }
  await Promise.all(jobs);
}

// ------------------------------------------------------------------ new request

async function viewTopics(t) {
  drawLoading();
  const topics = await loadTopics();
  if (t !== seq) return;
  draw(`<a class="back" href="#/home">← Home</a>
    <h1>New request</h1>
    <p class="lead">What's it about?</p>
    ${topics.length
      ? `<div class="topics">${topics.map((tp) => `<a class="topic" href="#/new/${enc(tp.key)}">${esc(tp.label)}</a>`).join("")}</div>`
      : '<p class="muted">Nothing to request yet.</p>'}`);
}

function fieldHtml(f, i) {
  const id = "f_" + i;
  const req = f.required ? " required" : "";
  const opt = f.required ? "" : ' <span class="opt">(optional)</span>';
  const label = `<label for="${id}">${esc(f.label)}${opt}</label>`;
  switch (f.type) {
    case "textarea":
      return `<div class="field">${label}<textarea id="${id}" rows="4"${req}></textarea></div>`;
    case "date":
      return `<div class="field">${label}<input id="${id}" type="date"${req}></div>`;
    case "select": {
      const options = (f.options || []).map((o) => (typeof o === "object" && o ? o : { value: o, label: o }));
      return `<div class="field">${label}<select id="${id}"${req}><option value="">Choose…</option>${options
        .map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join("")}</select></div>`;
    }
    case "checkbox":
      return `<div class="field"><label class="check"><input id="${id}" type="checkbox"${req}><span>${esc(f.label)}${opt}</span></label></div>`;
    case "file":
      return `<div class="field">${label}<input id="${id}" type="file" accept="image/*,application/pdf"${req}><p class="error" data-file-error="${id}"></p></div>`;
    default:
      return `<div class="field">${label}<input id="${id}" type="text"${req}></div>`;
  }
}

async function viewNewRequest(t, rawKey) {
  const key = decodeURIComponent(rawKey);
  drawLoading();
  const topics = await loadTopics();
  if (t !== seq) return;
  const tp = topics.find((x) => x.key === key);
  if (!tp) {
    draw('<a class="back" href="#/new">← All topics</a><section class="card"><p>That topic isn\'t available.</p></section>');
    return;
  }
  const units = approvedUnits();
  const fields = tp.fields || [];
  const deadline = parseMaybe(tp.deadline, null);
  draw(`<a class="back" href="#/new">← All topics</a>
    <h1>${esc(tp.label)}</h1>
    ${isTrue(tp.draft) ? `<p class="draft">${esc(DRAFT_TEXT)}</p>` : ""}
    ${tp.intro ? `<p class="lead">${lines(tp.intro)}</p>` : ""}
    ${deadline && num(deadline.days) ? `<p class="clock">Reply due within ${esc(num(deadline.days))} days.</p>` : ""}
    <form id="f" class="card" novalidate>
      ${units.length > 1 ? `<div class="field"><label for="unit">Which unit?</label><select id="unit">${units
        .map((u, i) => `<option value="${i}">${esc(u.unit_label)}</option>`).join("")}</select></div>` : ""}
      ${fields.map(fieldHtml).join("")}
      <p class="error" id="form-error" role="alert"></p>
      <button class="btn block" type="submit">Send request</button>
    </form>`);

  // Check files as soon as they're picked.
  fields.forEach((f, i) => {
    if (f.type !== "file") return;
    const input = $("#f_" + i);
    input.addEventListener("change", () => {
      const err = $(`[data-file-error="f_${i}"]`);
      err.textContent = "";
      const file = input.files[0];
      if (!file) return;
      if (!fileOk(file)) { err.textContent = "Photos or PDFs only."; input.value = ""; }
      else if (file.size > MAX_FILE) { err.textContent = "That file is over 5 MB."; input.value = ""; }
    });
  });

  const form = $("#f");
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    busy($('button[type="submit"]', form), $("#form-error"), async () => {
      const answers = {};
      const files = [];
      for (let i = 0; i < fields.length; i++) {
        const f = fields[i];
        const el = $("#f_" + i);
        if (f.type === "checkbox") {
          if (f.required && !el.checked) { el.focus(); throw new Error(`Please tick "${f.label}".`); }
          answers[f.key] = el.checked;
          continue;
        }
        if (f.type === "file") {
          const file = el.files[0];
          if (!file) { if (f.required) { el.focus(); throw new Error(`Please add "${f.label}".`); } continue; }
          if (!fileOk(file)) throw new Error(`"${file.name}": photos or PDFs only.`);
          const data = await readBase64(file);
          files.push({ name: file.name, type: file.type || guessType(file.name), data, field: f.key });
          answers[f.key] = file.name;
          continue;
        }
        const value = el.value.trim();
        if (f.required && !value) { el.focus(); throw new Error(`Please fill in "${f.label}".`); }
        if (value) answers[f.key] = value;
      }
      const unit = units.length > 1 ? units[Number($("#unit").value)] : units[0];
      if (!unit) throw new Error("You need an approved unit first.");
      const r = await api("/cases", { body: { b: state.b, unit_id: unit.unit_id, topic_key: tp.key, answers, files } });
      const c = r.case || {};
      state.flash = (c.ref ? `Sent. Your reference is ${c.ref}.` : "Sent.") + (r.warning ? " " + r.warning : "");
      go(c.id != null ? "#/request/" + enc(c.id) : "#/home");
    });
  });
}

// ------------------------------------------------------------------ one request (shared parts)

function unpackCase(r) {
  const c = { ...(r.case || {}) };
  c.answers = parseMaybe(c.answers, {}) || {};
  c.files = parseMaybe(c.files, []) || [];
  c.decision = parseMaybe(c.decision, null);
  const topic = parseMaybe(r.topic || c.topic, {}) || {};
  topic.fields = parseMaybe(topic.fields, []) || [];
  topic.deadline = parseMaybe(topic.deadline, null);
  const steps = parseMaybe(r.steps || c.steps, []) || [];
  const events = r.events || c.events || [];
  return { c, topic, steps, events };
}

function answersHtml(c, topic) {
  const fields = topic.fields || [];
  const known = new Set(fields.map((f) => f.key));
  const fileFields = new Set(fields.filter((f) => f.type === "file").map((f) => f.key));
  const typeOf = Object.fromEntries(fields.map((f) => [f.key, f.type]));
  const rows = [];
  const show = (key, v) => (typeof v === "boolean" || typeOf[key] === "checkbox" ? (isTrue(v) ? "Yes" : "No")
    : typeOf[key] === "date" ? fmtDate(v) || v : v);
  if (Array.isArray(c.answers_list) && c.answers_list.length) {
    c.answers_list.forEach((a) => {
      if (fileFields.has(a.key) || a.value === undefined || a.value === null || a.value === "") return;
      rows.push(`<dt>${esc(a.label || a.key)}</dt><dd>${lines(show(a.key, a.value))}</dd>`);
    });
    known.clear();
    Object.keys(c.answers).forEach((k) => known.add(k));
  }
  if (!rows.length) fields.forEach((f) => {
    if (fileFields.has(f.key)) return;
    const v = c.answers[f.key];
    if (v === undefined || v === null || v === "") return;
    const shown = f.type === "checkbox" ? (isTrue(v) ? "Yes" : "No") : f.type === "date" ? fmtDate(v) || v : v;
    rows.push(`<dt>${esc(f.label)}</dt><dd>${lines(shown)}</dd>`);
  });
  Object.keys(c.answers).forEach((k) => {
    if (known.has(k)) return;
    const v = c.answers[k];
    if (v === undefined || v === null || v === "" || typeof v === "object") return;
    rows.push(`<dt>${esc(k.replace(/_/g, " "))}</dt><dd>${lines(v)}</dd>`);
  });
  const files = c.files.map((f, i) => `<li>
      <span class="grow">${esc(f.name || "File " + (i + 1))}</span>
      <button type="button" class="btn small secondary" data-file="${i}" data-n="${esc(f.n != null ? f.n : i)}">Open</button>
      <div class="preview" data-preview="${i}"></div>
      <p class="error" data-file-error="${i}"></p>
    </li>`).join("");
  return (rows.length ? `<dl class="answers">${rows.join("")}</dl>` : '<p class="muted">No answers.</p>')
    + (files ? `<h3 class="sub">Attachments</h3><ul class="files">${files}</ul>` : "");
}

function wireCaseFiles(c) {
  $$("[data-file]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const n = btn.dataset.file;
      const file = c.files[Number(n)] || {};
      const box = $(`[data-preview="${n}"]`);
      busy(btn, $(`.files [data-file-error="${n}"]`), async () => {
        const blob = await fetchBlob(withB("/case/file", { id: c.id, n: btn.dataset.n }));
        const type = blob.type || file.type || guessType(file.name || "");
        if (type.startsWith("image/")) {
          box.textContent = "";
          const img = document.createElement("img");
          img.alt = file.name || "Attachment";
          img.src = URL.createObjectURL(blob);
          box.appendChild(img);
        } else {
          saveBlob(blob, file.name || "attachment");
        }
      });
    });
  });
}

function decisionHtml(d) {
  if (!d || !d.outcome) return "";
  return `<div class="decision">
    <p class="outcome">${esc(OUTCOMES[d.outcome] || d.outcome)}</p>
    ${d.at ? `<p class="muted small">${esc(fmtDate(d.at))}</p>` : ""}
    ${d.reasons ? `<h3 class="sub">Reasons</h3><p>${lines(d.reasons)}</p>` : ""}
    ${d.conditions ? `<h3 class="sub">Conditions</h3><p>${lines(d.conditions)}</p>` : ""}
  </div>`;
}

function personName(p) {
  if (!p) return "";
  if (typeof p === "string") return p;
  return [p.name, p.email].filter(Boolean)[0] || "";
}

function eventsHtml(events) {
  if (!events.length) return '<p class="muted">No messages yet.</p>';
  return `<ol class="events">${events.map((e) => {
    const internal = isTrue(e.internal);
    const kind = e.kind || "message";
    const isMessage = kind === "message" || kind === "reply" || kind === "note";
    const who = personName(e.author) || e.user_name || e.user_email || "";
    const when = fmtWhen(e.at || e.created || e.created_at);
    const body = e.body || EVENT_KINDS[kind] || "";
    return `<li class="ev ${isMessage ? "msg" : "sys"}${internal ? " internal" : ""}">
      <div class="ev-head">${internal ? '<span class="label-internal">Internal note</span>' : ""}${who ? `<b>${esc(who)}</b> ` : ""}<span class="muted small">${esc(when)}</span></div>
      <div class="ev-body">${lines(body)}</div>
    </li>`;
  }).join("")}</ol>`;
}

function dueHtml(c) {
  if (!c.due_at) return "";
  const days = isFinished(c) ? "" : daysText(c.days_left);
  return `<div><dt>Reply due</dt><dd>${esc(fmtDate(c.due_at))}${days ? ` · <span class="${isUrgent(c.days_left) ? "late" : ""}">${esc(days)}</span>` : ""}</dd></div>`;
}

// ------------------------------------------------------------------ resident: one request

async function viewRequest(t, rawId) {
  const id = decodeURIComponent(rawId);
  const flash = takeFlash();
  drawLoading();
  const r = await api(withB("/case", { id }));
  if (t !== seq) return;
  const { c, topic, events } = unpackCase(r);
  draw(`${flash}<a class="back" href="#/home">← Home</a>
    <h1>${esc(c.title || topic.label || "Request")}</h1>
    <p class="muted">${esc([c.ref, c.unit_label].filter(Boolean).join(" · "))}</p>
    ${isTrue(topic.draft) ? `<p class="draft">${esc(DRAFT_TEXT)}</p>` : ""}
    <section class="card"><dl class="facts">
      <div><dt>Status</dt><dd>${esc(STATUS_RESIDENT[c.status] || c.status_label || c.status)}</dd></div>
      ${dueHtml(c)}
      ${c.created ? `<div><dt>Sent</dt><dd>${esc(fmtDate(c.created))}</dd></div>` : ""}
    </dl></section>
    ${c.decision && c.decision.outcome ? `<section class="card"><h2>Decision</h2>${decisionHtml(c.decision)}</section>` : ""}
    <section class="card"><h2>Messages</h2>
      ${eventsHtml(events)}
      <form id="msg">
        <label for="body">Add a message</label>
        <textarea id="body" rows="3" maxlength="5000"></textarea>
        <p class="error" role="alert"></p>
        <button class="btn block" type="submit">Send message</button>
      </form>
    </section>
    <section class="card"><h2>What you sent</h2>${answersHtml(c, topic)}</section>`);
  wireCaseFiles(c);
  const form = $("#msg");
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const body = $("#body").value.trim();
    const err = $(".error", form);
    if (!body) { err.textContent = "Write a message first."; return; }
    busy($("button", form), err, async () => {
      await api("/case/message", { body: { b: state.b, id: c.id, body, to_resident: true } });
      state.flash = "Message sent.";
      route();
    });
  });
}

// ------------------------------------------------------------------ handler inbox

async function viewInbox(t, tab) {
  drawLoading();
  const r = await api(withB("/cases", { scope: "inbox" }));
  if (t !== seq) return;
  const all = r.cases || [];
  const byDue = (a, b) => {
    const x = num(a.days_left); const y = num(b.days_left);
    if (x === null && y === null) return 0;
    if (x === null) return 1;
    if (y === null) return -1;
    return x - y;
  };
  const open = all.filter((c) => !isFinished(c)).sort(byDue);
  const due = open.filter((c) => num(c.days_left) !== null && num(c.days_left) <= 7);
  const closed = all.filter(isFinished);
  const list = tab === "due" ? due : tab === "closed" ? closed : open;
  const tabs = [["#/inbox", "Open", open.length, !tab], ["#/inbox/due", "Due soon", due.length, tab === "due"],
    ["#/inbox/closed", "Closed", closed.length, tab === "closed"]];
  const rows = list.map((c) => {
    const days = isFinished(c) ? "" : daysText(c.days_left);
    return `<a class="row case" href="#/case/${enc(c.id)}">
      <span class="ref">${esc(c.ref)}</span>
      <span class="title">${esc(c.title)}</span>
      <span class="unit">${esc(c.unit_label || "")}</span>
      <span class="who">${esc(HANDLERS[c.handler] || c.handler || "")}</span>
      <span class="status">${esc(STATUS_STAFF[c.status] || c.status_label || c.status)}</span>
      <span class="due${!isFinished(c) && isUrgent(c.days_left) ? " late" : ""}">${esc(days)}</span>
    </a>`;
  }).join("");
  draw(`${takeFlash()}<h1>Inbox</h1>
    <nav class="tabs" aria-label="Inbox">${tabs.map(([href, text, n, on]) =>
      `<a href="${href}"${on ? ' class="on" aria-current="page"' : ""}>${esc(text)} (${n})</a>`).join("")}</nav>
    <section class="card flush">
      ${list.length ? `<div class="rows inbox">
        <div class="row case head" aria-hidden="true"><span class="ref">Ref</span><span class="title">Request</span><span class="unit">Unit</span><span class="who">Handled by</span><span class="status">Status</span><span class="due">Due</span></div>
        ${rows}</div>` : `<p class="muted pad">${tab === "closed" ? "Nothing closed yet." : tab === "due" ? "Nothing due soon." : "Nothing open. All clear."}</p>`}
    </section>`);
}

// ------------------------------------------------------------------ handler: one case

async function viewCase(t, rawId) {
  const id = decodeURIComponent(rawId);
  const flash = takeFlash();
  drawLoading();
  const r = await api(withB("/case", { id }));
  if (t !== seq) return;
  const { c, topic, steps, events } = unpackCase(r);
  const mine = c.can_handle === undefined ? canHandleCase(c) : isTrue(c.can_handle);
  const lodged = c.lodged_by && typeof c.lodged_by === "object"
    ? [c.lodged_by.name, c.lodged_by.email].filter(Boolean).join(" · ") : c.lodged_by;
  const resident = lodged || [c.user_name, c.user_email].filter(Boolean).join(" · ");
  const ifMissed = c.if_missed || (topic.deadline && topic.deadline.if_missed);
  const missed = c.missed;
  const banner = missed && missed.banner
    ? missedHtml(missed.banner, missed.due_at, missed.citation, missed.urgent, num(missed.days_left) < 0)
    : "";

  draw(`${flash}${banner}<a class="back" href="#/board">← Board</a>
    <h1>${esc(c.title || topic.label || "Request")}</h1>
    <p class="muted">${esc([c.ref, c.unit_label, HANDLERS[c.handler] || c.handler].filter(Boolean).join(" · "))}</p>
    ${resident ? `<p class="small">From ${esc(resident)}</p>` : ""}
    ${isTrue(topic.draft) ? `<p class="draft">${esc(DRAFT_TEXT)}</p>` : ""}
    <div class="case-grid">
      <div class="col-main">
        ${mine ? nextStepHtml(c.stage) : ""}
        <section class="card"><h2>Request</h2>${answersHtml(c, topic)}</section>
        <section class="card"><h2>Messages</h2>
          ${eventsHtml(events)}
          ${mine ? `<form id="msg">
            <label class="switch"><input type="checkbox" id="to-res" role="switch"><span class="switch-ui" aria-hidden="true"></span><span>Send to resident</span></label>
            <label for="body" id="body-label" class="mode-label internal">Internal note</label>
            <textarea id="body" rows="3" maxlength="5000" class="internal-box"></textarea>
            <p class="error" role="alert"></p>
            <button class="btn block" type="submit" id="msg-btn">Save internal note</button>
          </form>` : ""}
        </section>
      </div>
      <div class="col-side">
        <section class="card"><h2>Status</h2>
          <dl class="facts">
            <div><dt>Now</dt><dd>${esc(STATUS_STAFF[c.status] || c.status_label || c.status)}</dd></div>
            ${dueHtml(c)}
          </dl>
          ${ifMissed && !banner && !isFinished(c) ? `<p class="small">If missed: ${esc(ifMissed)}</p>` : ""}
          ${mine ? `<form id="status-form" class="inline-form">
            <label for="status" class="sr-only">New status</label>
            <select id="status">${STATUSES.map((s) => `<option value="${s}"${s === c.status ? " selected" : ""}>${esc(STATUS_STAFF[s])}</option>`).join("")}</select>
            <button class="btn secondary" type="submit">Change status</button>
          </form>
          <p class="error" id="status-error" role="alert"></p>` : ""}
        </section>
        ${r.votes ? caseVotesHtml(r.votes, c, r.can_open_vote && !(c.stage && (c.stage.buttons || []).some((b) => b.opens_vote))) : ""}
        ${r.tasks ? `<section class="card" id="case-tasks"><h2>Tasks</h2>${taskRowsHtml(r.tasks, false)}${taskFormHtml("case-task", [])}</section>` : ""}
        <section class="card"><h2>Checklist</h2>
          ${steps.length ? `<ol class="steps">${steps.map((s, i) => `<li>
            <label class="check"><input type="checkbox" data-step="${i}"${isTrue(s.done) ? " checked" : ""}${mine ? "" : " disabled"}>
              <span><span class="step-title">${esc(s.title)}</span>${s.rule ? `<span class="rule">${esc(s.rule)}</span>` : ""}</span></label>
          </li>`).join("")}</ol>
          <p class="small muted">${esc(GUIDANCE_TEXT)}</p>` : '<p class="muted">No steps for this topic.</p>'}
          <p class="error" id="step-error" role="alert"></p>
        </section>
        <section class="card" id="decide-card"><h2>Decision</h2>
          ${c.decision && c.decision.outcome ? decisionHtml(c.decision) : '<p class="muted">Not decided yet.</p>'}
          ${mine ? `${c.decision && c.decision.outcome ? '<button type="button" class="linkbtn" id="redecide">Change decision</button>' : ""}
          <form id="decide"${c.decision && c.decision.outcome ? " hidden" : ""} novalidate>
            <fieldset><legend>Outcome</legend>
              <label class="check"><input type="radio" name="outcome" value="approved"><span>Approve</span></label>
              <label class="check"><input type="radio" name="outcome" value="approved_with_conditions"><span>Approve with conditions</span></label>
              <label class="check"><input type="radio" name="outcome" value="refused"><span>Refuse</span></label>
            </fieldset>
            <div id="cond-wrap" hidden><label for="conditions">Conditions</label><textarea id="conditions" rows="3"></textarea></div>
            <label for="reasons" id="reasons-label">Reasons <span class="opt">(optional)</span></label>
            <textarea id="reasons" rows="3"></textarea>
            <p class="error" role="alert"></p>
            <button class="btn block" type="submit">Record decision</button>
          </form>` : ""}
        </section>
      </div>
    </div>`);

  wireCaseFiles(c);
  startCountdowns();
  if (!mine) return;
  wireNextStep(c, c.stage || {});
  if (r.tasks) {
    wireTaskBoxes($("#case-tasks"));
    wireTaskForm("case-task", { case_id: c.id }, () => { state.flash = "Task added."; route(); });
  }
  const caseVote = $("#case-vote");
  if (caseVote) {
    caseVote.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const words = $("#cv-words").value.trim();
      const err = $(".error", caseVote);
      if (!words) { err.textContent = "Write the motion first."; return; }
      busy($('button[type="submit"]', caseVote), err, async () => {
        await api("/votes", { body: { b: state.b, words, case_id: c.id } });
        state.flash = "Vote sent to the committee. Owners have been told.";
        route();
      });
    });
  }

  // Messages: off = internal note, on = goes to the resident.
  const toRes = $("#to-res");
  toRes.addEventListener("change", () => {
    const on = toRes.checked;
    const label = $("#body-label");
    label.textContent = on ? "Message to resident" : "Internal note";
    label.classList.toggle("internal", !on);
    $("#body").classList.toggle("internal-box", !on);
    $("#msg-btn").textContent = on ? "Send to resident" : "Save internal note";
  });
  const msg = $("#msg");
  msg.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const body = $("#body").value.trim();
    const err = $(".error", msg);
    if (!body) { err.textContent = "Write something first."; return; }
    const on = toRes.checked;
    busy($("#msg-btn"), err, async () => {
      await api("/case/message", { body: { b: state.b, id: c.id, body, to_resident: on } });
      state.flash = on ? "Sent to resident." : "Note saved.";
      route();
    });
  });

  $("#status-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const status = $("#status").value;
    if (status === c.status) { $("#status-error").textContent = "Pick a different status."; return; }
    busy($("#status-form button"), $("#status-error"), async () => {
      await api("/case/status", { body: { b: state.b, id: c.id, status, note: "" } });
      state.flash = "Status changed.";
      route();
    });
  });

  $$("[data-step]").forEach((cb) => {
    cb.addEventListener("change", async () => {
      const err = $("#step-error");
      err.textContent = "";
      cb.disabled = true;
      try {
        await api("/case/step", { body: { b: state.b, id: c.id, index: Number(cb.dataset.step), done: cb.checked } });
      } catch (e) {
        cb.checked = !cb.checked;
        if (!(e instanceof Quiet)) err.textContent = e.message;
      } finally {
        cb.disabled = false;
      }
    });
  });

  const decide = $("#decide");
  const redecide = $("#redecide");
  if (redecide) redecide.addEventListener("click", () => { decide.hidden = false; redecide.hidden = true; });
  $$('input[name="outcome"]', decide).forEach((radio) => {
    radio.addEventListener("change", () => {
      const outcome = radio.value;
      $("#cond-wrap").hidden = outcome !== "approved_with_conditions";
      $("#reasons-label").innerHTML = outcome === "refused" ? "Reasons" : 'Reasons <span class="opt">(optional)</span>';
    });
  });
  decide.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const err = $(".error", decide);
    const picked = $('input[name="outcome"]:checked', decide);
    const reasons = $("#reasons").value.trim();
    const conditions = $("#conditions").value.trim();
    if (!picked) { err.textContent = "Pick an outcome."; return; }
    const outcome = picked.value;
    if (outcome === "refused" && !reasons) { err.textContent = "Add reasons to refuse."; $("#reasons").focus(); return; }
    if (outcome === "approved_with_conditions" && !conditions) { err.textContent = "Add the conditions."; $("#conditions").focus(); return; }
    busy($('button[type="submit"]', decide), err, async () => {
      await api("/case/decide", {
        body: { b: state.b, id: c.id, outcome, reasons, conditions: outcome === "approved_with_conditions" ? conditions : "" },
      });
      state.flash = "Decision recorded. The resident has been told.";
      route();
    });
  });
}

// ------------------------------------------------------------------ what happens if nobody decides

// "20 days 11 h 4 min 9 s left": the time to the end of the last day, ticking.
function countdownText(dueIso) {
  const due = parseUtc(dueIso);
  if (!due) return "";
  let s = Math.floor((due.getTime() - Date.now()) / 1000);
  if (s < 0) return "The deadline has passed";
  const d = Math.floor(s / 86400); s -= d * 86400;
  const h = Math.floor(s / 3600); s -= h * 3600;
  const m = Math.floor(s / 60); s -= m * 60;
  return `${d} ${d === 1 ? "day" : "days"} ${h} h ${String(m).padStart(2, "0")} min ${String(s).padStart(2, "0")} s left`;
}

function startCountdowns() {
  const tick = () => $$("[data-countdown]").forEach((el) => { el.textContent = countdownText(el.dataset.countdown); });
  tick();
  if (ticker) clearInterval(ticker);
  if ($$("[data-countdown]").length) ticker = setInterval(tick, 1000);
}

// The first thing an approver sees: big, plain words, the date, the source, a live countdown. Red in the last 3 days.
function missedHtml(text, dueIso, citation, urgent, past) {
  if (!text) return "";
  return `<section class="missed${urgent ? " urgent" : ""}" aria-label="If nobody decides in time">
    <p class="missed-label">If nobody decides in time</p>
    <p class="missed-text">${esc(text)}</p>
    <p class="missed-meta">${past ? "" : `<span class="countdown" data-countdown="${esc(dueIso)}">${esc(countdownText(dueIso))}</span>`}${citation ? `<span class="cite">${esc(citation)}</span>` : ""}</p>
  </section>`;
}

function moduleNoteHtml(note) {
  return note ? `<p class="draft module-note">${esc(note)}</p>` : "";
}

// ------------------------------------------------------------------ the board

function boardCardHtml(c) {
  const days = num(c.days_left);
  const left = days === null ? "" : daysText(days);
  const vote = c.vote ? `<span class="b-vote">Voting: ${esc(c.vote.yes)} yes of ${esc(c.vote.needed)} needed${c.vote.no ? ` · ${esc(c.vote.no)} no` : ""}</span>` : "";
  return `<a class="bcard${c.urgent ? " urgent" : ""}" href="#/case/${enc(c.id)}">
    <span class="b-ref">${esc(c.ref)}${c.unit_label ? " · " + esc(c.unit_label) : ""}</span>
    <span class="b-title">${esc(c.title)}</span>
    ${c.missed_label ? `<span class="b-miss">${esc(c.missed_label)}${left ? ` · <span class="nowrap">${esc(left)}</span>` : ""}</span>` : left ? `<span class="b-miss quiet">${esc(left)}</span>` : ""}
    ${vote}
    <span class="b-who">${esc(c.owner_label)}'s step${c.status === "waiting_on_resident" ? " · waiting on resident" : ""}</span>
  </a>`;
}

async function viewBoard(t) {
  drawLoading();
  const r = await api(withB("/board"));
  if (t !== seq) return;
  const columns = r.columns || [];
  const total = columns.reduce((n, col) => n + col.cards.length, 0);
  draw(`${takeFlash()}<div class="page-head">
      <h1>Board</h1>
      <p class="link-row small"><a href="#/inbox">List view</a>${state.me.can.committee ? '<a href="#/committee">Who does what</a>' : ""}${r.closed ? `<a href="#/inbox/closed">Closed (${esc(r.closed)})</a>` : ""}</p>
    </div>
    ${moduleNoteHtml(r.module_note)}
    <p class="lead board-lead">${total ? `${total} open ${total === 1 ? "request" : "requests"}, by step. Red: 3 days or less before the deadline.` : "Nothing open. All clear."}</p>
    <div class="board" style="--cols:${columns.length || 1}">
      ${columns.map((col) => `<section class="bcol${col.cards.length ? "" : " empty"}" aria-label="${esc(col.label)}">
        <h2 class="bcol-head"><span>${esc(col.label)}</span><span class="count">${esc(col.cards.length)}</span></h2>
        ${col.cards.length ? `<div class="bcards">${col.cards.map(boardCardHtml).join("")}</div>` : '<p class="muted small pad">Nothing here.</p>'}
      </section>`).join("")}
    </div>`);
}

// ------------------------------------------------------------------ one case: the next step

function stepWhat(b, stage) {
  const parts = [];
  if (b.opens_vote) parts.push("opens a committee vote outside a meeting (21 days) and emails every committee member");
  if (b.extends) parts.push("extends the deadline once, by written notice");
  if (b.to) parts.push(`emails ${TO_WHO[b.to] || b.to} with a link back to this request`);
  const next = (stage.path || []).find((s) => s.key === b.next);
  parts.push(next && next.key !== stage.key ? `then moves it to ${next.label}` : "it stays at this step");
  const text = parts.join(", ");
  return text.charAt(0).toUpperCase() + text.slice(1) + ".";
}

function nextStepHtml(stage) {
  if (!stage) return "";
  const path = stage.path || [];
  const buttons = stage.buttons || [];
  return `<section class="card next-step" id="next">
    <h2>Next step</h2>
    <ol class="path" aria-label="Steps">${path.map((s, i) => `<li class="${i < stage.index ? "done" : i === stage.index ? "on" : ""}"${i === stage.index ? ' aria-current="step"' : ""}>${esc(s.label)}</li>`).join("")}</ol>
    <p class="whose label">${esc(stage.owner_label)}'s step</p>
    ${stage.instructions ? `<p class="instructions">${esc(stage.instructions)}</p>` : ""}
    ${stage.rule ? `<p class="rule">${esc(stage.rule)}</p>` : ""}
    ${!buttons.length ? '<p class="muted">Nothing more to do here.</p>' : stage.allowed ? `<div class="actions stage-buttons">${buttons.map((b, i) => `<button type="button" class="btn${i ? " secondary plain" : ""}" data-act="${esc(b.key)}">${esc(b.label)}</button>`).join("")}</div>
    <form id="act-form" class="act-form" hidden novalidate>
      <p class="act-what"></p>
      <div id="act-note-wrap"><label for="act-note" id="act-note-label">Note</label><textarea id="act-note" rows="3" maxlength="5000"></textarea></div>
      <p class="error" role="alert"></p>
      <div class="actions"><button class="btn" type="submit" id="act-go">Send</button><button type="button" class="linkbtn" id="act-cancel">Cancel</button></div>
    </form>` : `<p class="muted small">This step is for the ${esc(stage.owner_label.toLowerCase())}.</p>`}
  </section>`;
}

function wireNextStep(c, stage) {
  const form = $("#act-form");
  if (!form) return;
  let chosen = null;
  $$("[data-act]").forEach((btn) => {
    btn.addEventListener("click", () => {
      chosen = (stage.buttons || []).find((b) => b.key === btn.dataset.act);
      if (!chosen) return;
      $(".act-what", form).textContent = stepWhat(chosen, stage);
      $("#act-note-wrap").hidden = !chosen.note;
      $("#act-note-label").innerHTML = esc(chosen.note_label || "Note") + (chosen.note === "optional" ? ' <span class="opt">(optional)</span>' : "");
      $("#act-note").value = "";
      $("#act-go").textContent = chosen.label;
      $(".error", form).textContent = "";
      $(".stage-buttons").hidden = true;
      form.hidden = false;
      (chosen.note ? $("#act-note") : $("#act-go")).focus();
    });
  });
  $("#act-cancel").addEventListener("click", () => { form.hidden = true; $(".stage-buttons").hidden = false; });
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const note = $("#act-note").value.trim();
    if (chosen.note === "required" && !note) { $(".error", form).textContent = `Please fill in: ${chosen.note_label || "the note"}`; return; }
    busy($("#act-go"), $(".error", form), async () => {
      await api("/case/action", { body: { b: state.b, id: c.id, action: chosen.key, note } });
      state.flash = `Done: ${chosen.label}.`;
      route();
    });
  });
}

function caseVotesHtml(votes, c, canOpen) {
  const open = votes.some((v) => v.status === "open");
  const rows = votes.map((v) => (v.kind === "meeting"
    ? `<a class="mini-row" href="#/meeting/${enc(v.meeting_id)}">
      <span class="grow">${v.status === "pending" ? "On a meeting agenda · not voted yet" : esc(motionResultText(v))}</span>
      <span class="muted small">at a meeting</span>
    </a>`
    : `<a class="mini-row" href="#/vote/${enc(v.id)}">
      <span class="grow">${esc(v.status_label)}${v.status === "open" ? ` · ${esc(v.tally.yes)} yes of ${esc(v.tally.needed_yes)} needed` : ` · ${esc(v.tally.yes)} for, ${esc(v.tally.no)} against`}</span>
      <span class="muted small">${v.status === "open" ? "closes " + esc(v.closes_text) : esc(fmtDate(v.decided_at))}</span>
    </a>`)).join("");
  return `<section class="card"><h2>Votes</h2>
    ${rows ? `<div class="mini-rows">${rows}</div>` : '<p class="muted">No votes on this request.</p>'}
    ${canOpen && !open && !isFinished(c) ? `<form id="case-vote" class="sub-form">
      <h3 class="sub">Open a vote outside a meeting</h3>
      <label for="cv-words">The motion (exact words)</label>
      <textarea id="cv-words" rows="3">${esc(`That the committee approve request ${c.ref} (${c.title}, ${c.unit_label}).`)}</textarea>
      <p class="error" role="alert"></p>
      <button class="btn secondary plain" type="submit">Send to the committee</button>
    </form>` : ""}
  </section>`;
}

function taskRowsHtml(tasks, showLinks) {
  if (!tasks.length) return '<p class="muted">No tasks.</p>';
  return `<ul class="task-list">${tasks.map((k) => `<li class="task${k.done ? " is-done" : ""}">
    <label class="check"><input type="checkbox" data-task="${esc(k.id)}"${k.done ? " checked" : ""}>
      <span><span class="task-title">${esc(k.title)}</span>
      <span class="task-meta">${esc(k.assignee)}${k.due_date ? ` · <span class="${!k.done && k.urgent ? "late" : ""}">due ${esc(fmtDate(k.due_at))}${!k.done && num(k.days_left) !== null && num(k.days_left) < 0 ? ` (${esc(daysText(k.days_left))})` : ""}</span>` : ""}${showLinks && k.case_id ? ` · <a href="#/case/${enc(k.case_id)}">request</a>` : ""}${showLinks && k.meeting_id ? ` · <a href="#/meeting/${enc(k.meeting_id)}">meeting</a>` : ""}</span></span></label>
    <p class="error"></p>
  </li>`).join("")}</ul>`;
}

function wireTaskBoxes(root, after) {
  $$("[data-task]", root).forEach((cb) => {
    cb.addEventListener("change", async () => {
      const err = $(".error", cb.closest("li"));
      err.textContent = "";
      cb.disabled = true;
      try {
        await api("/task/done", { body: { b: state.b, id: cb.dataset.task, done: cb.checked } });
        cb.closest("li").classList.toggle("is-done", cb.checked);
        if (after) after();
      } catch (e) {
        cb.checked = !cb.checked;
        if (!(e instanceof Quiet)) err.textContent = e.message;
      } finally { cb.disabled = false; }
    });
  });
}

function assigneeOptions(people) {
  return `<optgroup label="A position">${Object.entries(POSITIONS).map(([k, v]) => `<option value="pos:${k}"${k === "secretary" ? " selected" : ""}>${esc(v)}</option>`).join("")}</optgroup>
    ${people && people.length ? `<optgroup label="A person">${people.map((p) => `<option value="user:${esc(p.user_id)}">${esc(p.name)}</option>`).join("")}</optgroup>` : ""}`;
}

function taskFormHtml(id, people) {
  return `<form id="${id}" class="sub-form" novalidate>
    <h3 class="sub">Add a task</h3>
    <label for="${id}-title">What needs doing?</label>
    <input id="${id}-title" maxlength="255">
    <div class="two-fields">
      <div><label for="${id}-who">Who</label><select id="${id}-who">${assigneeOptions(people)}</select></div>
      <div><label for="${id}-due">Due <span class="opt">(optional)</span></label><input id="${id}-due" type="date"></div>
    </div>
    <p class="error" role="alert"></p>
    <button class="btn secondary plain" type="submit">Add task</button>
  </form>`;
}

function wireTaskForm(id, extra, done) {
  const form = $("#" + id);
  if (!form) return;
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const err = $(".error", form);
    const title = $(`#${id}-title`).value.trim();
    if (!title) { err.textContent = "Say what needs doing."; return; }
    const who = $(`#${id}-who`).value.split(":");
    busy($('button[type="submit"]', form), err, async () => {
      await api("/tasks", {
        body: {
          b: state.b, title, due_date: $(`#${id}-due`).value || "",
          assignee_position: who[0] === "pos" ? who[1] : "", assignee_user_id: who[0] === "user" ? who[1] : "", ...extra,
        },
      });
      done();
    });
  });
}

// ------------------------------------------------------------------ votes outside a meeting

function tallyHtml(v) {
  const t = v.tally || {};
  const entitled = num(t.entitled) || 0;
  const pct = (n) => (entitled ? Math.min(100, (100 * n) / entitled) : 0);
  const line = entitled ? (100 * (Math.floor(entitled / 2) + 1)) / entitled : 0;
  return `<div class="tally">
    ${v.kind === "vocm" ? `<div class="meter" role="img" aria-label="${esc(t.yes)} yes and ${esc(t.no)} no of ${esc(entitled)} entitled; ${esc(t.needed_yes)} yes needed">
      <span class="m-yes" style="width:${pct(t.yes)}%"></span><span class="m-no" style="width:${pct(t.no)}%"></span>
      <span class="m-line" style="left:${line}%"></span>
    </div>` : ""}
    <p class="tally-words"><b>${esc(t.yes || 0)}</b> yes · <b>${esc(t.no || 0)}</b> no · <b>${esc(t.abstain || 0)}</b> abstain${t.conflicts ? ` · ${esc(t.conflicts)} conflict${t.conflicts === 1 ? "" : "s"} declared` : ""}</p>
    ${v.kind === "vocm" ? `<p class="small muted">${esc(entitled)} ${entitled === 1 ? "member is" : "members are"} entitled to vote. It passes at ${esc(t.needed_yes)} yes; it fails at ${esc(Math.ceil(entitled / 2))} no.</p>` : ""}
  </div>`;
}

async function viewVotes(t) {
  drawLoading();
  const r = await api(withB("/votes"));
  if (t !== seq) return;
  const all = r.votes || [];
  const open = all.filter((v) => v.status === "open");
  const done = all.filter((v) => v.status !== "open");
  const row = (v) => `<a class="row vrow" href="#/vote/${enc(v.id)}">
      <span class="ref">${esc(v.case_ref || "Motion")}</span>
      <span class="due${v.urgent ? " late" : ""}">${v.status === "open" ? "closes " + esc(v.closes_text) : esc(v.status_label)}</span>
      <span class="title">${esc(v.words.length > 140 ? v.words.slice(0, 137) + "…" : v.words)}</span>
      <span class="status">${v.status === "open" ? `${esc(v.tally.yes)} yes of ${esc(v.tally.needed_yes)} needed${v.my_vote ? " · you voted" : v.can_vote ? " · your vote is needed" : ""}` : `${esc(v.tally.yes)} for, ${esc(v.tally.no)} against`}</span>
    </a>`;
  draw(`${takeFlash()}<h1>Votes</h1>
    <p class="lead">Committee votes outside a meeting. A motion passes when more than half of all the members entitled to vote say yes.</p>
    ${moduleNoteHtml(r.module_note)}
    <section class="card"><h2>Open</h2>${open.length ? `<div class="rows">${open.map(row).join("")}</div>` : '<p class="muted">No votes open.</p>'}</section>
    ${r.can_open ? `<form id="new-vote" class="card" novalidate>
      <h2>Put a motion to the committee</h2>
      <label for="nv-words">The motion: the exact words voted on</label>
      <textarea id="nv-words" rows="4" placeholder="That the committee …"></textarea>
      <label for="nv-exempt">Can it be acted on straight away? <span class="opt">(optional)</span></label>
      <select id="nv-exempt"><option value="">No: owners get 7 days to oppose it</option><option value="routine">Routine admin, $240 or less</option><option value="emergency">Emergency, within the spending limit</option></select>
      <p class="small muted">It goes to every committee member, with advice to owners at the same time, and closes in 21 days (SM s 68–69).</p>
      <p class="error" role="alert"></p>
      <button class="btn block" type="submit">Send to the committee</button>
    </form>` : ""}
    <section class="card"><h2>Decided</h2>${done.length ? `<div class="rows">${done.map(row).join("")}</div>` : '<p class="muted">Nothing decided yet.</p>'}</section>`);
  const form = $("#new-vote");
  if (form) {
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const words = $("#nv-words").value.trim();
      const err = $(".error", form);
      if (!words) { err.textContent = "Write the motion first."; return; }
      busy($('button[type="submit"]', form), err, async () => {
        const res = await api("/votes", { body: { b: state.b, words, exempt: $("#nv-exempt").value } });
        state.flash = "Sent to the committee. Owners have been told.";
        go("#/vote/" + enc(res.vote.id));
      });
    });
  }
}

async function viewVote(t, rawId) {
  const id = decodeURIComponent(rawId);
  const flash = takeFlash();
  drawLoading();
  const r = await api(withB("/vote", { id }));
  if (t !== seq) return;
  const v = r.vote;
  const isOpen = v.status === "open";
  draw(`${flash}${isOpen ? missedHtml(v.missed, v.closes_at, v.missed_citation, v.urgent, false) : ""}
    <a class="back" href="#/votes">← Votes</a>
    <p class="label">${v.kind === "vocm" ? "Vote outside a meeting" : "Meeting motion"}${v.case_ref ? ` · <a href="#/case/${enc(v.case_id)}">${esc(v.case_ref)}</a>` : ""}</p>
    <blockquote class="motion">${lines(v.words)}</blockquote>
    <section class="card"><dl class="facts">
      <div><dt>Result</dt><dd>${esc(v.status_label)}</dd></div>
      ${isOpen ? `<div><dt>Closes</dt><dd>End of ${esc(v.closes_text)} · <span class="${v.urgent ? "late" : ""}">${esc(daysText(v.days_left))}</span></dd></div>` : `<div><dt>Decided</dt><dd>${esc(fmtDate(v.decided_at))}</dd></div>`}
      ${v.act_note ? `<div><dt>Acting on it</dt><dd>${esc(v.act_note)}</dd></div>` : ""}
    </dl>${tallyHtml(v)}</section>
    ${v.can_vote ? `<form id="ballot" class="card" novalidate>
      <h2>${v.my_vote ? "Change your vote" : "Your vote"}</h2>
      ${v.my_vote ? `<p class="small">You voted: <b>${esc(VOTE_WORDS[v.my_vote] || v.my_vote)}</b>. You can change it until it closes.</p>` : ""}
      <fieldset class="choices"><legend class="sr-only">Your vote</legend>
        ${["yes", "no", "abstain"].map((k) => `<label class="check"><input type="radio" name="vote" value="${k}"${v.my_vote === k ? " checked" : ""}><span>${VOTE_WORDS[k]}</span></label>`).join("")}
      </fieldset>
      <label class="check conflict"><input type="checkbox" id="conflict"${v.my_vote === "conflict" ? " checked" : ""}><span>I have a conflict of interest, so I won't vote</span></label>
      <div id="conflict-wrap" hidden><label for="conflict-note">What is the conflict?</label><input id="conflict-note" maxlength="255"></div>
      <p class="error" role="alert"></p>
      <button class="btn block" type="submit">${v.my_vote ? "Change my vote" : "Cast my vote"}</button>
    </form>` : ""}
    <section class="card"><h2>Who has voted</h2>
      ${(v.ballots || []).length ? `<div class="mini-rows">${v.ballots.map((b) => `<div class="mini-row"><span class="grow">${esc(b.name)}</span><span>${esc(VOTE_WORDS[b.vote] || b.vote)}${b.note ? ` <span class="muted small">(${esc(b.note)})</span>` : ""}</span></div>`).join("")}</div>` : '<p class="muted">Nobody yet.</p>'}
      <p class="small muted">Votes are kept on the record of motions, which goes to every committee member and owner (SM s 71).</p>
    </section>`);
  startCountdowns();
  const form = $("#ballot");
  if (!form) return;
  const conflict = $("#conflict");
  const sync = () => {
    $("#conflict-wrap").hidden = !conflict.checked;
    $$('input[name="vote"]', form).forEach((x) => { x.disabled = conflict.checked; });
  };
  conflict.addEventListener("change", sync);
  sync();
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const err = $(".error", form);
    const picked = $('input[name="vote"]:checked', form);
    const isConflict = conflict.checked;
    const note = $("#conflict-note").value.trim();
    if (!isConflict && !picked) { err.textContent = "Choose yes, no or abstain."; return; }
    if (isConflict && !note) { err.textContent = "Say briefly what the conflict is."; return; }
    busy($('button[type="submit"]', form), err, async () => {
      const res = await api("/vote/ballot", { body: { b: state.b, id: v.id, vote: picked ? picked.value : "", conflict: isConflict, note } });
      state.flash = res.vote.status === "open" ? "Vote recorded." : `Vote recorded. The motion is now: ${res.vote.status_label}.`;
      route();
    });
  });
}

// ------------------------------------------------------------------ meetings

function localInputValue(daysAhead) {
  const d = new Date(Date.now() + daysAhead * 86400000);
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: timeZone(), year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
  return parts + "T18:00";
}

async function viewMeetings(t) {
  drawLoading();
  const r = await api(withB("/meetings"));
  if (t !== seq) return;
  const list = r.meetings || [];
  const minutesText = (m) => {
    if (m.minutes_status === "draft") return `Minutes due ${m.minutes_due}`;
    if (m.minutes_status === "issued") return "Minutes issued";
    if (m.minutes_status === "confirmed") return "Minutes confirmed";
    return m.status === "closed" ? "" : m.status === "open" ? "Under way" : "Notice sent";
  };
  draw(`${takeFlash()}<h1>Meetings</h1>
    ${moduleNoteHtml(r.module_note)}
    <section class="card">${list.length ? `<div class="rows">${list.map((m) => `<a class="row mrow-link" href="#/meeting/${enc(m.id)}">
        <span class="ref">${esc(m.when)}</span>
        <span class="due${num(m.minutes_days_left) !== null && num(m.minutes_days_left) <= 3 ? " late" : ""}">${esc(minutesText(m))}</span>
        <span class="title">${esc(m.title)}</span>
        <span class="status">${esc(m.place || "")}</span>
      </a>`).join("")}</div>` : '<p class="muted">No meetings yet.</p>'}</section>
    ${r.can_call ? `<form id="new-meeting" class="card" novalidate>
      <h2>Call a committee meeting</h2>
      <p class="small muted">At least 7 clear days' notice. The notice and agenda go to every committee member, with advice to owners at the same time. Confirming the last minutes and any votes outside a meeting go on the agenda for you.</p>
      <label for="nm-title">Title</label><input id="nm-title" value="Committee meeting" maxlength="255">
      <div class="two-fields">
        <div><label for="nm-when">Date and time</label><input id="nm-when" type="datetime-local" value="${esc(localInputValue(8))}"></div>
        <div><label for="nm-place">Where</label><input id="nm-place" maxlength="255" placeholder="Level 1 meeting room"></div>
      </div>
      <label for="nm-items">Agenda: one item per line</label>
      <textarea id="nm-items" rows="4" placeholder="Pool fence quotes&#10;Lift contract renewal"></textarea>
      <label class="check"><input type="checkbox" id="nm-short"><span>Short notice (2 days): every voting member agreed</span></label>
      <div id="nm-short-wrap" hidden><label for="nm-short-why">How and when they agreed</label><input id="nm-short-why" maxlength="255" placeholder="All 5 agreed by email on 9 Nov"></div>
      <p class="error" role="alert"></p>
      <button class="btn block" type="submit">Send the notice</button>
    </form>` : ""}`);
  const form = $("#new-meeting");
  if (!form) return;
  $("#nm-short").addEventListener("change", () => { $("#nm-short-wrap").hidden = !$("#nm-short").checked; });
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const err = $(".error", form);
    const items = $("#nm-items").value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean).map((text) => ({ text }));
    const short = $("#nm-short").checked ? $("#nm-short-why").value.trim() : "";
    if ($("#nm-short").checked && !short) { err.textContent = "Say how and when every voting member agreed."; return; }
    busy($('button[type="submit"]', form), err, async () => {
      const res = await api("/meetings", {
        body: { b: state.b, title: $("#nm-title").value.trim(), starts_at: $("#nm-when").value, place: $("#nm-place").value.trim(), items, short_notice: short },
      });
      state.flash = "Notice sent to the committee and owners.";
      go("#/meeting/" + enc(res.meeting.id));
    });
  });
}

function motionResultText(mo) {
  const t = mo.tally || {};
  if (mo.status === "passed") return `Carried · ${t.yes} for, ${t.no} against${t.abstain ? `, ${t.abstain} abstained` : ""}`;
  if (mo.status === "lost") return t.yes === t.no ? `Lost · tied ${t.yes}–${t.no} (no casting vote)` : `Lost · ${t.yes} for, ${t.no} against`;
  return "Not voted yet";
}

function agendaHtml(m) {
  const voters = m.quorum ? [...m.quorum.present_ids, ...Object.keys(m.quorum.proxies || {})] : [];
  const nameOf = Object.fromEntries((m.members || []).map((p) => [p.user_id, p.name || p.email]));
  const canVote = m.can_run && m.status === "open" && m.quorum && m.quorum.ok;
  return `<ol class="agenda">${(m.agenda || []).map((item, i) => {
    const mo = item.motion;
    return `<li class="ag-item">
      <p class="ag-text">${item.case_ref && item.text.includes(item.case_ref)
        ? esc(item.text.split(item.case_ref)[0]) + `<a href="#/case/${enc(item.case_id)}">${esc(item.case_ref)}</a>` + esc(item.text.split(item.case_ref).slice(1).join(item.case_ref))
        : esc(item.text) + (item.case_ref ? ` · <a href="#/case/${enc(item.case_id)}">${esc(item.case_ref)}</a>` : "")}</p>
      ${mo ? `<p class="ag-motion">“${esc(mo.words)}”</p>
        <p class="ag-result${mo.status === "passed" ? " ok" : ""}">${esc(motionResultText(mo))}${mo.act_note ? ` <span class="muted small">· ${esc(mo.act_note)}</span>` : ""}</p>
        ${canVote && mo.status === "pending" ? `<details class="record"><summary>Record the votes</summary>
          <form class="vote-form" data-motion="${esc(mo.id)}">
            ${voters.map((uid) => `<div class="vote-line"><span class="grow">${esc(nameOf[uid] || "?")}${m.quorum.proxies[uid] ? ` <span class="muted small">by proxy</span>` : ""}</span>
              <select data-voter="${esc(uid)}" aria-label="Vote of ${esc(nameOf[uid] || "")}"><option value="">—</option><option value="yes">Yes</option><option value="no">No</option><option value="abstain">Abstain</option><option value="conflict">Conflict</option></select></div>`).join("")}
            <p class="error" role="alert"></p>
            <button class="btn secondary plain" type="submit">Record votes</button>
          </form></details>` : ""}` : ""}
    </li>`;
  }).join("")}</ol>`;
}

function attendanceHtml(m) {
  const by = Object.fromEntries((m.attendance || []).map((a) => [a.user_id, a]));
  const voting = (m.members || []).filter((p) => p.voting);
  return `<form id="attend" novalidate>
    ${(m.members || []).map((p) => {
      const a = by[p.user_id] || {};
      return `<div class="att-row" data-user="${esc(p.user_id)}">
        <span class="grow"><b>${esc(p.name || p.email)}</b><span class="muted small">${esc(p.label)}${p.unfinancial ? " · owes a debt: no vote" : ""}</span></span>
        <select data-how aria-label="How ${esc(p.name || p.email)} attended"${m.can_run && m.status !== "closed" ? "" : " disabled"}>
          <option value="">Not recorded</option>${Object.entries(HOW).filter(([k]) => p.voting || k !== "proxy").map(([k, v]) => `<option value="${k}"${a.how === k ? " selected" : ""}>${v}</option>`).join("")}
        </select>
        <select data-holder aria-label="Proxy held by"${a.how === "proxy" ? "" : " hidden"}${m.can_run && m.status !== "closed" ? "" : " disabled"}>
          <option value="">Proxy held by…</option>${voting.filter((x) => x.user_id !== p.user_id).map((x) => `<option value="${esc(x.user_id)}"${a.proxy_holder === x.user_id ? " selected" : ""}>${esc(x.name || x.email)}</option>`).join("")}
        </select>
      </div>`;
    }).join("")}
    <label for="others">Also attending <span class="opt">(owners observing, guests)</span></label>
    <input id="others" value="${esc(m.others || "")}"${m.can_run && m.status !== "closed" ? "" : " disabled"}>
    <p class="error" role="alert"></p>
    ${m.can_run && m.status !== "closed" ? '<button class="btn secondary plain" type="submit">Save attendance</button>' : ""}
  </form>`;
}

async function viewMeeting(t, rawId) {
  const id = decodeURIComponent(rawId);
  const flash = takeFlash();
  drawLoading();
  const r = await api(withB("/meeting", { id }));
  if (t !== seq) return;
  const m = r.meeting;
  const q = m.quorum || {};
  const stateWord = m.status === "scheduled" ? "Notice sent" : m.status === "open" ? "Under way" : "Closed";
  draw(`${flash}<a class="back" href="#/meetings">← Meetings</a>
    <p class="label">Committee meeting · ${esc(stateWord)}</p>
    <h1>${esc(m.title)}</h1>
    <p class="meta-line">${esc(m.when)}${m.place ? " · " + esc(m.place) : ""}</p>
    ${m.notice_text ? `<p class="small muted">${esc(m.notice_text)}${m.short_notice ? ` Short notice: ${esc(m.short_notice)}.` : ""}</p>` : ""}
    ${moduleNoteHtml(m.module_note)}
    <div class="case-grid">
      <div class="col-main">
        <section class="card"><h2>Agenda</h2>
          ${agendaHtml(m)}
          ${m.can_run && m.status !== "closed" ? `<details class="record"><summary>Add a motion</summary><form id="add-motion" class="sub-form" novalidate>
            <label for="am-words">The motion: the exact words voted on</label>
            <textarea id="am-words" rows="3" placeholder="That the committee …"></textarea>
            <p class="error" role="alert"></p>
            <button class="btn secondary plain" type="submit">Add to the agenda</button>
          </form></details>` : ""}
        </section>
      </div>
      <div class="col-side">
        <section class="card"><h2>Who's here</h2>
          <p class="quorum${q.ok ? " ok" : ""}">${m.status === "scheduled" && !(m.attendance || []).length ? `Quorum is ${esc(q.needed)} of ${esc(q.voting)} voting members.` : q.ok ? `Quorum: ${esc(q.present)} counted, ${esc(q.needed)} needed.` : `No quorum yet: ${esc(q.present)} counted, ${esc(q.needed)} needed. Nothing can be decided.`}</p>
          <p class="small muted">A proxy holder counts twice. Members with no vote don't count (SM s 60).</p>
          ${attendanceHtml(m)}
        </section>
        <section class="card"><h2>Minutes</h2>
          ${m.status === "closed" ? `<p>${m.minutes_status === "draft" ? `Draft ready. Issue by <span class="${num(m.minutes_days_left) !== null && num(m.minutes_days_left) <= 3 ? "late" : ""}">${esc(m.minutes_due)}</span>${num(m.minutes_days_left) !== null ? " · " + esc(daysText(m.minutes_days_left)) : ""}.` : m.minutes_status === "issued" ? "Issued to committee members and owners." : "Confirmed."}</p>
            <p class="link-row"><a href="#/minutes/${enc(m.id)}">${m.minutes_status === "draft" && m.can_minute ? "Check and issue the minutes" : "Read the minutes"}</a></p>`
            : `<p class="muted">Drafted for you from attendance and votes when the meeting closes. Due 21 days after it.</p>
            ${m.can_run && m.status === "open" ? '<p class="error" id="close-error" role="alert"></p><button type="button" class="btn block" id="close-meeting">Close the meeting</button>' : ""}`}
        </section>
      </div>
    </div>`);

  const attend = $("#attend");
  $$(".att-row", attend).forEach((row) => {
    const how = $("[data-how]", row);
    how.addEventListener("change", () => { $("[data-holder]", row).hidden = how.value !== "proxy"; });
  });
  attend.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const people = $$(".att-row", attend).map((row) => ({
      user_id: row.dataset.user, how: $("[data-how]", row).value, proxy_holder: $("[data-holder]", row).value,
    })).filter((p) => p.how);
    busy($('button[type="submit"]', attend), $(".error", attend), async () => {
      await api("/meeting/attendance", { body: { b: state.b, id: m.id, people, others: $("#others").value.trim() } });
      state.flash = "Attendance saved.";
      route();
    });
  });
  $$(".vote-form").forEach((form) => {
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const votes = {};
      $$("[data-voter]", form).forEach((sel) => { if (sel.value) votes[sel.dataset.voter] = sel.value; });
      if (!Object.keys(votes).length) { $(".error", form).textContent = "Record at least one vote."; return; }
      busy($('button[type="submit"]', form), $(".error", form), async () => {
        await api("/meeting/vote", { body: { b: state.b, motion_id: form.dataset.motion, votes } });
        state.flash = "Votes recorded.";
        route();
      });
    });
  });
  const add = $("#add-motion");
  if (add) {
    add.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const words = $("#am-words").value.trim();
      if (!words) { $(".error", add).textContent = "Write the motion first."; return; }
      busy($('button[type="submit"]', add), $(".error", add), async () => {
        await api("/meeting/motion", { body: { b: state.b, id: m.id, words } });
        route();
      });
    });
  }
  const closeBtn = $("#close-meeting");
  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      busy(closeBtn, $("#close-error"), async () => {
        await api("/meeting/close", { body: { b: state.b, id: m.id } });
        state.flash = "Meeting closed. The minutes are drafted.";
        go("#/minutes/" + enc(m.id));
      });
    });
  }
}

async function viewMinutes(t, rawId) {
  const id = decodeURIComponent(rawId);
  const flash = takeFlash();
  drawLoading();
  const r = await api(withB("/meeting", { id }));
  if (t !== seq) return;
  const m = r.meeting;
  const editable = m.minutes_status === "draft" && m.can_minute;
  const late = num(m.minutes_days_left) !== null && num(m.minutes_days_left) <= 3;
  draw(`${flash}<a class="back" href="#/meeting/${enc(m.id)}">← The meeting</a>
    <p class="label">Minutes · ${m.minutes_status === "draft" ? "Draft" : m.minutes_status === "issued" ? "Issued" : esc(m.minutes_status)}</p>
    <h1>${esc(m.title)}</h1>
    <p class="meta-line">${esc(m.when)}</p>
    ${m.minutes_status === "draft" ? `<p class="clock">Issue to committee members and owners by ${esc(m.minutes_due)}${num(m.minutes_days_left) !== null ? ` · <span class="${late ? "late" : ""}">${esc(daysText(m.minutes_days_left))}</span>` : ""} (SM s 71).</p>` : ""}
    ${editable ? `<form id="minutes" class="card" novalidate>
      <p class="small muted">Drafted from the meeting: every item the law asks for (SM s 71(6)). Check it, add item 7, then issue.</p>
      <label for="mtext" class="sr-only">Minutes</label>
      <textarea id="mtext" class="minutes-box" rows="24" maxlength="10000">${esc(m.minutes)}</textarea>
      ${m.secretary_ready ? "" : '<p class="draft">Before issuing: give someone the secretary position and add the secretary\'s contact address (Committee → Who does what).</p>'}
      <p class="error" role="alert"></p>
      <div class="actions"><button class="btn" type="button" id="issue">Issue to owners</button><button class="btn secondary plain" type="submit">Save draft</button></div>
    </form>` : `<section class="card"><div class="minutes-text">${lines(m.minutes || "No minutes yet.")}</div>
      ${m.doc_id ? '<p class="link-row"><a href="#/home">In Documents for owners</a></p>' : ""}</section>`}`);
  const form = $("#minutes");
  if (!form) return;
  const save = async () => api("/meeting/minutes", { body: { b: state.b, id: m.id, text: $("#mtext").value } });
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    busy($('button[type="submit"]', form), $(".error", form), async () => { await save(); state.flash = "Draft saved."; route(); });
  });
  confirmTap($("#issue"), "Tap again to send to every owner", () => {
    busy($("#issue"), $(".error", form), async () => {
      await save();
      await api("/meeting/minutes/issue", { body: { b: state.b, id: m.id } });
      state.flash = "Minutes issued: sent to committee members and owners, and saved in Documents.";
      route();
    });
  });
}

// ------------------------------------------------------------------ tasks

async function viewTasks(t, scope) {
  drawLoading();
  const r = await api(withB("/tasks", { scope: scope === "all" ? "all" : "mine" }));
  if (t !== seq) return;
  const list = r.tasks || [];
  const open = list.filter((k) => !k.done);
  const done = list.filter((k) => k.done);
  draw(`${takeFlash()}<h1>${scope === "all" ? "All tasks" : "My tasks"}</h1>
    <nav class="tabs" aria-label="Tasks"><a href="#/tasks"${scope !== "all" ? ' class="on" aria-current="page"' : ""}>Mine</a><a href="#/tasks/all"${scope === "all" ? ' class="on" aria-current="page"' : ""}>Everyone's</a></nav>
    <section class="card tasks-card">${open.length ? taskRowsHtml(open, true) : `<p class="muted pad">${scope === "all" ? "No open tasks." : "Nothing on your list."}</p>`}</section>
    ${done.length ? `<section class="card"><h2>Done</h2>${taskRowsHtml(done, true)}</section>` : ""}
    <section class="card">${taskFormHtml("new-task", r.people || []).replace('class="sub-form"', 'class="sub-form top"').replace('<button class="btn secondary plain" type="submit">', '<button class="btn block" type="submit">')}</section>`);
  wireTaskBoxes($("#view"));
  wireTaskForm("new-task", {}, () => { state.flash = "Task added. It shows in the daily reminders when it's due."; route(); });
}

// ------------------------------------------------------------------ the committee and who does what

async function viewCommittee(t) {
  drawLoading();
  const r = await api(withB("/committee"));
  if (t !== seq) return;
  const admin = state.me.can.admin;
  const positions = r.positions || [];
  const voting = (r.members || []).filter((p) => p.voting);
  draw(`${takeFlash()}<a class="back" href="#/board">← Board</a><h1>Committee</h1>
    ${moduleNoteHtml(r.module_note)}
    <div class="two-col">
      <section class="card"><h2>Who does what</h2>
        <p class="small muted">The law gives most jobs to the committee as a whole and names no minute-taker, so each building chooses. Request steps follow this list.</p>
        <form id="duties" novalidate>
          ${(r.duties || []).map((d) => `<div class="duty">
            <div class="grow"><span class="duty-label">${esc(d.label)}</span><span class="rule">${esc(d.rule)}</span></div>
            ${admin && d.key !== "vote" ? `<select data-duty="${esc(d.key)}" aria-label="${esc(d.label)}">${positions.map((p) => `<option value="${esc(p.key)}"${p.key === d.position ? " selected" : ""}>${esc(p.label)}</option>`).join("")}</select>` : `<span class="duty-who">${esc(d.position_label)}</span>`}
          </div>`).join("")}
          ${admin ? '<p class="error" role="alert"></p><button class="btn secondary plain" type="submit">Save who does what</button>' : ""}
        </form>
      </section>
      <div>
        <section class="card"><h2>Members</h2>
          ${(r.checks || []).map((c) => `<p class="draft">${esc(c)}</p>`).join("")}
          <div class="mini-rows">${(r.members || []).map((p) => `<div class="mini-row"><span class="grow"><b>${esc(p.name || p.email)}</b></span><span>${esc(p.label)}${p.unfinancial ? ' · <span class="late">no vote (debt)</span>' : ""}</span></div>`).join("") || '<p class="muted">Nobody yet. Give positions in Members.</p>'}</div>
          ${state.me.can.approve ? '<p class="link-row small"><a href="#/members">Give someone a position</a></p>' : ""}
        </section>
        ${admin ? `<form id="cset" class="card" novalidate><h2>Settings</h2>
          <label for="module">Regulation module (from the CMS)</label>
          <select id="module"><option value="">Not recorded yet</option><option value="standard"${r.module === "standard" ? " selected" : ""}>Standard Module</option><option value="accommodation"${r.module === "accommodation" ? " selected" : ""}>Accommodation Module</option></select>
          <label for="evidence">Evidence <span class="opt">(CMS dealing number and date)</span></label>
          <input id="evidence" maxlength="255" value="${esc(r.module_evidence || "")}">
          <label for="contact">Secretary's contact address <span class="opt">(printed in the minutes)</span></label>
          <input id="contact" maxlength="255" value="${esc(r.secretary_contact || "")}">
          ${voting.length ? `<fieldset><legend>Owes a body corporate debt (can't vote, still counts to quorum)</legend>${voting.map((p) => `<label class="check"><input type="checkbox" data-debt="${esc(p.user_id)}"${p.unfinancial ? " checked" : ""}><span>${esc(p.name || p.email)}</span></label>`).join("")}</fieldset>` : ""}
          <p class="error" role="alert"></p>
          <button class="btn block" type="submit">Save settings</button>
        </form>` : `<section class="card"><h2>Settings</h2><dl class="facts"><div><dt>Module</dt><dd>${esc(r.module ? r.module.charAt(0).toUpperCase() + r.module.slice(1) + " Module" : "Not recorded")}</dd></div><div><dt>Secretary</dt><dd>${esc(r.secretary_contact || "No contact address yet")}</dd></div></dl></section>`}
      </div>
    </div>`);
  if (!admin) return;
  const duties = $("#duties");
  duties.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const map = {};
    $$("[data-duty]", duties).forEach((s) => { map[s.dataset.duty] = s.value; });
    busy($('button[type="submit"]', duties), $(".error", duties), async () => {
      await api("/committee/settings", { body: { b: state.b, duties: map } });
      state.flash = "Saved. Request steps now go to these positions.";
      route();
    });
  });
  const form = $("#cset");
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    busy($('button[type="submit"]', form), $(".error", form), async () => {
      await api("/committee/settings", {
        body: {
          b: state.b, module: $("#module").value, evidence: $("#evidence").value.trim(), secretary_contact: $("#contact").value.trim(),
          unfinancial: $$("[data-debt]", form).filter((c) => c.checked).map((c) => c.dataset.debt),
        },
      });
      state.flash = "Settings saved.";
      route();
    });
  });
}

// ------------------------------------------------------------------ approvals

async function viewApprovals(t) {
  drawLoading();
  const r = await api(withB("/approvals"));
  if (t !== seq) return;
  const pending = r.pending || [];
  draw(`<h1>Approvals</h1>
    <p class="lead">Check each unit against the roll.</p>
    ${pending.length ? pending.map((p) => `<section class="card claim" data-id="${esc(p.id)}">
      <p class="claim-who"><b>${esc(p.user_name || p.user_email)}</b><br><span class="muted small email">${esc(p.user_email)}</span></p>
      <p><b>${esc(p.unit_label)}</b> · ${esc(p.relation === "tenant" ? "Tenant" : "Owner")}${p.created ? ` · <span class="muted small">asked ${esc(fmtDate(p.created))}</span>` : ""}</p>
      <div class="actions">
        <button type="button" class="btn" data-decide="approve">Approve</button>
        <button type="button" class="btn secondary" data-decide="reject">Reject</button>
      </div>
      <p class="error" role="alert"></p>
    </section>`).join("") : '<section class="card"><p class="muted">No one is waiting.</p></section>'}`);
  $$("[data-decide]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const card = btn.closest(".claim");
      const p = pending.find((x) => String(x.id) === card.dataset.id) || {};
      const decision = btn.dataset.decide;
      busy(btn, $(".error", card), async () => {
        await api("/approvals/decide", { body: { b: state.b, id: p.id, decision, note: "" } });
        card.innerHTML = `<p class="okmsg">${decision === "approve" ? "Approved" : "Rejected"}: ${esc(p.user_name || p.user_email)} · ${esc(p.unit_label)}</p>`;
      });
    });
  });
}

// ------------------------------------------------------------------ members and roles

function rolesHtml(roles, admin) {
  if (!roles.length) return '<p class="muted">No roles yet.</p>';
  return roles.map((r) => `<div class="mrow">
    <span class="grow email">${r.name ? `<b>${esc(r.name)}</b> ` : ""}${esc(r.email)}</span>
    <span>${esc(ROLES[r.role] || r.role)}</span>
    ${admin ? `<button type="button" class="btn small danger" data-role-off="${esc(r.email)}" data-role="${esc(r.role)}">Remove</button>` : ""}
    <p class="error"></p>
  </div>`).join("");
}

async function viewMembers(t) {
  drawLoading();
  const r = await api(withB("/members"));
  if (t !== seq) return;
  const members = r.members || [];
  const admin = state.me.can.admin;
  const live = (m) => m.status !== "removed" && m.status !== "rejected";
  draw(`${takeFlash()}<h1>Members &amp; roles</h1>
    <div class="two-col">
      <section class="card"><h2>Members</h2>
        ${members.length > 8 ? '<label for="find" class="sr-only">Find a member</label><input id="find" type="search" placeholder="Find a member" autocomplete="off">' : ""}
        <div id="members">${members.length ? members.map((m) => `<div class="mrow" data-find="${esc([m.user_name, m.user_email, m.unit_label].join(" ").toLowerCase())}">
          <div class="grow"><b>${esc(m.user_name || m.name || m.user_email || m.email)}</b>
            <span class="muted small email">${esc(m.user_email || m.email || "")}</span></div>
          <span>${esc(m.unit_label || "")} · ${esc(m.relation === "tenant" ? "Tenant" : "Owner")}${m.status && m.status !== "approved" ? " · " + esc(CLAIM_STATUS[m.status] || m.status) : ""}</span>
          ${live(m) ? `<button type="button" class="btn small danger" data-remove="${esc(m.id)}">Remove</button>` : ""}
          <p class="error"></p>
        </div>`).join("") : '<p class="muted">No members yet.</p>'}</div>
      </section>
      <section class="card"><h2>Roles</h2>
        <div id="roles">${rolesHtml(r.roles || [], admin)}</div>
        ${admin ? `<form id="add-role">
          <h3 class="sub">Give someone a role</h3>
          <label for="role-email">Their email</label>
          <input id="role-email" type="email" autocomplete="off" required>
          <label for="role">Role</label>
          <select id="role">${Object.entries(ROLES).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
          <p class="error" role="alert"></p>
          <button class="btn block" type="submit">Add role</button>
        </form>` : ""}
      </section>
    </div>`);

  const find = $("#find");
  if (find) {
    find.addEventListener("input", () => {
      const q = find.value.trim().toLowerCase();
      $$("#members .mrow").forEach((row) => { row.hidden = q && !row.dataset.find.includes(q); });
    });
  }
  $$("[data-remove]").forEach((btn) => {
    confirmTap(btn, "Tap again to remove", () => {
      const row = btn.closest(".mrow");
      const m = members.find((x) => String(x.id) === btn.dataset.remove) || {};
      busy(btn, $(".error", row), async () => {
        await api("/members/remove", { body: { b: state.b, id: m.id } });
        row.innerHTML = `<p class="okmsg">Removed: ${esc(m.user_name || m.user_email || "")} · ${esc(m.unit_label || "")}</p>`;
      });
    });
  });
  if (!admin) return;

  const wireRoles = () => {
    $$("[data-role-off]").forEach((btn) => {
      confirmTap(btn, "Tap again to remove", () => {
        busy(btn, $(".error", btn.closest(".mrow")), async () => {
          const res = await api("/roles", { body: { b: state.b, email: btn.dataset.roleOff, role: btn.dataset.role, on: false } });
          $("#roles").innerHTML = rolesHtml(res.roles || [], true);
          wireRoles();
          await refreshMeQuietly();
        });
      });
    });
  };
  wireRoles();

  const form = $("#add-role");
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const email = $("#role-email").value.trim().toLowerCase();
    const role = $("#role").value;
    const err = $(".error", form);
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { err.textContent = "Check the email address."; return; }
    busy($("button", form), err, async () => {
      const res = await api("/roles", { body: { b: state.b, email, role, on: true } });
      $("#roles").innerHTML = rolesHtml(res.roles || [], true);
      wireRoles();
      $("#role-email").value = "";
      await refreshMeQuietly();
    });
  });
}

async function refreshMeQuietly() {
  try { await loadMe(); } catch (e) { /* the page still works; the menu updates next load */ }
}

// ------------------------------------------------------------------ notices (handlers)

function noticeAdminHtml(notices) {
  if (!notices.length) return '<p class="muted">No notices yet.</p>';
  return notices.map((n) => `<div class="mrow">
    <div class="grow"><b>${esc(n.title)}</b>
      <span class="muted small">${esc(fmtDate(n.created || n.created_at))} · ${n.audience === "owners" ? "Owners only" : "Everyone"}</span></div>
    <button type="button" class="btn small danger" data-del-notice="${esc(n.id)}">Delete</button>
    <p class="error"></p>
  </div>`).join("");
}

async function viewNotices(t) {
  drawLoading();
  const r = await api(withB("/notices"));
  if (t !== seq) return;
  draw(`<h1>Notices</h1>
    <form id="f" class="card">
      <h2>Post a notice</h2>
      <label for="title">Title</label>
      <input id="title" required maxlength="200">
      <label for="body">Message</label>
      <textarea id="body" rows="5" required></textarea>
      <label for="audience">Who sees it?</label>
      <select id="audience"><option value="all">Everyone</option><option value="owners">Owners only</option></select>
      <p class="error" role="alert"></p>
      <button class="btn block" type="submit">Post notice</button>
    </form>
    <section class="card"><h2>Posted</h2><div id="list">${noticeAdminHtml(r.notices || [])}</div></section>`);

  const wireList = (notices) => {
    $$("[data-del-notice]").forEach((btn) => {
      confirmTap(btn, "Tap again to delete", () => {
        busy(btn, $(".error", btn.closest(".mrow")), async () => {
          const n = notices.find((x) => String(x.id) === btn.dataset.delNotice) || {};
          const res = await api("/notices/delete", { body: { b: state.b, id: n.id } });
          const next = res.notices || notices.filter((x) => x !== n);
          $("#list").innerHTML = noticeAdminHtml(next);
          wireList(next);
        });
      });
    });
  };
  wireList(r.notices || []);

  const f = $("#f");
  f.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const title = $("#title").value.trim();
    const body = $("#body").value.trim();
    const err = $(".error", f);
    if (!title || !body) { err.textContent = "Add a title and a message."; return; }
    busy($("button", f), err, async () => {
      const res = await api("/notices", { body: { b: state.b, title, body, audience: $("#audience").value } });
      const next = res.notices || (await api(withB("/notices"))).notices || [];
      $("#list").innerHTML = noticeAdminHtml(next);
      wireList(next);
      f.reset();
      err.innerHTML = "";
      f.insertAdjacentHTML("beforeend", '<p class="okmsg" role="status">Posted.</p>');
      setTimeout(() => { const ok = $(".okmsg", f); if (ok) ok.remove(); }, 3000);
    });
  });
}

// ------------------------------------------------------------------ documents (handlers)

async function viewDocs(t) {
  drawLoading();
  const r = await api(withB("/docs"));
  if (t !== seq) return;
  draw(`<h1>Documents</h1>
    <form id="f" class="card" novalidate>
      <h2>Add a document</h2>
      <label for="title">Title</label>
      <input id="title" required maxlength="200">
      <label for="category">What kind?</label>
      <select id="category">${DOC_KINDS.map((k) => `<option>${esc(k)}</option>`).join("")}</select>
      <label for="audience">Who sees it?</label>
      <select id="audience"><option value="all">Everyone</option><option value="owners">Owners only</option></select>
      <label for="file">File</label>
      <input id="file" type="file" accept="application/pdf,image/*,.doc,.docx">
      <p class="error" role="alert"></p>
      <button class="btn block" type="submit">Upload document</button>
    </form>
    <section class="card"><h2>Uploaded</h2><div id="list"></div></section>`);

  const show = (docs) => {
    $("#list").innerHTML = docsHtml(docs, true);
    wireDocDownloads($("#list"));
    $$("[data-del-doc]").forEach((btn) => {
      confirmTap(btn, "Tap again to delete", () => {
        busy(btn, $(".error", btn.closest(".doc-row")), async () => {
          const d = docs.find((x) => String(x.id) === btn.dataset.delDoc) || {};
          const res = await api("/docs/delete", { body: { b: state.b, id: d.id } });
          show(res.docs || docs.filter((x) => x !== d));
        });
      });
    });
  };
  show(r.docs || []);

  const f = $("#f");
  f.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const err = $(".error", f);
    const title = $("#title").value.trim();
    const file = $("#file").files[0];
    if (!title) { err.textContent = "Add a title."; return; }
    if (!file) { err.textContent = "Pick a file."; return; }
    if (file.size > MAX_FILE) { err.textContent = "That file is over 5 MB."; return; }
    busy($('button[type="submit"]', f), err, async () => {
      const data = await readBase64(file);
      const res = await api("/docs", {
        body: {
          b: state.b, title, category: $("#category").value, audience: $("#audience").value,
          name: file.name, type: file.type || guessType(file.name), data,
        },
      });
      show(res.docs || (await api(withB("/docs"))).docs || []);
      f.reset();
    });
  });
}

// ------------------------------------------------------------------ building settings (admin)

async function viewSettings(t) {
  drawLoading();
  const r = await api(withB("/building"));
  if (t !== seq) return;
  applyBrand(r.building || state.building);
  state.units = r.units || state.units;
  const b = state.building;
  const brand = brandOf(b);
  const colour = (c, fallback) => (isColour(c) ? longHex(c) : fallback);
  draw(`${takeFlash()}<h1>Building settings</h1>
    <form id="f" class="card">
      <h2>Name and look</h2>
      <label for="name">Building name</label>
      <input id="name" required value="${esc(b.name || "")}">
      <label for="scheme">Scheme number</label>
      <input id="scheme" value="${esc(b.scheme_no || "")}">
      <div class="colours">
        <div><label for="primary">Main colour</label><input id="primary" type="color" value="${esc(colour(brand.primary, "#243b2f"))}"></div>
        <div><label for="accent">Accent colour</label><input id="accent" type="color" value="${esc(colour(brand.accent, "#898f4e"))}"></div>
      </div>
      <label for="logo-url">Logo link <span class="opt">(optional)</span></label>
      <input id="logo-url" type="url" inputmode="url" placeholder="https://" value="${esc(brand.logo_url || "")}">
      <label for="banner-url">Banner image link <span class="opt">(optional)</span></label>
      <input id="banner-url" type="url" inputmode="url" placeholder="https://" value="${esc(brand.banner_url || "")}">
      <label for="footer">Footer name <span class="opt">(optional)</span></label>
      <input id="footer" value="${esc(brand.footer || "")}">
      <p class="error" role="alert"></p>
      <button class="btn block" type="submit">Save settings</button>
    </form>
    <form id="u" class="card">
      <h2>Units</h2>
      <p class="muted">${esc(state.units.length)} units set up.</p>
      ${state.units.length ? `<details><summary>See them</summary><p class="small">${state.units.map((u) => esc(u.label)).join(" · ")}</p></details>` : ""}
      <label for="paste">Paste units: unit,lot per line</label>
      <textarea id="paste" rows="6" placeholder="101,1&#10;102,2" spellcheck="false"></textarea>
      <p class="error" role="alert"></p>
      <button class="btn block" type="submit">Add units</button>
    </form>`);
  const f = $("#f");
  f.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const err = $(".error", f);
    const name = $("#name").value.trim();
    const logo = $("#logo-url").value.trim();
    if (!name) { err.textContent = "Add the building name."; return; }
    if (logo && !/^https:\/\//i.test(logo)) { err.textContent = "The logo link must start with https://"; return; }
    const bannerUrl = $("#banner-url").value.trim();
    if (bannerUrl && !/^https:\/\//i.test(bannerUrl)) { err.textContent = "The banner image link must start with https://"; return; }
    busy($("button", f), err, async () => {
      const res = await api("/admin/building", {
        body: {
          b: state.b, name, scheme_no: $("#scheme").value.trim(),
          brand: { ...brand, primary: $("#primary").value, accent: $("#accent").value, logo_url: logo, banner_url: bannerUrl, footer: $("#footer").value.trim() },
        },
      });
      applyBrand(res.building || { ...b, name });
      state.flash = "Settings saved.";
      route();
    });
  });

  const u = $("#u");
  u.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const err = $(".error", u);
    const units = $("#paste").value.split(/\r?\n/)
      .map((line) => line.split(/[,\t]/).map((s) => s.trim()))
      .filter((parts) => parts[0] && !/^unit/i.test(parts[0]))
      .map((parts) => ({ unit_no: parts[0], lot_no: parts[1] || "" }));
    if (!units.length) { err.textContent = "Paste at least one line, like 101,1"; return; }
    busy($("button", u), err, async () => {
      await api("/admin/units", { body: { b: state.b, units } });
      state.flash = `Sent ${units.length} units. Any new ones are added.`;
      route();
    });
  });
}

// ------------------------------------------------------------------ start

async function boot() {
  const slug = (new URLSearchParams(location.search).get("b") || "").trim().toLowerCase();
  if (!slug) { viewWhichBuilding(); return; }
  state.b = slug;
  try {
    const r = await api("/building?b=" + enc(slug));
    if (!r.building) throw new Error("not found");
    applyBrand(r.building);
    state.units = r.units || [];
  } catch (e) {
    viewWhichBuilding("We couldn't find that building. Check the code.");
    return;
  }
  window.addEventListener("hashchange", route);
  route();
}

boot();
