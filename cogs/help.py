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
                            "`/balance [user]` — Check a Meowney balance\n"
                            "`/daily` — Claim your daily reward\n"
                            "`/weekly` — Claim your weekly reward\n"
                            "`/monthly` — Claim your monthly reward\n"
                            "`/leaderboard` — View the top 10 players\n"
                            "`/transfer` — Send Meowney to another user\n"
                            "`/work` — Do a random job to earn Meowney\n"
                            "`/rob` — Attempt to rob another user"
                        ),
                        False,
                    ),
                    (
                        "🏦 Banking",
                        (
                            "`/deposit` — Deposit Meowney into the bank\n"
                            "`/withdraw` — Withdraw Meowney from the bank"
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
                            "`/roulette` — Spin the roulette wheel\n"
                            "`/crash` — Cash out before the crash!\n"
                            "`/highlow` — Guess higher or lower"
                        ),
                        False,
                    ),
                    (
                        "📊 Leveling",
                        (
                            "`/level [user]` — View your level card\n"
                            "`/xp_leaderboard` — Top users by XP"
                        ),
                        False,
                    ),
                    (
                        "🐾 Fun",
                        "`/cat` — Get a random cat picture",
                        False,
                    ),
                    (
                        "⚙️ Server Setup",
                        "`/setup` — Configure Pawsino for this server",
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
