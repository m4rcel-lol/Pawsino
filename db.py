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
                    bank         INTEGER NOT NULL DEFAULT 0,
                    last_daily   TEXT,
                    last_weekly  TEXT,
                    last_monthly TEXT,
                    total_won    INTEGER NOT NULL DEFAULT 0,
                    total_lost   INTEGER NOT NULL DEFAULT 0,
                    created_at   TEXT NOT NULL
                        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                )
            """)
            # Migrate: add bank column if it doesn't exist yet
            cursor = await db.execute(
                "SELECT COUNT(*) FROM pragma_table_info('users') "
                "WHERE name = 'bank'"
            )
            has_bank = (await cursor.fetchone())[0]
            if not has_bank:
                await db.execute(
                    "ALTER TABLE users ADD COLUMN bank"
                    " INTEGER NOT NULL DEFAULT 0"
                )
                await db.commit()
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
            await db.execute("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id          INTEGER PRIMARY KEY,
                    allowed_channels  TEXT,
                    blacklist_role_id INTEGER,
                    xp_boost          REAL NOT NULL DEFAULT 0.0,
                    setup_done        INTEGER NOT NULL DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS leveling (
                    guild_id   INTEGER NOT NULL,
                    user_id    INTEGER NOT NULL,
                    xp         INTEGER NOT NULL DEFAULT 0,
                    level      INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS level_roles (
                    guild_id INTEGER NOT NULL,
                    level    INTEGER NOT NULL,
                    role_id  INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, level)
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
            if column == "last_daily":
                await db.execute(
                    "UPDATE users SET last_daily = ? "
                    "WHERE user_id = ?",
                    (now, user_id),
                )
            elif column == "last_weekly":
                await db.execute(
                    "UPDATE users SET last_weekly = ? "
                    "WHERE user_id = ?",
                    (now, user_id),
                )
            elif column == "last_monthly":
                await db.execute(
                    "UPDATE users SET last_monthly = ? "
                    "WHERE user_id = ?",
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
            if column == "last_daily":
                await db.execute(
                    "UPDATE users SET last_daily = NULL "
                    "WHERE user_id = ?",
                    (user_id,),
                )
            elif column == "last_weekly":
                await db.execute(
                    "UPDATE users SET last_weekly = NULL "
                    "WHERE user_id = ?",
                    (user_id,),
                )
            elif column == "last_monthly":
                await db.execute(
                    "UPDATE users SET last_monthly = NULL "
                    "WHERE user_id = ?",
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


async def get_bank_balance(db_path: str, user_id: int) -> int:
    """Return the current bank balance for a user."""
    user = await get_or_create_user(db_path, user_id)
    return user.get("bank", 0)


async def deposit(
    db_path: str, user_id: int, amount: int
) -> tuple[int, int]:
    """Move amount from wallet to bank, return (new_wallet, new_bank)."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await get_or_create_user(db_path, user_id)
            cursor = await db.execute(
                "SELECT balance, bank FROM users WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            wallet, bank = row[0], row[1]
            if amount > wallet:
                raise DatabaseError("Insufficient wallet funds")
            new_wallet = wallet - amount
            new_bank = bank + amount
            await db.execute(
                "UPDATE users SET balance = ?, bank = ? "
                "WHERE user_id = ?",
                (new_wallet, new_bank, user_id),
            )
            await db.execute(
                "INSERT INTO transactions "
                "(user_id, type, amount, balance_after) "
                "VALUES (?, ?, ?, ?)",
                (user_id, "deposit", -amount, new_wallet),
            )
            await db.commit()
            return new_wallet, new_bank
    except DatabaseError:
        raise
    except Exception as exc:
        logger.exception("Failed to deposit for user %s", user_id)
        raise DatabaseError(f"deposit failed: {exc}") from exc


async def withdraw(
    db_path: str, user_id: int, amount: int
) -> tuple[int, int]:
    """Move amount from bank to wallet, return (new_wallet, new_bank)."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await get_or_create_user(db_path, user_id)
            cursor = await db.execute(
                "SELECT balance, bank FROM users WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            wallet, bank = row[0], row[1]
            if amount > bank:
                raise DatabaseError("Insufficient bank funds")
            new_wallet = wallet + amount
            new_bank = bank - amount
            await db.execute(
                "UPDATE users SET balance = ?, bank = ? "
                "WHERE user_id = ?",
                (new_wallet, new_bank, user_id),
            )
            await db.execute(
                "INSERT INTO transactions "
                "(user_id, type, amount, balance_after) "
                "VALUES (?, ?, ?, ?)",
                (user_id, "withdraw", amount, new_wallet),
            )
            await db.commit()
            return new_wallet, new_bank
    except DatabaseError:
        raise
    except Exception as exc:
        logger.exception("Failed to withdraw for user %s", user_id)
        raise DatabaseError(f"withdraw failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Guild settings
# ---------------------------------------------------------------------------

async def get_guild_settings(db_path: str, guild_id: int) -> dict | None:
    """Return guild settings or None if not configured."""
    try:
        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM guild_settings WHERE guild_id = ?",
                (guild_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
    except Exception as exc:
        logger.exception("Failed to get guild settings for %s", guild_id)
        raise DatabaseError(
            f"get_guild_settings failed: {exc}"
        ) from exc


async def save_guild_settings(
    db_path: str,
    guild_id: int,
    *,
    allowed_channels: str | None = None,
    blacklist_role_id: int | None = None,
    xp_boost: float = 0.0,
    setup_done: int = 1,
) -> None:
    """Insert or replace guild settings."""
    try:
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO guild_settings "
                "(guild_id, allowed_channels, blacklist_role_id, "
                "xp_boost, setup_done) VALUES (?, ?, ?, ?, ?)",
                (
                    guild_id,
                    allowed_channels,
                    blacklist_role_id,
                    xp_boost,
                    setup_done,
                ),
            )
            await conn.commit()
    except Exception as exc:
        logger.exception("Failed to save guild settings for %s", guild_id)
        raise DatabaseError(
            f"save_guild_settings failed: {exc}"
        ) from exc


async def set_xp_boost(
    db_path: str, guild_id: int, boost: float
) -> None:
    """Update the XP boost for a guild."""
    try:
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                "UPDATE guild_settings SET xp_boost = ? "
                "WHERE guild_id = ?",
                (boost, guild_id),
            )
            await conn.commit()
    except Exception as exc:
        logger.exception("Failed to set xp boost for guild %s", guild_id)
        raise DatabaseError(f"set_xp_boost failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Level roles
# ---------------------------------------------------------------------------

async def save_level_role(
    db_path: str, guild_id: int, level: int, role_id: int
) -> None:
    """Store the role id for a given level in a guild."""
    try:
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO level_roles "
                "(guild_id, level, role_id) VALUES (?, ?, ?)",
                (guild_id, level, role_id),
            )
            await conn.commit()
    except Exception as exc:
        logger.exception("Failed to save level role")
        raise DatabaseError(f"save_level_role failed: {exc}") from exc


async def get_level_role(
    db_path: str, guild_id: int, level: int
) -> int | None:
    """Return the role id for a level or None."""
    try:
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "SELECT role_id FROM level_roles "
                "WHERE guild_id = ? AND level = ?",
                (guild_id, level),
            )
            row = await cursor.fetchone()
            return row[0] if row else None
    except Exception as exc:
        logger.exception("Failed to get level role")
        raise DatabaseError(f"get_level_role failed: {exc}") from exc


async def get_all_level_roles(
    db_path: str, guild_id: int
) -> dict[int, int]:
    """Return {level: role_id} mapping for a guild."""
    try:
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "SELECT level, role_id FROM level_roles "
                "WHERE guild_id = ?",
                (guild_id,),
            )
            rows = await cursor.fetchall()
            return {r[0]: r[1] for r in rows}
    except Exception as exc:
        logger.exception("Failed to get all level roles")
        raise DatabaseError(
            f"get_all_level_roles failed: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Leveling
# ---------------------------------------------------------------------------

async def get_user_xp(
    db_path: str, guild_id: int, user_id: int
) -> dict:
    """Return {xp, level} for user in guild, creating row if absent."""
    try:
        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM leveling "
                "WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            await conn.execute(
                "INSERT INTO leveling (guild_id, user_id) "
                "VALUES (?, ?)",
                (guild_id, user_id),
            )
            await conn.commit()
            return {"guild_id": guild_id, "user_id": user_id,
                    "xp": 0, "level": 0}
    except Exception as exc:
        logger.exception("Failed to get user xp")
        raise DatabaseError(f"get_user_xp failed: {exc}") from exc


async def add_user_xp(
    db_path: str, guild_id: int, user_id: int,
    xp_delta: int, new_level: int,
) -> None:
    """Add xp and set level for a user in a guild."""
    try:
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                "INSERT INTO leveling (guild_id, user_id, xp, level) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
                "xp = xp + ?, level = ?",
                (guild_id, user_id, xp_delta, new_level,
                 xp_delta, new_level),
            )
            await conn.commit()
    except Exception as exc:
        logger.exception("Failed to add user xp")
        raise DatabaseError(f"add_user_xp failed: {exc}") from exc


async def set_user_xp(
    db_path: str, guild_id: int, user_id: int,
    xp: int, level: int,
) -> None:
    """Set absolute xp and level for a user in a guild."""
    try:
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                "INSERT INTO leveling (guild_id, user_id, xp, level) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
                "xp = ?, level = ?",
                (guild_id, user_id, xp, level, xp, level),
            )
            await conn.commit()
    except Exception as exc:
        logger.exception("Failed to set user xp")
        raise DatabaseError(f"set_user_xp failed: {exc}") from exc


async def get_xp_leaderboard(
    db_path: str, guild_id: int, limit: int = 10
) -> list[dict]:
    """Return top users by XP in a guild."""
    try:
        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT user_id, xp, level FROM leveling "
                "WHERE guild_id = ? ORDER BY xp DESC LIMIT ?",
                (guild_id, limit),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.exception("Failed to get xp leaderboard")
        raise DatabaseError(
            f"get_xp_leaderboard failed: {exc}"
        ) from exc
