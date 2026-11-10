// The lawyer's page: one legal pack, opened by the private link in their email (lawyer.html?t=…).
// No sign-in: the token is the key, and the server answers 404 for a wrong, expired or replaced link.
// The lawyer ticks or queries each item, then signs off with their name (the date is recorded),
// or sends their comments back to the committee.

"use strict";

const API = "/server/bodycorp_api";
const token = new URLSearchParams(location.search).get("t") || "";
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const KIND = { rule: "Rule", product: "Form or step", question: "Question" };

function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"'`]/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;", "`": "&#96;",
  }[c]));
}
const lines = (text) => esc(text).replace(/\r?\n/g, "<br>");

// Catalyst ids are longer than JavaScript numbers hold exactly: keep long numbers as strings.
function quoteBigInts(text) {
  return text.replace(/([:\[,]\s*)(-?\d{16,})(?=\s*[,\]}])/g, '$1"$2"');
}

async function call(path, body) {
  const opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.assign({ t: token }, body)) } : {};
  let res;
  try { res = await fetch(API + path + (body ? "" : "?t=" + encodeURIComponent(token)), opts); }
  catch (e) { throw new Error("Can't reach the server. Check your connection and try again."); }
  let data = null;
  try { data = JSON.parse(quoteBigInts(await res.text())); } catch (e) { data = null; }
  if (!data || data.ok !== true) {
    const err = new Error((data && data.error) || "Something went wrong. Please try again.");
    err.status = res.status;
    throw err;
  }
  return data;
}

function fieldHtml(f, i) {
  const id = "lf_" + i;
  const opt = f.required ? "" : ' <span class="opt">(optional)</span>';
  if (f.type === "checkbox") return `<div class="field"><label class="check"><input id="${id}" type="checkbox" checked disabled><span>${esc(f.label)}${opt}</span></label></div>`;
  const label = `<label for="${id}">${esc(f.label)}${opt}</label>`;
  if (f.type === "select") return `<div class="field">${label}<select id="${id}" disabled>${(f.options || []).map((o) => `<option${o === f.example ? " selected" : ""}>${esc(o)}</option>`).join("")}</select></div>`;
  if (f.type === "textarea") return `<div class="field">${label}<textarea id="${id}" rows="3" disabled>${esc(f.example)}</textarea></div>`;
  if (f.type === "file") return `<div class="field">${label}<input id="${id}" type="text" value="${esc(f.example)}" disabled></div>`;
  return `<div class="field">${label}<input id="${id}" type="text" value="${esc(f.example)}" disabled></div>`;
}

function itemBody(item) {
  if (item.kind === "rule") {
    const r = item.rule;
    return `<p class="label">${esc(r.layer_label)}${r.key.startsWith("qld_sm_") ? " · rule " + esc(r.key.slice(7)) : ""} · version ${esc(r.version)}</p>
      <dl class="rule-facts">
        <div><dt>When</dt><dd>${esc(r.trigger)}</dd></div>
        <div><dt>What must happen</dt><dd>${esc(r.action)}</dd></div>
        <div><dt>Who</dt><dd>${esc(r.who)}</dd></div>
        <div><dt>Deadline</dt><dd>${esc(r.deadline_text || "None stated")}</dd></div>
        <div><dt>If it's missed</dt><dd>${esc(r.if_missed || "The source doesn't say")}</dd></div>
      </dl>
      ${(r.citations || []).map((c) => `<blockquote class="quote"><p class="q-head">${esc(c.source === "law" ? "Law file" : "The source")} · ${esc(c.clause)}</p><p>“${esc(c.quote)}”</p></blockquote>`).join("")}`;
  }
  if (item.kind === "product") {
    const p = item.product;
    return `<p class="label">${esc(p.topic)}${p.building ? " · " + esc(p.building) : ""}</p>
      ${p.if_missed ? `<div class="prop-missed"><p class="label">If nobody decides in time</p>${p.if_missed.before ? `<p class="pm-old"><span>Now</span>${esc(p.if_missed.before)}</p>` : ""}<p class="pm-new"><span>Proposed</span>${esc(p.if_missed.after)}</p></div>` : ""}
      ${p.why ? `<p class="prop-why">${esc(p.why)}</p>` : ""}
      ${(p.changes || []).length ? `<dl class="cur-prop">${p.changes.map((c) => `<div><dt>${esc(c.where)}</dt><dd><span class="was">${esc(c.old)}</span> → <b>${esc(c.new)}</b></dd></div>`).join("")}</dl>` : ""}
      ${p.after_form ? `<p class="label">The form as residents will see it, with example answers</p><div class="form-preview" inert>${p.after_form.map(fieldHtml).join("")}</div>` : ""}
      ${(p.steps || []).filter((s) => s.instructions).map((s) => `<p><b>Step "${esc(s.stage)}":</b> ${esc(s.instructions)}</p>`).join("")}
      ${(p.emails || []).map((e) => `<div class="lp-email"><p class="small muted">Email to ${esc(e.to)}</p><p><b>${esc(e.subject)}</b></p><p>${lines(e.body)}</p></div>`).join("")}`;
  }
  const q = item.question;
  return `<p>${esc(q.text)}</p><ul class="why-list">${(q.plan || []).map((l) => `<li>${esc(l)}</li>`).join("")}</ul>`;
}

