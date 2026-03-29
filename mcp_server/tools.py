"""
tools.py — MCP инструменты: товары, калькулятор, внешние API.
"""
import ast
import operator
import httpx
from db import get_connection

# ─── Безопасный калькулятор ───────────────────────────────────────────────────

_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPS:
            raise ValueError(f"Операция не поддерживается: {op_type.__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if op_type == ast.Div and right == 0:
            raise ValueError("Деление на ноль")
        return _ALLOWED_OPS[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPS:
            raise ValueError(f"Операция не поддерживается: {op_type.__name__}")
        return _ALLOWED_OPS[op_type](_eval_node(node.operand))
    raise ValueError(f"Недопустимое выражение: {ast.dump(node)}")


def safe_eval(expression: str) -> float:
    """Безопасное вычисление математического выражения без eval()."""
    expression = expression.strip()
    if not expression:
        raise ValueError("Выражение не может быть пустым")
    if "=" in expression:
        expression = expression.split("=")[0].strip()
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree.body)
        return float(result)
    except SyntaxError:
        raise ValueError(f"Некорректное выражение: '{expression}'")
    except ValueError:
        raise


# ─── Инструменты для работы с товарами ───────────────────────────────────────

def _row_to_dict(row) -> dict:
    d = dict(row)
    # quantity может отсутствовать в старых записях
    d.setdefault("quantity", 0)
    return d


def list_products() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, category, price, quantity FROM products ORDER BY id"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def find_product(name: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, category, price, quantity FROM products WHERE name LIKE ?",
        (f"%{name}%",)
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def find_products_by_category(category: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, category, price, quantity FROM products WHERE category LIKE ?",
        (f"%{category}%",)
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_product_by_id(product_id: int) -> dict | None:
    """Возвращает товар по точному ID или None если не найден."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, name, category, price, quantity FROM products WHERE id = ?",
        (product_id,)
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def find_similar_products(product_id: int, limit: int = 5) -> list[dict]:
    """Возвращает похожие товары из той же категории (исключая сам товар)."""
    conn = get_connection()
    source = conn.execute(
        "SELECT category FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    if not source:
        conn.close()
        return []
    rows = conn.execute(
        """SELECT id, name, category, price, quantity FROM products
           WHERE category = ? AND id != ?
           ORDER BY ABS(price - (SELECT price FROM products WHERE id = ?))
           LIMIT ?""",
        (source["category"], product_id, product_id, limit)
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def add_product(name: str, category: str, price: float, quantity: int = 0) -> dict:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO products (name, category, price, quantity) VALUES (?, ?, ?, ?)",
        (name, category, price, quantity)
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id, "name": name, "category": category, "price": price, "quantity": quantity}


def calculate(expression: str) -> dict:
    result = safe_eval(expression)
    return {"expression": expression, "result": result}


# ─── Внешние API ──────────────────────────────────────────────────────────────

async def get_crypto_price(coin_id: str) -> dict:
    """
    Получает текущую цену криптовалюты через CoinGecko API (бесплатно, без ключа).
    coin_id: bitcoin, ethereum, solana, toncoin, dogecoin и т.д.
    """
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": coin_id.lower(),
        "vs_currencies": "usd,rub",
        "include_24hr_change": "true",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        raise ValueError(f"CoinGecko API вернул ошибку {e.response.status_code}: {e.response.text[:200]}")
    except httpx.RequestError as e:
        raise ValueError(f"Не удалось подключиться к CoinGecko: {e}")

    if coin_id.lower() not in data:
        raise ValueError(f"Монета '{coin_id}' не найдена. Попробуйте: bitcoin, ethereum, solana, toncoin, dogecoin")
    coin_data = data[coin_id.lower()]
    return {
        "coin": coin_id.lower(),
        "usd": coin_data.get("usd"),
        "rub": coin_data.get("rub"),
        "change_24h": coin_data.get("usd_24h_change"),
    }


async def search_games(query: str, page_size: int = 5) -> list[dict]:
    """
    Ищет игры через RAWG API (бесплатно, без ключа для базовых запросов).
    """
    url = "https://api.rawg.io/api/games"
    params = {
        "search": query,
        "page_size": min(page_size, 10),
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        raise ValueError(f"RAWG API вернул ошибку {e.response.status_code}: {e.response.text[:200]}")
    except httpx.RequestError as e:
        raise ValueError(f"Не удалось подключиться к RAWG: {e}")

    results = []
    for g in data.get("results", []):
        results.append({
            "name": g.get("name"),
            "released": g.get("released"),
            "rating": g.get("rating"),
            "genres": [genre["name"] for genre in g.get("genres", [])],
            "platforms": [p["platform"]["name"] for p in (g.get("platforms") or [])[:4]],
        })
    return results


async def translate_text(text: str, source_lang: str = "auto", target_lang: str = "ru") -> dict:
    """
    Переводит текст через LibreTranslate (публичный инстанс, бесплатно).
    """
    instances = [
        "https://libretranslate.com",
        "https://translate.argosopentech.com",
        "https://libretranslate.de",
    ]
    payload = {
        "q": text,
        "source": source_lang,
        "target": target_lang,
        "format": "text",
    }
    last_error = None
    # follow_redirects=True чтобы корректно обрабатывать 301/302
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for base_url in instances:
            try:
                resp = await client.post(f"{base_url}/translate", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "original": text,
                        "translated": data.get("translatedText", ""),
                        "source_lang": source_lang,
                        "target_lang": target_lang,
                        "instance": base_url,
                    }
                last_error = f"HTTP {resp.status_code} от {base_url}"
            except httpx.RequestError as e:
                last_error = f"{base_url}: {e}"
                continue
    raise ValueError(f"Все инстансы LibreTranslate недоступны. Последняя ошибка: {last_error}")
