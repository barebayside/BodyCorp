"""
Every database, file and mail call. Thin on purpose, so tests can hand in a fake one.

THE 300-ROW CAP
    ZCQL returns at most 300 rows and does not say when it stopped, so a plain
    SELECT looks complete at 300 and quietly drops the rest. `find` pages by ROWID.

VALUES
    Every value in a WHERE clause goes through `build_where`, which doubles single
    quotes. Ids are bigints: pass them as ints (see `as_id`); they come back as strings.
    Datetimes are written and read as 'YYYY-MM-DD HH:MM:SS' in UTC.

SCHEMA
    The columns that must be filled, the unique ones and the column sizes, exactly as
    the tables were made. `check_row` refuses a row the Data Store would refuse, so a
    too-long answer fails with a plain message, and the fake store in the tests uses
    the same rules.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("bodycorp_api.store")

BUCKET = "bodycorp-files"
PAGE = 300
TEXT_MAX = 10000
DT_FORMAT = "%Y-%m-%d %H:%M:%S"

BUILDINGS, UNITS, USERS, MEMBERSHIPS, ROLES = "Buildings", "Units", "Users", "Memberships", "Roles"
TOPICS, CASES, EVENTS, NOTICES, DOCS = "Topics", "Cases", "Events", "Notices", "Docs"
LOGIN_CODES, SESSIONS = "Login_Codes", "Sessions"

_TEXT = {"Brand", "Settings", "Definition", "Answers", "Steps", "Decision", "Files", "Body"}

SCHEMA = {
    BUILDINGS: {"required": ("Slug",), "unique": ("Slug",),
                "sizes": {"Slug": 100, "Name": 255, "Scheme_No": 255}},
    UNITS: {"required": ("Building_Id", "Unit_No"), "unique": (),
            "sizes": {"Unit_No": 50, "Lot_No": 50}},
    USERS: {"required": ("Email",), "unique": ("Email",), "sizes": {"Email": 255, "Name": 255}},
    MEMBERSHIPS: {"required": ("User_Id", "Building_Id", "Unit_Id", "Relation", "Status"), "unique": (),
                  "sizes": {"Relation": 20, "Status": 20, "Note": 255}},
    ROLES: {"required": ("User_Id", "Building_Id", "Role"), "unique": (), "sizes": {"Role": 20}},
    TOPICS: {"required": ("Building_Id", "Topic_Key", "Definition"), "unique": (), "sizes": {"Topic_Key": 60}},
    CASES: {"required": ("Building_Id", "Unit_Id", "User_Id", "Ref", "Topic_Key", "Status", "Handler"),
            "unique": ("Ref",),
            "sizes": {"Ref": 30, "Topic_Key": 60, "Title": 255, "Status": 30, "Handler": 20}},
    EVENTS: {"required": ("Case_Id", "Building_Id", "Kind"), "unique": (), "sizes": {"Kind": 30}},
    NOTICES: {"required": ("Building_Id", "Title", "Audience"), "unique": (),
              "sizes": {"Title": 255, "Audience": 20}},
    DOCS: {"required": ("Building_Id", "Title", "Audience", "File_Key"), "unique": (),
           "sizes": {"Title": 255, "Category": 50, "Audience": 20, "File_Key": 255, "File_Name": 255}},
    LOGIN_CODES: {"required": ("Email", "Code_Hash", "Expires_At"), "unique": (),
                  "sizes": {"Email": 255, "Code_Hash": 128}},
    SESSIONS: {"required": ("Token_Hash", "User_Id", "Expires_At"), "unique": ("Token_Hash",),
               "sizes": {"Token_Hash": 128}},
}


class RowRefused(Exception):
    """A row the Data Store would refuse. The message is safe to show."""


def check_row(table, row, inserting):
    """Raise RowRefused for a missing mandatory column or a value too long for its column."""
    spec = SCHEMA.get(table, {})
    if inserting:
        for col in spec.get("required", ()):
            if row.get(col) in (None, ""):
                raise RowRefused("{}.{} is required.".format(table, col))
    for col, value in row.items():
        limit = spec.get("sizes", {}).get(col) or (TEXT_MAX if col in _TEXT else None)
        if limit and value is not None and len(str(value)) > limit:
            raise RowRefused("That's too long ({} holds {} characters).".format(col.replace("_", " ").lower(), limit))


def as_id(value):
    """A bigint id as an int, or None if it isn't one. Ids arrive as strings from the page and the store."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def fmt_dt(value):
    """A UTC datetime as the Data Store writes it."""
    return value.strftime(DT_FORMAT)


