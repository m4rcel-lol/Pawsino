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
