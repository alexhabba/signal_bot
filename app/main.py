import asyncio
import contextlib
import logging

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import admin, channel, user
from app.bot.middlewares import DbSessionMiddleware
from app.config import get_settings
from app.db.seed import seed_plans
from app.db.session import create_tables, make_engine, make_sessionmaker
from app.services.tron import TronGridClient
from app.workers import payment_watcher, scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()

    engine = make_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)
    await create_tables(engine)
    async with sessionmaker() as session:
        await seed_plans(session)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(settings=settings)
    dp.update.outer_middleware(DbSessionMiddleware(sessionmaker))
    dp.include_routers(admin.router, channel.router, user.router)

    http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    tron = TronGridClient(http, api_key=settings.trongrid_api_key)
    workers = [
        asyncio.create_task(payment_watcher.run(bot, sessionmaker, tron, settings)),
        asyncio.create_task(scheduler.run(bot, sessionmaker, settings)),
    ]
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        for task in workers:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await http.close()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
