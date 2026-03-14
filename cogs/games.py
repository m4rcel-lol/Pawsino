"""Gambling commands — coinflip, dice, slots, blackjack, roulette."""

import logging
import random

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
)

logger = logging.getLogger(__name__)

SLOT_SYMBOLS: list[tuple[str, str, int, float]] = [
    ("Cherry", "🍒", 30, 3),
    ("Lemon", "🍋", 25, 2),
    ("Orange", "🍊", 20, 4),
    ("Plum", "🍇", 15, 5),
    ("Bell", "🔔", 7, 10),
    ("Diamond", "💎", 2, 25),
    ("Seven", "7️⃣", 1, 50),
]
SLOT_EMOJIS = [s[1] for s in SLOT_SYMBOLS]
SLOT_WEIGHTS = [s[2] for s in SLOT_SYMBOLS]
FRUIT_EMOJIS = {"🍒", "🍋", "🍊", "🍇"}

RED_NUMBERS: set[int] = {
    1, 3, 5, 7, 9, 12, 14, 16, 18,
    19, 21, 23, 25, 27, 30, 32, 34, 36,
}

VALID_ROULETTE_SPACES: list[str] = (
    [str(i) for i in range(37)]
    + ["red", "black", "odd", "even", "low", "high"]
    + ["dozen1", "dozen2", "dozen3"]
)

DICE_EMOJI = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]

CARD_SUITS = ["♠", "♥", "♦", "♣"]
CARD_RANKS = [
    "A", "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "J", "Q", "K",
]


def _card_value(rank: str) -> int:
    """Return the blackjack value of a card rank."""
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)


