"""
bot.py — Telegram-бот с LLM + MCP tool calling.
Запуск: python bot.py
"""
import asyncio
import json
import logging
import os
import sys

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from openai import AsyncOpenAI

sys.path.insert(0, os.path.dirname(__file__))
from config import BOT_TOKEN, PROVIDERS, DEFAULT_PROVIDER, DEFAULT_MODEL, DEFAULT_TEMPERATURE
from mcp_client import call_tool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

# ─── Прокси (для регионов с блокировкой Telegram) ────────────────────────────
PROXY_URL = os.getenv("TELEGRAM_PROXY_URL")  # например: socks5://127.0.0.1:1080

if PROXY_URL:
    from aiohttp import ClientSession
    from aiogram.client.session.aiohttp import AiohttpSession
    session = AiohttpSession(proxy=PROXY_URL)
    bot = Bot(token=BOT_TOKEN, session=session)
    logger.info("Proxy enabled: %s", PROXY_URL)
else:
    bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()

# ─── Состояние пользователей ──────────────────────────────────────────────────
# user_id -> {provider_key, model_key, temperature, history}
user_state: dict[int, dict] = {}

def get_state(user_id: int) -> dict:
    if user_id not in user_state:
        user_state[user_id] = {
            "provider_key": DEFAULT_PROVIDER,
            "model_key": DEFAULT_MODEL,
            "temperature": DEFAULT_TEMPERATURE,
            "history": [],
        }
    return user_state[user_id]

# ─── MCP Tools definition для LLM ────────────────────────────────────────────

