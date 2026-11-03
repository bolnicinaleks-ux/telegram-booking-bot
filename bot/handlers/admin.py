from contextlib import suppress
from datetime import date, datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot.config import Config
from bot.db import Database
from bot.notify import notify_admins, notify_user
from bot.utils import booking_card, fmt_day_long, fmt_price, now_local, safe_edit

HELP = (
    "<b>Админ-панель</b>\n\n"
    "/today — записи на сегодня\n"
    "/tomorrow — записи на завтра\n"
    "/day ДД.ММ[.ГГГГ] — записи на дату\n"
    "/services — список услуг\n"
    "/addservice Название | минуты | цена — добавить услугу\n"
    "/delservice ID — скрыть услугу"
)


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, cfg: Config) -> bool:
        return event.from_user is not None and event.from_user.id in cfg.admin_ids


router = Router(name="admin")
router.message.filter(IsAdmin())


def can_manage(user_id: int, cfg: Config, booking) -> bool:
    """Админ — любую запись; в демо-режиме клиент — свою (через копию карточки владельца)."""
    return user_id in cfg.admin_ids or (cfg.demo_mode and booking is not None and booking["user_id"] == user_id)


def _parse_day(raw: str, today: date) -> date | None:
    raw = raw.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    try:
        parsed = datetime.strptime(f"{raw}.{today.year}", "%d.%m.%Y").date()
    except ValueError:
        return None
    if parsed < today:
        with suppress(ValueError):
            parsed = parsed.replace(year=today.year + 1)
    return parsed


async def _send_day(message: Message, db: Database, cfg: Config, day: date) -> None:
    rows = await db.bookings_on(day)
    title = f"<b>{fmt_day_long(day)} {day:%Y}</b>"
    if not rows:
        await message.answer(f"{title}\n\nЗаписей нет.")
        return
    text = f"{title} · записей: {len(rows)}\n\n" + "\n\n".join(
        booking_card(r, cfg.currency, with_client=True) for r in rows
    )
    await message.answer(text, reply_markup=kb.admin_day_kb(rows))


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await message.answer(HELP)


@router.message(Command("today"))
async def cmd_today(message: Message, db: Database, cfg: Config) -> None:
    await _send_day(message, db, cfg, now_local(cfg).date())


@router.message(Command("tomorrow"))
async def cmd_tomorrow(message: Message, db: Database, cfg: Config) -> None:
    await _send_day(message, db, cfg, now_local(cfg).date() + timedelta(days=1))


@router.message(Command("day"))
async def cmd_day(message: Message, command: CommandObject, db: Database, cfg: Config) -> None:
    day = _parse_day(command.args or "", now_local(cfg).date())
    if day is None:
        await message.answer("Формат: /day 05.11 или /day 05.11.2026")
        return
    await _send_day(message, db, cfg, day)


@router.message(Command("services"))
async def cmd_services(message: Message, db: Database, cfg: Config) -> None:
    services = await db.list_services()
    if not services:
        await message.answer("Услуг нет. Добавьте: /addservice Название | 60 | 5000")
        return
    lines = [
        f"<code>{s['id']}</code> · {escape(s['name'])} · {s['duration']} мин · {fmt_price(s['price'], cfg.currency)}"
        for s in services
    ]
    await message.answer("<b>Услуги</b>\n\n" + "\n".join(lines))


@router.message(Command("addservice"))
async def cmd_addservice(message: Message, command: CommandObject, db: Database, cfg: Config) -> None:
    parts = [p.strip() for p in (command.args or "").split("|")]
    try:
        name, duration, price = parts[0], int(parts[1]), int(parts[2])
        if len(parts) != 3 or not 1 <= len(name) <= 60 or not 5 <= duration <= 600 or price < 0:
            raise ValueError
    except (ValueError, IndexError):
        await message.answer(
            "Формат: /addservice Название | минуты | цена\n"
            "Пример: /addservice Маникюр | 90 | 7000\n"
            "Длительность 5–600 мин, цена ≥ 0."
        )
        return
    service_id = await db.add_service(name, duration, price)
    await message.answer(
        f"Добавлено: <code>{service_id}</code> · {escape(name)} · {duration} мин · {fmt_price(price, cfg.currency)}"
    )


@router.message(Command("delservice"))
async def cmd_delservice(message: Message, command: CommandObject, db: Database) -> None:
    try:
        service_id = int((command.args or "").strip())
    except ValueError:
        await message.answer("Формат: /delservice ID (ID — в /services)")
        return
    if await db.hide_service(service_id):
        await message.answer(f"Услуга {service_id} скрыта. Существующие записи сохранены.")
    else:
        await message.answer("Услуга не найдена или уже скрыта.")


@router.callback_query(kb.BookingCb.filter(F.action == "acancel"))
async def ask_admin_cancel(cb: CallbackQuery, callback_data: kb.BookingCb, db: Database, cfg: Config) -> None:
    booking = await db.get_booking(callback_data.id)
    if not can_manage(cb.from_user.id, cfg, booking):
        await cb.answer("Нет доступа", show_alert=True)
        return
    if booking["status"] != "active":
        await cb.answer("Запись уже отменена", show_alert=True)
        return
    await cb.message.answer(
        "Отменить запись?\n\n" + booking_card(booking, cfg.currency, with_client=True),
        reply_markup=kb.admin_cancel_confirm_kb(booking["id"]),
    )
    await cb.answer()


@router.callback_query(kb.BookingCb.filter(F.action == "acancel_yes"))
async def do_admin_cancel(cb: CallbackQuery, callback_data: kb.BookingCb, db: Database, cfg: Config, bot: Bot) -> None:
    booking = await db.get_booking(callback_data.id)
    if not can_manage(cb.from_user.id, cfg, booking):
        await cb.answer("Нет доступа", show_alert=True)
        return
    if not await db.cancel_booking(booking["id"]):
        await cb.answer("Запись уже отменена", show_alert=True)
        return
    delivered = await notify_user(
        bot,
        booking["user_id"],
        "Ваша запись отменена администратором:\n\n" + booking_card(booking, cfg.currency),
    )
    suffix = "" if delivered else "\n\n⚠️ Клиент не получил уведомление (бот заблокирован)."
    await safe_edit(cb.message, f"Запись #{booking['id']} отменена.{suffix}")
    await cb.answer()
    if cb.from_user.id not in cfg.admin_ids:
        await notify_admins(
            bot, cfg, "🧪 Демо: клиент отменил запись через карточку владельца\n\n"
            + booking_card(booking, cfg.currency, with_client=True),
        )


@router.callback_query(kb.BookingCb.filter(F.action == "akeep"))
async def keep_booking(cb: CallbackQuery, callback_data: kb.BookingCb, db: Database, cfg: Config) -> None:
    if not can_manage(cb.from_user.id, cfg, await db.get_booking(callback_data.id)):
        await cb.answer("Нет доступа", show_alert=True)
        return
    await safe_edit(cb.message, f"Запись #{callback_data.id} оставлена.")
    await cb.answer()
