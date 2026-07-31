"""Shared SQLite connection policy for FieldStation42 runtime databases."""

import os
import sqlite3

DEFAULT_BUSY_TIMEOUT_MS = 30_000


def connect(path: str, **kwargs) -> sqlite3.Connection:
    """Open SQLite with bounded writer waits and concurrent-reader support."""
    timeout_ms = int(os.environ.get("FS42_SQLITE_BUSY_TIMEOUT_MS", DEFAULT_BUSY_TIMEOUT_MS))
    kwargs.setdefault("timeout", timeout_ms / 1000)
    connection = sqlite3.connect(path, **kwargs)
    connection.execute(f"PRAGMA busy_timeout={timeout_ms}")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    return connection
