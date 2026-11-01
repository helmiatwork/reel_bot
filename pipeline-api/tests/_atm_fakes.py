"""Tiny fake psycopg connection for ATM tests: results are chosen by SQL substring."""
from types import SimpleNamespace


class FakeCursor:
    def __init__(self, rules, log):
        self.rules, self.log = rules, log
        self._rows, self.description = [], []
        self.connection = SimpleNamespace(rollback=lambda: None)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.log.append((" ".join(sql.split()), params))
        self._rows, self.description = [], []
        for needle, (cols, rows) in self.rules:
            if needle in sql:
                self.description = [SimpleNamespace(name=c) for c in cols]
                self._rows = list(rows)
                return

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class FakeConn:
    """rules: [(sql_substring, (columns, rows))], first match wins."""

    def __init__(self, rules=()):
        self.rules, self.log, self.commits, self.closed = list(rules), [], 0, False

    def cursor(self):
        return FakeCursor(self.rules, self.log)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True

    def sqls(self, needle):
        return [(s, p) for s, p in self.log if needle in s]
