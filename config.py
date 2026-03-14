"""Pawsino configuration — all typed constants loaded from environment."""

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is required.")

DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/pawsino.db")

DAILY_REWARD: int = int(os.getenv("DAILY_REWARD", "500"))
WEEKLY_REWARD: int = int(os.getenv("WEEKLY_REWARD", "2000"))
MONTHLY_REWARD: int = int(os.getenv("MONTHLY_REWARD", "5000"))
STARTING_BALANCE: int = int(os.getenv("STARTING_BALANCE", "1000"))
MAX_BET: int = int(os.getenv("MAX_BET", "50000"))
MIN_BET: int = int(os.getenv("MIN_BET", "1"))

DAILY_COOLDOWN_HOURS: int = int(os.getenv("DAILY_COOLDOWN_HOURS", "24"))
WEEKLY_COOLDOWN_HOURS: int = int(os.getenv("WEEKLY_COOLDOWN_HOURS", "168"))
MONTHLY_COOLDOWN_HOURS: int = int(os.getenv("MONTHLY_COOLDOWN_HOURS", "720"))

CAT_API_URL: str = os.getenv(
    "CAT_API_URL", "https://cataas.com/cat?json=true"
)

CURRENCY_EMOJI: str = "<:meowney:1482477098256961617>"

WORK_MIN_REWARD: int = int(os.getenv("WORK_MIN_REWARD", "50"))
WORK_MAX_REWARD: int = int(os.getenv("WORK_MAX_REWARD", "300"))
WORK_COOLDOWN_SECONDS: int = int(os.getenv("WORK_COOLDOWN_SECONDS", "30"))
WORK_USES_BEFORE_COOLDOWN: int = int(
    os.getenv("WORK_USES_BEFORE_COOLDOWN", "5")
)

ROB_SUCCESS_CHANCE: float = 0.5
ROB_FAIL_PENALTY_PERCENT: float = 0.03

SUPERUSER_ID: int = 1435161291365814325

_admin_ids_raw: str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: set[int] = {
    int(uid.strip())
    for uid in _admin_ids_raw.split(",")
    if uid.strip().isdigit()
}
ADMIN_IDS.add(SUPERUSER_ID)

# ---------------------------------------------------------------------------
# Pawsino thumbnail shown on balance / inspect embeds (top-right corner)
# ---------------------------------------------------------------------------
PAWSINO_THUMBNAIL_URL: str = os.getenv(
    "PAWSINO_THUMBNAIL_URL",
    "https://cdn.discordapp.com/emojis/1482477098256961617.webp?size=128",
)

# ---------------------------------------------------------------------------
# Leveling system
# ---------------------------------------------------------------------------
BASE_XP_PER_LEVEL: int = int(os.getenv("BASE_XP_PER_LEVEL", "100"))
XP_PER_GAME_WIN: int = int(os.getenv("XP_PER_GAME_WIN", "15"))
MAX_LEVEL: int = 100
MAX_XP_BOOST: float = 4.5

LEVEL_ROLE_NAMES: list[str] = [
    "Tiny Meow", "Whisker Cat", "Purr Kitten", "Meow Scout", "Cat Pounce",
    "Purr Sprout", "Meow Napper", "Cat Whisper", "Purr Tumble", "Meow Dash",
    "Cat Prowler", "Purr Snuggle", "Meow Hunter", "Cat Shadow", "Purr Bounce",
    "Meow Drifter", "Cat Chaser", "Purr Spark", "Meow Glider", "Cat Streak",
    "Purr Storm", "Meow Knight", "Cat Striker", "Purr Blaze", "Meow Fang",
    "Cat Ember", "Purr Claw", "Meow Fury", "Cat Thunder", "Purr Mystic",
    "Meow Rogue", "Cat Phantom", "Purr Venom", "Meow Blade", "Cat Wraith",
    "Purr Frost", "Meow Spirit", "Cat Flame", "Purr Saber", "Meow Titan",
    "Cat Vortex", "Purr Hawk", "Meow Serpent", "Cat Bolt", "Purr Feral",
    "Meow Eclipse", "Cat Apex", "Purr Lynx", "Meow Panther", "Cat Jaguar",
    "Purr Cougar", "Meow Leopard", "Cat Ocelot", "Purr Cheetah", "Meow Tigress",
    "Cat Lioness", "Purr Wildcat", "Meow Bobcat", "Cat Caracal", "Purr Serval",
    "Meow Margay", "Cat Kodkod", "Purr Jaguarundi", "Meow Manul", "Cat Rusty",
    "Purr Fishing", "Meow Jungle", "Cat Sand", "Purr Snow", "Meow Cloud",
    "Cat Nebula", "Purr Comet", "Meow Star", "Cat Nova", "Purr Galaxy",
    "Meow Astral", "Cat Cosmic", "Purr Zenith", "Meow Apex", "Cat Oracle",
    "Purr Sage", "Meow Elder", "Cat Ancient", "Purr Mythic", "Meow Legend",
    "Cat Immortal", "Purr Eternal", "Meow Divine", "Cat Celestial", "Purr Ascended",
    "Meow Transcended", "Cat Enlightened", "Purr Awakened", "Meow Exalted", "Cat Sovereign",
    "Purr Emperor", "Meow Overlord", "Cat Almighty", "Purr Infinite", "Meow Omega",
]

assert len(LEVEL_ROLE_NAMES) >= MAX_LEVEL, (
    f"LEVEL_ROLE_NAMES has {len(LEVEL_ROLE_NAMES)} entries "
    f"but MAX_LEVEL is {MAX_LEVEL}"
)
