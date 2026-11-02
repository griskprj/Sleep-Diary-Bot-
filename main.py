import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, Message

from bot.config import settings
from bot.db.database import close_db, get_session_factory, init_db
from bot.db import repositories as repo
from bot.fsm import diary, questionnaires
# Импортируем роутеры
from bot.handlers import commands as commands_router_mod
from bot.handlers import stats, advice, report, export, reminders
from bot.services.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


async def user_middleware(handler, event: Message, data: dict):
    """Инжектит user_id (внутренний) и user_tz в data."""
    tg_id = event.from_user.id
    async with get_session_factory()() as s:
        user = await repo.get_or_create_user(s, tg_id=tg_id, tz=settings.default_tz)
        await s.commit()
    data["user_tg_id"] = user.id
    data["user_id"] = user.id
    data["user_tz"] = user.tz
    return await handler(event, data)


async def set_bot_commands(bot: Bot) -> None:
    """Устанавливает список команд в синем меню Telegram."""
    # ВАЖНО: переменная называется bot_commands, чтобы не перекрывать модуль commands
    bot_commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="diary", description="Заполнить дневник сна"),
        BotCommand(command="stats", description="Статистика и гипотезы"),
        BotCommand(command="advice", description="Рекомендации (CBT-I)"),
        BotCommand(command="isi", description="Опросник ISI (инсомния)"),
        BotCommand(command="ess", description="Опросник ESS (сонливость)"),
        BotCommand(command="stopbang", description="Скрининг апноэ"),
        BotCommand(command="psqi", description="Опросник PSQI (качество)"),
        BotCommand(command="report", description="Отчёт для врача (CSV)"),
        BotCommand(command="export", description="Выгрузить все данные"),
        BotCommand(command="remind", description="Настроить напоминание"),
        BotCommand(command="about", description="Методология и источники"),
        BotCommand(command="help", description="Помощь"),
    ]
    await bot.set_my_commands(bot_commands)


async def main() -> None:
    await init_db()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    
    # Устанавливаем меню
    await set_bot_commands(bot)

    dp = Dispatcher()
    dp.message.middleware(user_middleware)
    dp.callback_query.middleware(user_middleware)

    # Подключаем роутеры
    dp.include_router(commands_router_mod.router)
    dp.include_router(diary.router)
    dp.include_router(questionnaires.router)
    dp.include_router(stats.router)
    dp.include_router(advice.router)
    dp.include_router(report.router)
    dp.include_router(export.router)
    dp.include_router(reminders.router)

    await start_scheduler(bot)
    logger.info("Starting polling")
    try:
        await dp.start_polling(bot)
    finally:
        await shutdown_scheduler()
        await close_db()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())