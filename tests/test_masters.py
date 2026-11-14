"""Несколько мастеров: миграция старой базы, слоты по мастеру, пропуск шага выбора, админка и уведомления.

Запуск: python -m tests.test_masters
"""
import os

os.environ.setdefault("BOT_LANG", "ru")

import asyncio  # noqa: E402
import sqlite3  # noqa: E402
import tempfile  # noqa: E402
from datetime import date, datetime, time, timedelta  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from aiogram import Bot  # noqa: E402

from bot.__main__ import build_dispatcher  # noqa: E402
from bot.config import Config  # noqa: E402
from bot.db import Database  # noqa: E402
from bot.reminders import send_due_reminders  # noqa: E402
from bot.slots import free_slots, master_cfg  # noqa: E402
from bot.utils import now_local  # noqa: E402
from tests.test_flow import FakeSession, msg, press  # noqa: E402

ADMIN, CLIENT, CLIENT2, MASTER, STRANGER = 1000, 2000, 3000, 5000, 4000

# Схема bookings до появления мастеров (для проверки миграции)
OLD_SCHEMA = """
CREATE TABLE services (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, duration INTEGER NOT NULL,
                       price INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
    service_id INTEGER NOT NULL REFERENCES services(id), starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
    price INTEGER NOT NULL, client_name TEXT NOT NULL, phone TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active', reminded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE INDEX idx_bookings_time ON bookings(status, starts_at);
"""


def make_cfg(path: str) -> Config:
    return Config(
        bot_token="123456:" + "A" * 35, admin_ids=frozenset({ADMIN}), db_path=path, tz=ZoneInfo("Asia/Almaty"),
        currency="₸", work_start=time(10, 0), work_end=time(20, 0), breaks=((time(13, 0), time(14, 0)),),
        work_days=frozenset(range(1, 8)), slot_step=30, days_ahead=14, min_lead=60, remind_before=120,
        max_active_per_user=10,
    )


def book_kwargs(user_id: int, starts: datetime, master_id: int | None) -> dict:
    return dict(user_id=user_id, service_id=1, starts_at=starts, ends_at=starts + timedelta(minutes=60), price=0,
                client_name="Тест", phone="+70000000000", reminded=False, master_id=master_id)


async def test_migration(tmp: str) -> None:
    path = os.path.join(tmp, "old.db")
    con = sqlite3.connect(path)
    con.executescript(OLD_SCHEMA)
    con.execute("INSERT INTO services (name, duration, price) VALUES ('Стрижка', 60, 5000)")
    con.execute("""INSERT INTO bookings (user_id, service_id, starts_at, ends_at, price, client_name, phone)
                   VALUES (1, 1, '2030-01-07 10:00', '2030-01-07 11:00', 5000, 'Старый', '+70000000001')""")
    con.commit()
    con.close()

    db = Database(path)
    await db.connect()
    try:
        old = await db.get_booking(1)
        assert old["client_name"] == "Старый" and old["master_id"] is None and old["master_name"] is None
        assert [r["id"] for r in await db.bookings_on(date(2030, 1, 7))] == [1]
        assert await db.list_masters() == []
        # Старая запись (без мастера) блокирует время любого нового мастера
        mid = await db.add_master("Новый")
        assert await db.create_booking(**book_kwargs(1, datetime(2030, 1, 7, 10, 30), mid)) is None
        assert await db.create_booking(**book_kwargs(1, datetime(2030, 1, 7, 11, 0), mid)) is not None
    finally:
        await db.close()
    db = Database(path)  # повторное подключение: миграция идемпотентна
    await db.connect()
    await db.close()
    print("✔ миграция старой базы: master_id добавлен, старые записи на месте")


def test_master_cfg(cfg: Config) -> None:
    now = datetime(2030, 1, 6, 9, 0)  # воскресенье
    monday = date(2030, 1, 7)
    same = master_cfg(cfg, {"work_start": None, "work_end": None, "work_days": None, "breaks": None})
    assert same == cfg and master_cfg(cfg, None) is cfg

    own = master_cfg(cfg, {"work_start": "12:00", "work_end": "16:00", "work_days": "1,2", "breaks": ""})
    slots = [f"{s:%H%M}" for s in free_slots(own, monday, 60, [], now)]
    assert slots == ["1200", "1230", "1300", "1330", "1400", "1430", "1500"], slots  # без перерыва 13–14
    assert free_slots(own, monday + timedelta(days=2), 60, [], now) == []  # среда — не его день
    shared = [f"{s:%H%M}" for s in free_slots(cfg, monday, 60, [], now)]
    assert shared[0] == "1000" and "1300" not in shared
    print("✔ расписание мастера: свои часы, дни и перерывы, остальное из .env")


