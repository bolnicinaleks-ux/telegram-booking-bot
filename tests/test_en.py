"""Английская версия (BOT_LANG=en): основной сценарий проходит, и ни одно сообщение или кнопка не содержит кириллицы.

Запуск: python -m tests.test_en
"""
import os

os.environ["BOT_LANG"] = "en"

import asyncio  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402
from dataclasses import replace  # noqa: E402
from datetime import time, timedelta  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from aiogram import Bot  # noqa: E402
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage  # noqa: E402

from bot.__main__ import build_dispatcher  # noqa: E402
from bot.config import Config  # noqa: E402
from bot.db import Database  # noqa: E402
from bot.reminders import send_due_reminders  # noqa: E402
from bot.utils import now_local  # noqa: E402
from tests.test_flow import FakeSession, msg, press  # noqa: E402

ADMIN, CLIENT = 1000, 2000
CYR = re.compile(r"[А-Яа-яЁё]")


def outgoing_texts(session: FakeSession) -> list[str]:
    texts = []
    for c in session.calls:
        if isinstance(c, (SendMessage, EditMessageText, AnswerCallbackQuery)) and c.text:
            texts.append(c.text)
        markup = getattr(c, "reply_markup", None)
        for row in getattr(markup, "inline_keyboard", None) or getattr(markup, "keyboard", None) or []:
            texts += [b.text for b in row]
        if getattr(markup, "input_field_placeholder", None):
            texts.append(markup.input_field_placeholder)
    return texts


async def main() -> None:
    cfg = Config(
        bot_token="123456:" + "A" * 35, admin_ids=frozenset({ADMIN}),
        db_path=os.path.join(tempfile.mkdtemp(), "en.db"), tz=ZoneInfo("Asia/Almaty"), currency="$",
        work_start=time(10, 0), work_end=time(20, 0), breaks=((time(13, 0), time(14, 0)),),
        work_days=frozenset(range(1, 8)), slot_step=30, days_ahead=14, min_lead=60,
        remind_before=120, max_active_per_user=3, demo_mode=True,
    )
    db = Database(cfg.db_path)
    await db.connect()
    try:
        s = FakeSession()
        bot = Bot(cfg.bot_token, session=s)
        dp = build_dispatcher(db, cfg)
        feed = lambda u: dp.feed_update(bot, u)  # noqa: E731

        await feed(msg(CLIENT, "/start"))
        assert "You can book an appointment here" in s.texts(CLIENT)[-1] and "demo bot" in s.texts(CLIENT)[-1]
        await feed(msg(CLIENT, "📅 Book"))
        assert s.texts(CLIENT)[-1] == "Choose a service:"
        assert any("Haircut · 60 min · $30" in t for t in outgoing_texts(s))
        await feed(press(CLIENT, s.buttons("svc")[0]))
        await feed(press(CLIENT, s.buttons("day")[1]))
        assert "Choose a time:" in s.texts(CLIENT)[-1]
        await feed(press(CLIENT, s.buttons("tm")[0]))
        await feed(msg(CLIENT, "J"))
        assert "2 to 50 characters" in s.texts(CLIENT)[-1]
        await feed(msg(CLIENT, "John Smith"))
        await feed(msg(CLIENT, "+1 555 123 4567"))
        assert "Name: John Smith" in s.texts(CLIENT)[-1] and "When: <b>" in s.texts(CLIENT)[-1]
        await feed(press(CLIENT, "nav:confirm"))
        assert "You're booked!" in s.texts(CLIENT)[-2] and "what the owner sees" in s.texts(CLIENT)[-1]
        assert "New booking" in s.texts(ADMIN)[-1]

        await feed(msg(CLIENT, "📋 My bookings"))
        assert "Your bookings" in s.texts(CLIENT)[-1]
        booking_id = int(s.buttons("bk")[0].split(":")[-1])
        await feed(press(CLIENT, f"bk:cancel:{booking_id}"))
        assert "Cancel this booking?" in s.texts(CLIENT)[-1]
        await feed(press(CLIENT, f"bk:my:{booking_id}"))

        for cmd in ("/admin", "/today", "/tomorrow", "/services", "/addservice Manicure | 90 | 40",
                    "/addservice bad", "/delservice 99", "/day 31.13"):
            await feed(msg(ADMIN, cmd))
        assert "Admin panel" in s.texts(ADMIN)[-8] and "Added:" in s.texts(ADMIN)[-4]
        await feed(press(ADMIN, f"bk:acancel:{booking_id}"))
        await feed(press(ADMIN, f"bk:acancel_yes:{booking_id}"))
        assert "cancelled by the administrator" in s.texts(CLIENT)[-1]

        soon = now_local(cfg) + timedelta(minutes=90)
        await db.create_booking(user_id=CLIENT, service_id=1, starts_at=soon, ends_at=soon + timedelta(minutes=30),
                                price=0, client_name="John", phone="+15551234567", reminded=False)
        assert await send_due_reminders(bot, db, replace(cfg)) == 1
        assert s.texts(CLIENT)[-1].startswith("⏰ Reminder:")
        await feed(press(CLIENT, "tm:1200"))
        assert "outdated" in s.alerts()[-1]

        leaks = [t for t in outgoing_texts(s) if CYR.search(t)]
        assert not leaks, "Кириллица в английской версии:\n" + "\n".join(leaks)
        print(f"✔ английская версия: {len(outgoing_texts(s))} текстов и кнопок, кириллицы нет")
    finally:
        await db.close()
    print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    asyncio.run(main())
