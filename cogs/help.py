"""Help command — lists all available commands."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils import COLOR_INFO, build_embed

logger = logging.getLogger(__name__)


class Help(commands.Cog):
    """Help command for Pawsino."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    @app_commands.command(
        name="help", description="Show all Pawsino commands"
    )
    async def help(self, interaction: discord.Interaction) -> None:
        """Display the help menu."""
        try:
            embed = build_embed(
                title="🐾 Pawsino Help",
                description="Here are all available commands:",
                color=COLOR_INFO,
                fields=[
                    (
                        "💰 Economy",
                        (
                            "`/balance` — Check your Meowney balance\n"
                            "`/daily` — Claim your daily reward\n"
                            "`/weekly` — Claim your weekly reward\n"
                            "`/monthly` — Claim your monthly reward\n"
                            "`/leaderboard` — View the top 10 players\n"
                            "`/transfer` — Send Meowney to another user"
                        ),
                        False,
                    ),
                    (
                        "🎮 Games",
                        (
                            "`/coinflip` — Flip a coin and bet on it\n"
                            "`/dice` — Roll a die and predict the result\n"
                            "`/slots` — Spin the slot machine\n"
                            "`/blackjack` — Play a hand of blackjack\n"
                            "`/roulette` — Spin the roulette wheel"
                        ),
                        False,
                    ),
                    (
                        "🐾 Fun",
                        "`/cat` — Get a random cat picture",
                        False,
                    ),
                ],
            )
            embed.set_footer(
                text=(
                    "All winnings and losses use fake Meowney"
                    " — no real money involved.\n"
                    "🐾 Pawsino | GitHub: m4rcel-lol"
                    " · Discord: m5rcels"
                )
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
        except Exception:
            logger.exception("Error in /help")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=0xE74C3C,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    """Load the Help cog."""
    await bot.add_cog(Help(bot))