def utc_now():
    """Now in UTC, naive, as every datetime here is."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_dt(text):
    """'YYYY-MM-DD HH:MM:SS' (CREATEDTIME adds ':mmm') back to a naive UTC datetime, or None."""
    try:
        return datetime.strptime(str(text)[:19], DT_FORMAT)
    except (TypeError, ValueError):
        return None


def created_iso(row):
    """
    A row's CREATEDTIME as ISO UTC with Z.

    Catalyst writes CREATEDTIME in the project's timezone (Australia/Brisbane,
    UTC+10, no daylight saving), not UTC, unlike the datetimes we write ourselves.
    """
    local = parse_dt(row.get("CREATEDTIME"))
    return (local - timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ") if local else ""


def _literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return "'{}'".format(str(value).replace("'", "''"))


def build_where(where):
    """{"Email": "a'b", "User_Id": 5} -> "Email = 'a''b' AND User_Id = 5". Column names are ours, never input."""
    return " AND ".join("{} = {}".format(col, _literal(val)) for col, val in where.items())


class Db:
    def __init__(self):
        import zcatalyst_sdk  # imported here so tests never need the SDK
        self._app = zcatalyst_sdk.initialize()

    def find(self, table, where=None):
        """Every row matching `where` (all equal), paged by ROWID."""
        clause = build_where(where or {})
        out, last = [], 0
        while True:
            query = "SELECT * FROM {} WHERE {}ROWID > {} ORDER BY ROWID LIMIT {}".format(
                table, clause + " AND " if clause else "", last, PAGE)
            rows = self._app.zcql().execute_query(query) or []
            page = [next(iter(r.values())) if len(r) == 1 else r for r in rows]
            out.extend(page)
            if len(page) < PAGE:
                return out
            last = int(page[-1]["ROWID"])

    def get(self, table, rowid):
        number = as_id(rowid)
        if number is None:
            return None
        rows = self.find(table, {"ROWID": number})
        return rows[0] if rows else None

    def insert(self, table, row):
        check_row(table, row, True)
        return self._app.datastore().table(table).insert_row(row)

    def update(self, table, row):
        check_row(table, row, False)
        return self._app.datastore().table(table).update_row(dict(row, ROWID=str(row["ROWID"])))

    def delete(self, table, rowid):
        return self._app.datastore().table(table).delete_row(str(rowid))

    def put_file(self, key, data, content_type):
        self._app.stratus().bucket(BUCKET).put_object(
            key, data, {"content_type": content_type, "overwrite": "true"})

    def get_file(self, key):
        """The saved bytes, or None if there is nothing at that key."""
        try:
            raw = self._app.stratus().bucket(BUCKET).get_object(key)
        except Exception:  # noqa: BLE001 — a missing object raises
            logger.info("no file at %s", key)
            return None
        return raw.read() if hasattr(raw, "read") else raw

    def delete_file(self, key):
        try:
            self._app.stratus().bucket(BUCKET).delete_object(key)
        except Exception:  # noqa: BLE001 — a leftover file is unreachable once its row is gone
            logger.warning("could not delete file %s", key)

    def send_mail(self, to, subject, html, bcc=None):
        """
        Send through Catalyst Mail. False, never an exception, when there is no
        verified sender yet or the send fails: the request still succeeds and
        everything is visible in the portal.
        """
        sender = os.environ.get("MAIL_FROM", "").strip()
        to = [to] if isinstance(to, str) else list(to)
        if not sender:
            logger.info("mail not sent (MAIL_FROM unset): %r to %d people", subject, len(to) + len(bcc or []))
            return False
        mail = {"from_email": sender, "to_email": to, "subject": subject, "content": html, "html_mode": True,
                "display_name": os.environ.get("MAIL_FROM_NAME", "") or "BodyCorp"}
        if bcc:
            mail["bcc"] = list(bcc)
        try:
            self._app.email().send_mail(mail)
            return True
        except Exception:  # noqa: BLE001 — a failed email must never fail the request
            logger.exception("mail failed: %r", subject)
            return False