async def main() -> None:
    tmp = tempfile.mkdtemp()
    await test_migration(tmp)
    cfg = make_cfg(os.path.join(tmp, "masters.db"))
    test_master_cfg(cfg)

    db = Database(cfg.db_path)
    await db.connect()
    try:
        s = FakeSession()
        bot = Bot(cfg.bot_token, session=s)
        dp = build_dispatcher(db, cfg)
        feed = lambda u: dp.feed_update(bot, u)  # noqa: E731
        tomorrow = now_local(cfg).date() + timedelta(days=1)

        # 1. Мастеров нет — шаг выбора мастера пропущен, всё как раньше
        await feed(msg(CLIENT, "/book"))
        await feed(press(CLIENT, s.buttons("svc")[0]))
        assert s.buttons("day") and not s.buttons("mst")
        assert "Мастер" not in s.texts(CLIENT)[-1]
        print("✔ 0 мастеров: шаг выбора пропущен")

        # 2. Один мастер — шаг тоже пропущен, но запись привязана к нему, мастер получает уведомление
        await feed(msg(ADMIN, "/addmaster Арман | 5000"))
        assert "Мастер добавлен" in s.texts(ADMIN)[-1] and "Арман" in s.texts(ADMIN)[-1]
        await feed(msg(CLIENT, "/book"))
        await feed(press(CLIENT, s.buttons("svc")[0]))
        assert not s.buttons("mst") and "Мастер: <b>Арман</b>" in s.texts(CLIENT)[-1]
        day = s.buttons("day")[1]
        await feed(press(CLIENT, day))
        assert s.buttons("tm")[0] == "tm:1000"
        await feed(press(CLIENT, "tm:1000"))
        await feed(msg(CLIENT, "Иван"))
        await feed(msg(CLIENT, "+77011234567"))
        await feed(press(CLIENT, "nav:confirm"))
        assert "Вы записаны" in s.texts(CLIENT)[-1] and "Арман" in s.texts(CLIENT)[-1]
        b1 = (await db.bookings_on(tomorrow))[0]
        assert b1["master_id"] == 1
        assert "Новая запись" in s.texts(MASTER)[-1] and "Иван" in s.texts(MASTER)[-1]
        assert "Мастер: Арман" in s.texts(ADMIN)[-1]
        print("✔ 1 мастер: шаг пропущен, запись привязана, мастер уведомлён")

        # 3. Два мастера — шаг выбора, слоты у каждого свои
        await feed(msg(ADMIN, "/addmaster Данияр | - | 12:00-20:00 | - | 0"))
        assert "12:00–20:00" in s.texts(ADMIN)[-1]
        await feed(msg(ADMIN, "/addmaster | 1"))
        assert "Формат" in s.texts(ADMIN)[-1]
        await feed(msg(ADMIN, "/addmaster Кривой | 1 | 20:00-10:00"))
        assert "Формат" in s.texts(ADMIN)[-1]

        await feed(msg(CLIENT2, "/book"))
        await feed(press(CLIENT2, s.buttons("svc")[0]))
        assert s.buttons("mst") == ["mst:1", "mst:2"] and "Выберите мастера" in s.texts(CLIENT2)[-1]
        await feed(press(CLIENT2, "mst:1"))
        await feed(press(CLIENT2, day))
        assert "tm:1000" not in s.buttons("tm")  # у Армана 10:00 занято
        await feed(press(CLIENT2, "nav:days"))
        await feed(press(CLIENT2, "nav:masters"))  # назад к выбору мастера
        assert s.buttons("mst") == ["mst:1", "mst:2"]
        await feed(press(CLIENT2, "mst:2"))
        await feed(press(CLIENT2, day))
        times = s.buttons("tm")
        assert times[0] == "tm:1200" and "tm:1300" in times  # свои часы, без перерыва
        await feed(press(CLIENT2, "tm:1200"))
        await feed(msg(CLIENT2, "Анна"))
        await feed(msg(CLIENT2, "+77770001122"))
        assert "Мастер: <b>Данияр</b>" in s.texts(CLIENT2)[-1]
        await feed(press(CLIENT2, "nav:confirm"))
        assert (await db.bookings_on(tomorrow, 2))[0]["client_name"] == "Анна"
        print("✔ 2 мастера: выбор мастера, у каждого свои слоты и график")

        # 4. Двойное бронирование — только в пределах одного мастера
        at = datetime.combine(tomorrow, time(15, 0))
        assert await db.create_booking(**book_kwargs(CLIENT, at, 1)) is not None
        assert await db.create_booking(**book_kwargs(CLIENT2, at, 2)) is not None  # то же время, другой мастер
        assert await db.create_booking(**book_kwargs(STRANGER, at, 1)) is None
        assert await db.create_booking(**book_kwargs(STRANGER, at + timedelta(minutes=30), 2)) is None
        legacy = datetime.combine(tomorrow, time(17, 0))
        assert await db.create_booking(**book_kwargs(STRANGER, legacy, None)) is not None
        assert await db.create_booking(**book_kwargs(STRANGER, legacy, 1)) is None  # запись без мастера блокирует всех
        assert await db.create_booking(**book_kwargs(STRANGER, legacy, 2)) is None
        print("✔ нет двойных записей к одному мастеру; разные мастера — одно время")

        # 5. Расписание по мастерам у админа и у самого мастера
        await feed(msg(ADMIN, "/tomorrow"))
        day_text = s.texts(ADMIN)[-1]
        assert day_text.index("✂️ <b>Арман</b>") < day_text.index("✂️ <b>Данияр</b>") < day_text.index("Без мастера")
        await feed(msg(MASTER, "/schedule"))
        mine = s.texts(MASTER)[-1]
        assert "Ваше расписание, Арман" in mine and "Иван" in mine and "Анна" not in mine
        await feed(msg(STRANGER, "/schedule"))
        assert not any("Ваше расписание" in t for t in s.texts(STRANGER))
        await feed(msg(ADMIN, "/masters"))
        assert "Арман" in s.texts(ADMIN)[-1] and "TG 5000" in s.texts(ADMIN)[-1]
        print("✔ /tomorrow по мастерам, /schedule мастера")

        # 6. Отмена: мастер узнаёт и об отмене клиентом, и об отмене админом
        await feed(press(CLIENT, f"bk:cancel_yes:{b1['id']}"))
        assert "Клиент отменил" in s.texts(MASTER)[-1]
        rows = await db.bookings_on(tomorrow, 1)
        await feed(press(ADMIN, f"bk:acancel_yes:{rows[0]['id']}"))
        assert "отменена администратором" in s.texts(MASTER)[-1]
        print("✔ мастер получает уведомления об отменах")

        # 7. Напоминание с именем мастера
        soon = now_local(cfg) + timedelta(minutes=90)
        await db.create_booking(**book_kwargs(CLIENT, soon, 2))
        assert await send_due_reminders(bot, db, cfg) >= 1
        assert "мастер Данияр" in s.texts(CLIENT)[-1]
        print("✔ напоминание с именем мастера")

        # 8. Отключение мастера: посреди сценария и после
        await feed(msg(CLIENT2, "/book"))
        await feed(press(CLIENT2, s.buttons("svc")[0]))
        await feed(press(CLIENT2, "mst:2"))
        await feed(msg(ADMIN, "/delmaster 2"))
        assert "отключён" in s.texts(ADMIN)[-1]
        await feed(press(CLIENT2, day))
        assert "Мастер недоступен" in s.alerts()[-1]
        await feed(msg(CLIENT2, "/book"))
        await feed(press(CLIENT2, s.buttons("svc")[0]))
        assert not s.buttons("mst")  # остался один активный мастер — шаг снова пропущен
        await feed(msg(ADMIN, "/delmaster 2"))
        assert "не найден" in s.texts(ADMIN)[-1]
        await feed(msg(ADMIN, "/masters"))
        assert "отключён" in s.texts(ADMIN)[-1]
        await feed(msg(ADMIN, "/onmaster 2"))
        assert "снова принимает" in s.texts(ADMIN)[-1]
        await feed(msg(CLIENT2, "/book"))
        await feed(press(CLIENT2, s.buttons("svc")[0]))
        assert s.buttons("mst") == ["mst:1", "mst:2"]
        print("✔ отключение и включение мастера")
    finally:
        await db.close()

    # 9. Демо-режим: два демо-мастера, один раз
    demo = Database(os.path.join(tmp, "demo.db"))
    await demo.connect()
    try:
        assert await demo.seed_demo_masters() is True
        masters = await demo.list_masters()
        assert [m["name"] for m in masters] == ["Арман", "Данияр"] and masters[1]["work_start"] == "12:00"
        assert await demo.seed_demo_masters() is False and len(await demo.list_masters()) == 2
    finally:
        await demo.close()
    print("✔ DEMO_MODE: два демо-мастера")
    print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    asyncio.run(main())
