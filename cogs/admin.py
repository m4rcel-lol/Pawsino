"""Admin commands — balance management, inspection, broadcast, stats."""

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
import db
from utils import (
    COLOR_ERROR,
    COLOR_GOLD,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_WARNING,
    build_embed,
    format_meowney,
    is_admin,
    is_superuser,
)

logger = logging.getLogger(__name__)


class Admin(commands.GroupCog, group_name="admin"):
    """Administrator commands for Pawsino."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    @app_commands.command(
        name="balance_set",
        description="Set a user's balance to an exact amount",
    )
    @app_commands.describe(
        user="Target user", amount="New balance amount"
    )
    @is_admin()
    async def balance_set(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        amount: int,
    ) -> None:
        """Set a user's balance exactly."""
        try:
            if amount < 0 or amount > 2_147_483_647:
                embed = build_embed(
                    title="❌ Invalid Amount",
                    description=(
                        "Amount must be between 0 and 2,147,483,647."
                    ),
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            old_balance = await db.set_balance(
                config.DATABASE_PATH, user.id, amount, "admin_set"
            )

            await db.log_admin_action(
                config.DATABASE_PATH,
                interaction.user.id,
                "balance_set",
                user.id,
                {"old_balance": old_balance, "new_balance": amount},
            )

            embed = build_embed(
                title="✅ Balance Set",
                description=f"Updated {user.mention}'s balance.",
                color=COLOR_SUCCESS,
                fields=[
                    (
                        "Old Balance",
                        format_meowney(old_balance),
                        True,
                    ),
                    ("New Balance", format_meowney(amount), True),
                ],
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
        except Exception:
            logger.exception("Error in /admin balance_set")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="balance_add",
        description="Add or subtract from a user's balance",
    )
    @app_commands.describe(
        user="Target user", amount="Amount to add (negative to subtract)"
    )
    @is_admin()
    async def balance_add(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        amount: int,
    ) -> None:
        """Add or subtract from a user's balance, clamped to 0."""
        try:
            old_balance, new_balance = await db.add_balance(
                config.DATABASE_PATH, user.id, amount, "admin_add"
            )

            await db.log_admin_action(
                config.DATABASE_PATH,
                interaction.user.id,
                "balance_add",
                user.id,
                {"delta": amount, "resulting_balance": new_balance},
            )

            embed = build_embed(
                title="✅ Balance Updated",
                description=f"Updated {user.mention}'s balance.",
                color=COLOR_SUCCESS,
                fields=[
                    ("Delta", f"{amount:+,} {config.CURRENCY_EMOJI}", True),
                    (
                        "Result",
                        format_meowney(new_balance),
                        True,
                    ),
                ],
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
        except Exception:
            logger.exception("Error in /admin balance_add")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="balance_reset",
        description="Reset a user's balance and cooldowns",
    )
    @app_commands.describe(user="Target user")
    @is_admin()
    async def balance_reset(
        self,
        interaction: discord.Interaction,
        user: discord.User,
    ) -> None:
        """Reset user to starting balance and clear cooldowns."""
        try:
            await db.reset_user(
                config.DATABASE_PATH, user.id,
                config.STARTING_BALANCE,
            )

            await db.log_admin_action(
                config.DATABASE_PATH,
                interaction.user.id,
                "balance_reset",
                user.id,
                {
                    "reset_balance": config.STARTING_BALANCE,
                    "cooldowns_cleared": [
                        "daily", "weekly", "monthly"
                    ],
                },
            )

            embed = build_embed(
                title="✅ User Reset",
                description=(
                    f"{user.mention} has been reset to "
                    f"{format_meowney(config.STARTING_BALANCE)} "
                    f"with all cooldowns cleared."
                ),
                color=COLOR_SUCCESS,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
        except Exception:
            logger.exception("Error in /admin balance_reset")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="grant_daily",
        description="Reset a user's daily cooldown",
    )
    @app_commands.describe(user="Target user")
    @is_admin()
    async def grant_daily(
        self,
        interaction: discord.Interaction,
        user: discord.User,
    ) -> None:
        """Clear a user's daily cooldown."""
        try:
            await db.clear_cooldown(
                config.DATABASE_PATH, user.id, "daily"
            )

            await db.log_admin_action(
                config.DATABASE_PATH,
                interaction.user.id,
                "grant_daily",
                user.id,
                {"cooldown_cleared": "daily"},
            )

            embed = build_embed(
                title="✅ Daily Cooldown Reset",
                description=(
                    f"{user.mention}'s daily cooldown has been cleared."
                ),
                color=COLOR_SUCCESS,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
        except Exception:
            logger.exception("Error in /admin grant_daily")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="grant_weekly",
        description="Reset a user's weekly cooldown",
    )
    @app_commands.describe(user="Target user")
    @is_admin()
    async def grant_weekly(
        self,
        interaction: discord.Interaction,
        user: discord.User,
    ) -> None:
        """Clear a user's weekly cooldown."""
        try:
            await db.clear_cooldown(
                config.DATABASE_PATH, user.id, "weekly"
            )

            await db.log_admin_action(
                config.DATABASE_PATH,
                interaction.user.id,
                "grant_weekly",
                user.id,
                {"cooldown_cleared": "weekly"},
            )

            embed = build_embed(
                title="✅ Weekly Cooldown Reset",
                description=(
                    f"{user.mention}'s weekly cooldown has been cleared."
                ),
                color=COLOR_SUCCESS,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
        except Exception:
            logger.exception("Error in /admin grant_weekly")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="grant_monthly",
        description="Reset a user's monthly cooldown",
    )
    @app_commands.describe(user="Target user")
    @is_admin()
    async def grant_monthly(
        self,
        interaction: discord.Interaction,
        user: discord.User,
    ) -> None:
        """Clear a user's monthly cooldown."""
        try:
            await db.clear_cooldown(
                config.DATABASE_PATH, user.id, "monthly"
            )

            await db.log_admin_action(
                config.DATABASE_PATH,
                interaction.user.id,
                "grant_monthly",
                user.id,
                {"cooldown_cleared": "monthly"},
            )

            embed = build_embed(
                title="✅ Monthly Cooldown Reset",
                description=(
                    f"{user.mention}'s monthly cooldown "
                    f"has been cleared."
                ),
                color=COLOR_SUCCESS,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
        except Exception:
            logger.exception("Error in /admin grant_monthly")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="inspect",
        description="View a user's full profile and transactions",
    )
    @app_commands.describe(user="Target user")
    @is_admin()
    async def inspect(
        self,
        interaction: discord.Interaction,
        user: discord.User,
    ) -> None:
        """Show full user profile with recent transactions."""
        try:
            u = await db.get_or_create_user(
                config.DATABASE_PATH, user.id
            )
            total_games = u["total_won"] + u["total_lost"]
            win_rate = (
                f"{u['total_won'] / total_games * 100:.1f}%"
                if total_games > 0 else "N/A"
            )

            cooldown_info = (
                f"Daily: {u['last_daily'] or 'Never'}\n"
                f"Weekly: {u['last_weekly'] or 'Never'}\n"
                f"Monthly: {u['last_monthly'] or 'Never'}"
            )

            txs = await db.get_recent_transactions(
                config.DATABASE_PATH, user.id, 5
            )

            if txs:
                tx_lines = []
                for tx in txs:
                    tx_lines.append(
                        f"{tx['type']:15s} {tx['amount']:>+8d}"
                        f"  bal:{tx['balance_after']:>8d}"
                        f"  {tx['created_at']}"
                    )
                tx_block = "```\n" + "\n".join(tx_lines) + "\n```"
            else:
                tx_block = "No transactions yet."

            await db.log_admin_action(
                config.DATABASE_PATH,
                interaction.user.id,
                "inspect",
                user.id,
                {"inspected_user_id": user.id},
            )

            embed = build_embed(
                title=f"🔍 Inspect: {user.display_name}",
                color=COLOR_INFO,
                fields=[
                    ("Balance", format_meowney(u["balance"]), True),
                    (
                        "Total Won",
                        format_meowney(u["total_won"]),
                        True,
                    ),
                    (
                        "Total Lost",
                        format_meowney(u["total_lost"]),
                        True,
                    ),
                    ("Win Rate", win_rate, True),
                    ("Cooldowns", cooldown_info, False),
                    ("Created At", u["created_at"], True),
                    ("Last 5 Transactions", tx_block, False),
                ],
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
        except Exception:
            logger.exception("Error in /admin inspect")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="broadcast",
        description="Send a public announcement in this channel",
    )
    @app_commands.describe(message="Announcement message (max 2000 chars)")
    @is_admin()
    async def broadcast(
        self,
        interaction: discord.Interaction,
        message: str,
    ) -> None:
        """Send a public announcement embed."""
        try:
            if len(message) > 2000:
                embed = build_embed(
                    title="❌ Too Long",
                    description=(
                        "Broadcast message must be 2000 characters "
                        "or fewer."
                    ),
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            embed = build_embed(
                title="📢 Pawsino Announcement",
                description=message,
                color=COLOR_WARNING,
            )
            embed.set_footer(
                text=(
                    f"Announced by {interaction.user.display_name}"
                    f" · 🐾 Pawsino"
                )
            )
            await interaction.response.send_message(embed=embed)

            await db.log_admin_action(
                config.DATABASE_PATH,
                interaction.user.id,
                "broadcast",
                details={
                    "channel_id": interaction.channel_id,
                    "message": message,
                },
            )
        except Exception:
            logger.exception("Error in /admin broadcast")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="stats",
        description="View global Pawsino statistics",
    )
    @is_admin()
    async def stats(
        self, interaction: discord.Interaction
    ) -> None:
        """Display global bot statistics."""
        try:
            stats = await db.get_global_stats(config.DATABASE_PATH)
            user_count = stats["user_count"]
            total_meowney = stats["total_meowney"]
            total_won = stats["total_won"]
            total_lost = stats["total_lost"]
            tx_count = stats["tx_count"]

            uptime_str = "Unknown"
            if hasattr(self.bot, "start_time") and self.bot.start_time:
                delta = discord.utils.utcnow() - self.bot.start_time
                total_secs = int(delta.total_seconds())
                days, remainder = divmod(total_secs, 86400)
                hours, remainder = divmod(remainder, 3600)
                minutes, seconds = divmod(remainder, 60)
                uptime_str = (
                    f"{days}d {hours}h {minutes}m {seconds}s"
                )

            await db.log_admin_action(
                config.DATABASE_PATH,
                interaction.user.id,
                "stats",
                details={},
            )

            embed = build_embed(
                title="📊 Pawsino Stats",
                color=COLOR_GOLD,
                fields=[
                    ("Total Users", str(user_count), True),
                    (
                        "Meowney in Circulation",
                        format_meowney(total_meowney),
                        True,
                    ),
                    (
                        "All-time Won",
                        format_meowney(total_won),
                        True,
                    ),
                    (
                        "All-time Lost",
                        format_meowney(total_lost),
                        True,
                    ),
                    (
                        "Total Transactions",
                        f"{tx_count:,}",
                        True,
                    ),
                    ("Bot Uptime", uptime_str, True),
                ],
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
        except Exception:
            logger.exception("Error in /admin stats")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="shutdown", description="Shut down the bot (superuser only)"
    )
    @is_superuser()
    async def shutdown(
        self, interaction: discord.Interaction
    ) -> None:
        """Gracefully shut down the bot."""
        try:
            await db.log_admin_action(
                config.DATABASE_PATH,
                interaction.user.id,
                "shutdown",
                details={"reason": "manual_shutdown"},
            )
            logger.critical(
                "Shutdown initiated by %s (%s)",
                interaction.user, interaction.user.id,
            )

            embed = build_embed(
                title="🛑 Shutting Down",
                description="Pawsino is shutting down...",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
            await asyncio.sleep(2)
            await self.bot.close()
        except Exception:
            logger.exception("Error in /admin shutdown")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="purge_user",
        description="Delete a user and all their data (superuser only)",
    )
    @app_commands.describe(user="Target user to purge")
    @is_superuser()
    async def purge_user(
        self,
        interaction: discord.Interaction,
        user: discord.User,
    ) -> None:
        """Delete a user and all their transactions atomically."""
        try:
            user_rows, tx_rows = await db.purge_user(
                config.DATABASE_PATH, user.id
            )

            logger.warning(
                "User %s (%s) purged by %s (%s)",
                user, user.id, interaction.user, interaction.user.id,
            )

            await db.log_admin_action(
                config.DATABASE_PATH,
                interaction.user.id,
                "purge_user",
                user.id,
                {
                    "purged_user_id": user.id,
                    "users_rows": user_rows,
                    "tx_rows": tx_rows,
                },
            )

            embed = build_embed(
                title="🗑️ User Purged",
                description=f"{user.mention} has been purged.",
                color=COLOR_WARNING,
                fields=[
                    ("User Rows Deleted", str(user_rows), True),
                    (
                        "Transaction Rows Deleted",
                        str(tx_rows),
                        True,
                    ),
                ],
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
        except Exception:
            logger.exception("Error in /admin purge_user")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    """Load the Admin cog."""
    await bot.add_cog(Admin(bot))
