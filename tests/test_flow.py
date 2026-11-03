"""Сквозной прогон бота без Telegram: апдейты подаются в Dispatcher, ответы перехватывает фейковая сессия.

Запуск: python -m tests.test_flow
"""
import asyncio
import dataclasses
import itertools
import os
import tempfile
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Contact, Message, Update, User

from bot.__main__ import build_dispatcher
from bot.config import Config
from bot.db import Database
from bot.reminders import send_due_reminders
from bot.utils import now_local

ADMIN, CLIENT, CLIENT2, STRANGER = 1000, 2000, 3000, 4000
_ids = itertools.count(1)


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (SendMessage, EditMessageText)):
            return Message(
                message_id=getattr(method, "message_id", None) or next(_ids),
                date=datetime.now(),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
            )
        return True

    async def close(self) -> None:
        pass

    async def stream_content(self, *args, **kwargs):
        yield b""

    def texts(self, chat_id: int | None = None) -> list[str]:
        return [
            c.text for c in self.calls
            if isinstance(c, (SendMessage, EditMessageText)) and (chat_id is None or c.chat_id == chat_id)
        ]

    def alerts(self) -> list[str]:
        return [c.text for c in self.calls if isinstance(c, AnswerCallbackQuery) and c.text]

    def last_markup(self):
        for c in reversed(self.calls):
            if isinstance(c, (SendMessage, EditMessageText)) and c.reply_markup is not None and hasattr(c.reply_markup, "inline_keyboard"):
                return c.reply_markup
        raise AssertionError("Нет inline-клавиатуры")

    def buttons(self, prefix: str) -> list[str]:
        return [
            b.callback_data for row in self.last_markup().inline_keyboard for b in row
            if b.callback_data and b.callback_data.startswith(prefix + ":")
        ]


def user(uid: int) -> User:
    return User(id=uid, is_bot=False, first_name=f"U{uid}")


def msg(uid: int, text: str | None = None, contact: Contact | None = None) -> Update:
    return Update(
        update_id=next(_ids),
        message=Message(
            message_id=next(_ids), date=datetime.now(), chat=Chat(id=uid, type="private"),
            from_user=user(uid), text=text, contact=contact,
        ),
    )


def press(uid: int, data: str) -> Update:
    return Update(
        update_id=next(_ids),
        callback_query=CallbackQuery(
            id=str(next(_ids)), from_user=user(uid), chat_instance="ci", data=data,
            message=Message(message_id=next(_ids), date=datetime.now(), chat=Chat(id=uid, type="private"), text="-"),
        ),
    )


