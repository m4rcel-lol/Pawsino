"""Leveling commands — level card, XP leaderboard, game-win XP grants."""

import io
import logging
from typing import TYPE_CHECKING

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
    build_embed,
    level_from_xp,
    xp_for_level,
)

if TYPE_CHECKING:
    from main import PawsinoBot

logger = logging.getLogger(__name__)

# Card rendering constants
CARD_WIDTH = 934
CARD_HEIGHT = 282
BAR_X = 270
BAR_Y = 200
BAR_WIDTH = 620
BAR_HEIGHT = 40
BAR_RADIUS = 20
BG_COLOR = (30, 30, 46)
BAR_BG = (60, 60, 80)
BAR_FILL = (114, 137, 218)
TEXT_COLOR = (255, 255, 255)
SUBTEXT_COLOR = (180, 180, 200)
ACCENT_COLOR = (245, 196, 15)

# Whether Pillow is available for card rendering
_HAS_PIL = False
try:
    from PIL import Image, ImageDraw, ImageFont  # noqa: F401
    _HAS_PIL = True
except ImportError:
    pass


def _render_level_card(
    username: str,
    level: int,
    xp: int,
    xp_next: int,
    rank: int,
    avatar_bytes: bytes | None = None,
) -> io.BytesIO:
    """Render an Arcane-style level card and return PNG bytes."""
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Try to load a nicer font, fall back to default
    try:
        font_large = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28
        )
        font_medium = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22
        )
        font_small = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18
        )
    except (OSError, IOError):
        font_large = ImageFont.load_default()
        font_medium = font_large
        font_small = font_large

    # Rounded rectangle background
    draw.rounded_rectangle(
        [0, 0, CARD_WIDTH - 1, CARD_HEIGHT - 1],
        radius=20, fill=BG_COLOR, outline=(60, 60, 80), width=3,
    )

    # Avatar circle area
    avatar_size = 160
    avatar_x, avatar_y = 40, 60
    if avatar_bytes:
        try:
            av_img = Image.open(io.BytesIO(avatar_bytes)).resize(
                (avatar_size, avatar_size)
            )
            # Create circular mask
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse(
                [0, 0, avatar_size, avatar_size], fill=255
            )
            img.paste(av_img, (avatar_x, avatar_y), mask)
        except Exception:
            # Draw placeholder circle
            draw.ellipse(
                [avatar_x, avatar_y,
                 avatar_x + avatar_size, avatar_y + avatar_size],
                fill=(80, 80, 100),
            )
    else:
        draw.ellipse(
            [avatar_x, avatar_y,
             avatar_x + avatar_size, avatar_y + avatar_size],
            fill=(80, 80, 100),
        )

    # Username
    draw.text(
        (BAR_X, 60), username, fill=TEXT_COLOR, font=font_large,
    )
    draw.text(
        (BAR_X, 95), f"@{username}", fill=SUBTEXT_COLOR,
        font=font_small,
    )

    # Rank and Level badges
    draw.text(
        (BAR_X, 130), f"RANK #{rank}", fill=ACCENT_COLOR,
        font=font_medium,
    )
    draw.text(
        (BAR_X + 200, 130), f"LEVEL {level}", fill=ACCENT_COLOR,
        font=font_medium,
    )

    # XP progress text
    xp_text = f"{xp:,} / {xp_next:,} XP"
    # Right-align XP text
    bbox = draw.textbbox((0, 0), xp_text, font=font_small)
    text_w = bbox[2] - bbox[0]
    draw.text(
        (BAR_X + BAR_WIDTH - text_w, BAR_Y - 25),
        xp_text, fill=SUBTEXT_COLOR, font=font_small,
    )

    # Progress bar background
    draw.rounded_rectangle(
        [BAR_X, BAR_Y, BAR_X + BAR_WIDTH, BAR_Y + BAR_HEIGHT],
        radius=BAR_RADIUS, fill=BAR_BG,
    )

    # Progress bar fill
    if xp_next > 0:
        progress = min(xp / xp_next, 1.0)
    else:
        progress = 1.0
    fill_width = max(int(BAR_WIDTH * progress), BAR_RADIUS * 2)
    if progress > 0:
        draw.rounded_rectangle(
            [BAR_X, BAR_Y,
             BAR_X + fill_width, BAR_Y + BAR_HEIGHT],
            radius=BAR_RADIUS, fill=BAR_FILL,
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


class Leveling(commands.Cog):
    """Leveling system for Pawsino."""

    def __init__(self, bot: "PawsinoBot") -> None:
        super().__init__()
        self.bot = bot

    async def grant_xp(
        self,
        guild_id: int,
        user_id: int,
        base_xp: int,
        member: discord.Member | None = None,
        channel: discord.abc.Messageable | None = None,
    ) -> int | None:
        """Grant XP (with boost) and handle level-up. Return new level
        if leveled up, else None."""
        settings = await self.bot.get_guild_settings(guild_id)
        boost = 0.0
        if settings:
            boost = settings.get("xp_boost", 0.0)
        xp_gain = int(base_xp * (1 + boost / 100))
        if xp_gain < 1:
            xp_gain = 1

        data = await db.get_user_xp(
            config.DATABASE_PATH, guild_id, user_id
        )
        old_level = data["level"]
        new_xp = data["xp"] + xp_gain
        new_level = level_from_xp(new_xp)

        await db.add_user_xp(
            config.DATABASE_PATH, guild_id, user_id,
            xp_gain, new_level,
        )

        # Assign new level role if leveled up
        if new_level > old_level and member:
            role_id = await db.get_level_role(
                config.DATABASE_PATH, guild_id, new_level
            )
            if role_id:
                guild = member.guild
                role = guild.get_role(role_id)
                if role:
                    try:
                        await member.add_roles(role)
                    except discord.Forbidden:
                        pass
                    # Announce the level-up
                    if channel:
                        try:
                            embed = build_embed(
                                title="🎉 Level Up!",
                                description=(
                                    f"{member.mention} has reached "
                                    f"**Level {new_level}** and earned "
                                    f"the {role.mention} role!"
                                ),
                                color=COLOR_GOLD,
                            )
                            await channel.send(embed=embed)
                        except discord.Forbidden:
                            pass
            return new_level
        return None

    @app_commands.command(
        name="level",
        description="Check your or another user's level and XP",
    )
    @app_commands.describe(
        user="The user to check (defaults to you)",
    )
    async def level_cmd(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
    ) -> None:
        """Display an Arcane-style level card."""
        if not interaction.guild:
            return
        await interaction.response.defer()
        try:
            target = user or interaction.user
            data = await db.get_user_xp(
                config.DATABASE_PATH,
                interaction.guild.id,
                target.id,
            )
            current_level = data["level"]
            current_xp = data["xp"]
            if current_level < config.MAX_LEVEL:
                next_level_xp = xp_for_level(current_level + 1)
            else:
                next_level_xp = current_xp  # Maxed out

            # Calculate rank
            lb = await db.get_xp_leaderboard(
                config.DATABASE_PATH,
                interaction.guild.id,
                limit=9999,
            )
            rank = 1
            for entry in lb:
                if entry["user_id"] == target.id:
                    break
                rank += 1

            if _HAS_PIL:
                # Download avatar
                avatar_bytes: bytes | None = None
                try:
                    avatar_bytes = await target.display_avatar.read()
                except Exception:
                    pass

                buf = _render_level_card(
                    username=target.display_name,
                    level=current_level,
                    xp=current_xp,
                    xp_next=next_level_xp,
                    rank=rank,
                    avatar_bytes=avatar_bytes,
                )
                file = discord.File(buf, filename="level_card.png")
                await interaction.followup.send(file=file)
            else:
                # Fallback embed if Pillow is not installed
                progress = (
                    f"{current_xp:,} / {next_level_xp:,} XP"
                    if current_level < config.MAX_LEVEL
                    else f"{current_xp:,} XP (MAX)"
                )
                bar_len = 20
                filled = int(
                    (current_xp / next_level_xp * bar_len)
                    if next_level_xp > 0 else bar_len
                )
                bar = "█" * filled + "░" * (bar_len - filled)

                embed = build_embed(
                    title=f"🏅 {target.display_name}'s Level",
                    color=COLOR_GOLD,
                    thumbnail_url=target.display_avatar.url,
                    fields=[
                        ("Level", str(current_level), True),
                        ("Rank", f"#{rank}", True),
                        ("XP", progress, True),
                        ("Progress", f"`{bar}`", False),
                    ],
                )
                await interaction.followup.send(embed=embed)
        except Exception:
            logger.exception("Error in /level")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="xp_leaderboard",
        description="View the top users by XP in this server",
    )
    async def xp_leaderboard(
        self, interaction: discord.Interaction
    ) -> None:
        """Display the XP leaderboard."""
        if not interaction.guild:
            return
        try:
            top = await db.get_xp_leaderboard(
                config.DATABASE_PATH,
                interaction.guild.id,
                limit=10,
            )
            if not top:
                embed = build_embed(
                    title="🏆 XP Leaderboard",
                    description="No leveling data yet!",
                    color=COLOR_GOLD,
                )
                await interaction.response.send_message(embed=embed)
                return

            lines: list[str] = []
            for i, entry in enumerate(top, 1):
                uid = entry["user_id"]
                lines.append(
                    f"#{i} · <@{uid}> — Level **{entry['level']}** "
                    f"({entry['xp']:,} XP)"
                )

            embed = build_embed(
                title="🏆 XP Leaderboard",
                description="\n".join(lines),
                color=COLOR_GOLD,
            )
            await interaction.response.send_message(embed=embed)
        except Exception:
            logger.exception("Error in /xp_leaderboard")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    """Load the Leveling cog."""
    await bot.add_cog(Leveling(bot))