function tickHtml(item, canEdit) {
  if (!canEdit) return item.tick ? `<p class="lp-state">${item.tick === "ok" ? "Ticked" : "Queried"}${item.comment ? `: “${esc(item.comment)}”` : ""}</p>` : "";
  return `<form class="lp-tick" data-item="${esc(item.item_id)}" novalidate>
    <div class="choices" role="radiogroup" aria-label="Your verdict on item ${esc(item.no)}">
      <label class="check"><input type="radio" name="tk-${esc(item.no)}" value="ok"${item.tick === "ok" ? " checked" : ""}><span>OK</span></label>
      <label class="check"><input type="radio" name="tk-${esc(item.no)}" value="query"${item.tick === "query" ? " checked" : ""}><span>Query it</span></label>
    </div>
    <label for="cm-${esc(item.no)}">Comment <span class="opt">(needed when you query it)</span></label>
    <textarea id="cm-${esc(item.no)}" rows="2" maxlength="2000">${esc(item.comment)}</textarea>
    <p class="error" role="alert"></p>
    <button class="btn secondary plain" type="submit">Save</button>
    ${item.tick ? `<span class="small muted"> Saved: ${item.tick === "ok" ? "OK" : "queried"}.</span>` : ""}
  </form>`;
}

function draw(html) { $("#view").innerHTML = html; }