async def main() -> None:
    tmp = tempfile.mkdtemp()
    cfg = Config(
        bot_token="123456:" + "A" * 35,
        admin_ids=frozenset({ADMIN}),
        db_path=os.path.join(tmp, "test.db"),
        tz=ZoneInfo("Asia/Almaty"),
        currency="₸",
        work_start=time(10, 0),
        work_end=time(20, 0),
        breaks=((time(13, 0), time(14, 0)),),
        work_days=frozenset(range(1, 8)),
        slot_step=30,
        days_ahead=14,
        min_lead=60,
        remind_before=120,
        max_active_per_user=3,
    )
    db = Database(cfg.db_path)
    await db.connect()
    session = FakeSession()
    bot = Bot(cfg.bot_token, session=session)
    dp = build_dispatcher(db, cfg)
    feed = lambda upd: dp.feed_update(bot, upd)  # noqa: E731

    # 1. Полный сценарий записи
    await feed(msg(CLIENT, "/start"))
    await feed(msg(CLIENT, "📅 Записаться"))
    service = session.buttons("svc")[0]
    await feed(press(CLIENT, service))
    day = session.buttons("day")[1]  # завтра: не зависит от текущего часа
    await feed(press(CLIENT, day))
    slot = session.buttons("tm")[0]
    assert slot == "tm:1000", slot
    await feed(press(CLIENT, slot))
    await feed(msg(CLIENT, "  Иван   Петров "))
    await feed(msg(CLIENT, "8 (701) 123-45-67"))
    assert "+77011234567" in session.texts(CLIENT)[-1]
    await feed(press(CLIENT, "nav:confirm"))
    assert "Вы записаны" in session.texts(CLIENT)[-1]
    assert "Новая запись" in session.texts(ADMIN)[-1]

    tomorrow = now_local(cfg).date() + timedelta(days=1)
    rows = await db.bookings_on(tomorrow)
    assert len(rows) == 1 and rows[0]["client_name"] == "Иван Петров" and rows[0]["phone"] == "+77011234567"
    booking_id = rows[0]["id"]
    print("✔ запись создана, админ уведомлён")

    # 2. Занятый слот не предлагается; перерыв 13:00–14:00 исключён
    await feed(msg(CLIENT2, "/book"))
    await feed(press(CLIENT2, service))  # 60 мин
    await feed(press(CLIENT2, day))
    times = session.buttons("tm")
    assert "tm:1000" not in times and "tm:0930" not in times
    assert "tm:1030" not in times  # 10:30–11:30 пересекается с 10:00–11:00
    assert "tm:1100" in times
    assert "tm:1230" not in times and "tm:1300" not in times and "tm:1400" in times
    assert times[-1] == "tm:1900"
    print("✔ сетка слотов: занятость, перерыв, конец дня")

    # 3. Гонка: второй клиент жмёт устаревшую кнопку 10:00
    await feed(press(CLIENT2, "tm:1000"))
    assert any("занято" in a for a in session.alerts())
    start = datetime.combine(tomorrow, time(10, 30))
    assert await db.create_booking(
        user_id=CLIENT2, service_id=1, starts_at=start, ends_at=start + timedelta(minutes=60),
        price=0, client_name="X", phone="+70000000000", reminded=False,
    ) is None
    print("✔ двойное бронирование невозможно")

    # 4. Контакт-кнопкой, ввод мусора и отмена
    await feed(press(CLIENT2, "tm:1100"))
    await feed(msg(CLIENT2, "А"))
    assert "от 2 до 50" in session.texts(CLIENT2)[-1]
    await feed(msg(CLIENT2, "Анна"))
    await feed(msg(CLIENT2, "12"))
    assert "Не похоже" in session.texts(CLIENT2)[-1]
    await feed(msg(CLIENT2, contact=Contact(phone_number="77770001122", first_name="Анна", user_id=CLIENT2)))
    assert "+77770001122" in session.texts(CLIENT2)[-1]
    await feed(press(CLIENT2, "nav:cancel"))
    assert len(await db.bookings_on(tomorrow)) == 1
    print("✔ валидация имени/телефона, контакт, отмена сценария")

    # 5. Отмена клиентом из «Мои записи»
    await feed(msg(CLIENT2, "📋 Мои записи"))
    assert "нет предстоящих" in session.texts(CLIENT2)[-1]
    await feed(press(CLIENT2, f"bk:cancel_yes:{booking_id}"))  # чужая запись
    assert (await db.get_booking(booking_id))["status"] == "active"
    await feed(msg(CLIENT, "📋 Мои записи"))
    assert session.buttons("bk") == [f"bk:cancel:{booking_id}"]
    await feed(press(CLIENT, f"bk:cancel:{booking_id}"))
    await feed(press(CLIENT, f"bk:cancel_yes:{booking_id}"))
    assert (await db.get_booking(booking_id))["status"] == "cancelled"
    assert "Клиент отменил" in session.texts(ADMIN)[-1]
    print("✔ отмена клиентом, защита чужих записей")

    # 6. Админка
    await feed(msg(CLIENT, "/admin"))
    assert not any("Админ-панель" in t for t in session.texts(CLIENT))
    await feed(msg(ADMIN, "/admin"))
    assert "Админ-панель" in session.texts(ADMIN)[-1]
    await feed(msg(ADMIN, "/addservice Маникюр | 90 | 7000"))
    assert "Маникюр" in session.texts(ADMIN)[-1]
    await feed(msg(ADMIN, "/addservice кривой ввод"))
    assert "Формат" in session.texts(ADMIN)[-1]
    await feed(msg(ADMIN, "/services"))
    assert "7 000 ₸" in session.texts(ADMIN)[-1]
    await feed(msg(ADMIN, "/delservice 3"))
    assert "скрыта" in session.texts(ADMIN)[-1]
    assert [s["id"] for s in await db.list_services()] == [1, 2, 4]

    start = datetime.combine(tomorrow, time(15, 0))
    bid = await db.create_booking(
        user_id=CLIENT2, service_id=1, starts_at=start, ends_at=start + timedelta(minutes=60),
        price=5000, client_name="Анна", phone="+77770001122", reminded=False,
    )
    await feed(msg(ADMIN, "/tomorrow"))
    assert "Анна" in session.texts(ADMIN)[-1]
    await feed(msg(ADMIN, f"/day {tomorrow:%d.%m}"))
    assert "Анна" in session.texts(ADMIN)[-1]
    await feed(press(ADMIN, f"bk:acancel:{bid}"))
    await feed(press(ADMIN, f"bk:acancel_yes:{bid}"))
    assert (await db.get_booking(bid))["status"] == "cancelled"
    assert "отменена администратором" in session.texts(CLIENT2)[-1]
    print("✔ админ-команды, отмена админом с уведомлением клиента")

    # 7. Напоминания
    soon = now_local(cfg) + timedelta(minutes=90)
    await db.create_booking(
        user_id=CLIENT, service_id=1, starts_at=soon, ends_at=soon + timedelta(minutes=30),
        price=0, client_name="Иван", phone="+77011234567", reminded=False,
    )
    assert await send_due_reminders(bot, db, cfg) == 1
    assert "Напоминание" in session.texts(CLIENT)[-1]
    assert await send_due_reminders(bot, db, cfg) == 0
    print("✔ напоминание отправляется один раз")

    # 8. Устаревшая кнопка
    await feed(press(CLIENT, "tm:1200"))
    assert "устарела" in session.alerts()[-1]
    print("✔ устаревшие кнопки")

    # 9. Демо-режим: клиент получает копию карточки владельца и может управлять своей записью
    demo = dataclasses.replace(cfg, demo_mode=True)
    dfeed = lambda upd: dp.feed_update(bot, upd, cfg=demo)  # noqa: E731
    await dfeed(msg(CLIENT2, "/start"))
    assert "демо-бот" in session.texts(CLIENT2)[-1]
    await feed(msg(CLIENT2, "/start"))
    assert "демо-бот" not in session.texts(CLIENT2)[-1]
    await dfeed(msg(CLIENT2, "/book"))
    await dfeed(press(CLIENT2, session.buttons("svc")[0]))
    await dfeed(press(CLIENT2, session.buttons("day")[2]))
    await dfeed(press(CLIENT2, session.buttons("tm")[0]))
    await dfeed(msg(CLIENT2, "Анна"))
    await dfeed(msg(CLIENT2, "+77770001122"))
    await dfeed(press(CLIENT2, "nav:confirm"))
    copy = session.texts(CLIENT2)[-1]
    assert "Так эту запись увидит владелец" in copy and "Анна" in copy
    demo_id = int(session.buttons("bk")[0].split(":")[-1])
    await feed(press(CLIENT2, f"bk:acancel:{demo_id}"))
    assert session.alerts()[-1] == "Нет доступа"  # без демо-режима — только админ
    await dfeed(press(STRANGER, f"bk:acancel:{demo_id}"))
    assert session.alerts()[-1] == "Нет доступа"  # чужую запись — нельзя
    await dfeed(press(CLIENT2, f"bk:acancel:{demo_id}"))
    await dfeed(press(CLIENT2, f"bk:acancel_yes:{demo_id}"))
    assert (await db.get_booking(demo_id))["status"] == "cancelled"
    assert "отменена администратором" in session.texts(CLIENT2)[-2]
    assert "Демо: клиент отменил" in session.texts(ADMIN)[-1]
    await dfeed(msg(CLIENT2, "/today"))
    assert "Админ-панель" not in session.texts(CLIENT2)[-1] and "Записей" not in session.texts(CLIENT2)[-1]
    print("✔ демо-режим: копия карточки владельца, управление только своей записью")

    await db.close()
    print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    asyncio.run(main())