def _hand_value(hand: list[tuple[str, str]]) -> int:
    """Compute best blackjack hand value (soft ace logic)."""
    total = sum(_card_value(r) for r, _ in hand)
    aces = sum(1 for r, _ in hand if r == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def _format_hand(hand: list[tuple[str, str]]) -> str:
    """Format a hand as a readable string."""
    return "  ".join(f"{r}{s}" for r, s in hand)


def _new_deck() -> list[tuple[str, str]]:
    """Create and shuffle a standard 52-card deck."""
    deck = [(r, s) for s in CARD_SUITS for r in CARD_RANKS]
    random.shuffle(deck)
    return deck


async def _validate_bet(
    interaction: discord.Interaction, bet: int
) -> bool:
    """Validate bet amount; send error embed if invalid."""
    if bet < config.MIN_BET:
        embed = build_embed(
            title="❌ Invalid Bet",
            description=(
                f"Bet must be at least {config.MIN_BET} 🪙."
            ),
            color=COLOR_ERROR,
        )
        await interaction.response.send_message(
            embed=embed, ephemeral=True
        )
        return False
    if bet > config.MAX_BET:
        embed = build_embed(
            title="❌ Invalid Bet",
            description=(
                f"Bet cannot exceed {config.MAX_BET} 🪙."
            ),
            color=COLOR_ERROR,
        )
        await interaction.response.send_message(
            embed=embed, ephemeral=True
        )
        return False
    bal = await db.get_balance(config.DATABASE_PATH, interaction.user.id)
    if bet > bal:
        embed = build_embed(
            title="❌ Insufficient Funds",
            description=(
                f"You only have {bal} 🪙. "
                f"You can't bet {bet}."
            ),
            color=COLOR_ERROR,
        )
        await interaction.response.send_message(
            embed=embed, ephemeral=True
        )
        return False
    return True


class BlackjackView(discord.ui.View):
    """Interactive blackjack game view."""

    def __init__(
        self,
        cog: "Games",
        user_id: int,
        bet: int,
        deck: list[tuple[str, str]],
        player_hand: list[tuple[str, str]],
        dealer_hand: list[tuple[str, str]],
    ) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet
        self.deck = deck
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.resolved = False

    async def interaction_check(
        self, interaction: discord.Interaction
    ) -> bool:
        """Only allow the original user to interact."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                embed=build_embed(
                    title="❌ Not Your Game",
                    description="This isn't your blackjack game.",
                    color=COLOR_ERROR,
                ),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        """Auto-stand on timeout."""
        if not self.resolved:
            await self._resolve_stand(None)

    def _build_game_embed(
        self, reveal_dealer: bool = False, result: str = ""
    ) -> discord.Embed:
        """Build the blackjack game state embed."""
        player_val = _hand_value(self.player_hand)
        if reveal_dealer:
            dealer_str = _format_hand(self.dealer_hand)
            dealer_val = _hand_value(self.dealer_hand)
            dealer_display = f"{dealer_str} (Value: {dealer_val})"
        else:
            shown = f"{self.dealer_hand[0][0]}{self.dealer_hand[0][1]}"
            dealer_display = f"{shown}  🂠 (Value: ?)"

        player_str = _format_hand(self.player_hand)
        title = "🃏 Blackjack"
        desc = result if result else "Hit or Stand?"
        color = COLOR_GOLD if not result else (
            COLOR_SUCCESS if "win" in result.lower()
            or "blackjack" in result.lower()
            else COLOR_ERROR if "bust" in result.lower()
            or "lose" in result.lower()
            else 0x95A5A6
        )
        return build_embed(
            title=title,
            description=desc,
            color=color,
            fields=[
                (
                    "Your Hand",
                    f"{player_str} (Value: {player_val})",
                    False,
                ),
                ("Dealer's Hand", dealer_display, False),
                ("Bet", format_meowney(self.bet), True),
            ],
        )

    async def _resolve_stand(
        self, interaction: discord.Interaction | None
    ) -> None:
        """Resolve the game after standing."""
        if self.resolved:
            return
        self.resolved = True

        while _hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())

        player_val = _hand_value(self.player_hand)
        dealer_val = _hand_value(self.dealer_hand)

        if dealer_val > 21:
            result = "Dealer busts! You win!"
            new_bal = await db.update_balance(
                config.DATABASE_PATH, self.user_id,
                self.bet, "blackjack",
            )
        elif player_val > dealer_val:
            result = "You win!"
            new_bal = await db.update_balance(
                config.DATABASE_PATH, self.user_id,
                self.bet, "blackjack",
            )
        elif player_val == dealer_val:
            result = "Push! Bet refunded."
            new_bal = await db.update_balance(
                config.DATABASE_PATH, self.user_id,
                self.bet, "blackjack",
            )
        else:
            result = "You lose!"
            new_bal = await db.get_balance(
                config.DATABASE_PATH, self.user_id
            )

        embed = self._build_game_embed(reveal_dealer=True, result=result)
        embed.add_field(
            name="New Balance", value=format_meowney(new_bal), inline=True
        )

        for child in self.children:
            child.disabled = True  # type: ignore[union-attr]

        if interaction:
            await interaction.response.edit_message(
                embed=embed, view=self
            )
        else:
            try:
                msg = self.message  # type: ignore[attr-defined]
                await msg.edit(embed=embed, view=self)
            except Exception:
                logger.exception("Failed to edit blackjack on timeout")

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,  # type: ignore[type-arg]
    ) -> None:
        """Draw a card."""
        self.player_hand.append(self.deck.pop())
        player_val = _hand_value(self.player_hand)

        if player_val > 21:
            self.resolved = True
            result = "Bust! You lose!"
            new_bal = await db.get_balance(
                config.DATABASE_PATH, self.user_id
            )
            embed = self._build_game_embed(
                reveal_dealer=True, result=result
            )
            embed.add_field(
                name="New Balance",
                value=format_meowney(new_bal),
                inline=True,
            )
            for child in self.children:
                child.disabled = True  # type: ignore[union-attr]
            await interaction.response.edit_message(
                embed=embed, view=self
            )
            self.stop()
        else:
            embed = self._build_game_embed()
            await interaction.response.edit_message(
                embed=embed, view=self
            )

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,  # type: ignore[type-arg]
    ) -> None:
        """Stand and let the dealer play."""
        await self._resolve_stand(interaction)
        self.stop()


class Games(commands.Cog):
    """Gambling commands for Pawsino."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    @app_commands.command(
        name="coinflip",
        description="Flip a coin and bet on the outcome",
    )
    @app_commands.describe(bet="Amount to bet", choice="Heads or tails")
    @app_commands.choices(
        choice=[
            app_commands.Choice(name="Heads", value="heads"),
            app_commands.Choice(name="Tails", value="tails"),
        ]
    )
    async def coinflip(
        self,
        interaction: discord.Interaction,
        bet: int,
        choice: app_commands.Choice[str],
    ) -> None:
        """Flip a coin."""
        try:
            if not await _validate_bet(interaction, bet):
                return
            result = random.choice(["heads", "tails"])
            won = choice.value == result

            if won:
                new_bal = await db.update_balance(
                    config.DATABASE_PATH, interaction.user.id,
                    bet, "coinflip",
                )
                outcome = f"You won {format_meowney(bet)}!"
                color = COLOR_SUCCESS
            else:
                new_bal = await db.update_balance(
                    config.DATABASE_PATH, interaction.user.id,
                    -bet, "coinflip",
                )
                outcome = f"You lost {format_meowney(bet)}."
                color = COLOR_ERROR

            emoji = "🪙" if result == "heads" else "🪙"
            embed = build_embed(
                title=f"{emoji} Coinflip",
                description=outcome,
                color=color,
                fields=[
                    ("Result", result.capitalize(), True),
                    ("Your Choice", choice.value.capitalize(), True),
                    ("New Balance", format_meowney(new_bal), False),
                ],
            )
            await interaction.response.send_message(embed=embed)
        except Exception:
            logger.exception("Error in /coinflip")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="dice",
        description="Roll a die and predict the outcome",
    )
    @app_commands.describe(
        bet="Amount to bet",
        prediction="Your prediction (1-6)",
    )
    async def dice(
        self,
        interaction: discord.Interaction,
        bet: int,
        prediction: app_commands.Range[int, 1, 6],
    ) -> None:
        """Roll a die."""
        try:
            if not await _validate_bet(interaction, bet):
                return
            result = random.randint(1, 6)
            won = prediction == result

            if won:
                winnings = bet * 5
                new_bal = await db.update_balance(
                    config.DATABASE_PATH, interaction.user.id,
                    winnings, "dice",
                )
                outcome = f"You won {format_meowney(winnings)}!"
                color = COLOR_SUCCESS
            else:
                new_bal = await db.update_balance(
                    config.DATABASE_PATH, interaction.user.id,
                    -bet, "dice",
                )
                outcome = f"You lost {format_meowney(bet)}."
                color = COLOR_ERROR

            embed = build_embed(
                title="🎲 Dice Roll",
                description=outcome,
                color=color,
                fields=[
                    (
                        "Result",
                        f"{DICE_EMOJI[result - 1]} ({result})",
                        True,
                    ),
                    ("Your Prediction", str(prediction), True),
                    ("New Balance", format_meowney(new_bal), False),
                ],
            )
            await interaction.response.send_message(embed=embed)
        except Exception:
            logger.exception("Error in /dice")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="slots", description="Spin the slot machine"
    )
    @app_commands.describe(bet="Amount to bet")
    async def slots(
        self,
        interaction: discord.Interaction,
        bet: int,
    ) -> None:
        """Spin the slot machine."""
        try:
            if not await _validate_bet(interaction, bet):
                return

            reels = random.choices(
                SLOT_EMOJIS, weights=SLOT_WEIGHTS, k=3
            )
            display = f"```\n[ {reels[0]} | {reels[1]} | {reels[2]} ]\n```"

            payout = 0.0
            if reels[0] == reels[1] == reels[2]:
                for name, emoji, weight, mult in SLOT_SYMBOLS:
                    if emoji == reels[0]:
                        payout = mult
                        break
            elif (
                reels[0] in FRUIT_EMOJIS
                and reels[1] in FRUIT_EMOJIS
                and reels[2] in FRUIT_EMOJIS
            ):
                payout = 1.5
            elif (
                reels[0] == reels[1]
                or reels[1] == reels[2]
                or reels[0] == reels[2]
            ):
                payout = 0.5

            net = int(payout * bet) - bet
            if net > 0:
                new_bal = await db.update_balance(
                    config.DATABASE_PATH, interaction.user.id,
                    net, "slots",
                )
                outcome = f"You won {format_meowney(net)}!"
                color = COLOR_SUCCESS
            elif net == 0 and payout > 0:
                new_bal = await db.get_balance(
                    config.DATABASE_PATH, interaction.user.id
                )
                outcome = "Break even!"
                color = 0x95A5A6
            else:
                loss = bet if payout == 0 else bet - int(payout * bet)
                new_bal = await db.update_balance(
                    config.DATABASE_PATH, interaction.user.id,
                    -loss, "slots",
                )
                outcome = f"You lost {format_meowney(loss)}."
                color = COLOR_ERROR

            is_jackpot = (
                reels[0] == reels[1] == reels[2]
                and reels[0] == "7️⃣"
            )
            title = "🎰 JACKPOT!" if is_jackpot else "🎰 Slots"
            if is_jackpot:
                color = COLOR_GOLD

            embed = build_embed(
                title=title,
                description=f"{display}\n{outcome}",
                color=color,
                fields=[
                    ("New Balance", format_meowney(new_bal), False),
                ],
            )
            await interaction.response.send_message(embed=embed)
        except Exception:
            logger.exception("Error in /slots")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="blackjack", description="Play a hand of blackjack"
    )
    @app_commands.describe(bet="Amount to bet")
    async def blackjack(
        self,
        interaction: discord.Interaction,
        bet: int,
    ) -> None:
        """Play blackjack with interactive buttons."""
        try:
            if not await _validate_bet(interaction, bet):
                return

            await db.update_balance(
                config.DATABASE_PATH, interaction.user.id,
                -bet, "blackjack",
            )

            deck = _new_deck()
            player_hand = [deck.pop(), deck.pop()]
            dealer_hand = [deck.pop(), deck.pop()]

            view = BlackjackView(
                cog=self,
                user_id=interaction.user.id,
                bet=bet,
                deck=deck,
                player_hand=player_hand,
                dealer_hand=dealer_hand,
            )

            player_val = _hand_value(player_hand)
            if player_val == 21:
                view.resolved = True
                winnings = int(bet * 2.5)
                new_bal = await db.update_balance(
                    config.DATABASE_PATH, interaction.user.id,
                    winnings, "blackjack",
                )
                embed = view._build_game_embed(
                    reveal_dealer=True,
                    result="🎉 Blackjack! You win!",
                )
                embed.add_field(
                    name="New Balance",
                    value=format_meowney(new_bal),
                    inline=True,
                )
                for child in view.children:
                    child.disabled = True  # type: ignore[union-attr]
                await interaction.response.send_message(
                    embed=embed, view=view
                )
            else:
                embed = view._build_game_embed()
                await interaction.response.send_message(
                    embed=embed, view=view
                )
        except Exception:
            logger.exception("Error in /blackjack")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

    @app_commands.command(
        name="roulette",
        description="Spin the roulette wheel",
    )
    @app_commands.describe(
        bet="Amount to bet",
        space="Where to place your bet",
    )
    async def roulette(
        self,
        interaction: discord.Interaction,
        bet: int,
        space: str,
    ) -> None:
        """Spin the roulette wheel."""
        try:
            if not await _validate_bet(interaction, bet):
                return

            space = space.lower().strip()
            if space not in VALID_ROULETTE_SPACES:
                valid_list = ", ".join(
                    f"`{s}`" for s in VALID_ROULETTE_SPACES
                )
                embed = build_embed(
                    title="❌ Invalid Space",
                    description=(
                        f"Valid spaces: {valid_list}"
                    ),
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
                return

            result = random.randint(0, 36)
            if result == 0:
                color_emoji = "🟢"
                result_color = "green"
            elif result in RED_NUMBERS:
                color_emoji = "🔴"
                result_color = "red"
            else:
                color_emoji = "⚫"
                result_color = "black"

            won = False
            net_payout = 0

            if space.isdigit():
                if int(space) == result:
                    won = True
                    net_payout = bet * 35
            elif space == "red":
                if result in RED_NUMBERS:
                    won = True
                    net_payout = bet
            elif space == "black":
                if result != 0 and result not in RED_NUMBERS:
                    won = True
                    net_payout = bet
            elif space == "odd":
                if result != 0 and result % 2 == 1:
                    won = True
                    net_payout = bet
            elif space == "even":
                if result != 0 and result % 2 == 0:
                    won = True
                    net_payout = bet
            elif space == "low":
                if 1 <= result <= 18:
                    won = True
                    net_payout = bet
            elif space == "high":
                if 19 <= result <= 36:
                    won = True
                    net_payout = bet
            elif space == "dozen1":
                if 1 <= result <= 12:
                    won = True
                    net_payout = bet * 2
            elif space == "dozen2":
                if 13 <= result <= 24:
                    won = True
                    net_payout = bet * 2
            elif space == "dozen3":
                if 25 <= result <= 36:
                    won = True
                    net_payout = bet * 2

            if won:
                new_bal = await db.update_balance(
                    config.DATABASE_PATH, interaction.user.id,
                    net_payout, "roulette",
                )
                outcome = f"You won {format_meowney(net_payout)}!"
                embed_color = COLOR_SUCCESS
            else:
                new_bal = await db.update_balance(
                    config.DATABASE_PATH, interaction.user.id,
                    -bet, "roulette",
                )
                outcome = f"You lost {format_meowney(bet)}."
                embed_color = COLOR_ERROR

            embed = build_embed(
                title="🎡 Roulette",
                description=outcome,
                color=embed_color,
                fields=[
                    (
                        "Result",
                        f"{color_emoji} {result} ({result_color})",
                        True,
                    ),
                    ("Your Bet", space, True),
                    ("New Balance", format_meowney(new_bal), False),
                ],
            )
            await interaction.response.send_message(embed=embed)
        except Exception:
            logger.exception("Error in /roulette")
            embed = build_embed(
                title="❌ Error",
                description="Something went wrong.",
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    """Load the Games cog."""
    await bot.add_cog(Games(bot))
