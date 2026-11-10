"""
Every email the portal sends, in the building's colours, and the queue that makes sure it gets there.

Plain HTML with real colours written inline on each element: Zoho Mail strips
<style> blocks and CSS variables, which turns branded text white on white.
Everything a person typed is escaped before it goes into an email.

THE QUEUE
    send  ->  Catalyst Mail now  ->  sent: done (nothing is stored)
                                 ->  failed, or MAIL_FROM empty: a Mail_Queue row (queued,
                                     Attempts 1, Next_Try +5 min) and a Failures row (mail)
    retry_queue (start of /cron/reminders and /cron/check)  ->  each due row tried again,
        waiting 5 min, 30 min, 2 h, 6 h between tries  ->  sent, or after 5 tries failed
        (Failures row mail_gave_up)

    So a person still gets their email when the sender is fixed, and somebody is
    told when they won't. Callers see the same True/False as before.

    Sign-in code emails are never queued: the code lasts 10 minutes and only its
    hash is ever stored, so a queued copy would be both useless and a stored secret.
    A failure is still logged; the person just asks for a new code.

SIZE
    A queued copy has to fit Html text(10000). The template is kept compact so
    normal emails fit with room to spare (a 5,000-character notice is about 7,000).
    A bigger one is still sent in full, never cut, and a Failures row
    (mail_too_long) says it couldn't have been kept for a retry.
"""

import html
import logging
import os
import re
from datetime import timedelta

import failures
import store

logger = logging.getLogger("bodycorp_api.mailer")

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_PRIMARY = "#24466b"
FIRST_WAIT = timedelta(minutes=5)
# Wait after try 1, 2, 3, 4. Try 5 is the last.
WAITS = (FIRST_WAIT, timedelta(minutes=30), timedelta(hours=2), timedelta(hours=6))
MAX_TRIES = 5


def _colour(value, default=DEFAULT_PRIMARY):
    return value if isinstance(value, str) and HEX.match(value) else default


def _text(value):
    """Escaped for the inside of an element. Quotes only need escaping in attributes, and cost 6 characters each."""
    return html.escape(str(value), quote=False)


def portal_link(building):
    base = os.environ.get("PORTAL_URL", "").strip()
    if not base:
        return ""
    return "{}?b={}".format(base, building["slug"]) if building else base


def page(building, heading, lines, button=None):
    """
    One email body. `lines` are plain strings (escaped here); `button` is a label
    for a link to the portal, left out when PORTAL_URL isn't set. Colour and size
    are set once on the body block and inherited, to keep the HTML small.
    """
    brand = (building or {}).get("brand") or {}
    primary = _colour(brand.get("primary"))
    name = _text((building or {}).get("name") or "BodyCorp")
    footer = _text(brand.get("footer") or (building or {}).get("name") or "")
    paragraphs = "".join('<p style="margin:0 0 14px">{}</p>'.format(_text(line).replace("\n", "<br>"))
                         for line in lines if line)
    link = portal_link(building)
    action = ""
    if button and link:
        action = ('<p style="margin:22px 0"><a href="{}" style="background:{};color:#fff;padding:12px 20px;'
                  'border-radius:6px;text-decoration:none;font-weight:bold;display:inline-block">{}</a></p>').format(
            html.escape(link, quote=True), primary, _text(button))
    return (
        '<div style="background:#f4f4f2;padding:24px 12px;font-family:Arial,Helvetica,sans-serif">'
        '<div style="max-width:560px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden">'
        '<div style="background:{p};color:#fff;padding:16px 22px;font-size:18px;font-weight:bold">{n}</div>'
        '<div style="padding:22px;color:#222;font-size:16px;line-height:1.5">'
        '<h1 style="margin:0 0 16px;font-size:20px;color:{p}">{h}</h1>{body}{action}</div>'
        '<div style="padding:14px 22px;border-top:1px solid #e5e5e0;color:#777;font-size:12px">'
        '{f}<br>Powered by BodyCorp</div></div></div>'
    ).format(p=primary, n=name, h=_text(heading), body=paragraphs, action=action, f=footer)


def _deliver(db, to, subject, body_html, bcc):
    """None if Catalyst Mail took it, else why not. Never raises."""
    if not os.environ.get("MAIL_FROM", "").strip():
        return "MAIL_FROM is not set"
    try:
        return db.deliver(to, subject, body_html, bcc=bcc or None)
    except Exception as exc:  # noqa: BLE001 — a failed email must never fail the request
        logger.exception("mail failed: %r", subject)
        return "{}: {}".format(type(exc).__name__, exc)[:255]


