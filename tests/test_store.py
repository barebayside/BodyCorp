"""store.Db against a stand-in for the Catalyst app: paging, row checks, mail payload."""

import pytest

import store


class FakeApp:
    def __init__(self, rows=0):
        self.rows = [{"Users": {"ROWID": str(i), "Email": "u{}@x.com".format(i)}} for i in range(1, rows + 1)]
        self.queries, self.mails = [], []

    def zcql(self):
        return self

    def execute_query(self, query):
        self.queries.append(query)
        last = int(query.split("ROWID > ")[1].split(" ")[0])
        return [r for r in self.rows if int(r["Users"]["ROWID"]) > last][:300]

    def email(self):
        return self

    def send_mail(self, mail):
        self.mails.append(mail)


def _db(app):
    db = store.Db.__new__(store.Db)
    db._app = app
    return db


def test_find_pages_past_300():
    app = FakeApp(650)
    rows = _db(app).find(store.USERS, {"Email": "x'y"})
    assert len(rows) == 650 and len(app.queries) == 3
    assert app.queries[0] == "SELECT * FROM Users WHERE Email = 'x''y' AND ROWID > 0 ORDER BY ROWID LIMIT 300"
    assert "ROWID > 300 " in app.queries[1]


def test_row_checks_mandatory_and_size():
    with pytest.raises(store.RowRefused):
        store.check_row(store.CASES, {"Building_Id": 1}, True)
    with pytest.raises(store.RowRefused):
        store.check_row(store.EVENTS, {"Body": "x" * 10001}, False)
    store.check_row(store.EVENTS, {"Body": "x" * 10000}, False)


def test_send_mail_payload_and_no_sender(monkeypatch):
    app = FakeApp()
    monkeypatch.setenv("MAIL_FROM", "")
    assert _db(app).send_mail("a@x.com", "Hi", "<p>x</p>") is False and app.mails == []
    monkeypatch.setenv("MAIL_FROM", "portal@x.com")
    assert _db(app).send_mail("a@x.com", "Hi", "<p>x</p>", bcc=["b@x.com"]) is True
    mail = app.mails[0]
    assert mail["from_email"] == "portal@x.com" and mail["to_email"] == ["a@x.com"] and mail["html_mode"] is True
    sdk_email = pytest.importorskip("zcatalyst_sdk.email")
    sdk_email.Email._generate_data(mail)       # the SDK's own type checks accept it


def test_send_mail_failure_is_false(monkeypatch):
    class Broken(FakeApp):
        def send_mail(self, mail):
            raise RuntimeError("sender not verified")
    monkeypatch.setenv("MAIL_FROM", "portal@x.com")
    assert _db(Broken()).send_mail(["a@x.com"], "Hi", "x") is False


def test_created_iso_reads_catalyst_brisbane_time_as_utc():
    # Catalyst stamps CREATEDTIME in the project's timezone (Brisbane, UTC+10).
    assert store.created_iso({"CREATEDTIME": "2026-11-10 16:22:36:151"}) == "2026-11-10T06:22:36Z"
    assert store.created_iso({}) == ""
