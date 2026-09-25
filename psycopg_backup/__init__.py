"""
Pure Python drop-in replacement for psycopg (v3) using pg8000.
Avoids Windows Application Control / Smart App Control DLL blocking errors with C-extensions.
"""
import os
import pg8000.dbapi
from .rows import dict_row

class Error(Exception):
    pass

class DatabaseError(Error):
    pass

class OperationalError(DatabaseError):
    pass

class CursorWrapper:
    def __init__(self, raw_cursor, row_factory=None):
        self._cursor = raw_cursor
        self.row_factory = row_factory

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def execute(self, query, params=None):
        if params is None:
            return self._cursor.execute(query)
        return self._cursor.execute(query, params)

    def executemany(self, query, param_seq):
        return self._cursor.executemany(query, param_seq)

    def _format_row(self, row):
        if row is None:
            return None
        if self.row_factory == dict_row or self.row_factory == "dict_row":
            if self.description:
                cols = [col[0] for col in self.description]
                return dict(zip(cols, row))
        return row

    def fetchone(self):
        row = self._cursor.fetchone()
        return self._format_row(row)

    def fetchall(self):
        rows_data = self._cursor.fetchall()
        if self.row_factory == dict_row or self.row_factory == "dict_row":
            if self.description:
                cols = [col[0] for col in self.description]
                return [dict(zip(cols, r)) for r in rows_data]
        return rows_data

    def fetchmany(self, size=None):
        rows_data = self._cursor.fetchmany(size)
        if self.row_factory == dict_row or self.row_factory == "dict_row":
            if self.description:
                cols = [col[0] for col in self.description]
                return [dict(zip(cols, r)) for r in rows_data]
        return rows_data

    def close(self):
        return self._cursor.close()

    def __iter__(self):
        for r in self.fetchall():
            yield r

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

class ConnectionWrapper:
    def __init__(self, raw_conn, row_factory=None):
        self._conn = raw_conn
        self.row_factory = row_factory

    def cursor(self, row_factory=None):
        rf = row_factory if row_factory is not None else self.row_factory
        return CursorWrapper(self._conn.cursor(), row_factory=rf)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    @property
    def autocommit(self):
        return self._conn.autocommit

    @autocommit.setter
    def autocommit(self, value):
        self._conn.autocommit = value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()

def connect(host=None, port=None, dbname=None, database=None, user=None, password=None, row_factory=None, **kwargs):
    db = dbname or database or os.getenv("DB_NAME") or "railway_block_planning"
    u = user or os.getenv("DB_USER") or "postgres"
    p = password or os.getenv("DB_PASSWORD") or ""
    h = host or os.getenv("DB_HOST") or "localhost"
    pt = int(port or os.getenv("DB_PORT") or 5432)

    try:
        raw_conn = pg8000.dbapi.connect(
            user=u,
            password=p,
            host=h,
            port=pt,
            database=db
        )
        return ConnectionWrapper(raw_conn, row_factory=row_factory)
    except Exception as e:
        raise OperationalError(f"Database connection error: {e}") from e
