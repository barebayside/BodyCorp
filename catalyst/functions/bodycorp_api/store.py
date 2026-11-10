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
FAILURES, MAIL_QUEUE = "Failures", "Mail_Queue"
MOTIONS, BALLOTS, MEETINGS, TASKS = "Motions", "Ballots", "Meetings", "Tasks"
PUSH_SUBS = "Push_Subs"
DOC_VERSIONS, RULE_REVIEWS, RULE_PROPOSALS = "Doc_Versions", "Rule_Reviews", "Rule_Proposals"
TOPIC_VERSIONS, AI_USAGE, AI_QUESTIONS = "Topic_Versions", "AI_Usage", "AI_Questions"
RULES, RULE_LINKS, CHANGES = "Rules", "Rule_Links", "Changes"
LEGAL_PACKS, PACK_ITEMS, NOTIFY_PLANS = "Legal_Packs", "Pack_Items", "Notify_Plans"

_TEXT = {"Brand", "Settings", "Definition", "Answers", "Steps", "Decision", "Files", "Body", "Words", "Eligible",
         "Tally", "Agenda", "Attendance", "Minutes", "Detail", "Endpoint", "Sub_Keys", "Trigger_Text", "Action_Text",
         "If_Missed", "Citations", "Summary", "Stage_Checks", "Impact_Json", "Lawyer_Why", "Note", "Comment",
         "Groups_Json", "Recipients"}

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
            "sizes": {"Ref": 30, "Topic_Key": 60, "Title": 255, "Status": 30, "Handler": 20, "Stage": 60}},
    EVENTS: {"required": ("Case_Id", "Building_Id", "Kind"), "unique": (), "sizes": {"Kind": 30}},
    NOTICES: {"required": ("Building_Id", "Title", "Audience"), "unique": (),
              "sizes": {"Title": 255, "Audience": 20}},
    DOCS: {"required": ("Building_Id", "Title", "Audience", "File_Key"), "unique": (),
           "sizes": {"Title": 255, "Category": 50, "Audience": 20, "File_Key": 255, "File_Name": 255}},
    LOGIN_CODES: {"required": ("Email", "Code_Hash", "Expires_At"), "unique": (),
                  "sizes": {"Email": 255, "Code_Hash": 128}},
    SESSIONS: {"required": ("Token_Hash", "User_Id", "Expires_At"), "unique": ("Token_Hash",),
               "sizes": {"Token_Hash": 128}},
    # Building_Id empty = product-wide. Resolved defaults to false in the table; we always write it anyway.
    FAILURES: {"required": ("Kind",), "unique": (), "sizes": {"Kind": 40, "Detail": TEXT_MAX}},
    MAIL_QUEUE: {"required": ("To_Email", "Subject", "Html", "Status"), "unique": (),
                 "sizes": {"To_Email": TEXT_MAX, "Bcc": TEXT_MAX, "Subject": 255, "Html": TEXT_MAX,
                           "Status": 20, "Last_Error": 255}},
    # Committee working view (2026-11-10). "Result" is a reserved word in the Data Store, hence Tally.
    MOTIONS: {"required": ("Building_Id", "Kind", "Words", "Status"), "unique": (),
              "sizes": {"Kind": 20, "Words": TEXT_MAX, "Status": 20, "Eligible": TEXT_MAX, "Tally": TEXT_MAX,
                        "Exempt": 30}},
    BALLOTS: {"required": ("Motion_Id", "Building_Id", "User_Id", "Vote"), "unique": (),
              "sizes": {"Vote": 20, "Note": 255}},
    MEETINGS: {"required": ("Building_Id", "Title", "Starts_At", "Status"), "unique": (),
               "sizes": {"Title": 255, "Place": 255, "Agenda": TEXT_MAX, "Status": 20, "Short_Notice": 255,
                         "Attendance": TEXT_MAX, "Minutes": TEXT_MAX, "Minutes_Status": 20}},
    TASKS: {"required": ("Building_Id", "Title"), "unique": (),
            "sizes": {"Title": 255, "Detail": TEXT_MAX, "Assignee_Position": 20}},
    # Web Push devices (2026-11-10). "Keys" is a reserved word in the Data Store, hence Sub_Keys.
    PUSH_SUBS: {"required": ("User_Id", "Building_Id", "Endpoint", "Sub_Keys"), "unique": (),
                "sizes": {"Endpoint": TEXT_MAX, "Sub_Keys": TEXT_MAX, "User_Agent": 255}},
    # The AI compliance helper (2026-11-10, ai.py). "Change", "Month" and "Batch" are reserved words, hence
    # Proposed_Json, Edited_Json, Usage_Month and Is_Batch. Long text (document text, the clause diff, raw batch
    # results) lives in Stratus under ai/<building id>/..., never in these columns.
    DOC_VERSIONS: {"required": ("Building_Id", "Kind", "Title", "File_Key", "Status"), "unique": (),
                   "sizes": {"Kind": 20, "Title": 255, "Version_Label": 100, "Dealing_No": 100, "File_Key": 255,
                             "Text_Key": 255, "Text_Source": 20, "Sha256": 64, "Status": 20, "Batch_Id": 100,
                             "Error": 255}},
    RULE_REVIEWS: {"required": ("Building_Id", "Old_Doc_Id", "New_Doc_Id", "Status"), "unique": (),
                   "sizes": {"Status": 20, "Batch_Id": 100, "Diff_Key": 255, "Error": 255}},
    RULE_PROPOSALS: {"required": ("Building_Id", "Review_Id", "Seq", "Kind", "Title", "Citations", "Status"),
                     "unique": (),
                     "sizes": {"Kind": 20, "Topic_Key": 60, "Title": 255, "Why": TEXT_MAX, "Citations": TEXT_MAX,
                               "Proposed_Json": TEXT_MAX, "Edited_Json": TEXT_MAX, "Unconfirmed_Reason": 255,
                               "Problems": TEXT_MAX, "Status": 20, "Decision_Note": 255}},
    TOPIC_VERSIONS: {"required": ("Building_Id", "Topic_Key", "Version", "Definition", "Effective_From", "Source"),
                     "unique": (),
                     "sizes": {"Topic_Key": 60, "Definition": TEXT_MAX, "Source": 20, "Proposal_Ids": 255,
                               "Note": 255}},
    AI_USAGE: {"required": ("Building_Id", "Usage_Month", "Kind", "Model", "Cost_Usd", "Cost_Aud"), "unique": (),
               "sizes": {"Usage_Month": 7, "Kind": 20, "Model": 40, "Request_Id": 100}},
    AI_QUESTIONS: {"required": ("Building_Id", "User_Id", "Question", "Status"), "unique": (),
                   "sizes": {"Question": TEXT_MAX, "Answer": TEXT_MAX, "Citations": TEXT_MAX, "Model": 40,
                             "Status": 20, "Batch_Id": 100}},
    # The rules loop (2026-11-10, rules.py, legal.py). Building_Id 0 = the law layer, shared by every building of
    # that state. Varchar columns can't be longer than 255 in the Data Store (it caps them silently), so anything
    # longer is text. TRIGGER, ACTION and SECTION are SQL words, hence Trigger_Text, Action_Text, Rule_Section.
    RULES: {"required": ("Building_Id", "Layer", "Jurisdiction", "Rule_Key", "Version", "Title", "Trigger_Text",
                         "Action_Text", "Who", "Citations", "Status"), "unique": (),
            "sizes": {"Layer": 10, "Jurisdiction": 10, "Reg_Module": 20, "Rule_Key": 60, "Rule_Section": 100,
                      "Title": 255, "Who": 255, "Duty": 60, "Deadline_Text": 255, "Status": 20}},
    RULE_LINKS: {"required": ("Building_Id", "Rule_Key", "Product_Kind", "Product_Path"), "unique": (),
                 "sizes": {"Rule_Key": 60, "Product_Kind": 20, "Topic_Key": 60, "Product_Path": 255, "Note": 255}},
    CHANGES: {"required": ("Building_Id", "Layer", "Entry_Point", "Source_Kind", "Title", "Stage"), "unique": (),
              "sizes": {"Layer": 10, "Entry_Point": 10, "Source_Kind": 20, "Title": 255, "Stage": 20, "Items_Key": 255,
                        "Error": 255}},
    LEGAL_PACKS: {"required": ("Building_Id", "Change_Id", "Pack_No", "Status"), "unique": (),
                  "sizes": {"Status": 20, "Lawyer_Name": 255, "Lawyer_Email": 255, "Token_Hash": 128, "Pdf_Key": 255,
                            "Snapshot_Key": 255, "Signed_Name": 255, "Signed_Via": 10, "Reply_Key": 255}},
    PACK_ITEMS: {"required": ("Building_Id", "Pack_Id", "Item_No", "Item_Kind", "Title"), "unique": (),
                 "sizes": {"Item_Kind": 20, "Ref_Id": 60, "Title": 255, "Tick": 10}},
    NOTIFY_PLANS: {"required": ("Building_Id", "Change_Id", "Status"), "unique": (),
                   "sizes": {"Status": 20, "Channels": 100, "Notice_Audience": 20, "Subject": 255}},
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


