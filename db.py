"""Pawsino database layer — all SQL lives here."""

import json
import logging
import os
from datetime import datetime, timezone

import aiosqlite

logger = logging.getLogger(__name__)

_COOLDOWN_COLUMNS: dict[str, str] = {
    "daily": "last_daily",
    "weekly": "last_weekly",
    "monthly": "last_monthly",
}


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
    column = _COOLDOWN_COLUMNS.get(cooldown_type)
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


async def get_user_rank(db_path: str, user_id: int) -> int:
    """Return the 1-based rank of a user by balance."""
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM users WHERE balance > "
                "(SELECT balance FROM users WHERE user_id = ?)",
                (user_id,),
            )
            row = await cursor.fetchone()
            return (row[0] if row else 0) + 1
    except Exception as exc:
        logger.exception("Failed to get rank for user %s", user_id)
        raise DatabaseError(
            f"get_user_rank failed: {exc}"
        ) from exc


async def transfer_meowney(
    db_path: str, sender_id: int, receiver_id: int, amount: int
) -> tuple[int, int]:
    """Transfer Meowney atomically, return (sender_bal, receiver_bal)."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await get_or_create_user(db_path, receiver_id)
            cursor = await db.execute(
                "SELECT balance FROM users WHERE user_id = ?",
                (sender_id,),
            )
            row = await cursor.fetchone()
            sender_new = row[0] - amount

            cursor = await db.execute(
                "SELECT balance FROM users WHERE user_id = ?",
                (receiver_id,),
            )
            row = await cursor.fetchone()
            receiver_new = row[0] + amount

            await db.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (sender_new, sender_id),
            )
            await db.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (receiver_new, receiver_id),
            )
            await db.execute(
                "INSERT INTO transactions "
                "(user_id, type, amount, balance_after) "
                "VALUES (?, ?, ?, ?)",
                (sender_id, "transfer_out", -amount, sender_new),
            )
            await db.execute(
                "INSERT INTO transactions "
                "(user_id, type, amount, balance_after) "
                "VALUES (?, ?, ?, ?)",
                (receiver_id, "transfer_in", amount, receiver_new),
            )
            await db.commit()
            return sender_new, receiver_new
    except DatabaseError:
        raise
    except Exception as exc:
        logger.exception("Failed to transfer meowney")
        raise DatabaseError(
            f"transfer_meowney failed: {exc}"
        ) from exc


async def set_balance(
    db_path: str, user_id: int, amount: int, tx_type: str
) -> int:
    """Set a user's balance to an exact amount, return old balance."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await get_or_create_user(db_path, user_id)
            cursor = await db.execute(
                "SELECT balance FROM users WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            old_balance = row[0]
            delta = amount - old_balance

            await db.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (amount, user_id),
            )
            await db.execute(
                "INSERT INTO transactions "
                "(user_id, type, amount, balance_after) "
                "VALUES (?, ?, ?, ?)",
                (user_id, tx_type, delta, amount),
            )
            await db.commit()
            return old_balance
    except DatabaseError:
        raise
    except Exception as exc:
        logger.exception("Failed to set balance for user %s", user_id)
        raise DatabaseError(
            f"set_balance failed: {exc}"
        ) from exc


async def add_balance(
    db_path: str, user_id: int, delta: int, tx_type: str
) -> tuple[int, int]:
    """Add/subtract from balance (clamped to 0), return (old, new)."""
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
            actual_delta = new_balance - old_balance

            await db.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (new_balance, user_id),
            )
            await db.execute(
                "INSERT INTO transactions "
                "(user_id, type, amount, balance_after) "
                "VALUES (?, ?, ?, ?)",
                (user_id, tx_type, actual_delta, new_balance),
            )
            await db.commit()
            return old_balance, new_balance
    except DatabaseError:
        raise
    except Exception as exc:
        logger.exception("Failed to add balance for user %s", user_id)
        raise DatabaseError(
            f"add_balance failed: {exc}"
        ) from exc


