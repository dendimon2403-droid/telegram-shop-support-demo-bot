"""AI support mode: per-chat context kept in SQLite, provider-agnostic LLM."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, Filter
from aiogram.types import Message

from . import llm
from .config import Settings
from .db import Database

log = logging.getLogger(__name__)
router = Router(name="support")

FALLBACK = "Sorry, I couldn't reach the AI service right now. Please try again in a minute."


class InMode(Filter):
    def __init__(self, mode: str):
        self.mode = mode

    async def __call__(self, message: Message, db: Database) -> bool:
        return db.get_mode(message.chat.id) == self.mode


async def open_support(message: Message, db: Database) -> None:
    db.set_mode(message.chat.id, "support")
    await message.answer(
        "🤖 Support mode. Ask me anything about delivery, returns or products.\n"
        "/reset clears our conversation, /menu goes back."
    )


@router.message(Command("support"))
async def cmd_support(message: Message, db: Database) -> None:
    await open_support(message, db)


@router.message(Command("reset"))
async def cmd_reset(message: Message, db: Database) -> None:
    n = db.reset_history(message.chat.id)
    await message.answer(f"Conversation cleared ({n} messages removed).")


@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database, settings: Settings) -> None:
    if settings.admin_id is not None and message.from_user.id != settings.admin_id:
        await message.answer("Admin only.")
        return
    s = db.stats()
    await message.answer(
        f"📊 Chats with history: {s['chats']}\nMessages stored: {s['messages']}\nOrders: {s['orders']}"
    )


@router.message(F.text, ~F.text.startswith("/"), InMode("support"))
async def on_text(message: Message, db: Database, settings: Settings) -> None:
    chat_id = message.chat.id
    db.add_message(chat_id, message.from_user.id, "user", message.text)
    await message.bot.send_chat_action(chat_id, "typing")
    try:
        answer = await llm.ask(settings, db.history(chat_id))
    except Exception:
        log.exception("LLM call failed")
        await message.answer(FALLBACK)
        return
    db.add_message(chat_id, message.from_user.id, "assistant", answer)
    await message.answer(answer)