def created_utc(row):
    """
    A row's CREATEDTIME as a naive UTC datetime, or None.

    Catalyst writes CREATEDTIME in the project's timezone (Australia/Brisbane,
    UTC+10, no daylight saving), not UTC, unlike the datetimes we write ourselves.
    """
    local = parse_dt(row.get("CREATEDTIME"))
    return local - timedelta(hours=10) if local else None


def created_iso(row):
    """A row's CREATEDTIME as ISO UTC with Z, for the page."""
    when = created_utc(row)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ") if when else ""


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

    def deliver(self, to, subject, html, bcc=None, attachments=None):
        """
        Send through Catalyst Mail. None when it went, otherwise a short reason
        (never an exception), which mailer keeps on the queued copy so the retry
        and the failure log can say why. `attachments` = [(file name, bytes)]: Catalyst
        Mail wants open files, so each is written to the function's temp folder first.
        """
        sender = os.environ.get("MAIL_FROM", "").strip()
        to = [to] if isinstance(to, str) else list(to)
        if not sender:
            logger.info("mail not sent (MAIL_FROM unset): %r to %d people", subject, len(to) + len(bcc or []))
            return "MAIL_FROM is not set"
        mail = {"from_email": sender, "to_email": to, "subject": subject, "content": html, "html_mode": True,
                "display_name": os.environ.get("MAIL_FROM_NAME", "") or "BodyCorp"}
        if bcc:
            mail["bcc"] = list(bcc)
        handles = []
        try:
            if attachments:
                import tempfile
                folder = tempfile.mkdtemp()
                for name, data in attachments:
                    path = os.path.join(folder, os.path.basename(str(name)) or "file")
                    with open(path, "wb") as out:
                        out.write(data)
                    handles.append(open(path, "rb"))
                mail["attachments"] = handles
            self._app.email().send_mail(mail)
            return None
        except Exception as exc:  # noqa: BLE001 — a failed email must never fail the request
            logger.exception("mail failed: %r", subject)
            return "{}: {}".format(type(exc).__name__, exc)[:255]
        finally:
            for handle in handles:
                handle.close()

    def send_mail(self, to, subject, html, bcc=None):
        """True if sent. False, never an exception, when there is no verified sender yet or the send fails."""
        return self.deliver(to, subject, html, bcc) is None
