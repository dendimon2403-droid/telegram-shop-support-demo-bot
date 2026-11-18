# Demo Telegram bot: Shop + AI Support

One Telegram bot with two modes, built with Python 3.11+, aiogram 3 and SQLite.
It is a portfolio demo of the building blocks used in real bot projects.

**Shop mode (`/shop`)**
- Catalog with categories, a photo, description and price for every product
- Cart that survives restarts (stored per user in SQLite): add, +/-, remove
- Checkout wizard (name, phone, address) with input validation, `/cancel` at any time
- Payment receipt upload, saved to disk next to the order
- Admin view (`/admin`): recent orders, "mark done" button, new-order notifications

**Support mode (`/support`)**
- AI assistant that remembers the last messages of each chat (SQLite), `/reset` clears them
- Provider-agnostic: Anthropic, OpenAI-compatible APIs, or a keyless `mock` mode for demos
- Graceful errors: if the AI service is down the user gets a clear message, not a crash

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then put your BOT_TOKEN from @BotFather into .env
python -m bot.main
```

Open your bot in Telegram and send `/start`.

Tip: instead of `.env` you can put the token alone on the first line of a file named `token.txt`.

### Settings (`.env`)

| Variable | Meaning |
|---|---|
| `BOT_TOKEN` | Token from @BotFather (required) |
| `ADMIN_ID` | Your numeric Telegram id (from @userinfobot): enables `/admin` and order notifications |
| `LLM_PROVIDER` | `mock` (default, no key), `anthropic` or `openai` |
| `LLM_API_KEY` | API key for the chosen provider |
| `LLM_MODEL` | Optional model override |
| `LLM_BASE_URL` | Optional, for OpenAI-compatible servers |
| `DATA_DIR` | Folder for the database and receipts (default `data`) |

### Docker / VPS

```bash
docker compose up -d --build
docker compose logs -f
```

Data lives in `./data`, so the bot keeps carts and orders across restarts.
Without Docker, a systemd unit running `python -m bot.main` with `Restart=always` does the same.

## Tests

```bash
pytest -q
```

The tests cover the cart, orders, per-chat history, mode switching, LLM history
normalisation and the mock provider. They run without a Telegram token or network.

## Project layout

```
bot/
  main.py      entry point, menu, polling
  shop.py      catalog, cart, checkout FSM, receipts, admin
  support.py   AI support mode
  llm.py       Anthropic / OpenAI-compatible / mock provider
  db.py        SQLite layer
  catalog.py   demo products
tests/         pytest suite
```

## Notes

- Product photos in the demo catalog are placeholder images fetched by Telegram from a URL;
  if a URL is unreachable the bot falls back to a text card.
- Replace `bot/catalog.py` with your own products (or load them from a database) to reuse it.
