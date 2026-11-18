"""Provider-agnostic LLM call: Anthropic, OpenAI-compatible, or a keyless mock."""
from __future__ import annotations

from .config import Settings

SYSTEM_PROMPT = (
    "You are a friendly, concise customer-support assistant for 'Demo Store', an online "
    "shop selling coffee gear. Answer in the user's language. Be brief (max 5 sentences). "
    "If you do not know something (order status, exact stock), say so and offer to pass "
    "the question to a human. Never invent policies. Facts you can rely on: free shipping "
    "over $50, delivery 2-5 business days, 30-day returns, support hours 9:00-18:00 UTC."
)

# Keyless fallback so the demo works without any API key.
_FAQ = [
    (("shipping", "delivery", "доставк", "deliver"),
     "Delivery takes 2-5 business days, and shipping is free for orders over $50."),
    (("return", "refund", "возврат", "вернуть"),
     "You can return any item within 30 days of delivery for a full refund."),
    (("hours", "open", "time", "работа", "время"),
     "Our support team is available 9:00-18:00 UTC on weekdays."),
    (("price", "cost", "цена", "стоит"),
     "Prices are listed in the shop section. Send /shop to browse the catalog."),
]


def mock_answer(text: str) -> str:
    low = text.lower()
    for keys, answer in _FAQ:
        if any(k in low for k in keys):
            return answer + " (demo mode: answers come from a built-in FAQ)"
    return (
        "I'm the demo support assistant. Ask me about delivery, returns or support hours. "
        "(demo mode: connect an LLM key to get free-form answers)"
    )


def normalize(history: list[dict]) -> list[dict]:
    """Make a history valid for chat APIs: starts with 'user', roles alternate.

    A trimmed window can start with an assistant turn, and a failed LLM call leaves two
    user turns in a row; both are rejected by some providers.
    """
    out: list[dict] = []
    for m in history:
        if not out and m["role"] != "user":
            continue
        if out and out[-1]["role"] == m["role"]:
            out[-1] = {"role": m["role"], "content": out[-1]["content"] + "\n" + m["content"]}
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out


async def ask(settings: Settings, history: list[dict], system: str = SYSTEM_PROMPT) -> str:
    """history: [{'role': 'user'|'assistant', 'content': str}, ...] ending with a user turn."""
    history = normalize(history)
    provider = settings.llm_provider
    if provider == "mock" or not settings.llm_api_key:
        last = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
        return mock_answer(last)

    if provider not in ("anthropic", "openai"):
        raise ValueError(f"Unknown LLM_PROVIDER: {provider!r} (use anthropic, openai or mock)")

    import httpx  # imported lazily so tests run without it

    async with httpx.AsyncClient(timeout=60) as client:
        if provider == "anthropic":
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.llm_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "max_tokens": 500,
                    "system": system,
                    "messages": history,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text").strip()

        if provider == "openai":
            resp = await client.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": settings.llm_model,
                    "max_tokens": 500,
                    "messages": [{"role": "system", "content": system}, *history],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r} (use anthropic, openai or mock)")
