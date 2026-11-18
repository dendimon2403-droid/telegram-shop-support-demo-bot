"""Entry point: python -m bot.main"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import shop, support
from .config import load_settings
from .db import Database

log = logging.getLogger("bot")

WELCOME = (
    "👋 Hi! This is a demo bot with two modes:\n\n"
    "🛍 Shop — catalog, cart, checkout, receipt upload\n"
    "🤖 Support — AI assistant that remembers the conversation"
)


def menu_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🛍 Shop demo", callback_data="mode:shop")
    b.button(text="🤖 Support demo", callback_data="mode:support")
    b.adjust(1)
    return b.as_markup()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    if not settings.bot_token:
        sys.exit("BOT_TOKEN is empty. Copy .env.example to .env and paste your token from @BotFather.")

    db = Database(settings.db_path)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=None))
    dp = Dispatcher(storage=MemoryStorage(), db=db, settings=settings)

    @dp.message(CommandStart())
    @dp.message(Command("menu"))
    async def start(message: Message) -> None:
        db.set_mode(message.chat.id, "menu")
        await message.answer(WELCOME, reply_markup=menu_kb())

    @dp.callback_query(F.data == "mode:menu")
    async def to_menu(cb: CallbackQuery) -> None:
        db.set_mode(cb.message.chat.id, "menu")
        await cb.message.answer(WELCOME, reply_markup=menu_kb())
        await cb.answer()

    @dp.callback_query(F.data == "mode:shop")
    async def to_shop(cb: CallbackQuery) -> None:
        await cb.answer()
        await shop.open_shop(cb.message, db)

    @dp.callback_query(F.data == "mode:support")
    async def to_support(cb: CallbackQuery) -> None:
        await cb.answer()
        await support.open_support(cb.message, db)

    dp.include_router(shop.router)
    dp.include_router(support.router)

    await bot.set_my_commands(
        [
            BotCommand(command="menu", description="Main menu"),
            BotCommand(command="shop", description="Open the shop"),
            BotCommand(command="cart", description="Show my cart"),
            BotCommand(command="support", description="Talk to AI support"),
            BotCommand(command="reset", description="Clear support conversation"),
            BotCommand(command="cancel", description="Cancel checkout"),
        ]
    )
    me = await bot.get_me()
    log.info("Started as @%s (LLM provider: %s)", me.username, settings.llm_provider)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
