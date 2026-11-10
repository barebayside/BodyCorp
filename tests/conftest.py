"""
Shared set-up: the function's folder on the path, test env vars, and a seeded
Altai with helpers to make people, roles and signed-in calls.
"""

import os
import re
import sys
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "catalyst", "functions", "bodycorp_api"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import admin  # noqa: E402
import auth  # noqa: E402
import buildings  # noqa: E402
import main  # noqa: E402
import people  # noqa: E402
import store  # noqa: E402
from fake_store import FakeDb  # noqa: E402

NOW = datetime(2026, 11, 10, 2, 0, 0)     # noon in Brisbane
ADMIN = "edward@example.com"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("AUTH_SALT", "test-salt")
    monkeypatch.setenv("ADMIN_KEY", "admin-key")
    monkeypatch.setenv("CRON_KEY", "cron-key")
    monkeypatch.setenv("MAIL_FROM", "portal@example.com")
    monkeypatch.setenv("MAIL_FROM_NAME", "BodyCorp")
    monkeypatch.setenv("PORTAL_URL", "https://example.com/app/portal.html")


class World:
    """A seeded building and quick ways to put people in it."""

    def __init__(self):
        self.db = FakeDb()
        admin.bootstrap(self.db, "admin-key", "altai", ADMIN)
        self.building = buildings.find(self.db, "altai")
        self.units = {u.get("Unit_No"): str(u["ROWID"]) for u in buildings.units(self.db, self.building)}
        self.tokens = {}

    def user(self, email):
        return auth.public_user(auth.find_or_make_user(self.db, email))

    def member(self, email, unit_no, relation="owner", status="approved"):
        user = self.user(email)
        self.db.insert(store.MEMBERSHIPS, {"User_Id": int(user["id"]), "Building_Id": int(self.building["id"]),
                                           "Unit_Id": int(self.units[unit_no]), "Relation": relation,
                                           "Status": status})
        return user

    def role(self, email, role):
        user = self.user(email)
        self.db.insert(store.ROLES, {"User_Id": int(user["id"]), "Building_Id": int(self.building["id"]),
                                     "Role": role})
        return user

    def ctx(self, email, building=None):
        return people.context(self.db, self.user(email), building or self.building)

    def last_code(self, email):
        mail = self.db.mail_to(email)[-1]
        return re.search(r"(\d{6})", mail["subject"]).group(1)

    def token(self, email, now=NOW):
        """Signs in once per email, through the real code flow."""
        if email not in self.tokens:
            auth.start(self.db, email, self.building, now)
            self.tokens[email] = auth.verify(self.db, email, self.last_code(email), now)[0]
        return self.tokens[email]

    def call(self, method, path, body=None, email=None, headers=None, now=NOW):
        headers = dict(headers or {})
        if email:
            headers["X-Session"] = self.token(email, now)
        body = dict({"b": "altai"}, **(body or {}))
        return main.route(self.db, method, path, body, headers, now)


@pytest.fixture
def world():
    return World()
