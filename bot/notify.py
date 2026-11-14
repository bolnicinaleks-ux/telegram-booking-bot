import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from bot.config import Config

log = logging.getLogger(__name__)


async def notify_admins(bot: Bot, cfg: Config, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    for admin_id in cfg.admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=markup)
        except TelegramAPIError as e:
            log.warning("Не удалось уведомить админа %s: %s", admin_id, e)


async def notify_master(bot: Bot, cfg: Config, booking, text: str) -> None:
    """Копия уведомления мастеру записи, если у него указан Telegram ID (админы уже получили своё)."""
    tg_id = booking["master_tg_id"]
    if tg_id and tg_id not in cfg.admin_ids:
        try:
            await bot.send_message(tg_id, text)
        except TelegramAPIError as e:
            log.warning("Не удалось уведомить мастера %s: %s", tg_id, e)


async def notify_user(bot: Bot, user_id: int, text: str) -> bool:
    try:
        await bot.send_message(user_id, text)
        return True
    except TelegramAPIError as e:
        log.warning("Не удалось отправить сообщение пользователю %s: %s", user_id, e)
        return False
