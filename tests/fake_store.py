"""
An in-memory store with the same methods as store.Db.

It refuses what the Data Store refuses (missing mandatory columns, values too long,
duplicates in unique columns) using the same SCHEMA, keeps files in a dict and
records every email in `.outbox` instead of sending it.

Set `.mail_error` to a reason to make every send fail with it, as Catalyst Mail
does before the sender is verified. `.clock` is CREATEDTIME, in Brisbane time.
"""

from datetime import datetime, timedelta

import store


def _norm(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class Duplicate(Exception):
    """What the Data Store raises for a repeated value in a unique column."""


class FakeDb:
    def __init__(self):
        self.tables = {name: [] for name in store.SCHEMA}
        self.files = {}
        self.outbox = []
        self.mail_error = None
        self.next_id = 694000000500000
        self.clock = datetime(2026, 11, 10, 0, 0, 0)

    def _unique(self, table, row, rowid=None):
        for col in store.SCHEMA.get(table, {}).get("unique", ()):
            if col in row and any(str(r.get(col)) == str(row[col]) and str(r["ROWID"]) != str(rowid)
                                  for r in self.tables[table]):
                raise Duplicate("DUPLICATE_VALUE {}.{}".format(table, col))

    def find(self, table, where=None):
        where = where or {}
        return [dict(r) for r in self.tables[table]
                if all(_norm(r.get(k)) == _norm(v) for k, v in where.items())]

    def get(self, table, rowid):
        rows = self.find(table, {"ROWID": rowid})
        return rows[0] if rows else None

    def insert(self, table, row):
        store.check_row(table, row, True)
        self._unique(table, row)
        self.next_id += 1
        self.clock += timedelta(seconds=1)
        # Bigints come back as strings, as they do from Catalyst.
        made = {k: (str(v) if isinstance(v, int) and not isinstance(v, bool) and k.endswith("_Id") else v)
                for k, v in row.items()}
        made.update(ROWID=str(self.next_id), CREATEDTIME=self.clock.strftime("%Y-%m-%d %H:%M:%S:000"))
        self.tables[table].append(made)
        return dict(made)

    def update(self, table, row):
        store.check_row(table, row, False)
        self._unique(table, row, row["ROWID"])
        for r in self.tables[table]:
            if str(r["ROWID"]) == str(row["ROWID"]):
                r.update({k: v for k, v in row.items() if k != "ROWID"})
                return dict(r)
        raise KeyError(row["ROWID"])

    def delete(self, table, rowid):
        self.tables[table] = [r for r in self.tables[table] if str(r["ROWID"]) != str(rowid)]

    def put_file(self, key, data, content_type):
        self.files[key] = (data, content_type)

    def get_file(self, key):
        found = self.files.get(key)
        return found[0] if found else None

    def delete_file(self, key):
        self.files.pop(key, None)

    def deliver(self, to, subject, html, bcc=None):
        if self.mail_error:
            return self.mail_error
        self.outbox.append({"to": list(to), "subject": subject, "html": html, "bcc": list(bcc or [])})
        return None

    def send_mail(self, to, subject, html, bcc=None):
        return self.deliver(to, subject, html, bcc) is None

    def mail_to(self, email):
        """Every email that reached this address, directly or by blind copy."""
        return [m for m in self.outbox if email in m["to"] or email in m["bcc"]]
