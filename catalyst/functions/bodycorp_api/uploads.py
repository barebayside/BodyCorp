"""
Files sent by the page as base64 JSON: photos and PDFs only, 5 MB each.

The type is read from the file's first bytes, not trusted from the page, so a file
named photo.jpg that is really something else is refused.
"""

import base64
import binascii
import re

from errors import bad

MAX_BYTES = 5 * 1024 * 1024
MAX_FILES = 5
TYPES = ("image/jpeg", "image/png", "image/heic", "image/webp", "application/pdf")


def sniff(data):
    """The real type of the bytes, or None if it isn't one we accept."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"heim", b"heis", b"mif1", b"msf1", b"hevc"):
        return "image/heic"
    if data[:5] == b"%PDF-":
        return "application/pdf"
    return None


def safe_name(name):
    """A file name safe for a storage key and a download header."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(name or "").strip()).strip("-.")
    return (cleaned or "file")[:120]


def decode(item):
    """{name, data} -> (bytes, type, safe name). Refuses anything too big or not a photo or PDF."""
    if not isinstance(item, dict):
        raise bad("A file was sent the wrong way.")
    text = str(item.get("data") or "")
    if text.startswith("data:") and "," in text:
        text = text.split(",", 1)[1]    # a data URL from the page's FileReader
    if len(text) > (MAX_BYTES * 4) // 3 + 8:
        raise bad("Each file must be 5 MB or smaller.")
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise bad("A file couldn't be read. Try attaching it again.")
    if not data:
        raise bad("A file was empty.")
    if len(data) > MAX_BYTES:
        raise bad("Each file must be 5 MB or smaller.")
    kind = sniff(data)
    if not kind:
        raise bad("Only photos (JPEG, PNG, HEIC, WebP) and PDFs can be attached.")
    return data, kind, safe_name(item.get("name"))
