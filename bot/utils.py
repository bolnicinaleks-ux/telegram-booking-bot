import re
from datetime import date, datetime
from html import escape
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message

from bot.i18n import LANG, _

if TYPE_CHECKING:
    from bot.config import Config

DT_FMT = "%Y-%m-%d %H:%M"
WEEKDAYS = (_("Пн"), _("Вт"), _("Ср"), _("Чт"), _("Пт"), _("Сб"), _("Вс"))
MONTHS = (
    _("января"), _("февраля"), _("марта"), _("апреля"), _("мая"), _("июня"),
    _("июля"), _("августа"), _("сентября"), _("октября"), _("ноября"), _("декабря"),
)
MONTHS_SHORT_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def now_local(cfg: "Config") -> datetime:
    """Текущее время в часовом поясе бизнеса, без tzinfo (так хранится в БД)."""
    return datetime.now(cfg.tz).replace(tzinfo=None, second=0, microsecond=0)


def dt_to_str(dt: datetime) -> str:
    return dt.strftime(DT_FMT)


def str_to_dt(value: str) -> datetime:
    return datetime.strptime(value, DT_FMT)


def fmt_day_short(d: date) -> str:
    if LANG == "en":
        return f"{WEEKDAYS[d.weekday()]} {MONTHS_SHORT_EN[d.month - 1]} {d.day}"
    return f"{WEEKDAYS[d.weekday()]} {d:%d.%m}"


def fmt_day_long(d: date) -> str:
    if LANG == "en":
        return f"{WEEKDAYS[d.weekday()]}, {MONTHS[d.month - 1]} {d.day}"
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}"


def fmt_dt(dt: datetime) -> str:
    return f"{fmt_day_long(dt.date())}, {dt:%H:%M}"


def fmt_price(amount: int, currency: str) -> str:
    if LANG == "en":
        return f"{currency}{amount:,}" if currency in ("$", "€", "£") else f"{amount:,} {currency}"
    return f"{amount:,}".replace(",", " ") + f" {currency}"


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if not 10 <= len(digits) <= 15:
        return None
    return "+" + digits


def booking_card(row, currency: str, with_client: bool = False) -> str:
    lines = [
        f"<b>#{row['id']}</b> · {fmt_dt(str_to_dt(row['starts_at']))}",
        f"{escape(row['service_name'])} · {fmt_price(row['price'], currency)}",
    ]
    if with_client:
        lines.append(f"👤 {escape(row['client_name'])}, {escape(row['phone'])}")
    return "\n".join(lines)


async def safe_edit(message: Message, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
