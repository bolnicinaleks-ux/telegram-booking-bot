# Telegram Booking Bot

<p align="center"><img src="docs/demo.gif" width="320" alt="Demo: booking an appointment"></p>

🇷🇺 [Русская версия](README.md) · The demo GIF shows the Russian UI; set `BOT_LANG=en` for English.

aiogram 3 · SQLite (aiosqlite) · Docker

An appointment booking bot for small businesses: salons, barbershops, tutors, clinics, repair services.

## Features

**Client**
- Booking flow: service → date → free time slot → name → phone (share-contact button or typed) → confirmation
- Free slots are calculated from working hours, breaks, service duration and existing bookings
- “My bookings”: view and cancel
- Reminder N minutes before the visit
- Name and phone are pre-filled from the previous booking

**Admin**
- A notification for every new booking and cancellation; one-tap cancellation (the client is notified)
- `/today`, `/tomorrow`, `/day 05.11` — schedule for a day
- `/services`, `/addservice Name | minutes | price`, `/delservice ID`

**Reliability**
- No double booking: the overlap check and the insert run in one `BEGIN IMMEDIATE` transaction
- The slot is re-checked on confirmation; outdated buttons are handled
- Limit of active bookings per client
- A client can't cancel someone else's booking by forging button data

## Demo mode

`DEMO_MODE=1` is for showing the bot to potential clients. After booking, the user also gets a copy of the owner's card with a working cancel button — for their own booking only. Admin commands and other people's bookings stay inaccessible.

## Language

`BOT_LANG=ru` (default) or `BOT_LANG=en` switches the whole interface: buttons, messages, dates and price format (`CURRENCY=$` → `$1,200`). The language applies to the whole bot instance — run a separate instance with its own token for each language. Source strings are written in Russian and wrapped in `_()`; translations live in `bot/locales/en.py`, and `tests/test_i18n.py` makes sure none are missing.

## Run

```bash
cp .env.example .env   # set BOT_TOKEN, ADMIN_IDS, BOT_LANG=en
```

Docker:
```bash
docker compose up -d --build
```

Without Docker (Python 3.11+):
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m bot
```

The database is created in `data/bot.db` and seeded with three demo services on first start.

## Settings (`.env`)

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | Token from @BotFather |
| `ADMIN_IDS` | — | Comma-separated admin Telegram IDs |
| `BOT_LANG` | `ru` | Interface language: `ru` or `en` |
| `TIMEZONE` | `Asia/Almaty` | Business time zone |
| `CURRENCY` | `₸` | Currency symbol |
| `WORK_START` / `WORK_END` | `10:00` / `20:00` | Working hours |
| `BREAKS` | — | Breaks: `13:00-14:00,17:00-17:15` |
| `WORK_DAYS` | `1,2,3,4,5,6` | Working days (1 = Mon) |
| `SLOT_STEP_MINUTES` | `30` | Slot grid step |
| `DAYS_AHEAD` | `14` | How many days ahead booking is open |
| `MIN_LEAD_MINUTES` | `60` | Minimum time before a booking starts |
| `REMIND_BEFORE_MINUTES` | `120` | Reminder (0 — off) |
| `MAX_ACTIVE_PER_USER` | `3` | Active bookings limit per client |
| `DEMO_MODE` | `0` | Demo mode for showing to clients |

## Structure

```
bot/
  __main__.py      entry point, Dispatcher setup
  config.py        settings from .env
  i18n.py          _() translation function, BOT_LANG
  locales/en.py    English translations
  db.py            SQLite schema and queries
  slots.py         free slot calculation
  keyboards.py     keyboards and CallbackData
  states.py        booking FSM states
  reminders.py     background reminders
  notify.py        notifications
  utils.py         formatting, phone, time
  handlers/
    client.py      client flow
    admin.py       admin commands
tests/             end-to-end tests without Telegram
```

## Tests

```bash
python -m tests.test_flow   # full scenario (Russian UI)
python -m tests.test_en     # English UI: scenario + no Cyrillic in any message or button
python -m tests.test_i18n   # every string is wrapped in _() and translated
```
