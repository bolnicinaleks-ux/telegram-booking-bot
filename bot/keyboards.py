from datetime import date, datetime

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.i18n import _
from bot.utils import fmt_day_short, fmt_price, str_to_dt

BTN_BOOK = _("📅 Записаться")
BTN_MY = _("📋 Мои записи")
BACK = _("◀️ Назад")
CANCEL = _("✖️ Отмена")


class ServiceCb(CallbackData, prefix="svc"):
    id: int


class MasterCb(CallbackData, prefix="mst"):
    id: int


class DayCb(CallbackData, prefix="day"):
    d: str  # YYYYMMDD


class TimeCb(CallbackData, prefix="tm"):
    t: str  # HHMM


class NavCb(CallbackData, prefix="nav"):
    to: str  # services | masters | days | confirm | cancel


class BookingCb(CallbackData, prefix="bk"):
    action: str  # cancel | cancel_yes | my | acancel | acancel_yes | akeep
    id: int


def _nav(to: str, text: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=NavCb(to=to).pack())


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_BOOK), KeyboardButton(text=BTN_MY)]],
        resize_keyboard=True,
    )


def services_kb(services, currency: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for s in services:
        b.button(
            text=_("{name} · {duration} мин · {price}", name=s["name"], duration=s["duration"],
                   price=fmt_price(s["price"], currency)),
            callback_data=ServiceCb(id=s["id"]),
        )
    b.adjust(1)
    b.row(_nav("cancel", CANCEL))
    return b.as_markup()


def masters_kb(masters) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for m in masters:
        b.button(text=m["name"], callback_data=MasterCb(id=m["id"]))
    b.adjust(2)
    b.row(_nav("services", BACK), _nav("cancel", CANCEL))
    return b.as_markup()


def days_kb(days: list[date], back: str = "services") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for d in days:
        b.button(text=fmt_day_short(d), callback_data=DayCb(d=d.strftime("%Y%m%d")))
    b.adjust(3)
    b.row(_nav(back, BACK), _nav("cancel", CANCEL))
    return b.as_markup()


def times_kb(slots: list[datetime]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for s in slots:
        b.button(text=f"{s:%H:%M}", callback_data=TimeCb(t=f"{s:%H%M}"))
    b.adjust(4)
    b.row(_nav("days", BACK), _nav("cancel", CANCEL))
    return b.as_markup()


def back_kb(to: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_nav(to, BACK), _nav("cancel", CANCEL)]])


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_nav("confirm", _("✅ Подтвердить")), _nav("cancel", CANCEL)]])


def name_kb(prev_name: str | None) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    if not prev_name:
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=prev_name)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=_("Ваше имя"),
    )


def phone_kb(prev_phone: str | None) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=_("📱 Отправить мой номер"), request_contact=True)]]
    if prev_phone:
        rows.append([KeyboardButton(text=prev_phone)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="+7 701 123 45 67",
    )


def my_bookings_kb(rows) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for r in rows:
        starts = str_to_dt(r["starts_at"])
        b.button(
            text=_("❌ Отменить #{id} · {day} {time}", id=r["id"], day=fmt_day_short(starts.date()),
                   time=f"{starts:%H:%M}"),
            callback_data=BookingCb(action="cancel", id=r["id"]),
        )
    b.adjust(1)
    return b.as_markup()


def user_cancel_confirm_kb(booking_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=_("Да, отменить"), callback_data=BookingCb(action="cancel_yes", id=booking_id))
    b.button(text=BACK, callback_data=BookingCb(action="my", id=booking_id))
    return b.as_markup()


def admin_booking_kb(booking_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=_("❌ Отменить запись"), callback_data=BookingCb(action="acancel", id=booking_id))
    return b.as_markup()


def admin_day_kb(rows) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for r in rows:
        b.button(
            text=f"❌ #{r['id']} · {str_to_dt(r['starts_at']):%H:%M}",
            callback_data=BookingCb(action="acancel", id=r["id"]),
        )
    b.adjust(2)
    return b.as_markup()


def admin_cancel_confirm_kb(booking_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=_("Да, отменить"), callback_data=BookingCb(action="acancel_yes", id=booking_id))
    b.button(text=_("Нет"), callback_data=BookingCb(action="akeep", id=booking_id))
    return b.as_markup()
