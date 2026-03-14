"""Pawsino utilities — embeds, formatting, cooldowns, access control."""

from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands

import config

COLOR_SUCCESS: int = 0x2ECC71
COLOR_ERROR: int = 0xE74C3C
COLOR_INFO: int = 0x3498DB
COLOR_GOLD: int = 0xF1C40F
COLOR_WARNING: int = 0xE67E22


class AdminOnly(app_commands.CheckFailure):
    """Raised when a non-admin invokes an admin-only command."""


class UserBlacklisted(app_commands.CheckFailure):
    """Raised when a blacklisted user invokes a command."""


class WrongChannel(app_commands.CheckFailure):
    """Raised when a command is used outside allowed channels."""


def build_embed(
    title: str,
    description: str = "",
    color: int = COLOR_INFO,
    fields: list[tuple[str, str, bool]] | None = None,
    thumbnail_url: str | None = None,
    image_url: str | None = None,
) -> discord.Embed:
    """Create a styled Pawsino embed with footer and timestamp."""
    embed = discord.Embed(
        title=title, description=description, color=color
    )
    embed.set_footer(
        text="🐾 Pawsino | GitHub: m4rcel-lol · Discord: m5rcels"
    )
    embed.timestamp = discord.utils.utcnow()
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    if image_url:
        embed.set_image(url=image_url)
    return embed


def format_meowney(amount: int) -> str:
    """Format an integer as '1,234 <emoji> Meowney'."""
    return f"{amount:,} {config.CURRENCY_EMOJI} Meowney"


def remaining_cooldown(
    last_claimed: str | None, cooldown_hours: int
) -> timedelta | None:
    """Return remaining cooldown or None if ready to claim."""
    if not last_claimed:
        return None
    last_dt = datetime.fromisoformat(last_claimed).replace(
        tzinfo=timezone.utc
    )
    next_dt = last_dt + timedelta(hours=cooldown_hours)
    now = datetime.now(timezone.utc)
    if now < next_dt:
        return next_dt - now
    return None


def format_remaining(td: timedelta) -> str:
    """Format a timedelta as 'Xh Ym Zs'."""
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def xp_for_level(level: int) -> int:
    """Return cumulative XP required to reach *level*."""
    return int(config.BASE_XP_PER_LEVEL * level * (1 + level * 0.1))


def level_from_xp(xp: int) -> int:
    """Return the current level for a given XP total."""
    lvl = 0
    while lvl < config.MAX_LEVEL and xp >= xp_for_level(lvl + 1):
        lvl += 1
    return lvl


def is_admin() -> app_commands.check:
    """App-command check: user must be in ADMIN_IDS."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id not in config.ADMIN_IDS:
            raise AdminOnly(
                "This command is restricted to Pawsino administrators."
            )
        return True
    return app_commands.check(predicate)


def is_superuser() -> app_commands.check:
    """App-command check: user must be the superuser."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id != config.SUPERUSER_ID:
            raise AdminOnly(
                "This command is restricted to Pawsino administrators."
            )
        return True
    return app_commands.check(predicate)
