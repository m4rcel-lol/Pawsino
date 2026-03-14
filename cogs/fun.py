"""Fun commands — cat pictures."""

import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import COLOR_ERROR, COLOR_INFO, build_embed

logger = logging.getLogger(__name__)


class Fun(commands.Cog):
    """Fun commands for Pawsino."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    @app_commands.command(
        name="cat", description="Get a random cat picture"
    )
    async def cat(self, interaction: discord.Interaction) -> None:
        """Fetch and display a random cat image."""
        await interaction.response.defer()
        try:
            async with self.bot.session.get(
                config.CAT_API_URL,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    raise ValueError(
                        f"Cat API returned status {resp.status}"
                    )
                data = await resp.json()
                cat_id = data.get("_id")
                if not cat_id:
                    raise ValueError("No _id in cat API response")
                image_url = f"https://cataas.com/cat/{cat_id}"

            embed = build_embed(
                title="🐱 Random Cat",
                color=COLOR_INFO,
                image_url=image_url,
            )
            await interaction.followup.send(embed=embed)
        except Exception:
            logger.exception("Error in /cat")
            embed = build_embed(
                title="❌ Error",
                description=(
                    "Could not fetch a cat picture. Try again later!"
                ),
                color=COLOR_ERROR,
            )
            await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Load the Fun cog."""
    await bot.add_cog(Fun(bot))
