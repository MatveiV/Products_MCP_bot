"""
server.py — MCP-совместимый сервер на FastAPI.
Запуск: python server.py
"""
import sys
import os
import logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("server.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("mcp_server")

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn

from db import init_db
from tools import (
    list_products, find_product, find_products_by_category,
    get_product_by_id, find_similar_products,
    add_product, calculate,
    get_crypto_price, search_games, translate_text,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("product-mcp server started. DB ready.")
    yield

app = FastAPI(title="product-mcp", version="1.0.0", lifespan=lifespan)


# ─── MCP Schema ───────────────────────────────────────────────────────────────

MCP_SCHEMA = {
    "name": "product-mcp",
    "version": "1.0.0",
    "description": "MCP сервер: товары, калькулятор, крипта, игры, перевод",
    "tools": [
        {
            "name": "list_products",
            "description": "Возвращает список всех товаров",
            "inputSchema": {"type": "object", "properties": {}, "required": []}
        },
        {
            "name": "find_product",
            "description": "Ищет товары по совпадению имени",
            "inputSchema": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Строка для поиска"}},
                "required": ["name"]
            }
        },
        {
            "name": "find_products_by_category",
            "description": "Ищет товары по категории",
            "inputSchema": {
                "type": "object",
                "properties": {"category": {"type": "string", "description": "Название категории"}},
                "required": ["category"]
            }
        },
        {
            "name": "get_product_by_id",
            "description": "Возвращает товар по ID",
            "inputSchema": {
                "type": "object",
                "properties": {"product_id": {"type": "integer", "description": "ID товара"}},
                "required": ["product_id"]
            }
        },
        {
            "name": "find_similar_products",
            "description": "Возвращает похожие товары из той же категории по ID товара",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "ID товара"},
                    "limit": {"type": "integer", "description": "Количество результатов (по умолчанию 5)"}
                },
                "required": ["product_id"]
            }
        },
        {
            "name": "add_product",
            "description": "Добавляет новый товар",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name":     {"type": "string"},
                    "category": {"type": "string"},
                    "price":    {"type": "number"},
                    "quantity": {"type": "integer", "description": "Количество на складе"}
                },
                "required": ["name", "category", "price"]
            }
        },
        {
            "name": "calculate",
            "description": "Безопасный калькулятор математических выражений",
            "inputSchema": {
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "Например: 2 + 2 * 10"}},
                "required": ["expression"]
            }
        },
        {
            "name": "get_crypto_price",
            "description": "Получает текущую цену криптовалюты (CoinGecko, бесплатно)",
            "inputSchema": {
                "type": "object",
                "properties": {"coin_id": {"type": "string", "description": "ID монеты: bitcoin, ethereum, solana, toncoin, dogecoin"}},
                "required": ["coin_id"]
            }
        },
        {
            "name": "search_games",
            "description": "Ищет видеоигры через RAWG API (бесплатно)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Название игры для поиска"},
                    "page_size": {"type": "integer", "description": "Количество результатов (макс 10)"}
                },
                "required": ["query"]
            }
        },
        {
            "name": "translate_text",
            "description": "Переводит текст через LibreTranslate (бесплатно, без ключа)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text":        {"type": "string", "description": "Текст для перевода"},
                    "source_lang": {"type": "string", "description": "Язык источника: auto, en, ru, de, fr, es, zh"},
                    "target_lang": {"type": "string", "description": "Язык назначения: ru, en, de, fr, es, zh"}
                },
                "required": ["text"]
            }
        },
    ]
}


@app.get("/mcp/schema")
def get_schema():
    return JSONResponse(MCP_SCHEMA)


# ─── Pydantic модели ──────────────────────────────────────────────────────────

class FindRequest(BaseModel):
    name: str

class FindByCategoryRequest(BaseModel):
    category: str

class ProductIdRequest(BaseModel):
    product_id: int

class SimilarRequest(BaseModel):
    product_id: int
    limit: int = 5

