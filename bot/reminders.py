import asyncio
import logging
from datetime import timedelta
from html import escape

from aiogram import Bot

from bot.config import Config
from bot.db import Database
from bot.keyboards import BTN_MY
from bot.notify import notify_user
from bot.utils import fmt_dt, now_local, str_to_dt

log = logging.getLogger(__name__)
CHECK_INTERVAL = 60


async def send_due_reminders(bot: Bot, db: Database, cfg: Config) -> int:
    now = now_local(cfg)
    rows = await db.due_reminders(now, now + timedelta(minutes=cfg.remind_before))
    for r in rows:
        await notify_user(
            bot,
            r["user_id"],
            f"⏰ Напоминание: {fmt_dt(str_to_dt(r['starts_at']))} — {escape(r['service_name'])}.\n"
            f"Если не сможете прийти, отмените запись в «{BTN_MY}».",
        )
        await db.mark_reminded(r["id"])
    return len(rows)


async def reminder_loop(bot: Bot, db: Database, cfg: Config) -> None:
    if cfg.remind_before <= 0:
        return
    while True:
        try:
            await send_due_reminders(bot, db, cfg)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Ошибка при отправке напоминаний")
        await asyncio.sleep(CHECK_INTERVAL)
