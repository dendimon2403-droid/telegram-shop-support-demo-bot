"""Shop mode: catalog -> cart -> checkout (FSM) -> receipt upload, plus a tiny admin view."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .catalog import CATEGORIES, PRODUCTS, money, products_in
from .config import Settings
from .db import Database

log = logging.getLogger(__name__)
router = Router(name="shop")

PHONE_RE = re.compile(r"^\+?[0-9 ()\-]{7,20}$")


class Checkout(StatesGroup):
    name = State()
    phone = State()
    address = State()
    receipt = State()


# ---------- helpers ----------
async def show(cb: CallbackQuery, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    """Edit the message if possible (it may be a photo card), otherwise replace it."""
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "not modified" in str(exc):
            return
        try:
            await cb.message.delete()
        except TelegramBadRequest:
            pass
        await cb.message.answer(text, reply_markup=kb)


def categories_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for cid, title in CATEGORIES.items():
        b.button(text=title, callback_data=f"shop:cat:{cid}")
    b.button(text="🛒 Cart", callback_data="shop:cart")
    b.button(text="⬅️ Menu", callback_data="mode:menu")
    b.adjust(1)
    return b.as_markup()


def cart_lines(db: Database, user_id: int) -> tuple[list[str], int]:
    lines, total = [], 0
    for pid, qty in db.cart_items(user_id):
        p = PRODUCTS.get(pid)
        if not p:
            continue
        subtotal = p.price_cents * qty
        total += subtotal
        lines.append(f"{p.name} × {qty} — {money(subtotal)}")
    return lines, total


def cart_view(db: Database, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    lines, total = cart_lines(db, user_id)
    b = InlineKeyboardBuilder()
    if not lines:
        b.button(text="🛍 Browse catalog", callback_data="shop:cats")
        b.adjust(1)
        return "Your cart is empty.", b.as_markup()
    for pid, qty in db.cart_items(user_id):
        p = PRODUCTS[pid]
        b.button(text="➖", callback_data=f"shop:dec:{pid}")
        b.button(text=f"{p.name[:18]} ({qty})", callback_data="shop:noop")
        b.button(text="➕", callback_data=f"shop:inc:{pid}")
        b.button(text="🗑", callback_data=f"shop:del:{pid}")
    b.button(text="✅ Checkout", callback_data="shop:checkout")
    b.button(text="🛍 Keep shopping", callback_data="shop:cats")
    rows = [4] * len(db.cart_items(user_id)) + [1, 1]
    b.adjust(*rows)
    return "🛒 Your cart:\n\n" + "\n".join(lines) + f"\n\nTotal: {money(total)}", b.as_markup()


# ---------- entry ----------
async def open_shop(message: Message, db: Database) -> None:
    db.set_mode(message.chat.id, "shop")
    await message.answer("🛍 Demo Store — pick a category:", reply_markup=categories_kb())


@router.message(Command("shop"))
async def cmd_shop(message: Message, db: Database) -> None:
    await open_shop(message, db)


@router.message(Command("cart"))
async def cmd_cart(message: Message, db: Database) -> None:
    text, kb = cart_view(db, message.from_user.id)
    await message.answer(text, reply_markup=kb)


# ---------- browsing ----------
@router.callback_query(F.data == "shop:cats")
async def cb_cats(cb: CallbackQuery, db: Database) -> None:
    db.set_mode(cb.message.chat.id, "shop")
    await show(cb, "🛍 Demo Store — pick a category:", categories_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("shop:cat:"))
async def cb_category(cb: CallbackQuery) -> None:
    cid = cb.data.split(":")[2]
    if cid not in CATEGORIES:
        await cb.answer("Unknown category", show_alert=True)
        return
    b = InlineKeyboardBuilder()
    for p in products_in(cid):
        b.button(text=f"{p.name} — {money(p.price_cents)}", callback_data=f"shop:p:{p.id}")
    b.button(text="⬅️ Categories", callback_data="shop:cats")
    b.adjust(1)
    await show(cb, f"{CATEGORIES[cid]}:", b.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("shop:p:"))
async def cb_product(cb: CallbackQuery) -> None:
    p = PRODUCTS.get(cb.data.split(":")[2])
    if not p:
        await cb.answer("Product not found", show_alert=True)
        return
    b = InlineKeyboardBuilder()
    b.button(text="➕ Add to cart", callback_data=f"shop:add:{p.id}")
    b.button(text="⬅️ Back", callback_data=f"shop:cat:{p.category}")
    b.adjust(1)
    caption = f"{p.name}\n{p.description}\n\nPrice: {money(p.price_cents)}"
    sent = False
    try:
        await cb.message.answer_photo(p.image_url, caption=caption, reply_markup=b.as_markup())
        sent = True
    except Exception:  # photo URL unreachable -> degrade to text
        log.warning("photo failed for %s, falling back to text", p.id)
        await cb.message.answer(caption, reply_markup=b.as_markup())
    if sent:
        try:
            await cb.message.delete()
        except TelegramBadRequest:
            pass
    await cb.answer()


# ---------- cart ----------
@router.callback_query(F.data.startswith("shop:add:"))
async def cb_add(cb: CallbackQuery, db: Database) -> None:
    pid = cb.data.split(":")[2]
    if pid not in PRODUCTS:
        await cb.answer("Product not found", show_alert=True)
        return
    qty = db.cart_add(cb.from_user.id, pid, +1)
    await cb.answer(f"Added. In cart: {qty}")


@router.callback_query(F.data == "shop:cart")
async def cb_cart(cb: CallbackQuery, db: Database) -> None:
    text, kb = cart_view(db, cb.from_user.id)
    await show(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data.regexp(r"^shop:(inc|dec|del):"))
async def cb_cart_change(cb: CallbackQuery, db: Database) -> None:
    _, action, pid = cb.data.split(":")
    if pid in PRODUCTS:
        if action == "del":
            db.cart_remove(cb.from_user.id, pid)
        else:
            db.cart_add(cb.from_user.id, pid, +1 if action == "inc" else -1)
    text, kb = cart_view(db, cb.from_user.id)
    await show(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data == "shop:noop")
async def cb_noop(cb: CallbackQuery) -> None:
    await cb.answer()


# ---------- checkout ----------
@router.callback_query(F.data == "shop:checkout")
async def cb_checkout(cb: CallbackQuery, db: Database, state: FSMContext) -> None:
    if not db.cart_items(cb.from_user.id):
        await cb.answer("Your cart is empty", show_alert=True)
        return
    await state.set_state(Checkout.name)
    await cb.message.answer("Checkout. What's your full name? (send /cancel to stop)")
    await cb.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Nothing to cancel.")
        return
    await state.clear()
    await message.answer("Cancelled. Your cart is still saved (/cart).")


@router.message(Checkout.name, F.text, ~F.text.startswith("/"))
async def step_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2 or len(name) > 80:
        await message.answer("Please send a name between 2 and 80 characters.")
        return
    await state.update_data(name=name)
    await state.set_state(Checkout.phone)
    await message.answer("Phone number? (e.g. +373 69 123 456)")


@router.message(Checkout.phone, F.text, ~F.text.startswith("/"))
async def step_phone(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    if not PHONE_RE.match(phone):
        await message.answer("That doesn't look like a phone number. Try again, e.g. +373 69 123 456")
        return
    await state.update_data(phone=phone)
    await state.set_state(Checkout.address)
    await message.answer("Delivery address?")


@router.message(Checkout.address, F.text, ~F.text.startswith("/"))
async def step_address(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    address = message.text.strip()
    if len(address) < 5:
        await message.answer("Please send a full delivery address.")
        return
    data = await state.get_data()
    lines, total = cart_lines(db, message.from_user.id)
    if not lines:
        await state.clear()
        await message.answer("Your cart is empty, nothing to order.")
        return
    order_id = db.create_order(
        message.from_user.id, data["name"], data["phone"], address, "\n".join(lines), total
    )
    db.cart_clear(message.from_user.id)
    await state.update_data(order_id=order_id)
    await state.set_state(Checkout.receipt)
    await message.answer(
        f"✅ Order #{order_id} created. Total: {money(total)}\n\n"
        "Demo payment: send a photo of your payment receipt (any picture works), "
        "or /skip to finish without it."
    )
    if settings.admin_id:
        try:
            await message.bot.send_message(
                settings.admin_id,
                f"🆕 Order #{order_id} — {money(total)}\n{data['name']}, {data['phone']}\n{address}\n\n"
                + "\n".join(lines),
            )
        except Exception:
            log.exception("could not notify admin")


@router.message(Checkout.receipt, Command("skip"))
async def step_skip(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Done! We'll contact you about your order. /shop to keep browsing.")


@router.message(Checkout.receipt, F.photo)
async def step_receipt(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    data = await state.get_data()
    order_id = data["order_id"]
    settings.receipts_dir.mkdir(parents=True, exist_ok=True)
    path = Path(settings.receipts_dir) / f"order_{order_id}.jpg"
    await message.bot.download(message.photo[-1], destination=path)
    db.set_receipt(order_id, str(path))
    await state.clear()
    await message.answer(f"Receipt saved for order #{order_id}. Thank you! /shop to keep browsing.")
    if settings.admin_id:
        try:
            await message.bot.send_photo(settings.admin_id, message.photo[-1].file_id,
                                         caption=f"Receipt for order #{order_id}")
        except Exception:
            log.exception("could not forward receipt")


@router.message(Checkout.receipt)
async def step_receipt_other(message: Message) -> None:
    await message.answer("Please send a photo of the receipt, or /skip.")


# ---------- admin ----------
def _is_admin(user_id: int, settings: Settings) -> bool:
    return settings.admin_id is not None and user_id == settings.admin_id


@router.message(Command("admin"))
async def cmd_admin(message: Message, db: Database, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        await message.answer("Admin only. Set ADMIN_ID in .env to enable this.")
        return
    orders = list(db.recent_orders(10))
    if not orders:
        await message.answer("No orders yet.")
        return
    for o in orders:
        b = InlineKeyboardBuilder()
        if o["status"] != "done":
            b.button(text="✅ Mark done", callback_data=f"adm:done:{o['id']}")
        await message.answer(
            f"#{o['id']} [{o['status']}] {money(o['total_cents'])}\n"
            f"{o['name']}, {o['phone']}\n{o['address']}\n\n{o['items']}"
            + ("\n📎 receipt saved" if o["receipt_path"] else ""),
            reply_markup=b.as_markup() if o["status"] != "done" else None,
        )


@router.callback_query(F.data.startswith("adm:done:"))
async def cb_admin_done(cb: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(cb.from_user.id, settings):
        await cb.answer("Admin only", show_alert=True)
        return
    order_id = int(cb.data.split(":")[2])
    db.set_status(order_id, "done")
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer(f"Order #{order_id} marked done")
