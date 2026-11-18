"""Small SQLite layer. Synchronous on purpose: queries are tiny and local."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_mode (
    chat_id INTEGER PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'menu'
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);
CREATE TABLE IF NOT EXISTS cart (
    user_id INTEGER NOT NULL,
    product_id TEXT NOT NULL,
    qty INTEGER NOT NULL,
    PRIMARY KEY (user_id, product_id)
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    address TEXT NOT NULL,
    items TEXT NOT NULL,
    total_cents INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    receipt_path TEXT,
    ts INTEGER NOT NULL
);
"""


class Database:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---- mode ----
    def set_mode(self, chat_id: int, mode: str) -> None:
        self.conn.execute(
            "INSERT INTO chat_mode(chat_id, mode) VALUES(?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET mode = excluded.mode",
            (chat_id, mode),
        )
        self.conn.commit()

    def get_mode(self, chat_id: int) -> str:
        row = self.conn.execute(
            "SELECT mode FROM chat_mode WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return row["mode"] if row else "menu"

    # ---- support history ----
    def add_message(self, chat_id: int, user_id: int, role: str, content: str) -> None:
        self.conn.execute(
            "INSERT INTO messages(chat_id, user_id, role, content, ts) VALUES(?,?,?,?,?)",
            (chat_id, user_id, role, content, int(time.time())),
        )
        self.conn.commit()

    def history(self, chat_id: int, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def reset_history(self, chat_id: int) -> int:
        cur = self.conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        self.conn.commit()
        return cur.rowcount

    def stats(self) -> dict:
        c = self.conn
        return {
            "chats": c.execute("SELECT COUNT(DISTINCT chat_id) FROM messages").fetchone()[0],
            "messages": c.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
            "orders": c.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        }

    # ---- cart ----
    def cart_add(self, user_id: int, product_id: str, delta: int = 1) -> int:
        row = self.conn.execute(
            "SELECT qty FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id)
        ).fetchone()
        qty = (row["qty"] if row else 0) + delta
        if qty <= 0:
            self.conn.execute(
                "DELETE FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id)
            )
            qty = 0
        else:
            self.conn.execute(
                "INSERT INTO cart(user_id, product_id, qty) VALUES(?,?,?) "
                "ON CONFLICT(user_id, product_id) DO UPDATE SET qty = excluded.qty",
                (user_id, product_id, qty),
            )
        self.conn.commit()
        return qty

    def cart_remove(self, user_id: int, product_id: str) -> None:
        self.conn.execute(
            "DELETE FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id)
        )
        self.conn.commit()

    def cart_items(self, user_id: int) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT product_id, qty FROM cart WHERE user_id = ? ORDER BY product_id", (user_id,)
        ).fetchall()
        return [(r["product_id"], r["qty"]) for r in rows]

    def cart_clear(self, user_id: int) -> None:
        self.conn.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        self.conn.commit()

    # ---- orders ----
    def create_order(
        self, user_id: int, name: str, phone: str, address: str, items_text: str, total_cents: int
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO orders(user_id, name, phone, address, items, total_cents, ts) "
            "VALUES(?,?,?,?,?,?,?)",
            (user_id, name, phone, address, items_text, total_cents, int(time.time())),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def set_receipt(self, order_id: int, path: str) -> None:
        self.conn.execute("UPDATE orders SET receipt_path = ? WHERE id = ?", (path, order_id))
        self.conn.commit()

    def set_status(self, order_id: int, status: str) -> None:
        self.conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        self.conn.commit()

    def recent_orders(self, limit: int = 10) -> Iterable[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def get_order(self, order_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
