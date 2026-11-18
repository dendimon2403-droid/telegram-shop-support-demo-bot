import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import llm  # noqa: E402
from bot.catalog import PRODUCTS, money, products_in  # noqa: E402
from bot.config import Settings  # noqa: E402
from bot.db import Database  # noqa: E402


def make_db() -> Database:
    return Database(":memory:")


def mock_settings() -> Settings:
    return Settings("", None, "mock", "", "", "", Path("data"))


# ---- cart ----
def test_cart_add_increment_and_remove():
    db = make_db()
    assert db.cart_add(1, "v60") == 1
    assert db.cart_add(1, "v60") == 2
    assert db.cart_add(1, "v60", -1) == 1
    assert db.cart_add(1, "v60", -1) == 0
    assert db.cart_items(1) == []


def test_cart_is_per_user():
    db = make_db()
    db.cart_add(1, "v60")
    db.cart_add(2, "hand", 3)
    assert db.cart_items(1) == [("v60", 1)]
    assert db.cart_items(2) == [("hand", 3)]


def test_cart_persists_until_cleared():
    db = make_db()
    db.cart_add(1, "v60")
    db.cart_add(1, "eth", 2)
    assert len(db.cart_items(1)) == 2
    db.cart_clear(1)
    assert db.cart_items(1) == []


# ---- orders ----
def test_order_lifecycle():
    db = make_db()
    oid = db.create_order(1, "Ann", "+37369123456", "Main st 1", "V60 × 1", 1800)
    assert db.get_order(oid)["status"] == "new"
    db.set_receipt(oid, "data/receipts/order_1.jpg")
    db.set_status(oid, "done")
    row = db.get_order(oid)
    assert row["status"] == "done" and row["receipt_path"].endswith("order_1.jpg")
    assert db.stats()["orders"] == 1


# ---- support history ----
def test_history_is_per_chat_and_resettable():
    db = make_db()
    db.add_message(10, 1, "user", "hi")
    db.add_message(10, 1, "assistant", "hello")
    db.add_message(20, 2, "user", "other chat")
    assert [m["content"] for m in db.history(10)] == ["hi", "hello"]
    assert db.reset_history(10) == 2
    assert db.history(10) == []
    assert len(db.history(20)) == 1


def test_history_limit_keeps_latest_in_order():
    db = make_db()
    for i in range(15):
        db.add_message(1, 1, "user", f"m{i}")
    assert [m["content"] for m in db.history(1, limit=3)] == ["m12", "m13", "m14"]


def test_mode_roundtrip():
    db = make_db()
    assert db.get_mode(5) == "menu"
    db.set_mode(5, "support")
    assert db.get_mode(5) == "support"


# ---- llm ----
def test_normalize_drops_leading_assistant_and_merges_user_turns():
    hist = [
        {"role": "assistant", "content": "old"},
        {"role": "user", "content": "a"},
        {"role": "user", "content": "b"},
        {"role": "assistant", "content": "c"},
        {"role": "user", "content": "d"},
    ]
    assert llm.normalize(hist) == [
        {"role": "user", "content": "a\nb"},
        {"role": "assistant", "content": "c"},
        {"role": "user", "content": "d"},
    ]


def test_mock_answers_faq_and_has_default():
    s = mock_settings()
    shipping = asyncio.run(llm.ask(s, [{"role": "user", "content": "How long is shipping?"}]))
    assert "2-5 business days" in shipping
    other = asyncio.run(llm.ask(s, [{"role": "user", "content": "asdf"}]))
    assert "demo support assistant" in other


def test_unknown_provider_raises():
    s = Settings("", None, "nope", "key", "m", "", Path("data"))
    try:
        asyncio.run(llm.ask(s, [{"role": "user", "content": "x"}]))
    except ValueError as exc:
        assert "Unknown LLM_PROVIDER" in str(exc)
    else:
        raise AssertionError("expected ValueError")


# ---- catalog ----
def test_catalog_is_consistent():
    assert all(p.category in {"brew", "grind", "beans"} for p in PRODUCTS.values())
    assert len(products_in("brew")) == 3
    assert money(1800) == "$18.00"