function render(d, flash) {
  const p = d.pack;
  document.title = "Legal pack " + p.no + " · " + d.building;
  $("#bname").textContent = d.building;
  if (d.brand && /^#[0-9a-f]{6}$/i.test(d.brand.primary || "")) document.documentElement.style.setProperty("--brand", d.brand.primary);
  const signed = p.status === "signed";
  draw(`${flash ? `<p class="okmsg" role="status">${esc(flash)}</p>` : ""}
    <p class="label">Legal pack ${esc(p.no)} · ${esc(p.status_label)}</p>
    <h1>${esc(d.change.title)}</h1>
    ${d.change.summary ? `<p class="lead">${esc(d.change.summary)}</p>` : ""}
    <dl class="facts">
      <div><dt>From</dt><dd>${esc(d.change.source)} (${esc((d.change.entry || "").toLowerCase())})</dd></div>
      <div><dt>Starts</dt><dd>${esc(d.change.starts)}. Requests already lodged keep the rules they were lodged under.</dd></div>
      <div><dt>Why you</dt><dd>${esc(d.change.lawyer_why || "The committee asked for a lawyer's check.")}</dd></div>
      <div><dt>Link</dt><dd>${signed ? "Signed off: read only." : "Works until " + esc(p.expires_text) + "."}</dd></div>
    </dl>
    <p class="guidance">This pack is what the portal will do. Please tick each item, or query it with a comment, then sign off below. Your name and the date are recorded on the change.</p>
    <p class="link-row small"><a href="${esc(API + "/pack/pdf?t=" + encodeURIComponent(token))}">Download the PDF</a><a href="#" id="print">Print this page</a></p>
    ${d.items.map((item) => `<article class="lp-item"><p class="label">${esc(item.no)} · ${esc(KIND[item.kind] || item.kind)}</p>
      <h2>${esc(item.title)}</h2>${itemBody(item)}${tickHtml(item, d.can_edit)}</article>`).join("")}
    <section class="lp-sign">
      ${signed ? `<h2>Signed off</h2><p>By ${esc(p.signed_name)} on ${esc(p.signed_text)}${p.signed_via === "email" ? " (by email)" : ""}.</p>`
        : `<h2>Sign off</h2>
        <p class="small muted">${esc(p.counts.ok)} ticked · ${esc(p.counts.query)} queried · ${esc(p.counts.open)} to do</p>
        <form id="sign" novalidate><label for="sg-name">Your name</label><input id="sg-name" maxlength="255" autocomplete="name" value="${esc(p.lawyer_name)}">
          <label for="sg-note">A note for the committee <span class="opt">(optional)</span></label><textarea id="sg-note" rows="2" maxlength="2000"></textarea>
          <p class="error" role="alert"></p>
          <div class="actions"><button class="btn" type="submit"${p.counts.open || p.counts.query ? " disabled" : ""}>Sign off: I've checked every item</button>
          <button class="btn secondary plain" type="button" id="comments">Send my comments instead</button></div>
          ${p.counts.open ? '<p class="small muted">Tick or query every item first.</p>' : p.counts.query ? '<p class="small muted">You queried something: send your comments, and the committee will send a revised pack.</p>' : ""}
        </form>`}
    </section>`);
  $("#print").addEventListener("click", (ev) => { ev.preventDefault(); window.print(); });
  $$(".lp-tick").forEach((f) => f.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const tick = ($("input[type=radio]:checked", f) || {}).value || "";
    const comment = $("textarea", f).value.trim();
    const err = $(".error", f);
    if (!tick) { err.textContent = "Choose OK or Query it."; return; }
    if (tick === "query" && !comment) { err.textContent = "Say what needs to change."; return; }
    try { const res = await call("/pack/item", { item_id: f.dataset.item, tick, comment }); keep(res, "Saved.", f.dataset.item); }
    catch (e) { err.textContent = e.message; }
  }));
  const sign = $("#sign");
  if (sign) {
    sign.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const name = $("#sg-name").value.trim();
      if (!name) { $(".error", sign).textContent = "Type your name."; return; }
      try { render(await call("/pack/sign", { name, note: $("#sg-note").value.trim() }), "Signed off. Thank you: the committee has been told."); window.scrollTo(0, 0); }
      catch (e) { $(".error", sign).textContent = e.message; }
    });
    $("#comments").addEventListener("click", async () => {
      try { render(await call("/pack/comments", { note: $("#sg-note").value.trim() }), "Your comments went to the committee. They'll send a revised pack."); window.scrollTo(0, 0); }
      catch (e) { $(".error", sign).textContent = e.message; }
    });
  }
}

function keep(data, flash, itemId) {
  const y = window.scrollY;
  render(data, "");
  window.scrollTo(0, y);
  const form = itemId && $(`.lp-tick[data-item="${itemId}"]`);
  if (form) { const note = document.createElement("p"); note.className = "okmsg"; note.setAttribute("role", "status"); note.textContent = flash; form.appendChild(note); }
}

(async function start() {
  if (!token) { draw('<section class="card narrow"><h1>That link isn\'t complete</h1><p>Open the link from the email again.</p></section>'); return; }
  try { render(await call("/pack")); }
  catch (e) {
    draw(`<section class="card narrow"><h1>${e.status === 404 ? "This link doesn't work any more" : "That didn't work"}</h1>
      <p>${e.status === 404 ? "It may have expired, or a newer pack was sent. Ask the committee for a new link." : esc(e.message)}</p></section>`);
  }
})();
