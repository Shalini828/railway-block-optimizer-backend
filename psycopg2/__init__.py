"""
Pure Python drop-in replacement for psycopg2 using psycopg shim / pg8000.
Avoids Windows Application Control / Smart App Control DLL blocking errors with C-extensions.
"""
import psycopg
from psycopg import Error, DatabaseError, OperationalError
from . import extras

def connect(dsn=None, **kwargs):
    if dsn and isinstance(dsn, str) and dsn.startswith("postgresql://"):
        import urllib.parse
        parsed = urllib.parse.urlparse(dsn)
        return psycopg.connect(
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port,
            dbname=parsed.path.lstrip("/"),
            row_factory=kwargs.get("cursor_factory")
        )
    return psycopg.connect(
        host=kwargs.get("host"),
        port=kwargs.get("port"),
        dbname=kwargs.get("database") or kwargs.get("dbname"),
        user=kwargs.get("user"),
        password=kwargs.get("password"),
        row_factory=kwargs.get("cursor_factory")
    )
