"""Economy commands — balance, daily, weekly, monthly, leaderboard, transfer."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
import db
from utils import (
    COLOR_ERROR,
    COLOR_GOLD,
    COLOR_SUCCESS,
    build_embed,
    format_meowney,
    format_remaining,
    remaining_cooldown,
)

logger = logging.getLogger(__name__)


class Economy(commands.Cog):
    """Economy commands for Pawsino."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    @app_commands.command(
        name="balance", description="Check your Meowney balance"
    )
    async def balance(self, interaction: discord.Interaction) -> None:
        """Show balance, total won/lost, and win rate."""
        try:
            user = await db.get_or_create_user(
                config.DATABASE_PATH, interaction.user.id
            )
            total_games = user["total_won"] + user["total_lost"]
            if total_games > 0:
                win_rate = f"{user['total_won'] / total_games * 100:.1f}%"
            else:
                win_rate = "N/A"

            embed = build_embed(
                title=f"💰 {interaction.user.display_name}'s Balance",
                color=COLOR_GOLD,
                fields=[
                    ("Balance", format_meowney(user["balance"]), False),
                    ("Total Won", format_meowney(user["total_won"]), True),
                    (
                        "Total Lost",
                        format_meowney(user["total_lost"]),
                        True,
                    ),
                    ("Win Rate", win_rate, True),
                ],
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
        except Exception:
            logger.exception("Error in /balance")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    async def _claim_reward(
        self,
        interaction: discord.Interaction,
        reward_type: str,
        reward_amount: int,
        cooldown_hours: int,
        cooldown_key: str,
    ) -> None:
        """Shared logic for daily/weekly/monthly claims."""
        try:
            cooldowns = await db.get_cooldowns(
                config.DATABASE_PATH, interaction.user.id
            )
            remaining = remaining_cooldown(
                cooldowns[cooldown_key], cooldown_hours
            )
            if remaining:
                embed = build_embed(
                    title=f"⏳ {reward_type.capitalize()} Cooldown",
                    description=(
                        f"You can claim your {reward_type} reward "
                        f"in **{format_remaining(remaining)}**."
                    ),
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            new_bal = await db.update_balance(
                config.DATABASE_PATH,
                interaction.user.id,
                reward_amount,
                reward_type,
            )
            await db.update_cooldown(
                config.DATABASE_PATH,
                interaction.user.id,
                reward_type,
            )
            embed = build_embed(
                title=f"🎁 {reward_type.capitalize()} Reward",
                description=(
                    f"You claimed {format_meowney(reward_amount)}!"
                ),
                color=COLOR_SUCCESS,
                fields=[
                    ("New Balance", format_meowney(new_bal), False),
                ],
            )
            await interaction.response.send_message(embed=embed)
        except Exception:
            logger.exception("Error in /%s", reward_type)
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="daily", description="Claim your daily Meowney reward"
    )
    async def daily(self, interaction: discord.Interaction) -> None:
        """Claim daily reward."""
        await self._claim_reward(
            interaction,
            "daily",
            config.DAILY_REWARD,
            config.DAILY_COOLDOWN_HOURS,
            "last_daily",
        )

    @app_commands.command(
        name="weekly", description="Claim your weekly Meowney reward"
    )
    async def weekly(self, interaction: discord.Interaction) -> None:
        """Claim weekly reward."""
        await self._claim_reward(
            interaction,
            "weekly",
            config.WEEKLY_REWARD,
            config.WEEKLY_COOLDOWN_HOURS,
            "last_weekly",
        )

    @app_commands.command(
        name="monthly",
        description="Claim your monthly Meowney reward",
    )
    async def monthly(self, interaction: discord.Interaction) -> None:
        """Claim monthly reward."""
        await self._claim_reward(
            interaction,
            "monthly",
            config.MONTHLY_REWARD,
            config.MONTHLY_COOLDOWN_HOURS,
            "last_monthly",
        )

    @app_commands.command(
        name="leaderboard",
        description="Top 10 richest Pawsino players",
    )
    async def leaderboard(
        self, interaction: discord.Interaction
    ) -> None:
        """Show the top 10 users by balance."""
        try:
            top = await db.get_leaderboard(config.DATABASE_PATH, 10)
            if not top:
                embed = build_embed(
                    title="🏆 Leaderboard",
                    description="No players yet!",
                    color=COLOR_GOLD,
                )
                await interaction.response.send_message(embed=embed)
                return

            lines: list[str] = []
            for i, entry in enumerate(top, 1):
                uid = entry["user_id"]
                user_obj = self.bot.get_user(uid)
                name = (
                    f"@{user_obj.display_name}"
                    if user_obj
                    else f"User {uid}"
                )
                lines.append(
                    f"#{i} · {name} — "
                    f"{format_meowney(entry['balance'])}"
                )

            invoker_id = interaction.user.id
            top_ids = [e["user_id"] for e in top]
            if invoker_id not in top_ids:
                invoker_user = await db.get_or_create_user(
                    config.DATABASE_PATH, invoker_id
                )
                rank = await self._get_user_rank(invoker_id)
                lines.append(
                    f"\n#{rank} · @{interaction.user.display_name}"
                    f" — {format_meowney(invoker_user['balance'])}"
                )

            embed = build_embed(
                title="🏆 Leaderboard",
                description="\n".join(lines),
                color=COLOR_GOLD,
            )
            await interaction.response.send_message(embed=embed)
        except Exception:
            logger.exception("Error in /leaderboard")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    async def _get_user_rank(self, user_id: int) -> int:
        """Return the 1-based rank of a user by balance."""
        import aiosqlite

        async with aiosqlite.connect(config.DATABASE_PATH) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM users WHERE balance > "
                "(SELECT balance FROM users WHERE user_id = ?)",
                (user_id,),
            )
            row = await cursor.fetchone()
            return (row[0] if row else 0) + 1

    @app_commands.command(
        name="transfer",
        description="Transfer Meowney to another user",
    )
    @app_commands.describe(
        user="The user to send Meowney to",
        amount="Amount of Meowney to transfer",
    )
    async def transfer(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        amount: int,
    ) -> None:
        """Transfer Meowney to another user."""
        try:
            if amount <= 0:
                embed = build_embed(
                    title="❌ Invalid Amount",
                    description="Transfer amount must be positive.",
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            if user.id == interaction.user.id:
                embed = build_embed(
                    title="❌ Invalid Transfer",
                    description="You can't transfer to yourself.",
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            if user.bot:
                embed = build_embed(
                    title="❌ Invalid Transfer",
                    description="You can't transfer to a bot.",
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            sender_bal = await db.get_balance(
                config.DATABASE_PATH, interaction.user.id
            )
            if amount > sender_bal:
                embed = build_embed(
                    title="❌ Insufficient Funds",
                    description=(
                        f"You only have "
                        f"{format_meowney(sender_bal)}."
                    ),
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            import aiosqlite

            async with aiosqlite.connect(
                config.DATABASE_PATH
            ) as conn:
                await db.get_or_create_user(
                    config.DATABASE_PATH, user.id
                )

                cursor = await conn.execute(
                    "SELECT balance FROM users WHERE user_id = ?",
                    (interaction.user.id,),
                )
                row = await cursor.fetchone()
                sender_new = row[0] - amount

                cursor = await conn.execute(
                    "SELECT balance FROM users WHERE user_id = ?",
                    (user.id,),
                )
                row = await cursor.fetchone()
                receiver_new = row[0] + amount

                await conn.execute(
                    "UPDATE users SET balance = ? WHERE user_id = ?",
                    (sender_new, interaction.user.id),
                )
                await conn.execute(
                    "UPDATE users SET balance = ? WHERE user_id = ?",
                    (receiver_new, user.id),
                )
                await conn.execute(
                    "INSERT INTO transactions "
                    "(user_id, type, amount, balance_after) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        interaction.user.id,
                        "transfer_out",
                        -amount,
                        sender_new,
                    ),
                )
                await conn.execute(
                    "INSERT INTO transactions "
                    "(user_id, type, amount, balance_after) "
                    "VALUES (?, ?, ?, ?)",
                    (user.id, "transfer_in", amount, receiver_new),
                )
                await conn.commit()

            embed = build_embed(
                title="💸 Transfer Complete",
                description=(
                    f"{interaction.user.mention} sent "
                    f"{format_meowney(amount)} to {user.mention}!"
                ),
                color=COLOR_SUCCESS,
                fields=[
                    (
                        f"{interaction.user.display_name}",
                        format_meowney(sender_new),
                        True,
                    ),
                    (
                        f"{user.display_name}",
                        format_meowney(receiver_new),
                        True,
                    ),
                ],
            )
            await interaction.response.send_message(embed=embed)
        except Exception:
            logger.exception("Error in /transfer")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    """Load the Economy cog."""
    await bot.add_cog(Economy(bot))
