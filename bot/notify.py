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


async def notify_user(bot: Bot, user_id: int, text: str) -> bool:
    try:
        await bot.send_message(user_id, text)
        return True
    except TelegramAPIError as e:
        log.warning("Не удалось отправить сообщение пользователю %s: %s", user_id, e)
        return False
