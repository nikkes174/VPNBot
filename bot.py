import asyncio
import logging

import betterlogging as bl
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from aiogram.types import (BotCommand, BotCommandScopeDefault,
                           MenuButtonCommands)

from tgbot.config import Config, load_config
from tgbot.handlers import user_router
from tgbot.middlewares.config import ConfigMiddleware
from tgbot.services import broadcaster

config = load_config(".env")

bot = Bot(
    token=config.tg_bot.token, default=DefaultBotProperties(parse_mode="HTML")
)


async def on_startup(bot: Bot, admin_ids: list[int]):
    commands = [
        BotCommand(command="start", description="Перезапуск бота"),
        BotCommand(command="/admin_panel", description="Панель админа"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    await broadcaster.broadcast(bot, admin_ids, "Бот запущен")


def register_global_middlewares(
    dp: Dispatcher, config: Config, session_pool=None
):
    middleware_types = [
        ConfigMiddleware(config),
    ]
    for middleware_type in middleware_types:
        dp.message.outer_middleware(middleware_type)
        dp.callback_query.outer_middleware(middleware_type)


def setup_logging():
    log_level = logging.INFO
    bl.basic_colorized_config(level=log_level)
    logging.basicConfig(
        level=logging.INFO,
        format="%(filename)s:%(lineno)d "
               "#%(levelname)-8s "
               "[%(asctime)s] - %(name)s - %(message)s",
    )
    logger = logging.getLogger(__name__)
    logger.info("Starting bot")


def get_storage(config):
    if config.tg_bot.use_redis:
        return RedisStorage.from_url(
            config.redis.dsn(),
            key_builder=DefaultKeyBuilder(with_bot_id=True, with_destiny=True),
        )
    else:
        return MemoryStorage()


async def main():
    setup_logging()
    storage = get_storage(config)
    dp = Dispatcher(storage=storage)
    dp.include_router(user_router)
    register_global_middlewares(dp, config)
    await on_startup(bot, config.tg_bot.admin_ids)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error("Бот остановлен!")
