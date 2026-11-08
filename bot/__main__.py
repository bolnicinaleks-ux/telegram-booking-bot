import asyncio
import logging
import os
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import load_config
from bot.db import Database
from bot.i18n import _
from bot.handlers import admin, client
from bot.reminders import reminder_loop


def build_dispatcher(db: Database, cfg) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage(), db=db, cfg=cfg)
    dp.include_routers(admin.router, client.router)
    return dp


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    if not cfg.admin_ids:
        logging.warning("ADMIN_IDS пуст — уведомления о записях никто не получит")

    os.makedirs(os.path.dirname(cfg.db_path) or ".", exist_ok=True)
    db = Database(cfg.db_path)
    await db.connect()

    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(db, cfg)
    reminders = asyncio.create_task(reminder_loop(bot, db, cfg))
    # Всё, что может упасть (например, нет сети при старте), — внутри try:
    # иначе открытая БД не даст процессу завершиться и супервизор не перезапустит бота.
    try:
        await bot.set_my_commands([
            BotCommand(command="book", description=_("Записаться")),
            BotCommand(command="my", description=_("Мои записи")),
            BotCommand(command="start", description=_("Главное меню")),
        ])
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        reminders.cancel()
        with suppress(asyncio.CancelledError):
            await reminders
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
