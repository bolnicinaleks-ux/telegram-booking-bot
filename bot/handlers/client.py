from datetime import date, datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import keyboards as kb
from bot.config import Config
from bot.db import Database
from bot.i18n import _
from bot.notify import notify_admins
from bot.slots import candidate_days, free_slots
from bot.states import Booking
from bot.utils import (
    booking_card,
    dt_to_str,
    fmt_day_long,
    fmt_dt,
    fmt_price,
    normalize_phone,
    now_local,
    safe_edit,
    str_to_dt,
)

router = Router(name="client")

DEMO_NOTE = _(
    "\n\n🧪 <b>Это демо-бот.</b> После записи вы получите копию карточки, "
    "которую видит владелец, и сможете сами отменить запись как администратор."
)


# --- Вспомогательные функции ---

async def _slots(db: Database, cfg: Config, day: date, duration: int) -> list[datetime]:
    return free_slots(cfg, day, duration, await db.busy_intervals(day), now_local(cfg))


async def _available_days(db: Database, cfg: Config, duration: int) -> list[date]:
    now = now_local(cfg)
    result = []
    for day in candidate_days(cfg, now):
        if free_slots(cfg, day, duration, await db.busy_intervals(day), now):
            result.append(day)
    return result


def _service_line(data: dict, cfg: Config) -> str:
    return _(
        "Услуга: <b>{name}</b> · {duration} мин · {price}",
        name=escape(data["service_name"]), duration=data["duration"], price=fmt_price(data["price"], cfg.currency),
    )


def _summary(data: dict, cfg: Config) -> str:
    return "\n".join([
        _service_line(data, cfg),
        _("Когда: <b>{when}</b>", when=fmt_dt(str_to_dt(data["starts_at"]))),
        _("Имя: {name}", name=escape(data["client_name"])),
        _("Телефон: {phone}", phone=escape(data["phone"])),
    ])


async def _show_services(message: Message, state: FSMContext, db: Database, cfg: Config, edit: bool) -> None:
    await state.clear()
    services = await db.list_services()
    if services:
        await state.set_state(Booking.service)
        text, markup = _("Выберите услугу:"), kb.services_kb(services, cfg.currency)
    else:
        text, markup = _("Сейчас нет доступных услуг."), None
    if edit:
        await safe_edit(message, text, markup)
    else:
        await message.answer(text, reply_markup=markup)


async def _show_days(message: Message, state: FSMContext, db: Database, cfg: Config) -> None:
    data = await state.get_data()
    days = await _available_days(db, cfg, data["duration"])
    await state.set_state(Booking.day)
    if days:
        await safe_edit(message, f"{_service_line(data, cfg)}\n\n{_('Выберите дату:')}", kb.days_kb(days))
    else:
        await safe_edit(
            message,
            f"{_service_line(data, cfg)}\n\n{_('Свободных дат нет. Выберите другую услугу.')}",
            kb.back_kb("services"),
        )


async def _show_times(message: Message, state: FSMContext, db: Database, cfg: Config) -> None:
    data = await state.get_data()
    day = date.fromisoformat(data["day"])
    slots = await _slots(db, cfg, day, data["duration"])
    if not slots:
        await _show_days(message, state, db, cfg)
        return
    await state.set_state(Booking.time)
    await safe_edit(
        message,
        f"{_service_line(data, cfg)}\n" + _("Дата: <b>{day}</b>\n\nВыберите время:", day=fmt_day_long(day)),
        kb.times_kb(slots),
    )


async def _own_upcoming(db: Database, cfg: Config, user_id: int, booking_id: int):
    booking = await db.get_booking(booking_id)
    if (
        booking is None
        or booking["user_id"] != user_id
        or booking["status"] != "active"
        or str_to_dt(booking["starts_at"]) <= now_local(cfg)
    ):
        return None
    return booking


async def _my_list(db: Database, cfg: Config, user_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    rows = await db.user_bookings(user_id, now_local(cfg))
    if not rows:
        return _("У вас нет предстоящих записей."), None
    text = _("<b>Ваши записи</b>") + "\n\n" + "\n\n".join(booking_card(r, cfg.currency) for r in rows)
    return text, kb.my_bookings_kb(rows)


# --- Меню (работает из любого состояния) ---

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, cfg: Config) -> None:
    await state.clear()
    await message.answer(
        _("Здравствуйте! Здесь можно записаться на приём.\n\n{book} — новая запись\n{my} — ваши записи",
          book=kb.BTN_BOOK, my=kb.BTN_MY) + (DEMO_NOTE if cfg.demo_mode else ""),
        reply_markup=kb.main_menu(),
    )


