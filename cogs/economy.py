"""Economy commands — balance, daily, weekly, monthly, leaderboard, transfer, bank, work, rob."""

import logging
import random
import time

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

WORK_JOBS: list[tuple[str, str]] = [
    ("🐟 Fisher", "You caught some fish and sold them at the market"),
    ("📦 Delivery Driver", "You delivered packages around town"),
    ("🧹 Janitor", "You cleaned the office building spotless"),
    ("👨‍🍳 Chef", "You cooked meals at the local restaurant"),
    ("🌾 Farmer", "You harvested crops on the farm"),
    ("🔧 Mechanic", "You fixed up a car at the garage"),
    ("🎨 Artist", "You sold a painting at the art fair"),
    ("📰 Newspaper Boy", "You delivered the morning papers"),
    ("🐕 Dog Walker", "You walked dogs around the neighborhood"),
    ("💻 Programmer", "You wrote some code for a client"),
    ("🎸 Street Musician", "You played music on the street corner"),
    ("🧑‍🏫 Tutor", "You tutored students after school"),
    ("🛒 Cashier", "You worked a shift at the grocery store"),
    ("📮 Mail Carrier", "You delivered mail on your route"),
    ("🧑‍🔬 Lab Assistant", "You helped run experiments in the lab"),
]


class Economy(commands.Cog):
    """Economy commands for Pawsino."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        # Track work uses per user: {user_id: [timestamp, ...]}
        self._work_uses: dict[int, list[float]] = {}

    @app_commands.command(
        name="balance",
        description="Check a user's Meowney balance",
    )
    @app_commands.describe(
        user="The user whose balance to check (defaults to you)",
    )
    async def balance(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
    ) -> None:
        """Show balance, total won/lost, and win rate."""
        try:
            target = user or interaction.user
            user_data = await db.get_or_create_user(
                config.DATABASE_PATH, target.id
            )
            total_games = user_data["total_won"] + user_data["total_lost"]
            if total_games > 0:
                win_rate = (
                    f"{user_data['total_won'] / total_games * 100:.1f}%"
                )
            else:
                win_rate = "N/A"

            embed = build_embed(
                title=f"💰 {target.display_name}'s Balance",
                color=COLOR_GOLD,
                thumbnail_url=target.display_avatar.url,
                fields=[
                    (
                        "Wallet",
                        format_meowney(user_data["balance"]),
                        True,
                    ),
                    (
                        "Bank",
                        format_meowney(user_data.get("bank", 0)),
                        True,
                    ),
                    (
                        "Total Won",
                        format_meowney(user_data["total_won"]),
                        True,
                    ),
                    (
                        "Total Lost",
                        format_meowney(user_data["total_lost"]),
                        True,
                    ),
                    ("Win Rate", win_rate, True),
                ],
            )
            await interaction.response.send_message(embed=embed)
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
                lines.append(
                    f"#{i} · <@{uid}> — "
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
                    f"\n#{rank} · <@{invoker_id}>"
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
        return await db.get_user_rank(config.DATABASE_PATH, user_id)

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

            sender_new, receiver_new = await db.transfer_meowney(
                config.DATABASE_PATH,
                interaction.user.id,
                user.id,
                amount,
            )

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

    @app_commands.command(
        name="deposit",
        description="Deposit Meowney from your wallet into the bank",
    )
    @app_commands.describe(
        amount="Amount of Meowney to deposit",
    )
    async def deposit_cmd(
        self,
        interaction: discord.Interaction,
        amount: int,
    ) -> None:
        """Deposit Meowney into the bank for safekeeping."""
        try:
            if amount <= 0:
                embed = build_embed(
                    title="❌ Invalid Amount",
                    description="Deposit amount must be positive.",
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            wallet_bal = await db.get_balance(
                config.DATABASE_PATH, interaction.user.id
            )
            if amount > wallet_bal:
                embed = build_embed(
                    title="❌ Insufficient Funds",
                    description=(
                        f"You only have "
                        f"{format_meowney(wallet_bal)} in your wallet."
                    ),
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            new_wallet, new_bank = await db.deposit(
                config.DATABASE_PATH, interaction.user.id, amount
            )
            embed = build_embed(
                title="🏦 Deposit Successful",
                description=(
                    f"Deposited {format_meowney(amount)} into your bank!"
                ),
                color=COLOR_SUCCESS,
                fields=[
                    ("Wallet", format_meowney(new_wallet), True),
                    ("Bank", format_meowney(new_bank), True),
                ],
            )
            await interaction.response.send_message(embed=embed)
        except Exception:
            logger.exception("Error in /deposit")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="withdraw",
        description="Withdraw Meowney from the bank to your wallet",
    )
    @app_commands.describe(
        amount="Amount of Meowney to withdraw",
    )
    async def withdraw_cmd(
        self,
        interaction: discord.Interaction,
        amount: int,
    ) -> None:
        """Withdraw Meowney from the bank."""
        try:
            if amount <= 0:
                embed = build_embed(
                    title="❌ Invalid Amount",
                    description="Withdrawal amount must be positive.",
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            bank_bal = await db.get_bank_balance(
                config.DATABASE_PATH, interaction.user.id
            )
            if amount > bank_bal:
                embed = build_embed(
                    title="❌ Insufficient Bank Funds",
                    description=(
                        f"You only have "
                        f"{format_meowney(bank_bal)} in your bank."
                    ),
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            new_wallet, new_bank = await db.withdraw(
                config.DATABASE_PATH, interaction.user.id, amount
            )
            embed = build_embed(
                title="🏦 Withdrawal Successful",
                description=(
                    f"Withdrew {format_meowney(amount)} from your bank!"
                ),
                color=COLOR_SUCCESS,
                fields=[
                    ("Wallet", format_meowney(new_wallet), True),
                    ("Bank", format_meowney(new_bank), True),
                ],
            )
            await interaction.response.send_message(embed=embed)
        except Exception:
            logger.exception("Error in /withdraw")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    def _check_work_cooldown(self, user_id: int) -> float | None:
        """Return remaining cooldown seconds or None if ready."""
        uses = self._work_uses.get(user_id, [])
        now = time.time()
        # Remove entries older than the cooldown window
        uses = [t for t in uses if now - t < config.WORK_COOLDOWN_SECONDS]
        self._work_uses[user_id] = uses
        if len(uses) >= config.WORK_USES_BEFORE_COOLDOWN:
            oldest = uses[0]
            remaining = config.WORK_COOLDOWN_SECONDS - (now - oldest)
            if remaining > 0:
                return remaining
            # Cooldown expired, clear and allow
            self._work_uses[user_id] = []
        return None

    def _record_work_use(self, user_id: int) -> None:
        """Record a work command use."""
        if user_id not in self._work_uses:
            self._work_uses[user_id] = []
        self._work_uses[user_id].append(time.time())

    @app_commands.command(
        name="work",
        description="Do a random job to earn some Meowney",
    )
    async def work(self, interaction: discord.Interaction) -> None:
        """Work a random job for Meowney."""
        try:
            remaining = self._check_work_cooldown(interaction.user.id)
            if remaining is not None:
                embed = build_embed(
                    title="⏳ Work Cooldown",
                    description=(
                        f"You're tired! Rest for **{int(remaining)}s** "
                        f"before working again."
                    ),
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            job_title, job_desc = random.choice(WORK_JOBS)
            reward = random.randint(
                config.WORK_MIN_REWARD, config.WORK_MAX_REWARD
            )
            new_bal = await db.update_balance(
                config.DATABASE_PATH,
                interaction.user.id,
                reward,
                "work",
            )
            self._record_work_use(interaction.user.id)

            uses = len(self._work_uses.get(interaction.user.id, []))
            remaining_uses = (
                config.WORK_USES_BEFORE_COOLDOWN - uses
            )
            cooldown_note = ""
            if remaining_uses <= 0:
                cooldown_note = (
                    f"\n⏳ You need to rest for "
                    f"**{config.WORK_COOLDOWN_SECONDS}s** before "
                    f"working again!"
                )
            else:
                cooldown_note = (
                    f"\n🔄 **{remaining_uses}** uses left before "
                    f"cooldown."
                )

            embed = build_embed(
                title=f"{job_title}",
                description=(
                    f"{job_desc} and earned "
                    f"{format_meowney(reward)}!{cooldown_note}"
                ),
                color=COLOR_SUCCESS,
                fields=[
                    ("New Balance", format_meowney(new_bal), False),
                ],
            )
            await interaction.response.send_message(embed=embed)
        except Exception:
            logger.exception("Error in /work")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="rob",
        description="Attempt to rob another user's wallet",
    )
    @app_commands.describe(
        user="The user to rob",
    )
    async def rob(
        self,
        interaction: discord.Interaction,
        user: discord.User,
    ) -> None:
        """Attempt to rob another user. 50% chance of success."""
        try:
            if user.id == interaction.user.id:
                embed = build_embed(
                    title="❌ Invalid Target",
                    description="You can't rob yourself!",
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            if user.bot:
                embed = build_embed(
                    title="❌ Invalid Target",
                    description="You can't rob a bot!",
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            robber_bal = await db.get_balance(
                config.DATABASE_PATH, interaction.user.id
            )
            victim_bal = await db.get_balance(
                config.DATABASE_PATH, user.id
            )

            if victim_bal <= 0:
                embed = build_embed(
                    title="❌ Not Worth It",
                    description=(
                        f"{user.mention} has no Meowney in their wallet "
                        f"to rob!"
                    ),
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            success = random.random() < config.ROB_SUCCESS_CHANCE

            if success:
                # Steal 10-30% of victim's wallet
                steal_pct = random.uniform(0.10, 0.30)
                stolen = max(1, int(victim_bal * steal_pct))
                await db.update_balance(
                    config.DATABASE_PATH, user.id,
                    -stolen, "rob_victim",
                )
                new_bal = await db.update_balance(
                    config.DATABASE_PATH, interaction.user.id,
                    stolen, "rob_success",
                )
                embed = build_embed(
                    title="💰 Robbery Successful!",
                    description=(
                        f"You robbed {format_meowney(stolen)} from "
                        f"{user.mention}!"
                    ),
                    color=COLOR_SUCCESS,
                    fields=[
                        (
                            "Your New Balance",
                            format_meowney(new_bal),
                            False,
                        ),
                    ],
                )
            else:
                # Fail: lose 3% of your own balance
                penalty = max(1, int(
                    robber_bal * config.ROB_FAIL_PENALTY_PERCENT
                ))
                new_bal = await db.update_balance(
                    config.DATABASE_PATH, interaction.user.id,
                    -penalty, "rob_fail",
                )
                embed = build_embed(
                    title="🚔 Robbery Failed!",
                    description=(
                        f"You got caught trying to rob {user.mention}! "
                        f"You paid {format_meowney(penalty)} in fines."
                    ),
                    color=COLOR_ERROR,
                    fields=[
                        (
                            "Your New Balance",
                            format_meowney(new_bal),
                            False,
                        ),
                    ],
                )

            await interaction.response.send_message(embed=embed)
        except Exception:
            logger.exception("Error in /rob")
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
