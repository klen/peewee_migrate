from psycopg2.extensions import connection, cursor

class MockConnection(connection):
    def __init__(self, *args, **kwargs):
        self._cursor = MockCursor()
    def cursor(self, *args, **kwargs):
        return self._cursor

class MockCursor(cursor):
    def __init__(self, *args, **kwargs):
        self.queries = []
    def execute(self, query, *args, **kwargs):
        self.queries.append(query)
    def fetchall(self, *args, **kwargs):
        return []
    def fetchone(self, *args, **kwargs):
        return None

__all__ = ["MockConnection"]