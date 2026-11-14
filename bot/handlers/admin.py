from contextlib import suppress
from datetime import date, datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot.config import Config, parse_breaks, parse_ints, parse_time
from bot.db import Database
from bot.i18n import _
from bot.notify import notify_admins, notify_master, notify_user
from bot.utils import WEEKDAYS, booking_card, fmt_day_long, fmt_price, now_local, safe_edit

HELP = _(
    "<b>Админ-панель</b>\n\n"
    "/today — записи на сегодня\n"
    "/tomorrow — записи на завтра\n"
    "/day ДД.ММ[.ГГГГ] — записи на дату\n"
    "/services — список услуг\n"
    "/addservice Название | минуты | цена — добавить услугу\n"
    "/delservice ID — скрыть услугу\n\n"
    "<b>Мастера</b> (необязательно: без них одно общее расписание)\n"
    "/masters — список мастеров\n"
    "/addmaster Имя | Telegram ID | 10:00-19:00 | 1,2,3,4,5 | 13:00-14:00 — добавить мастера; "
    "всё после имени необязательно, «-» — как в общем графике, перерывы «0» — без перерывов\n"
    "/delmaster ID — отключить мастера\n"
    "/onmaster ID — включить мастера снова"
)
ADDMASTER_FORMAT = _(
    "Формат: /addmaster Имя | Telegram ID | часы | дни | перерывы\n"
    "Пример: /addmaster Арман | 123456789 | 10:00-19:00 | 1,2,3,4,5 | 13:00-14:00\n"
    "Всё после имени необязательно; «-» — как в общем графике."
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


def _by_master(rows, masters) -> list[tuple[str, list]]:
    """Записи дня по мастерам: сначала активные мастера по порядку, затем остальные (без мастера — в конце)."""
    order = {m["id"]: i for i, m in enumerate(masters)}
    groups: dict = {}
    for r in rows:
        groups.setdefault(r["master_id"], []).append(r)
    keys = sorted(groups, key=lambda k: (k is None, order.get(k, len(order)), k or 0))
    return [(groups[k][0]["master_name"] if k is not None else _("Без мастера"), groups[k]) for k in keys]


async def _send_day(message: Message, db: Database, cfg: Config, day: date) -> None:
    rows = await db.bookings_on(day)
    title = f"<b>{fmt_day_long(day)} {day:%Y}</b>"
    if not rows:
        await message.answer(f"{title}\n\n{_('Записей нет.')}")
        return
    masters = await db.list_masters()
    if len(masters) < 2:  # одно расписание — вывод как раньше
        body = "\n\n".join(booking_card(r, cfg.currency, with_client=True) for r in rows)
    else:
        body = "\n\n".join(
            f"✂️ <b>{escape(name)}</b>" + _(" · записей: {n}", n=len(group)) + "\n\n"
            + "\n\n".join(booking_card(r, cfg.currency, with_client=True, with_master=False) for r in group)
            for name, group in _by_master(rows, masters)
        )
    text = title + _(" · записей: {n}", n=len(rows)) + "\n\n" + body
    await message.answer(text, reply_markup=kb.admin_day_kb(rows))


def _days_label(value: str | None) -> str:
    if not value:
        return _("дни как в общем графике")
    return ",".join(WEEKDAYS[d - 1] for d in sorted(parse_ints(value)))


def master_line(m) -> str:
    hours = f"{m['work_start'] or '…'}–{m['work_end'] or '…'}" if m["work_start"] or m["work_end"] else None
    parts = [f"<code>{m['id']}</code> · <b>{escape(m['name'])}</b>"]
    parts.append(hours or _("часы как в общем графике"))
    parts.append(_days_label(m["work_days"]))
    if m["breaks"] is not None:
        parts.append(_("перерывы: {breaks}", breaks=m["breaks"] or _("нет")))
    if m["tg_id"]:
        parts.append(f"TG {m['tg_id']}")
    if not m["active"]:
        parts.append(_("отключён"))
    return " · ".join(parts)


def parse_master_args(raw: str) -> dict:
    """Разбор /addmaster. ValueError — неверный формат."""
    parts = [p.strip() for p in raw.split("|")]
    parts += [""] * (5 - len(parts))
    if len(parts) > 5:
        raise ValueError
    name, tg, hours, days, breaks = (None if p in ("", "-") else p for p in parts)
    if name is None or not 1 <= len(name) <= 40:
        raise ValueError
    result = {"name": name, "tg_id": int(tg) if tg else None,
              "work_start": None, "work_end": None, "work_days": None, "breaks": None}
    if hours:
        start, end = (parse_time(v) for v in hours.split("-"))
        if start >= end:
            raise ValueError
        result["work_start"], result["work_end"] = f"{start:%H:%M}", f"{end:%H:%M}"
    if days:
        parsed = parse_ints(days)
        if not parsed or not parsed <= set(range(1, 8)):
            raise ValueError
        result["work_days"] = ",".join(map(str, sorted(parsed)))
    if breaks:
        if breaks == "0":
            result["breaks"] = ""
        else:
            parsed_breaks = parse_breaks(breaks)
            if any(b_start >= b_end for b_start, b_end in parsed_breaks):
                raise ValueError
            result["breaks"] = ",".join(f"{a:%H:%M}-{b:%H:%M}" for a, b in parsed_breaks)
    return result


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
        await message.answer(_("Формат: /day 05.11 или /day 05.11.2026"))
        return
    await _send_day(message, db, cfg, day)


@router.message(Command("services"))
async def cmd_services(message: Message, db: Database, cfg: Config) -> None:
    services = await db.list_services()
    if not services:
        await message.answer(_("Услуг нет. Добавьте: /addservice Название | 60 | 5000"))
        return
    lines = [
        f"<code>{s['id']}</code> · " + _("{name} · {duration} мин · {price}", name=escape(s["name"]),
                                          duration=s["duration"], price=fmt_price(s["price"], cfg.currency))
        for s in services
    ]
    await message.answer(_("<b>Услуги</b>") + "\n\n" + "\n".join(lines))


@router.message(Command("addservice"))
async def cmd_addservice(message: Message, command: CommandObject, db: Database, cfg: Config) -> None:
    parts = [p.strip() for p in (command.args or "").split("|")]
    try:
        name, duration, price = parts[0], int(parts[1]), int(parts[2])
        if len(parts) != 3 or not 1 <= len(name) <= 60 or not 5 <= duration <= 600 or price < 0:
            raise ValueError
    except (ValueError, IndexError):
        await message.answer(_(
            "Формат: /addservice Название | минуты | цена\n"
            "Пример: /addservice Маникюр | 90 | 7000\n"
            "Длительность 5–600 мин, цена ≥ 0."
        ))
        return
    service_id = await db.add_service(name, duration, price)
    await message.answer(
        _("Добавлено: <code>{id}</code> · {name} · {duration} мин · {price}", id=service_id, name=escape(name),
          duration=duration, price=fmt_price(price, cfg.currency))
    )


@router.message(Command("delservice"))
async def cmd_delservice(message: Message, command: CommandObject, db: Database) -> None:
    try:
        service_id = int((command.args or "").strip())
    except ValueError:
        await message.answer(_("Формат: /delservice ID (ID — в /services)"))
        return
    if await db.hide_service(service_id):
        await message.answer(_("Услуга {id} скрыта. Существующие записи сохранены.", id=service_id))
    else:
        await message.answer(_("Услуга не найдена или уже скрыта."))


@router.message(Command("masters"))
async def cmd_masters(message: Message, db: Database, cfg: Config) -> None:
    masters = await db.list_masters(include_inactive=True)
    if not masters:
        await message.answer(_(
            "Мастеров нет — запись идёт по одному общему расписанию.\n"
            "Добавить: /addmaster Имя | Telegram ID"
        ))
        return
    general = f"{cfg.work_start:%H:%M}–{cfg.work_end:%H:%M}, " + ",".join(
        WEEKDAYS[d - 1] for d in sorted(cfg.work_days)
    )
    await message.answer(
        _("<b>Мастера</b>") + "\n\n" + "\n".join(master_line(m) for m in masters)
        + "\n\n" + _("Общий график: {general}", general=general)
    )


@router.message(Command("addmaster"))
async def cmd_addmaster(message: Message, command: CommandObject, db: Database) -> None:
    try:
        fields = parse_master_args(command.args or "")
    except (ValueError, IndexError):
        await message.answer(ADDMASTER_FORMAT)
        return
    master_id = await db.add_master(**fields)
    await message.answer(_("Мастер добавлен:") + "\n" + master_line(await db.get_master(master_id)))


async def _toggle_master(message: Message, command: CommandObject, db: Database, active: bool) -> None:
    try:
        master_id = int((command.args or "").strip())
    except ValueError:
        await message.answer(_("Формат: /delmaster ID или /onmaster ID (ID — в /masters)"))
        return
    if not await db.set_master_active(master_id, active):
        await message.answer(_("Мастер не найден или уже в этом состоянии."))
    elif active:
        await message.answer(_("Мастер {id} снова принимает записи.", id=master_id))
    else:
        await message.answer(_("Мастер {id} отключён: новые записи к нему недоступны, существующие сохранены.",
                               id=master_id))


@router.message(Command("delmaster"))
async def cmd_delmaster(message: Message, command: CommandObject, db: Database) -> None:
    await _toggle_master(message, command, db, active=False)


@router.message(Command("onmaster"))
async def cmd_onmaster(message: Message, command: CommandObject, db: Database) -> None:
    await _toggle_master(message, command, db, active=True)


@router.callback_query(kb.BookingCb.filter(F.action == "acancel"))
async def ask_admin_cancel(cb: CallbackQuery, callback_data: kb.BookingCb, db: Database, cfg: Config) -> None:
    booking = await db.get_booking(callback_data.id)
    if not can_manage(cb.from_user.id, cfg, booking):
        await cb.answer(_("Нет доступа"), show_alert=True)
        return
    if booking["status"] != "active":
        await cb.answer(_("Запись уже отменена"), show_alert=True)
        return
    await cb.message.answer(
        _("Отменить запись?") + "\n\n" + booking_card(booking, cfg.currency, with_client=True),
        reply_markup=kb.admin_cancel_confirm_kb(booking["id"]),
    )
    await cb.answer()


@router.callback_query(kb.BookingCb.filter(F.action == "acancel_yes"))
async def do_admin_cancel(cb: CallbackQuery, callback_data: kb.BookingCb, db: Database, cfg: Config, bot: Bot) -> None:
    booking = await db.get_booking(callback_data.id)
    if not can_manage(cb.from_user.id, cfg, booking):
        await cb.answer(_("Нет доступа"), show_alert=True)
        return
    if not await db.cancel_booking(booking["id"]):
        await cb.answer(_("Запись уже отменена"), show_alert=True)
        return
    delivered = await notify_user(
        bot,
        booking["user_id"],
        _("Ваша запись отменена администратором:") + "\n\n" + booking_card(booking, cfg.currency),
    )
    suffix = "" if delivered else "\n\n" + _("⚠️ Клиент не получил уведомление (бот заблокирован).")
    await safe_edit(cb.message, _("Запись #{id} отменена.", id=booking["id"]) + suffix)
    await cb.answer()
    await notify_master(
        bot, cfg, booking, _("❌ <b>Запись отменена администратором</b>") + "\n\n"
        + booking_card(booking, cfg.currency, with_client=True),
    )
    if cb.from_user.id not in cfg.admin_ids:
        await notify_admins(
            bot, cfg, _("🧪 Демо: клиент отменил запись через карточку владельца") + "\n\n"
            + booking_card(booking, cfg.currency, with_client=True),
        )


@router.callback_query(kb.BookingCb.filter(F.action == "akeep"))
async def keep_booking(cb: CallbackQuery, callback_data: kb.BookingCb, db: Database, cfg: Config) -> None:
    if not can_manage(cb.from_user.id, cfg, await db.get_booking(callback_data.id)):
        await cb.answer(_("Нет доступа"), show_alert=True)
        return
    await safe_edit(cb.message, _("Запись #{id} оставлена.", id=callback_data.id))
    await cb.answer()