@router.message(Command("book"))
@router.message(F.text == kb.BTN_BOOK)
async def cmd_book(message: Message, state: FSMContext, db: Database, cfg: Config) -> None:
    if await db.count_user_active(message.from_user.id, now_local(cfg)) >= cfg.max_active_per_user:
        await state.clear()
        await message.answer(
            _("У вас уже {n} активных записей. Отмените одну из них в разделе «{my}».",
              n=cfg.max_active_per_user, my=kb.BTN_MY),
            reply_markup=kb.main_menu(),
        )
        return
    await _show_services(message, state, db, cfg, edit=False)


@router.message(Command("my"))
@router.message(F.text == kb.BTN_MY)
async def cmd_my(message: Message, state: FSMContext, db: Database, cfg: Config) -> None:
    await state.clear()
    text, markup = await _my_list(db, cfg, message.from_user.id)
    await message.answer(text, reply_markup=markup or kb.main_menu())


# --- Сценарий записи ---

@router.callback_query(Booking.service, kb.ServiceCb.filter())
async def pick_service(
    cb: CallbackQuery, callback_data: kb.ServiceCb, state: FSMContext, db: Database, cfg: Config
) -> None:
    service = await db.get_service(callback_data.id)
    if service is None or not service["active"]:
        await cb.answer(_("Услуга недоступна"), show_alert=True)
        await _show_services(cb.message, state, db, cfg, edit=True)
        return
    await state.update_data(
        service_id=service["id"],
        service_name=service["name"],
        duration=service["duration"],
        price=service["price"],
    )
    await _show_days(cb.message, state, db, cfg)
    await cb.answer()


@router.callback_query(Booking.day, kb.DayCb.filter())
async def pick_day(cb: CallbackQuery, callback_data: kb.DayCb, state: FSMContext, db: Database, cfg: Config) -> None:
    try:
        day = datetime.strptime(callback_data.d, "%Y%m%d").date()
    except ValueError:
        await cb.answer()
        return
    data = await state.get_data()
    if not await _slots(db, cfg, day, data["duration"]):
        await cb.answer(_("На эту дату свободного времени уже нет"), show_alert=True)
        await _show_days(cb.message, state, db, cfg)
        return
    await state.update_data(day=day.isoformat())
    await _show_times(cb.message, state, db, cfg)
    await cb.answer()


@router.callback_query(Booking.time, kb.TimeCb.filter())
async def pick_time(cb: CallbackQuery, callback_data: kb.TimeCb, state: FSMContext, db: Database, cfg: Config) -> None:
    data = await state.get_data()
    day = date.fromisoformat(data["day"])
    try:
        starts = datetime.combine(day, datetime.strptime(callback_data.t, "%H%M").time())
    except ValueError:
        await cb.answer()
        return
    if starts not in await _slots(db, cfg, day, data["duration"]):
        await cb.answer(_("Это время уже занято, выберите другое"), show_alert=True)
        await _show_times(cb.message, state, db, cfg)
        return

    await state.update_data(starts_at=dt_to_str(starts))
    await state.set_state(Booking.name)
    await safe_edit(cb.message, f"{_service_line(data, cfg)}\n" + _("Когда: <b>{when}</b>", when=fmt_dt(starts)))
    await cb.answer()
    last = await db.last_client(cb.from_user.id)
    await cb.message.answer(
        _("Как к вам обращаться? Напишите имя."),
        reply_markup=kb.name_kb(last["client_name"] if last else None),
    )


@router.message(Booking.name, F.text)
async def enter_name(message: Message, state: FSMContext, db: Database) -> None:
    name = " ".join(message.text.split())
    if not 2 <= len(name) <= 50 or name.startswith("/"):
        await message.answer(_("Имя должно быть от 2 до 50 символов."))
        return
    await state.update_data(client_name=name)
    await state.set_state(Booking.phone)
    last = await db.last_client(message.from_user.id)
    await message.answer(
        _("Ваш номер телефона — кнопкой ниже или текстом:"),
        reply_markup=kb.phone_kb(last["phone"] if last else None),
    )


async def _accept_phone(message: Message, state: FSMContext, cfg: Config, raw: str) -> None:
    phone = normalize_phone(raw)
    if phone is None:
        await message.answer(_("Не похоже на номер телефона. Пример: +7 701 123 45 67"))
        return
    await state.update_data(phone=phone)
    await state.set_state(Booking.confirm)
    data = await state.get_data()
    await message.answer(_("Проверьте данные 👇"), reply_markup=kb.main_menu())
    await message.answer(_summary(data, cfg), reply_markup=kb.confirm_kb())


@router.message(Booking.phone, F.contact)
async def enter_contact(message: Message, state: FSMContext, cfg: Config) -> None:
    await _accept_phone(message, state, cfg, message.contact.phone_number)


@router.message(Booking.phone, F.text)
async def enter_phone(message: Message, state: FSMContext, cfg: Config) -> None:
    await _accept_phone(message, state, cfg, message.text)


@router.message(Booking.name)
@router.message(Booking.phone)
async def wrong_input(message: Message) -> None:
    await message.answer(_("Отправьте ответ текстом."))


