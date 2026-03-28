class FakeCursor:
    def __init__(
        self,
        *,
        fetchone_values=None,
        fetchall_values=None,
        description=None,
        description_values=None,
        rowcount=1,
    ):
        self.fetchone_values = list(fetchone_values or [])
        self.fetchall_values = list(fetchall_values or [])
        self.description = description or []
        self.description_values = list(description_values or [])
        self.rowcount = rowcount
        self.fast_executemany = False
        self.input_sizes = None
        self.executed = []
        self.executemany_sql = None
        self.executemany_params = None
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self.description_values:
            self.description = self.description_values.pop(0)
        return self

    def executemany(self, sql, params):
        self.executemany_sql = sql
        self.executemany_params = params

    def fetchone(self):
        return self.fetchone_values.pop(0)

    def fetchall(self):
        if self.fetchall_values and isinstance(self.fetchall_values[0], list):
            return self.fetchall_values.pop(0)
        return list(self.fetchall_values)

    def setinputsizes(self, input_sizes):
        self.input_sizes = input_sizes

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, cursor=None):
        self.cursor_instance = cursor or FakeCursor()
        self.commit_called = False
        self.rollback_called = False
        self.close_called = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_called = True

    def rollback(self):
        self.rollback_called = True

    def close(self):
        self.close_called = True