class AddRequest(BaseModel):
    name: str
    category: str
    price: float
    quantity: int = 0

class CalcRequest(BaseModel):
    expression: str

class CryptoRequest(BaseModel):
    coin_id: str

class GamesRequest(BaseModel):
    query: str
    page_size: int = 5

class TranslateRequest(BaseModel):
    text: str
    source_lang: str = "auto"
    target_lang: str = "ru"


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/tools/list_products")
def tool_list_products():
    return {"result": list_products()}

@app.post("/tools/find_product")
def tool_find_product(req: FindRequest):
    return {"result": find_product(req.name)}

@app.post("/tools/find_products_by_category")
def tool_find_products_by_category(req: FindByCategoryRequest):
    return {"result": find_products_by_category(req.category)}

@app.post("/tools/get_product_by_id")
def tool_get_product_by_id(req: ProductIdRequest):
    result = get_product_by_id(req.product_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Товар с ID {req.product_id} не найден")
    return {"result": result}

@app.post("/tools/find_similar_products")
def tool_find_similar_products(req: SimilarRequest):
    return {"result": find_similar_products(req.product_id, req.limit)}

@app.post("/tools/add_product")
def tool_add_product(req: AddRequest):
    return {"result": add_product(req.name, req.category, req.price, req.quantity)}

@app.post("/tools/calculate")
def tool_calculate(req: CalcRequest):
    try:
        return {"result": calculate(req.expression)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/tools/get_crypto_price")
async def tool_get_crypto_price(req: CryptoRequest):
    try:
        return {"result": await get_crypto_price(req.coin_id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка CoinGecko: {e}")

@app.post("/tools/search_games")
async def tool_search_games(req: GamesRequest):
    try:
        return {"result": await search_games(req.query, req.page_size)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка RAWG: {e}")

@app.post("/tools/translate_text")
async def tool_translate_text(req: TranslateRequest):
    try:
        return {"result": await translate_text(req.text, req.source_lang, req.target_lang)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка LibreTranslate: {e}")


# ─── Универсальный /mcp/call ──────────────────────────────────────────────────

class MCPCallRequest(BaseModel):
    tool: str
    arguments: Optional[dict] = {}

@app.post("/mcp/call")
async def mcp_call(req: MCPCallRequest):
    args = req.arguments or {}
    try:
        if req.tool == "list_products":
            return {"result": list_products()}
        elif req.tool == "find_product":
            return {"result": find_product(args["name"])}
        elif req.tool == "find_products_by_category":
            return {"result": find_products_by_category(args["category"])}
        elif req.tool == "get_product_by_id":
            result = get_product_by_id(int(args["product_id"]))
            if result is None:
                raise HTTPException(status_code=404, detail=f"Товар с ID {args['product_id']} не найден")
            return {"result": result}
        elif req.tool == "find_similar_products":
            return {"result": find_similar_products(int(args["product_id"]), int(args.get("limit", 5)))}
        elif req.tool == "add_product":
            return {"result": add_product(args["name"], args["category"], float(args["price"]), int(args.get("quantity", 0)))}
        elif req.tool == "calculate":
            return {"result": calculate(args["expression"])}
        elif req.tool == "get_crypto_price":
            try:
                return {"result": await get_crypto_price(args["coin_id"])}
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Ошибка CoinGecko: {e}")
        elif req.tool == "search_games":
            try:
                return {"result": await search_games(args["query"], int(args.get("page_size", 5)))}
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Ошибка RAWG: {e}")
        elif req.tool == "translate_text":
            try:
                return {"result": await translate_text(args["text"], args.get("source_lang", "auto"), args.get("target_lang", "ru"))}
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Ошибка LibreTranslate: {e}")
        else:
            raise HTTPException(status_code=404, detail=f"Инструмент '{req.tool}' не найден")
    except HTTPException:
        raise
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"Отсутствует параметр: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
