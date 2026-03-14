"""Setup command — configure channels, blacklist role, and leveling roles."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
import db
from utils import (
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_WARNING,
    build_embed,
    is_admin,
)

logger = logging.getLogger(__name__)


class Setup(commands.Cog):
    """Server setup commands for Pawsino."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    @app_commands.command(
        name="setup",
        description="Configure Pawsino for this server",
    )
    @app_commands.describe(
        channel="Channel where Pawsino commands are allowed "
                "(leave empty to allow all)",
        auto_create_blacklist="Automatically create a blacklist role?",
        blacklist_role="Existing role to use as blacklist "
                       "(only if auto_create is No)",
        create_level_roles="Create 100 leveling roles? "
                           "(takes a moment)",
    )
    @app_commands.choices(
        auto_create_blacklist=[
            app_commands.Choice(name="Yes", value="yes"),
            app_commands.Choice(name="No", value="no"),
        ],
        create_level_roles=[
            app_commands.Choice(name="Yes", value="yes"),
            app_commands.Choice(name="No", value="no"),
        ],
    )
    @is_admin()
    async def setup_cmd(
        self,
        interaction: discord.Interaction,
        auto_create_blacklist: app_commands.Choice[str],
        create_level_roles: app_commands.Choice[str],
        channel: discord.TextChannel | None = None,
        blacklist_role: discord.Role | None = None,
    ) -> None:
        """Run the Pawsino server setup."""
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        try:
            guild = interaction.guild
            status_lines: list[str] = []

            # ----- Allowed channels -----
            allowed_channels_str: str | None = None
            if channel:
                allowed_channels_str = str(channel.id)
                status_lines.append(
                    f"✅ Commands restricted to {channel.mention}"
                )
            else:
                status_lines.append(
                    "✅ Commands allowed in all channels"
                )

            # ----- Blacklist role -----
            bl_role_id: int | None = None
            if auto_create_blacklist.value == "yes":
                bl_role = await guild.create_role(
                    name="Pawsino Blacklisted",
                    color=discord.Color.dark_grey(),
                    reason="Pawsino setup: auto-created blacklist role",
                )
                bl_role_id = bl_role.id
                status_lines.append(
                    f"✅ Created blacklist role: {bl_role.mention}"
                )
            elif blacklist_role:
                bl_role_id = blacklist_role.id
                status_lines.append(
                    f"✅ Using blacklist role: {blacklist_role.mention}"
                )
            else:
                status_lines.append(
                    "⚠️ No blacklist role configured"
                )

            # ----- Preserve existing XP boost -----
            existing = await db.get_guild_settings(
                config.DATABASE_PATH, guild.id
            )
            xp_boost = existing["xp_boost"] if existing else 0.0

            # ----- Save settings -----
            await db.save_guild_settings(
                config.DATABASE_PATH,
                guild.id,
                allowed_channels=allowed_channels_str,
                blacklist_role_id=bl_role_id,
                xp_boost=xp_boost,
                setup_done=1,
            )
            self.bot.invalidate_guild_cache(guild.id)

            # ----- Level roles -----
            if create_level_roles.value == "yes":
                status_lines.append(
                    "⏳ Creating 100 leveling roles (this may take"
                    " a moment)..."
                )
                # Send interim status
                embed = build_embed(
                    title="⚙️ Pawsino Setup",
                    description="\n".join(status_lines),
                    color=COLOR_INFO,
                )
                await interaction.followup.send(
                    embed=embed, ephemeral=True
                )

                created = 0
                max_lvl = min(
                    config.MAX_LEVEL, len(config.LEVEL_ROLE_NAMES)
                )
                for lvl in range(1, max_lvl + 1):
                    name = (
                        f"Level {lvl} - "
                        f"{config.LEVEL_ROLE_NAMES[lvl - 1]}"
                    )
                    try:
                        role = await guild.create_role(
                            name=name,
                            reason="Pawsino setup: leveling role",
                        )
                        await db.save_level_role(
                            config.DATABASE_PATH,
                            guild.id,
                            lvl,
                            role.id,
                        )
                        created += 1
                    except discord.HTTPException as exc:
                        logger.warning(
                            "Failed to create role for level %d: %s",
                            lvl, exc,
                        )
                        break

                status_lines[-1] = (
                    f"✅ Created **{created}** leveling roles"
                )
            else:
                status_lines.append(
                    "ℹ️ Leveling roles were not created"
                )

            await db.log_admin_action(
                config.DATABASE_PATH,
                interaction.user.id,
                "setup",
                details={
                    "guild_id": guild.id,
                    "blacklist_role_id": bl_role_id,
                    "allowed_channels": allowed_channels_str,
                },
            )

            embed = build_embed(
                title="✅ Pawsino Setup Complete",
                description="\n".join(status_lines),
                color=COLOR_SUCCESS,
            )
            await interaction.followup.send(
                embed=embed, ephemeral=True
            )

        except discord.Forbidden:
            embed = build_embed(
                title="❌ Missing Permissions",
                description=(
                    "Pawsino needs **Manage Roles** permission to "
                    "create roles."
                ),
                color=COLOR_ERROR,
            )
            await interaction.followup.send(
                embed=embed, ephemeral=True
            )
        except Exception:
            logger.exception("Error in /setup")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong during setup.",
                color=COLOR_ERROR,
            )
            await interaction.followup.send(
                embed=embed, ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    """Load the Setup cog."""
    await bot.add_cog(Setup(bot))
