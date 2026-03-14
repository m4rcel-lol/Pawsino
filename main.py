"""Pawsino — main bot entry point."""

import asyncio
import logging
import os
import signal
import sys

import aiohttp
import discord
from discord.ext import commands

import config
import db
from utils import AdminOnly, COLOR_ERROR, build_embed

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
]


class PawsinoBot(commands.Bot):
    """Custom bot subclass with setup hook and session management."""

    def __init__(self) -> None:
        super().__init__(
            command_prefix=None,
            intents=discord.Intents.default(),
        )
        self.start_time: discord.utils.MISSING = discord.utils.MISSING
        self.session: aiohttp.ClientSession = None  # type: ignore[assignment]

    async def setup_hook(self) -> None:
        """Create HTTP session, init database, load cogs."""
        self.session = aiohttp.ClientSession()
        await db.setup_database(config.DATABASE_PATH)
        for cog in COGS:
            await self.load_extension(cog)
            logger.info("Loaded cog: %s", cog)

    async def on_ready(self) -> None:
        """Log ready status and optionally sync command tree."""
        self.start_time = discord.utils.utcnow()
        logger.info(
            "Logged in as %s (ID: %s) in %d guild(s)",
            self.user, self.user.id if self.user else "?",
            len(self.guilds),
        )
        if os.getenv("SYNC_COMMANDS", "").lower() == "true":
            synced = await self.tree.sync()
            logger.info("Synced %d commands", len(synced))

    async def close(self) -> None:
        """Close HTTP session then the bot."""
        if self.session and not self.session.closed:
            await self.session.close()
        await super().close()


bot = PawsinoBot()


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
