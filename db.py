"""Pawsino database layer — all SQL lives here."""

import json
import logging
import os
from datetime import datetime, timezone

import aiosqlite

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Raised when a database operation fails."""


async def setup_database(db_path: str) -> None:
    """Create tables and enable WAL journal mode."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id      INTEGER PRIMARY KEY,
                    balance      INTEGER NOT NULL DEFAULT 1000,
                    last_daily   TEXT,
                    last_weekly  TEXT,
                    last_monthly TEXT,
                    total_won    INTEGER NOT NULL DEFAULT 0,
                    total_lost   INTEGER NOT NULL DEFAULT 0,
                    created_at   TEXT NOT NULL
                        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id       INTEGER NOT NULL,
                    type          TEXT NOT NULL,
                    amount        INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    created_at    TEXT NOT NULL
                        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS admin_audit (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id   INTEGER NOT NULL,
                    command    TEXT NOT NULL,
                    target_id  INTEGER,
                    details    TEXT,
                    created_at TEXT NOT NULL
                        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                )
            """)
            await db.commit()
    except Exception as exc:
        logger.exception("Failed to set up database")
        raise DatabaseError(f"Database setup failed: {exc}") from exc


async def get_or_create_user(db_path: str, user_id: int) -> dict:
    """Return user row as dict, creating with defaults if absent."""
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            from config import STARTING_BALANCE
            await db.execute(
                "INSERT INTO users (user_id, balance) VALUES (?, ?)",
                (user_id, STARTING_BALANCE),
            )
            await db.commit()
            cursor = await db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            return dict(row)
    except DatabaseError:
        raise
    except Exception as exc:
        logger.exception("Failed to get or create user %s", user_id)
        raise DatabaseError(
            f"get_or_create_user failed: {exc}"
        ) from exc


async def get_balance(db_path: str, user_id: int) -> int:
    """Return the current balance for a user."""
    user = await get_or_create_user(db_path, user_id)
    return user["balance"]


async def update_balance(
    db_path: str, user_id: int, delta: int, tx_type: str
) -> int:
    """Apply delta to balance, log transaction, return new balance."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await get_or_create_user(db_path, user_id)
            cursor = await db.execute(
                "SELECT balance FROM users WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            old_balance = row[0]
            new_balance = max(old_balance + delta, 0)

            if delta > 0:
                await db.execute(
                    "UPDATE users SET balance = ?, total_won = "
                    "total_won + ? WHERE user_id = ?",
                    (new_balance, delta, user_id),
                )
            elif delta < 0:
                await db.execute(
                    "UPDATE users SET balance = ?, total_lost = "
                    "total_lost + ? WHERE user_id = ?",
                    (new_balance, abs(delta), user_id),
                )
            else:
                await db.execute(
                    "UPDATE users SET balance = ? WHERE user_id = ?",
                    (new_balance, user_id),
                )

            await db.execute(
                "INSERT INTO transactions "
                "(user_id, type, amount, balance_after) "
                "VALUES (?, ?, ?, ?)",
                (user_id, tx_type, delta, new_balance),
            )
            await db.commit()
            return new_balance
    except DatabaseError:
        raise
    except Exception as exc:
        logger.exception(
            "Failed to update balance for user %s", user_id
        )
        raise DatabaseError(
            f"update_balance failed: {exc}"
        ) from exc


async def get_cooldowns(db_path: str, user_id: int) -> dict:
    """Return cooldown timestamps for a user."""
    user = await get_or_create_user(db_path, user_id)
    return {
        "last_daily": user["last_daily"],
        "last_weekly": user["last_weekly"],
        "last_monthly": user["last_monthly"],
    }


async def update_cooldown(
    db_path: str, user_id: int, cooldown_type: str
) -> None:
    """Set a cooldown timestamp to current UTC time."""
    column_map = {
        "daily": "last_daily",
        "weekly": "last_weekly",
        "monthly": "last_monthly",
    }
    column = column_map.get(cooldown_type)
    if not column:
        raise ValueError(f"Invalid cooldown type: {cooldown_type}")
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                f"UPDATE users SET {column} = ? WHERE user_id = ?",
                (now, user_id),
            )
            await db.commit()
    except Exception as exc:
        logger.exception("Failed to update cooldown for user %s", user_id)
        raise DatabaseError(
            f"update_cooldown failed: {exc}"
        ) from exc


async def get_leaderboard(
    db_path: str, limit: int = 10
) -> list[dict]:
    """Return top users by balance."""
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT user_id, balance FROM users "
                "ORDER BY balance DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.exception("Failed to get leaderboard")
        raise DatabaseError(
            f"get_leaderboard failed: {exc}"
        ) from exc


async def log_admin_action(
    db_path: str,
    admin_id: int,
    command: str,
    target_id: int | None = None,
    details: dict | None = None,
) -> None:
    """Record an admin action in the audit log."""
    try:
        details_json = json.dumps(details) if details else None
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO admin_audit "
                "(admin_id, command, target_id, details) "
                "VALUES (?, ?, ?, ?)",
                (admin_id, command, target_id, details_json),
            )
            await db.commit()
    except Exception as exc:
        logger.exception("Failed to log admin action")
        raise DatabaseError(
            f"log_admin_action failed: {exc}"
        ) from exc
