"""Pawsino — main bot entry point."""

import asyncio
import logging
import signal
import sys
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands

import config
import db
from utils import (
    AdminOnly,
    UserBlacklisted,
    WrongChannel,
    COLOR_ERROR,
    build_embed,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

COGS = [
    "cogs.economy",
    "cogs.games",
    "cogs.fun",
    "cogs.help",
    "cogs.admin",
    "cogs.setup",
    "cogs.leveling",
]


class PawsinoBot(commands.Bot):
    """Custom bot subclass with setup hook and session management."""

    def __init__(self) -> None:
        super().__init__(
            command_prefix=None,
            intents=discord.Intents.default(),
        )
        self.start_time: datetime | None = None
        self.session: aiohttp.ClientSession = None  # type: ignore[assignment]
        # Cache guild settings to avoid repeated DB reads
        self._guild_settings_cache: dict[int, dict | None] = {}

    async def setup_hook(self) -> None:
        """Create HTTP session, init database, load cogs, sync commands."""
        self.session = aiohttp.ClientSession()
        await db.setup_database(config.DATABASE_PATH)
        for cog in COGS:
            await self.load_extension(cog)
            logger.info("Loaded cog: %s", cog)
        synced = await self.tree.sync()
        logger.info("Synced %d application commands", len(synced))

    async def on_ready(self) -> None:
        """Log ready status."""
        self.start_time = discord.utils.utcnow()
        logger.info(
            "Logged in as %s (ID: %s) in %d guild(s)",
            self.user, self.user.id if self.user else "?",
            len(self.guilds),
        )

    async def close(self) -> None:
        """Close HTTP session then the bot."""
        if self.session and not self.session.closed:
            await self.session.close()
        await super().close()

    async def get_guild_settings(self, guild_id: int) -> dict | None:
        """Return cached guild settings, refreshing from DB if needed."""
        if guild_id not in self._guild_settings_cache:
            self._guild_settings_cache[guild_id] = (
                await db.get_guild_settings(config.DATABASE_PATH, guild_id)
            )
        return self._guild_settings_cache[guild_id]

    def invalidate_guild_cache(self, guild_id: int) -> None:
        """Remove a guild from the settings cache."""
        self._guild_settings_cache.pop(guild_id, None)


bot = PawsinoBot()


@bot.tree.interaction_check
async def global_interaction_check(
    interaction: discord.Interaction,
) -> bool:
    """Run blacklist and channel checks before every command."""
    # Skip checks for DMs
    if not interaction.guild:
        return True

    # Allow admin commands to bypass restrictions
    cmd_name = interaction.command.name if interaction.command else ""
    parent = getattr(interaction.command, "parent", None)
    group_name = parent.name if parent else ""
    if group_name == "admin" or cmd_name == "setup":
        return True

    settings = await bot.get_guild_settings(interaction.guild.id)
    if not settings or not settings.get("setup_done"):
        return True  # Not configured yet — allow all

    # Channel restriction check
    allowed_raw = settings.get("allowed_channels")
    if allowed_raw:
        allowed_ids = {
            int(c) for c in allowed_raw.split(",") if c.strip().isdigit()
        }
        if allowed_ids and interaction.channel_id not in allowed_ids:
            raise WrongChannel(
                "This command can only be used in designated channels."
            )

    # Blacklist role check
    bl_role_id = settings.get("blacklist_role_id")
    if bl_role_id and isinstance(interaction.user, discord.Member):
        if any(r.id == bl_role_id for r in interaction.user.roles):
            raise UserBlacklisted("You are blacklisted from Pawsino.")

    return True


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: discord.app_commands.AppCommandError,
) -> None:
    """Global slash-command error handler."""
    if isinstance(error, AdminOnly):
        logger.warning(
            "Unauthorized admin access: user=%s (%s) guild=%s cmd=%s",
            interaction.user,
            interaction.user.id,
            interaction.guild,
            interaction.command.name if interaction.command else "?",
        )
        embed = build_embed(
            title="🔒 Access Denied",
            description=(
                "This command is restricted to"
                " Pawsino administrators."
            ),
            color=COLOR_ERROR,
        )
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=embed, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
    elif isinstance(error, UserBlacklisted):
        embed = build_embed(
            title="🚫 Blacklisted",
            description="You are blacklisted from using Pawsino.",
            color=COLOR_ERROR,
        )
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=embed, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
    elif isinstance(error, WrongChannel):
        embed = build_embed(
            title="📛 Wrong Channel",
            description=(
                "This command can only be used in designated channels."
            ),
            color=COLOR_ERROR,
        )
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=embed, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
    else:
        logger.exception("Unhandled command error: %s", error)
        embed = build_embed(
            title="❌ Error",
            description="An unexpected error occurred.",
            color=COLOR_ERROR,
        )
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=embed, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )


def _handle_sigterm(*_: object) -> None:
    """Gracefully shut down on SIGTERM."""
    logger.info("Received SIGTERM, shutting down...")
    asyncio.get_event_loop().create_task(bot.close())


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_sigterm)
    bot.run(config.BOT_TOKEN, log_handler=None)