@router.callback_query(Booking.confirm, kb.NavCb.filter(F.to == "confirm"))
async def confirm(cb: CallbackQuery, state: FSMContext, db: Database, cfg: Config, bot: Bot) -> None:
    data = await state.get_data()
    starts = str_to_dt(data["starts_at"])
    now = now_local(cfg)

    if await db.count_user_active(cb.from_user.id, now) >= cfg.max_active_per_user:
        await state.clear()
        await safe_edit(cb.message, _("Достигнут лимит активных записей ({n}).", n=cfg.max_active_per_user))
        await cb.answer()
        return

    if starts not in await _slots(db, cfg, starts.date(), data["duration"]):
        await cb.answer(_("Это время уже недоступно, выберите другое"), show_alert=True)
        await _show_times(cb.message, state, db, cfg)
        return

    booking_id = await db.create_booking(
        user_id=cb.from_user.id,
        service_id=data["service_id"],
        starts_at=starts,
        ends_at=starts + timedelta(minutes=data["duration"]),
        price=data["price"],
        client_name=data["client_name"],
        phone=data["phone"],
        reminded=starts - now <= timedelta(minutes=cfg.remind_before),
    )
    if booking_id is None:
        await cb.answer(_("Это время только что заняли, выберите другое"), show_alert=True)
        await _show_times(cb.message, state, db, cfg)
        return

    await state.clear()
    await safe_edit(cb.message, _("✅ <b>Вы записаны!</b> Номер записи #{id}", id=booking_id) + f"\n\n{_summary(data, cfg)}")
    await cb.answer()

    booking = await db.get_booking(booking_id)
    await notify_admins(
        bot,
        cfg,
        _("🆕 <b>Новая запись</b>") + "\n\n" + booking_card(booking, cfg.currency, with_client=True),
        kb.admin_booking_kb(booking_id),
    )
    if cfg.demo_mode and cb.from_user.id not in cfg.admin_ids:
        await cb.message.answer(
            _("👀 <b>Так эту запись увидит владелец</b> — кнопка работает:") + "\n\n"
            + _("🆕 <b>Новая запись</b>") + "\n\n" + booking_card(booking, cfg.currency, with_client=True),
            reply_markup=kb.admin_booking_kb(booking_id),
        )


# --- Навигация ---

@router.callback_query(kb.NavCb.filter(F.to == "cancel"))
async def nav_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit(cb.message, _("Запись отменена."))
    await cb.answer()


@router.callback_query(kb.NavCb.filter(F.to == "services"))
async def nav_services(cb: CallbackQuery, state: FSMContext, db: Database, cfg: Config) -> None:
    await _show_services(cb.message, state, db, cfg, edit=True)
    await cb.answer()


@router.callback_query(Booking.time, kb.NavCb.filter(F.to == "days"))
async def nav_days(cb: CallbackQuery, state: FSMContext, db: Database, cfg: Config) -> None:
    await _show_days(cb.message, state, db, cfg)
    await cb.answer()


# --- Мои записи: отмена клиентом ---

@router.callback_query(kb.BookingCb.filter(F.action == "cancel"))
async def ask_cancel(cb: CallbackQuery, callback_data: kb.BookingCb, db: Database, cfg: Config) -> None:
    booking = await _own_upcoming(db, cfg, cb.from_user.id, callback_data.id)
    if booking is None:
        await cb.answer(_("Запись не найдена или уже неактуальна"), show_alert=True)
        return
    await safe_edit(
        cb.message,
        _("Отменить запись?") + "\n\n" + booking_card(booking, cfg.currency),
        kb.user_cancel_confirm_kb(booking["id"]),
    )
    await cb.answer()


@router.callback_query(kb.BookingCb.filter(F.action == "cancel_yes"))
async def do_cancel(cb: CallbackQuery, callback_data: kb.BookingCb, db: Database, cfg: Config, bot: Bot) -> None:
    booking = await _own_upcoming(db, cfg, cb.from_user.id, callback_data.id)
    if booking is None or not await db.cancel_booking(booking["id"]):
        await cb.answer(_("Запись не найдена или уже отменена"), show_alert=True)
        return
    await safe_edit(cb.message, _("Запись #{id} отменена.", id=booking["id"]))
    await cb.answer()
    await notify_admins(
        bot, cfg, _("❌ <b>Клиент отменил запись</b>") + "\n\n" + booking_card(booking, cfg.currency, with_client=True)
    )


@router.callback_query(kb.BookingCb.filter(F.action == "my"))
async def back_to_my(cb: CallbackQuery, db: Database, cfg: Config) -> None:
    text, markup = await _my_list(db, cfg, cb.from_user.id)
    await safe_edit(cb.message, text, markup)
    await cb.answer()


@router.callback_query()
async def stale_callback(cb: CallbackQuery) -> None:
    await cb.answer(_("Кнопка устарела. Начните заново: /book"), show_alert=True)
