import sqlite3
from pathlib import Path

from portal.infrastructure.config import settings

_DB_PATH = Path(settings.data_dir) / "portal.sqlite"


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS account_settings (
                account_id INTEGER PRIMARY KEY,
                auto_submit INTEGER NOT NULL DEFAULT 0
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                ran_at INTEGER NOT NULL,
                success INTEGER NOT NULL,
                readings_count INTEGER,
                error TEXT
            )
        """)


def get_auto_submit(account_id: int) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT auto_submit FROM account_settings WHERE account_id = ?",
            (account_id,),
        ).fetchone()
    return bool(row["auto_submit"]) if row else False


def set_auto_submit(account_id: int, enabled: bool) -> None:
    with _conn() as con:
        con.execute(
            """
            INSERT INTO account_settings (account_id, auto_submit) VALUES (?, ?)
            ON CONFLICT(account_id) DO UPDATE SET auto_submit = excluded.auto_submit
            """,
            (account_id, int(enabled)),
        )


def get_auto_submit_accounts() -> list[int]:
    """Return account_ids where auto_submit is enabled."""
    with _conn() as con:
        rows = con.execute(
            "SELECT account_id FROM account_settings WHERE auto_submit = 1"
        ).fetchall()
    return [row["account_id"] for row in rows]


def upsert_account(account_id: int) -> None:
    """Ensure an account row exists (preserves existing settings)."""
    with _conn() as con:
        con.execute(
            "INSERT INTO account_settings (account_id) VALUES (?) ON CONFLICT DO NOTHING",
            (account_id,),
        )


def add_log_entry(account_id: int, *, success: bool, readings_count: int = 0, error: str | None = None) -> None:
    import time
    with _conn() as con:
        con.execute(
            """
            INSERT INTO scheduler_log (account_id, ran_at, success, readings_count, error)
            VALUES (?, ?, ?, ?, ?)
            """,
            (account_id, int(time.time()), int(success), readings_count, error),
        )


def get_log(limit: int = 100) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            """
            SELECT id, account_id, ran_at, success, readings_count, error
            FROM scheduler_log
            ORDER BY ran_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
