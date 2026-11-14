"""Команды мастера: мастер с указанным Telegram ID видит своё расписание."""
from datetime import timedelta
from html import escape

from aiogram import Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import Message

from bot.config import Config
from bot.db import Database
from bot.i18n import _
from bot.utils import booking_card, fmt_day_long, now_local


class IsMaster(BaseFilter):
    """Пропускает активного мастера и передаёт его в обработчик как `master`."""

    async def __call__(self, message: Message, db: Database) -> bool | dict:
        if message.from_user is None:
            return False
        master = await db.master_by_tg(message.from_user.id)
        return {"master": master} if master is not None else False


router = Router(name="master")


@router.message(Command("schedule"), IsMaster())  # Command первым: без лишних запросов к БД
async def cmd_schedule(message: Message, master, db: Database, cfg: Config) -> None:
    today = now_local(cfg).date()
    parts = [_("<b>Ваше расписание, {name}</b>", name=escape(master["name"]))]
    for day in (today, today + timedelta(days=1)):
        rows = await db.bookings_on(day, master["id"])
        title = f"<b>{fmt_day_long(day)}</b>"
        if rows:
            cards = "\n\n".join(booking_card(r, cfg.currency, with_client=True, with_master=False) for r in rows)
            parts.append(title + _(" · записей: {n}", n=len(rows)) + "\n\n" + cards)
        else:
            parts.append(f"{title}\n{_('Записей нет.')}")
    await message.answer("\n\n".join(parts))
