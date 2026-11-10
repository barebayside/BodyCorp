"""
Every email the portal sends, in the building's colours.

Plain HTML with real colours written inline on each element: Zoho Mail strips
<style> blocks and CSS variables, which turns branded text white on white.
Everything a person typed is escaped before it goes into an email.
"""

import html
import os
import re

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_PRIMARY = "#24466b"


def _colour(value, default=DEFAULT_PRIMARY):
    return value if isinstance(value, str) and HEX.match(value) else default


def portal_link(building):
    base = os.environ.get("PORTAL_URL", "").strip()
    if not base:
        return ""
    return "{}?b={}".format(base, building["slug"]) if building else base


def page(building, heading, lines, button=None):
    """
    One email body. `lines` are plain strings (escaped here); `button` is a label
    for a link to the portal, left out when PORTAL_URL isn't set.
    """
    brand = (building or {}).get("brand") or {}
    primary = _colour(brand.get("primary"))
    name = html.escape((building or {}).get("name") or "BodyCorp")
    footer = html.escape(brand.get("footer") or (building or {}).get("name") or "")
    paragraphs = "".join(
        '<p style="margin:0 0 14px 0;color:#222222;font-size:16px;line-height:1.5;">{}</p>'.format(
            html.escape(str(line)).replace("\n", "<br>")) for line in lines if line)
    link = portal_link(building)
    action = ""
    if button and link:
        action = ('<p style="margin:22px 0;"><a href="{}" style="background:{};color:#ffffff;padding:12px 20px;'
                  'border-radius:6px;text-decoration:none;font-weight:bold;display:inline-block;">{}</a></p>').format(
            html.escape(link, quote=True), primary, html.escape(button))
    return (
        '<div style="background:#f4f4f2;padding:24px 12px;font-family:Arial,Helvetica,sans-serif;">'
        '<div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:8px;overflow:hidden;">'
        '<div style="background:{p};color:#ffffff;padding:16px 22px;font-size:18px;font-weight:bold;">{n}</div>'
        '<div style="padding:22px;">'
        '<h1 style="margin:0 0 16px 0;font-size:20px;color:{p};">{h}</h1>{body}{action}</div>'
        '<div style="padding:14px 22px;border-top:1px solid #e5e5e0;color:#777777;font-size:12px;">'
        '{f}<br>Powered by BodyCorp</div></div></div>'
    ).format(p=primary, n=name, h=html.escape(heading), body=paragraphs, action=action, f=footer)


def send(db, to, subject, body_html, bcc=None):
    """True if sent. Never raises: the store logs and returns False when mail isn't set up."""
    to = [to] if isinstance(to, str) else [t for t in to if t]
    if not to:
        return False
    return bool(db.send_mail(to, subject, body_html, bcc=bcc))


def send_many(db, emails, subject, body_html, batch=20):
    """One message to many people, in blind-copy batches so nobody sees the others' addresses."""
    emails = sorted({e for e in emails if e})
    sender = os.environ.get("MAIL_FROM", "").strip()
    sent = 0
    for start in range(0, len(emails), batch):
        chunk = emails[start:start + batch]
        if send(db, sender or chunk[0], subject, body_html, bcc=chunk if sender else chunk[1:]):
            sent += len(chunk)
    return sent
