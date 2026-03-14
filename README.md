# 🐾 Pawsino

Pawsino is an open-source Discord bot that runs a cat-themed casino. Players gamble with **Meowney** (`🪙`) — a completely fake currency. No real money is ever involved. If you're ever bored, come gamble some Meowney!

---

## Prerequisites

- **Docker** and **Docker Compose** installed
- A **Discord Bot Token** — [create one here](https://discord.com/developers/applications)
- Python 3.11+ (only if running without Docker)

---

## Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/m4rcel-lol/Pawsino.git
   cd Pawsino
   ```

2. **Create your `.env` file:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set your `DISCORD_TOKEN`.

3. **Start the bot:**
   ```bash
   docker compose up -d --build
   ```

4. **Sync slash commands** (first run only):
   Set `SYNC_COMMANDS=true` in your `.env`, then restart the bot. Remove it after the first sync.

---

## Commands Reference

### 💰 Economy

| Command | Arguments | Description |
|---|---|---|
| `/balance` | — | Check your Meowney balance, total won/lost, and win rate |
| `/daily` | — | Claim your daily Meowney reward (24h cooldown) |
| `/weekly` | — | Claim your weekly Meowney reward (7d cooldown) |
| `/monthly` | — | Claim your monthly Meowney reward (30d cooldown) |
| `/leaderboard` | — | View the top 10 richest players |
| `/transfer` | `<user> <amount>` | Send Meowney to another user |

### 🎮 Games

| Command | Arguments | Description |
|---|---|---|
| `/coinflip` | `<bet> <choice>` | Flip a coin — choose heads or tails |
| `/dice` | `<bet> <prediction>` | Roll a die — predict the number (1-6, 5× payout) |
| `/slots` | `<bet>` | Spin the slot machine with weighted symbols |
| `/blackjack` | `<bet>` | Play a full interactive hand of blackjack |
| `/roulette` | `<bet> <space>` | Spin the roulette wheel — bet on numbers, colors, or ranges |

### 🐾 Fun

| Command | Arguments | Description |
|---|---|---|
| `/cat` | — | Get a random cat picture |

### 🛡️ Admin

| Command | Permission | Description |
|---|---|---|
| `/admin balance_set <user> <amount>` | Admin | Set a user's balance exactly |
| `/admin balance_add <user> <amount>` | Admin | Add/subtract from a user's balance |
| `/admin balance_reset <user>` | Admin | Reset balance to starting amount and clear cooldowns |
| `/admin grant_daily <user>` | Admin | Clear a user's daily cooldown |
| `/admin grant_weekly <user>` | Admin | Clear a user's weekly cooldown |
| `/admin grant_monthly <user>` | Admin | Clear a user's monthly cooldown |
| `/admin inspect <user>` | Admin | View full profile and last 5 transactions |
| `/admin broadcast <message>` | Admin | Send a public announcement in the current channel |
| `/admin stats` | Admin | View global bot statistics and uptime |
| `/admin shutdown` | Superuser | Gracefully shut down the bot |
| `/admin purge_user <user>` | Superuser | Delete a user and all their data permanently |

---

## Configuration

All configuration is done via environment variables (`.env` file):

| Variable | Default | Description |
|---|---|---|
| `DISCORD_TOKEN` | *Required* | Your Discord bot token |
| `ADMIN_IDS` | `1435161291365814325` | Comma-separated admin user IDs |
| `DATABASE_PATH` | `data/pawsino.db` | Path to the SQLite database |
| `DAILY_REWARD` | `500` | Daily reward amount |
| `WEEKLY_REWARD` | `2000` | Weekly reward amount |
| `MONTHLY_REWARD` | `5000` | Monthly reward amount |
| `STARTING_BALANCE` | `1000` | Balance for new users |
| `MAX_BET` | `50000` | Maximum bet amount |
| `MIN_BET` | `1` | Minimum bet amount |
| `DAILY_COOLDOWN_HOURS` | `24` | Hours between daily claims |
| `WEEKLY_COOLDOWN_HOURS` | `168` | Hours between weekly claims |
| `MONTHLY_COOLDOWN_HOURS` | `720` | Hours between monthly claims |
| `SYNC_COMMANDS` | — | Set to `true` to sync slash commands on startup |

---

## Administrator Guide

### Adding Admins

Add Discord user IDs to the `ADMIN_IDS` environment variable as a comma-separated list:

```env
ADMIN_IDS=1435161291365814325,123456789012345678
```

The **superuser** (`1435161291365814325`) is always included in the admin set and has access to additional destructive commands (`/admin shutdown`, `/admin purge_user`).

### Admin vs Superuser

- **Admin** — Can manage user balances, cooldowns, inspect users, broadcast announcements, and view stats.
- **Superuser** — Has all admin privileges plus the ability to shut down the bot and permanently purge user data.

### Audit Log

All admin actions are logged in the `admin_audit` database table. Query the audit log:

```bash
docker exec -it pawsino_bot sqlite3 /app/data/pawsino.db "SELECT * FROM admin_audit ORDER BY created_at DESC LIMIT 20;"
```

### Security Note

Keep your `.env` file in `.gitignore` — never commit bot tokens or secrets to version control.

---

## Monitoring

View live logs:

```bash
docker logs -f pawsino_bot
```

Logs use structured format: `timestamp [LEVEL] module: message`.

---

## Development without Docker

1. **Create a virtual environment:**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your DISCORD_TOKEN
   ```

4. **Run the bot:**
   ```bash
   python main.py
   ```

---

## Credits

- **GitHub:** [m4rcel-lol](https://github.com/m4rcel-lol)
- **Discord:** m5rcels

---

## Disclaimer

Pawsino uses **fake Meowney currency only**. No real money or gambling is involved. This bot is for entertainment purposes only.