LLM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_products",
            "description": "Показать все товары из базы данных",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_product",
            "description": "Найти товары по имени",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_products_by_category",
            "description": "Найти товары по категории",
            "parameters": {
                "type": "object",
                "properties": {"category": {"type": "string"}},
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_by_id",
            "description": "Получить товар по его ID",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "integer"}},
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_products",
            "description": "Найти похожие товары из той же категории по ID товара",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_product",
            "description": "Добавить новый товар в базу данных",
            "parameters": {
                "type": "object",
                "properties": {
                    "name":     {"type": "string"},
                    "category": {"type": "string"},
                    "price":    {"type": "number"},
                    "quantity": {"type": "integer"},
                },
                "required": ["name", "category", "price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Вычислить математическое выражение",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_crypto_price",
            "description": "Получить текущую цену криптовалюты (bitcoin, ethereum, solana, toncoin, dogecoin и др.)",
            "parameters": {
                "type": "object",
                "properties": {"coin_id": {"type": "string", "description": "ID монеты на CoinGecko"}},
                "required": ["coin_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_games",
            "description": "Найти видеоигры по названию через RAWG",
            "parameters": {
                "type": "object",
                "properties": {
                    "query":     {"type": "string"},
                    "page_size": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "translate_text",
            "description": "Перевести текст через LibreTranslate",
            "parameters": {
                "type": "object",
                "properties": {
                    "text":        {"type": "string"},
                    "source_lang": {"type": "string", "description": "auto, en, ru, de, fr, es, zh"},
                    "target_lang": {"type": "string", "description": "ru, en, de, fr, es, zh"},
                },
                "required": ["text"],
            },
        },
    },
]

SYSTEM_PROMPT = """Ты — умный помощник для работы с базой данных товаров.
Ты можешь использовать следующие инструменты:
- list_products — показать все товары
- find_product — найти товары по имени (требует параметр "name")
- find_products_by_category — найти товары по категории (требует параметр "category")
- get_product_by_id — получить товар по ID (требует параметр "product_id")
- find_similar_products — похожие товары по ID (требует параметр "product_id", опционально "limit")
- add_product — добавить товар (требует параметры "name", "category", "price", опционально "quantity")
- calculate — вычислить математическое выражение (требует параметр "expression")
- get_crypto_price — цена криптовалюты (требует параметр "coin_id": bitcoin/ethereum/solana/toncoin/dogecoin)
- search_games — поиск игр через RAWG (требует параметр "query")
- translate_text — перевод текста (требует параметр "text", опционально "source_lang", "target_lang")

Когда пользователь просит что-то сделать, определи, какой инструмент нужен, и верни JSON в формате:
{"tool": "название_инструмента", "arguments": {"параметр": "значение"}}

Если инструмент не нужен, просто ответь пользователю обычным текстом.

Примеры:
"покажи все товары" → {"tool": "list_products", "arguments": {}}
"найди чай" → {"tool": "find_product", "arguments": {"name": "чай"}}
"покажи товары в категории электроника" → {"tool": "find_products_by_category", "arguments": {"category": "Электроника"}}
"найди все товары категории одежда" → {"tool": "find_products_by_category", "arguments": {"category": "Одежда"}}
"товар с ID 5" → {"tool": "get_product_by_id", "arguments": {"product_id": 5}}
"похожие на товар 5" → {"tool": "find_similar_products", "arguments": {"product_id": 5}}
"добавь товар яблоки 120 фрукт" → {"tool": "add_product", "arguments": {"name": "яблоки", "category": "фрукт", "price": 120}}
"сколько будет 2+2*2:2^2-2" → {"tool": "calculate", "arguments": {"expression": "2+2*2/2**2-2"}}
"курс биткоина" → {"tool": "get_crypto_price", "arguments": {"coin_id": "bitcoin"}}
"найди игру witcher" → {"tool": "search_games", "arguments": {"query": "witcher"}}
"переведи hello на русский" → {"tool": "translate_text", "arguments": {"text": "hello", "source_lang": "en", "target_lang": "ru"}}

Отвечай на русском языке, будь дружелюбным и полезным. Если запрос непонятен — уточни."""

# ─── Управление историей ─────────────────────────────────────────────────────

MAX_HISTORY_MESSAGES = 20  # максимум пар user/assistant в истории (не считая system)

def trim_history(history: list) -> None:
    """Обрезает историю, оставляя system prompt + последние MAX_HISTORY_MESSAGES сообщений."""
    # Отделяем system prompt
    system = [m for m in history if m["role"] == "system"]
    rest = [m for m in history if m["role"] != "system"]

    # Считаем только user/assistant пары, tool-сообщения идут вместе с assistant
    if len(rest) > MAX_HISTORY_MESSAGES * 2:
        rest = rest[-(MAX_HISTORY_MESSAGES * 2):]
        # Убеждаемся что не начинаем с tool или assistant (должен быть user)
        while rest and rest[0]["role"] != "user":
            rest = rest[1:]
        history.clear()
        history.extend(system + rest)

def history_summary(history: list) -> str:
    """Возвращает читаемую сводку истории диалога."""
    messages = [m for m in history if m["role"] in ("user", "assistant")]
    if not messages:
        return "История диалога пуста."
    lines = [f"📋 История диалога ({len(messages)} сообщений):\n"]
    for m in messages[-10:]:  # показываем последние 10
        role_icon = "👤" if m["role"] == "user" else "🤖"
        content = str(m.get("content") or "")
        preview = content[:80] + "..." if len(content) > 80 else content
        lines.append(f"{role_icon} {preview}")
    if len(messages) > 10:
        lines.insert(1, f"(показаны последние 10 из {len(messages)})\n")
    return "\n".join(lines)

def format_products(products: list) -> str:
    if not products:
        return "📭 Товары не найдены."
    total = len(products)
    shown = products[:30]  # показываем не более 30, остальное — сводка
    lines = [f"📦 Найдено товаров: {total}\n"]
    for p in shown:
        qty = p.get('quantity', 0)
        stock = f"склад: {qty} шт." if qty > 0 else "нет в наличии"
        lines.append(f"• [#{p['id']}] {p['name']} — {p['category']} — {p['price']:.2f} руб. ({stock})")
    if total > 30:
        lines.append(f"\n...и ещё {total - 30} товаров. Уточните запрос для более точного поиска.")
    return "\n".join(lines)

def format_tool_result(tool_name: str, result) -> str:
    if tool_name in ("list_products", "find_product", "find_products_by_category", "find_similar_products"):
        return format_products(result if isinstance(result, list) else [])
    if tool_name == "get_product_by_id" and isinstance(result, dict):
        qty = result.get('quantity', 0)
        stock = f"{qty} шт." if qty > 0 else "нет в наличии"
        return (f"📦 Товар #{result['id']}\n"
                f"Название: {result['name']}\n"
                f"Категория: {result['category']}\n"
                f"Цена: {result['price']:.2f} руб.\n"
                f"На складе: {stock}")
    if tool_name == "add_product" and isinstance(result, dict):
        return (f"✅ Товар добавлен:\n"
                f"• [{result['id']}] {result['name']} — {result['category']} — "
                f"{result['price']:.2f} руб. (кол-во: {result.get('quantity', 0)})")
    if tool_name == "calculate" and isinstance(result, dict):
        return f"🧮 {result['expression']} = {result['result']}"
    if tool_name == "get_crypto_price" and isinstance(result, dict):
        change = result.get('change_24h')
        change_str = f" ({change:+.2f}% за 24ч)" if change is not None else ""
        return (f"💰 {result['coin'].upper()}\n"
                f"USD: ${result['usd']:,.2f}{change_str}\n"
                f"RUB: {result['rub']:,.0f} руб.")
    if tool_name == "search_games" and isinstance(result, list):
        if not result:
            return "🎮 Игры не найдены."
        lines = ["🎮 Найденные игры:\n"]
        for g in result:
            genres = ", ".join(g.get("genres", [])) or "—"
            platforms = ", ".join(g.get("platforms", [])) or "—"
            rating = g.get("rating") or "—"
            lines.append(f"• {g['name']} ({g.get('released', '?')})\n"
                         f"  Рейтинг: {rating} | Жанры: {genres}\n"
                         f"  Платформы: {platforms}")
        return "\n".join(lines)
    if tool_name == "translate_text" and isinstance(result, dict):
        return (f"🌐 Перевод ({result['source_lang']} → {result['target_lang']}):\n"
                f"{result['translated']}")
    return str(result)

# ─── LLM + Tool calling ───────────────────────────────────────────────────────

async def process_with_llm(user_id: int, user_text: str) -> str:
    state = get_state(user_id)
    provider = PROVIDERS[state["provider_key"]]
    model = provider["models"][state["model_key"]]

    client = AsyncOpenAI(api_key=provider["api_key"], base_url=provider["base_url"])

    history = state["history"]
    if not history:
        history.append({"role": "system", "content": SYSTEM_PROMPT})

    history.append({"role": "user", "content": user_text})

    # Первый запрос к LLM
    response = await client.chat.completions.create(
        model=model["id"],
        messages=history,
        tools=LLM_TOOLS,
        tool_choice="auto",
        temperature=state["temperature"],
        max_tokens=model["max_tokens"],
    )

    msg = response.choices[0].message
    finish_reason = response.choices[0].finish_reason

    # Если LLM хочет вызвать инструмент
    if finish_reason == "tool_calls" and msg.tool_calls:
        # Сериализуем assistant message с tool_calls вручную для совместимости
        assistant_entry = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        history.append(assistant_entry)

        tool_results = []
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
                result = await call_tool(tool_name, args)
                result_str = format_tool_result(tool_name, result)
            except Exception as e:
                result_str = f"Ошибка при вызове {tool_name}: {e}"
                logger.error("Tool call error: %s", e)

            tool_results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str,
            })

        history.extend(tool_results)

        # Второй запрос — финальный ответ
        response2 = await client.chat.completions.create(
            model=model["id"],
            messages=history,
            temperature=state["temperature"],
            max_tokens=model["max_tokens"],
        )
        final_text = response2.choices[0].message.content or ""
        history.append({"role": "assistant", "content": final_text})
        trim_history(history)
        return final_text

    # Обычный ответ без tool calling
    final_text = msg.content or "Не удалось получить ответ."
    history.append({"role": "assistant", "content": final_text})
    trim_history(history)
    return final_text

# ─── Клавиатуры ───────────────────────────────────────────────────────────────

def provider_keyboard():
    builder = InlineKeyboardBuilder()
    for key, p in PROVIDERS.items():
        builder.button(text=p["name"], callback_data=f"provider:{key}")
    builder.adjust(1)
    return builder.as_markup()

def model_keyboard(provider_key: str):
    builder = InlineKeyboardBuilder()
    for key, m in PROVIDERS[provider_key]["models"].items():
        builder.button(text=m["label"], callback_data=f"model:{provider_key}:{key}")
    builder.adjust(1)
    return builder.as_markup()

# ─── Handlers ─────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message):
    state = get_state(message.from_user.id)
    p = PROVIDERS[state["provider_key"]]
    m = p["models"][state["model_key"]]
    await message.answer(
        f"👋 Привет! Я бот-помощник магазина.\n\n"
        f"🤖 Провайдер: *{p['name']}*\n"
        f"🧠 Модель: *{m['label']}*\n"
        f"🌡 Температура: *{state['temperature']}*\n\n"
        f"Просто напиши мне что-нибудь, например:\n"
        f"• _покажи все товары_\n"
        f"• _найди чай_\n"
        f"• _добавь товар: яблоки, фрукты, 120_\n"
        f"• _посчитай 15 * 8 + 42_\n\n"
        f"Команды: /settings — настройки, /new — очистить историю, /history — показать историю",
        parse_mode="Markdown"
    )

@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    await message.answer("Выберите AI-провайдера:", reply_markup=provider_keyboard())

@dp.message(Command("new"))
async def cmd_new(message: Message):
    state = get_state(message.from_user.id)
    state["history"].clear()
    await message.answer("🔄 История очищена. Начинаем заново!")

@dp.message(Command("history"))
async def cmd_history(message: Message):
    state = get_state(message.from_user.id)
    await message.answer(history_summary(state["history"]))

@dp.callback_query(F.data.startswith("provider:"))
async def cb_provider(callback: CallbackQuery):
    provider_key = callback.data.split(":")[1]
    await callback.message.edit_text(
        f"Провайдер: *{PROVIDERS[provider_key]['name']}*\nВыберите модель:",
        reply_markup=model_keyboard(provider_key),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("model:"))
async def cb_model(callback: CallbackQuery):
    _, provider_key, model_key = callback.data.split(":")
    state = get_state(callback.from_user.id)
    state["provider_key"] = provider_key
    state["model_key"] = model_key
    state["history"].clear()

    p = PROVIDERS[provider_key]
    m = p["models"][model_key]
    await callback.message.edit_text(
        f"✅ Настройки сохранены:\n"
        f"🤖 Провайдер: *{p['name']}*\n"
        f"🧠 Модель: *{m['label']}*",
        parse_mode="Markdown"
    )
    await callback.answer("Готово!")

@dp.message()
async def handle_message(message: Message):
    user_id = message.from_user.id
    text = message.text or ""
    if not text.strip():
        return

    thinking = await message.answer("⏳ Думаю...")
    try:
        reply = await process_with_llm(user_id, text)
        await thinking.delete()
        # Telegram ограничивает сообщение 4096 символами — разбиваем на части
        if len(reply) <= 4096:
            await message.answer(reply)
        else:
            for i in range(0, len(reply), 4096):
                await message.answer(reply[i:i + 4096])
    except Exception as e:
        logger.error("Error processing message: %s", e)
        try:
            await thinking.edit_text(f"❌ Ошибка: {e}")
        except Exception:
            await message.answer(f"❌ Ошибка: {e}")

# ─── Запуск ───────────────────────────────────────────────────────────────────

async def main():
    logger.info("Bot starting...")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        handle_signals=True,
        close_bot_session=True,
    )

if __name__ == "__main__":
    asyncio.run(main())