async def reset_user(
    db_path: str, user_id: int, starting_balance: int
) -> None:
    """Reset user to starting balance and clear all cooldowns."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await get_or_create_user(db_path, user_id)
            await db.execute(
                "UPDATE users SET balance = ?, last_daily = NULL, "
                "last_weekly = NULL, last_monthly = NULL "
                "WHERE user_id = ?",
                (starting_balance, user_id),
            )
            await db.execute(
                "INSERT INTO transactions "
                "(user_id, type, amount, balance_after) "
                "VALUES (?, ?, ?, ?)",
                (user_id, "admin_reset", 0, starting_balance),
            )
            await db.commit()
    except DatabaseError:
        raise
    except Exception as exc:
        logger.exception("Failed to reset user %s", user_id)
        raise DatabaseError(f"reset_user failed: {exc}") from exc


async def clear_cooldown(
    db_path: str, user_id: int, cooldown_type: str
) -> None:
    """Set a single cooldown to NULL."""
    column = _COOLDOWN_COLUMNS.get(cooldown_type)
    if not column:
        raise ValueError(f"Invalid cooldown type: {cooldown_type}")
    try:
        async with aiosqlite.connect(db_path) as db:
            await get_or_create_user(db_path, user_id)
            await db.execute(
                f"UPDATE users SET {column} = NULL WHERE user_id = ?",
                (user_id,),
            )
            await db.commit()
    except Exception as exc:
        logger.exception(
            "Failed to clear cooldown for user %s", user_id
        )
        raise DatabaseError(
            f"clear_cooldown failed: {exc}"
        ) from exc


async def get_recent_transactions(
    db_path: str, user_id: int, limit: int = 5
) -> list[dict]:
    """Return the most recent transactions for a user."""
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT type, amount, balance_after, created_at "
                "FROM transactions WHERE user_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.exception(
            "Failed to get transactions for user %s", user_id
        )
        raise DatabaseError(
            f"get_recent_transactions failed: {exc}"
        ) from exc


async def get_global_stats(db_path: str) -> dict:
    """Return aggregate statistics across all users and transactions."""
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM users"
            )
            user_count = (await cursor.fetchone())[0]

            cursor = await db.execute(
                "SELECT COALESCE(SUM(balance), 0) FROM users"
            )
            total_meowney = (await cursor.fetchone())[0]

            cursor = await db.execute(
                "SELECT COALESCE(SUM(total_won), 0), "
                "COALESCE(SUM(total_lost), 0) FROM users"
            )
            row = await cursor.fetchone()
            total_won, total_lost = row[0], row[1]

            cursor = await db.execute(
                "SELECT COUNT(*) FROM transactions"
            )
            tx_count = (await cursor.fetchone())[0]

            return {
                "user_count": user_count,
                "total_meowney": total_meowney,
                "total_won": total_won,
                "total_lost": total_lost,
                "tx_count": tx_count,
            }
    except Exception as exc:
        logger.exception("Failed to get global stats")
        raise DatabaseError(
            f"get_global_stats failed: {exc}"
        ) from exc


async def purge_user(
    db_path: str, user_id: int
) -> tuple[int, int]:
    """Delete a user and all their transactions, return row counts."""
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM transactions "
                "WHERE user_id = ?",
                (user_id,),
            )
            tx_rows = (await cursor.fetchone())[0]

            cursor = await db.execute(
                "SELECT COUNT(*) FROM users WHERE user_id = ?",
                (user_id,),
            )
            user_rows = (await cursor.fetchone())[0]

            await db.execute(
                "DELETE FROM transactions WHERE user_id = ?",
                (user_id,),
            )
            await db.execute(
                "DELETE FROM users WHERE user_id = ?",
                (user_id,),
            )
            await db.commit()
            return user_rows, tx_rows
    except Exception as exc:
        logger.exception("Failed to purge user %s", user_id)
        raise DatabaseError(
            f"purge_user failed: {exc}"
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