def _queue(db, to, subject, body_html, bcc, building_id, reason):
    """Keep a failed email for retry. The queue row's id, or None if it couldn't be saved."""
    row = {"To_Email": ",".join(to), "Bcc": ",".join(bcc), "Subject": subject[:255], "Html": body_html,
           "Status": "queued", "Attempts": 1, "Last_Error": reason[:255],
           "Next_Try": store.fmt_dt(store.utc_now() + FIRST_WAIT)}
    if store.as_id(building_id):
        row["Building_Id"] = store.as_id(building_id)
    try:
        return db.insert(store.MAIL_QUEUE, row)["ROWID"]
    except Exception:  # noqa: BLE001 — the Failures row below still records it
        logger.exception("could not queue %r", subject)
        return None


def send(db, to, subject, body_html, bcc=None, building=None, secret=False):
    """
    True if sent now. Never raises. A failed send is queued for retry and logged
    (see THE QUEUE); `building` tags those rows so that building's admins see them.
    `secret` (sign-in codes) logs a failure but never stores the email.
    """
    to = [t for t in ([to] if isinstance(to, str) else list(to or [])) if t]
    bcc = [b for b in (bcc or []) if b]
    if not to:
        return False
    building_id = (building or {}).get("id")
    reason = _deliver(db, to, subject, body_html, bcc)
    too_long = len(body_html) > store.TEXT_MAX
    if reason is None:
        if too_long:
            failures.log(db, "mail_too_long", "Sent \"{}\", but at {:,} characters it's too big to keep for a "
                         "retry ({:,} max), so if it had failed it would have been lost. Shorten the template."
                         .format(subject, len(body_html), store.TEXT_MAX), building_id)
        return True
    if secret:
        failures.log(db, "mail", "A sign-in code email couldn't be sent ({}). Not queued: the code lasts "
                     "10 minutes and is never stored. The person can ask for a new code.".format(reason), building_id)
    elif too_long:
        failures.log(db, "mail_too_long", "\"{}\" couldn't be sent ({}) and at {:,} characters is too big to "
                     "queue, so it was not kept. Tell the {} recipient(s) to check the portal."
                     .format(subject, reason, len(body_html), len(to) + len(bcc)), building_id)
    else:
        queued = _queue(db, to, subject, body_html, bcc, building_id, reason)
        failures.log(db, "mail", "\"{}\" to {} recipient(s) couldn't be sent ({}). {}".format(
            subject, len(to) + len(bcc), reason,
            "Queued as #{}; it will be tried again.".format(queued) if queued else "It could not be queued either."),
            building_id)
    return False


def send_many(db, emails, subject, body_html, batch=20, building=None):
    """One message to many people, in blind-copy batches so nobody sees the others' addresses."""
    emails = sorted({e for e in emails if e})
    sender = os.environ.get("MAIL_FROM", "").strip()
    sent = 0
    for start in range(0, len(emails), batch):
        chunk = emails[start:start + batch]
        if send(db, sender or chunk[0], subject, body_html, bcc=chunk if sender else chunk[1:], building=building):
            sent += len(chunk)
    return sent


# ---------- retry ----------

def _split(text):
    return [part.strip() for part in str(text or "").split(",") if part.strip()]


def _retry_one(db, row, now):
    tries = int(row.get("Attempts") or 0) + 1
    reason = _deliver(db, _split(row.get("To_Email")), row.get("Subject") or "", row.get("Html") or "",
                      _split(row.get("Bcc")))
    if reason is None:
        db.update(store.MAIL_QUEUE, {"ROWID": row["ROWID"], "Status": "sent", "Attempts": tries})
        return "sent"
    if tries >= MAX_TRIES:
        db.update(store.MAIL_QUEUE, {"ROWID": row["ROWID"], "Status": "failed", "Attempts": tries,
                                     "Last_Error": reason[:255]})
        failures.log(db, "mail_gave_up", "Gave up on \"{}\" after {} tries ({}). Queue row #{}.".format(
            row.get("Subject"), tries, reason, row["ROWID"]), row.get("Building_Id"))
        return "failed"
    db.update(store.MAIL_QUEUE, {"ROWID": row["ROWID"], "Attempts": tries, "Last_Error": reason[:255],
                                 "Next_Try": store.fmt_dt(now + WAITS[tries - 1])})
    return "waiting"


def retry_queue(db, now=None):
    """
    Try every queued email whose Next_Try has come. Returns counts
    {sent, failed (gave up), waiting}. One bad row never stops the rest.
    """
    now = now or store.utc_now()
    counts = {"sent": 0, "failed": 0, "waiting": 0}
    for row in db.find(store.MAIL_QUEUE, {"Status": "queued"}):
        due = store.parse_dt(row.get("Next_Try"))
        if due and due > now:
            counts["waiting"] += 1
            continue
        try:
            counts[_retry_one(db, row, now)] += 1
        except Exception:  # noqa: BLE001 — tried again next run
            logger.exception("retry failed for queue row %s", row.get("ROWID"))
            counts["waiting"] += 1
    return counts
