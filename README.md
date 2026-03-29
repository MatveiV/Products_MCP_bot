# Product MCP Bot

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green)
![aiogram](https://img.shields.io/badge/aiogram-3.x-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Version](https://img.shields.io/badge/version-1.0.0-orange)

## Описание

**Product MCP Bot** — учебный MCP-проект: магазин товаров с Telegram-ботом на базе LLM.

Предметная область — каталог товаров интернет-магазина. Пользователь общается с ботом на естественном языке: ищет товары, добавляет новые, получает курсы криптовалют, ищет игры и переводит текст. Бот использует LLM с function calling для определения нужного инструмента и обращается к MCP-серверу по HTTP.

Компоненты:
- `mcp_server/` — MCP-совместимый сервер (FastAPI + SQLite): инструменты для работы с товарами, калькулятор, интеграции с внешними API
- `telegram_bot/` — Telegram-бот (aiogram 3 + OpenAI-compatible API): системный промпт, история диалога, форматирование ответов

Расширения относительно базового product-mcp:
- инструменты `get_product_by_id`, `find_similar_products`
- внешние API: CoinGecko (крипта), RAWG (игры), LibreTranslate (перевод)
- поддержка 3 AI-провайдеров с выбором модели через `/settings`
- история диалога с автоматической обрезкой (до 20 пар сообщений)
- разбивка длинных ответов на части (лимит Telegram 4096 символов)
- логирование в файл (`bot.log`, `server.log`)
- поддержка прокси для регионов с блокировкой Telegram

---

## Архитектура (C4)

### Уровень 1 — System Context

```mermaid
C4Context
    title System Context — Product MCP Bot

    Person(user, "Пользователь", "Общается с ботом на естественном языке через Telegram")

    System(system, "Product MCP Bot", "Telegram-бот + MCP-сервер: каталог товаров, калькулятор, внешние API")

    System_Ext(telegram, "Telegram API", "Платформа обмена сообщениями")
    System_Ext(llm, "LLM Provider", "Z.AI / ProxyAPI / GenAPI — языковая модель с function calling")
    System_Ext(coingecko, "CoinGecko API", "Котировки криптовалют, бесплатно без ключа")
    System_Ext(rawg, "RAWG API", "База данных видеоигр, бесплатно без ключа")
    System_Ext(libretranslate, "LibreTranslate", "Открытый сервис машинного перевода")

    Rel(user, telegram, "Пишет сообщение")
    Rel(telegram, system, "Webhook / long polling")
    Rel(system, llm, "ChatCompletions API с tool calling")
    Rel(system, coingecko, "GET /simple/price")
    Rel(system, rawg, "GET /api/games")
    Rel(system, libretranslate, "POST /translate (fallback по инстансам)")
    Rel(system, telegram, "Отправляет ответ")
```

### Уровень 2 — Container

```mermaid
C4Container
    title Container Diagram — Product MCP Bot

    Person(user, "Пользователь")

    System_Boundary(bot_sys, "Telegram Bot (telegram_bot/)") {
        Container(bot_py, "bot.py", "Python / aiogram 3", "Обработка сообщений, LLM tool calling, история диалога, форматирование, логирование")
        Container(config_py, "config.py", "Python / python-dotenv", "Конфигурация провайдеров и моделей из .env")
        Container(mcp_client_py, "mcp_client.py", "Python / httpx", "HTTP-клиент для вызова MCP инструментов через /mcp/call")
    }

    System_Boundary(mcp_sys, "MCP Server (mcp_server/)") {
        Container(server_py, "server.py", "Python / FastAPI + uvicorn", "REST API: /mcp/call, /mcp/schema, /tools/*, логирование")
        Container(tools_py, "tools.py", "Python / httpx", "Бизнес-логика: товары, AST-калькулятор, CoinGecko, RAWG, LibreTranslate")
        Container(db_py, "db.py", "Python / sqlite3", "Инициализация БД, подключение, seed 160 товаров")
        ContainerDb(sqlite, "products.db", "SQLite", "Таблица products: id, name, category, price, quantity")
    }

    System_Ext(telegram, "Telegram API", "api.telegram.org:443")
    System_Ext(llm, "LLM Provider API", "ProxyAPI / Z.AI / GenAPI")
    System_Ext(ext_apis, "Внешние API", "CoinGecko, RAWG, LibreTranslate")

    Rel(user, telegram, "Сообщение")
    Rel(telegram, bot_py, "Update (long polling)")
    Rel(bot_py, config_py, "Читает PROVIDERS, BOT_TOKEN")
    Rel(bot_py, llm, "POST /chat/completions + tools")
    Rel(bot_py, mcp_client_py, "call_tool(name, args)")
    Rel(mcp_client_py, server_py, "POST /mcp/call {tool, arguments}")
    Rel(server_py, tools_py, "Вызов функций инструментов")
    Rel(tools_py, db_py, "get_connection()")
    Rel(db_py, sqlite, "SQL: SELECT / INSERT")
    Rel(tools_py, ext_apis, "httpx async GET/POST, follow_redirects=True")
    Rel(bot_py, telegram, "sendMessage (с разбивкой >4096 символов)")
```

### Уровень 3 — Component (MCP Server)

```mermaid
C4Component
    title Component Diagram — MCP Server

    Container_Boundary(server, "server.py — FastAPI") {
        Component(lifespan, "lifespan()", "asynccontextmanager", "Вызывает init_db() при старте, настраивает логирование")
        Component(schema_ep, "GET /mcp/schema", "FastAPI route", "Возвращает JSON Schema всех 10 инструментов")
        Component(call_ep, "POST /mcp/call", "FastAPI async route", "Универсальный диспетчер: принимает {tool, arguments}, маршрутизирует вызов")
        Component(tool_eps, "POST /tools/{name}", "FastAPI routes", "Индивидуальные endpoints для каждого инструмента")
        Component(pydantic, "Pydantic Models", "BaseModel", "Валидация: FindRequest, AddRequest, CryptoRequest и др.")
        Component(error_h, "Error Handling", "try/except", "ValueError→400, KeyError→422, HTTPException→404, Exception→400/500")
    }

    Container_Boundary(tools, "tools.py") {
        Component(product_tools, "Product Tools", "sqlite3 sync", "list/find/find_by_category/get_by_id/find_similar/add_product")
        Component(calc, "safe_eval()", "Python AST", "Безопасный калькулятор: +−×÷^%// без eval()")
        Component(crypto, "get_crypto_price()", "httpx async", "CoinGecko: USD+RUB+24h change, обработка HTTPStatusError/RequestError")
        Component(games, "search_games()", "httpx async", "RAWG: название, рейтинг, жанры, платформы")
        Component(translate, "translate_text()", "httpx async", "LibreTranslate: fallback по 3 инстансам, follow_redirects=True")
    }

    Container_Boundary(db, "db.py") {
        Component(init, "init_db()", "sqlite3", "CREATE TABLE IF NOT EXISTS + ALTER TABLE (миграция quantity) + seed 160 товаров")
        Component(conn, "get_connection()", "sqlite3", "sqlite3.connect() с row_factory=sqlite3.Row")
    }

    ContainerDb(sqlite, "products.db", "SQLite")

    Rel(lifespan, init, "init_db() при старте")
    Rel(call_ep, pydantic, "Валидирует MCPCallRequest")
    Rel(call_ep, error_h, "Перехватывает исключения")
    Rel(call_ep, product_tools, "tool in (list/find/add...)")
    Rel(call_ep, calc, "tool == calculate")
    Rel(call_ep, crypto, "tool == get_crypto_price")
    Rel(call_ep, games, "tool == search_games")
    Rel(call_ep, translate, "tool == translate_text")
    Rel(product_tools, conn, "get_connection()")
    Rel(conn, sqlite, "sqlite3.connect(DB_PATH)")
```

---

## Процессы и взаимодействия (UML)

### Sequence — Полный цикл обработки сообщения с tool calling

```mermaid
sequenceDiagram
    actor User as Пользователь
    participant TG as Telegram API
    participant Bot as bot.py
    participant LLM as LLM Provider
    participant MCP as mcp_client.py
    participant Server as server.py
    participant Tools as tools.py
    participant DB as products.db

    User->>TG: Отправляет сообщение
    TG->>Bot: Update (long polling)
    Bot->>TG: answer("⏳ Думаю...")

    Bot->>Bot: get_state(user_id)
    Note over Bot: history пуст → добавляет SYSTEM_PROMPT
    Bot->>Bot: history.append({role:user, content:text})

    Bot->>LLM: ChatCompletions(messages=history, tools=LLM_TOOLS, tool_choice=auto)
    LLM-->>Bot: finish_reason=tool_calls, tool_calls=[{id, name, arguments}]

    Bot->>Bot: Сериализует assistant entry в history

    loop Для каждого tool_call
        Bot->>MCP: call_tool(name, args)
        MCP->>Server: POST /mcp/call {"tool":"...", "arguments":{...}}
        Server->>Server: Pydantic валидация MCPCallRequest
        Server->>Tools: Вызов функции инструмента

        alt Инструмент работает с БД
            Tools->>DB: SQL запрос (SELECT / INSERT)
            DB-->>Tools: sqlite3.Row[]
        else Внешний API (CoinGecko / RAWG / LibreTranslate)
            Tools->>Tools: httpx.AsyncClient(follow_redirects=True)
            Tools-->>Tools: JSON ответ
        else Калькулятор
            Tools->>Tools: ast.parse() + _eval_node()
            Tools-->>Tools: float результат
        end

        Tools-->>Server: dict с результатом
        Server-->>MCP: {"result": ...}
        MCP-->>Bot: result dict
        Bot->>Bot: format_tool_result(name, result)
        Bot->>Bot: history.append({role:tool, content:formatted})
    end

    Bot->>LLM: ChatCompletions(messages=history с tool results)
    LLM-->>Bot: finish_reason=stop, content=финальный текст

    Bot->>Bot: history.append({role:assistant})
    Bot->>Bot: trim_history() — обрезка до MAX_HISTORY_MESSAGES=20

    Bot->>TG: thinking.delete()
    alt len(reply) <= 4096
        Bot->>TG: message.answer(reply)
    else len(reply) > 4096
        loop Каждые 4096 символов
            Bot->>TG: message.answer(chunk)
        end
    end
    TG->>User: Финальный ответ
```

### Sequence — Ответ без tool calling

```mermaid
sequenceDiagram
    actor User as Пользователь
    participant TG as Telegram API
    participant Bot as bot.py
    participant LLM as LLM Provider

    User->>TG: Сообщение (не требует инструментов)
    TG->>Bot: Update
    Bot->>TG: "⏳ Думаю..."
    Bot->>LLM: ChatCompletions(messages, tools, tool_choice=auto)
    LLM-->>Bot: finish_reason=stop, content=текст
    Bot->>Bot: history.append({role:assistant})
    Bot->>Bot: trim_history()
    Bot->>TG: thinking.delete()
    Bot->>TG: message.answer(reply)
    TG->>User: Ответ
```

### Sequence — Инициализация сервера

```mermaid
sequenceDiagram
    participant Main as __main__
    participant Uvicorn as uvicorn
    participant App as FastAPI lifespan
    participant DB as db.py
    participant SQLite as products.db

    Main->>Uvicorn: uvicorn.run("server:app", host=0.0.0.0, port=8000)
    Uvicorn->>App: Вход в asynccontextmanager lifespan()
    App->>DB: init_db()
    DB->>SQLite: CREATE TABLE IF NOT EXISTS products (id, name, category, price, quantity)
    DB->>SQLite: ALTER TABLE ADD COLUMN quantity (миграция, игнорирует ошибку если есть)
    DB->>SQLite: SELECT COUNT(*) FROM products
    alt count == 0
        DB->>DB: Генерирует 160 товаров из CATALOG (8 категорий × 20, random.seed(42))
        DB->>SQLite: INSERT 160 строк
        DB->>DB: print("[DB] Таблица заполнена...")
    else count > 0
        DB->>DB: Пропускает seed
    end
    DB-->>App: Готово
    App->>App: logger.info("product-mcp server started")
    App-->>Uvicorn: yield (сервер готов принимать запросы)
```

### Sequence — Выбор провайдера и модели (/settings)

```mermaid
sequenceDiagram
    actor User as Пользователь
    participant TG as Telegram API
    participant Bot as bot.py

    User->>TG: /settings
    TG->>Bot: Command("settings")
    Bot->>TG: answer("Выберите провайдера", inline_keyboard=[Z.AI, ProxyAPI, GenAPI])
    TG->>User: Кнопки провайдеров

    User->>TG: Нажимает кнопку провайдера
    TG->>Bot: CallbackQuery data="provider:{key}"
    Bot->>TG: edit_text("Выберите модель", inline_keyboard=[модели провайдера])
    TG->>User: Кнопки моделей

    User->>TG: Нажимает кнопку модели
    TG->>Bot: CallbackQuery data="model:{provider_key}:{model_key}"
    Bot->>Bot: state.provider_key = provider_key
    Bot->>Bot: state.model_key = model_key
    Bot->>Bot: state.history.clear()
    Bot->>TG: edit_text("Настройки сохранены: провайдер + модель")
    Bot->>TG: callback.answer("Готово!")
    TG->>User: Подтверждение
```

### Activity — Диспетчеризация в /mcp/call

```mermaid
flowchart TD
    A([POST /mcp/call]) --> B[Pydantic: MCPCallRequest\ntool: str, arguments: dict]
    B --> C{tool?}

    C -->|list_products| P1[list_products]
    C -->|find_product| P2[find_product name]
    C -->|find_products_by_category| P3[find_products_by_category category]
    C -->|get_product_by_id| P4{найден?}
    C -->|find_similar_products| P5[find_similar_products id limit]
    C -->|add_product| P6[add_product name category price qty]
    C -->|calculate| P7[safe_eval expression]
    C -->|get_crypto_price| P8[CoinGecko API]
    C -->|search_games| P9[RAWG API]
    C -->|translate_text| P10[LibreTranslate fallback]
    C -->|unknown| E1[HTTPException 404]

    P1 --> DB[(SQLite)]
    P2 --> DB
    P3 --> DB
    P4 -->|None| E2[HTTPException 404]
    P4 -->|found| DB
    P5 --> DB
    P6 --> DB

    P7 --> AST{SyntaxError?}
    AST -->|да| E3[HTTPException 400]
    AST -->|нет| OK

    P8 --> CG{HTTP OK?}
    CG -->|HTTPStatusError| E4[HTTPException 400]
    CG -->|RequestError| E4
    CG -->|OK| OK

    P9 --> RW{HTTP OK?}
    RW -->|HTTPStatusError| E5[HTTPException 400]
    RW -->|RequestError| E5
    RW -->|OK| OK

    P10 --> LT1{instance 1 OK?}
    LT1 -->|нет| LT2{instance 2 OK?}
    LT2 -->|нет| LT3{instance 3 OK?}
    LT3 -->|нет| E6[HTTPException 400]
    LT1 -->|да| OK
    LT2 -->|да| OK
    LT3 -->|да| OK

    DB --> OK([return result])
```

### Activity — Управление историей диалога

```mermaid
flowchart TD
    A([Новое сообщение]) --> B[get_state user_id]
    B --> C{history пуст?}
    C -->|да| D[history.append SYSTEM_PROMPT]
    C -->|нет| E
    D --> E[history.append user message]
    E --> F[LLM запрос]
    F --> G{tool_calls?}
    G -->|да| H[Выполнить инструменты]
    H --> I[history.append tool results]
    I --> J[LLM финальный запрос]
    J --> K[history.append assistant]
    G -->|нет| K
    K --> L[trim_history]
    L --> M{len rest > MAX*2\nMAX=20}
    M -->|да| N[Обрезать до последних 40 сообщений]
    N --> O{rest начинается с user?}
    O -->|нет| P[Удалить первое сообщение]
    P --> O
    O -->|да| Q[history = system + rest]
    M -->|нет| R([Готово])
    Q --> R
```

### Class — Структура модулей

```mermaid
classDiagram
    class BotPy {
        +user_state: dict~int, dict~
        +LLM_TOOLS: list
        +SYSTEM_PROMPT: str
        +MAX_HISTORY_MESSAGES: int = 20
        +PROXY_URL: str
        +get_state(user_id) dict
        +trim_history(history)
        +history_summary(history) str
        +format_products(products) str
        +format_tool_result(tool_name, result) str
        +process_with_llm(user_id, text) str
        +provider_keyboard() InlineKeyboardMarkup
        +model_keyboard(provider_key) InlineKeyboardMarkup
        +cmd_start(message)
        +cmd_settings(message)
        +cmd_new(message)
        +cmd_history(message)
        +cb_provider(callback)
        +cb_model(callback)
        +handle_message(message)
        +main()
    }

    class MCPClientPy {
        +call_tool(tool, arguments) dict
        +get_schema() dict
    }

    class ConfigPy {
        +BOT_TOKEN: str
        +MCP_SERVER_URL: str
        +PROVIDERS: dict
        +DEFAULT_PROVIDER: str = "2"
        +DEFAULT_MODEL: str = "3"
        +DEFAULT_TEMPERATURE: float = 0.7
    }

    class ServerPy {
        +app: FastAPI
        +MCP_SCHEMA: dict
        +logger: Logger
        +lifespan()
        +get_schema() JSONResponse
        +mcp_call(req) dict
        +tool_list_products() dict
        +tool_find_product(req) dict
        +tool_find_products_by_category(req) dict
        +tool_get_product_by_id(req) dict
        +tool_find_similar_products(req) dict
        +tool_add_product(req) dict
        +tool_calculate(req) dict
        +tool_get_crypto_price(req) dict
        +tool_search_games(req) dict
        +tool_translate_text(req) dict
    }

    class ToolsPy {
        +list_products() list
        +find_product(name) list
        +find_products_by_category(category) list
        +get_product_by_id(product_id) dict
        +find_similar_products(product_id, limit) list
        +add_product(name, category, price, quantity) dict
        +calculate(expression) dict
        +safe_eval(expression) float
        +_eval_node(node) float
        +get_crypto_price(coin_id) dict
        +search_games(query, page_size) list
        +translate_text(text, source_lang, target_lang) dict
    }

    class DbPy {
        +DB_PATH: str
        +CATALOG: dict
        +get_connection() Connection
        +init_db()
    }

    class ProductsDB {
        +id: INTEGER PK AUTOINCREMENT
        +name: TEXT NOT NULL
        +category: TEXT NOT NULL
        +price: REAL NOT NULL
        +quantity: INTEGER DEFAULT 0
    }

    BotPy --> MCPClientPy : call_tool()
    BotPy --> ConfigPy : PROVIDERS, BOT_TOKEN, MCP_SERVER_URL
    MCPClientPy --> ServerPy : POST /mcp/call
    ServerPy --> ToolsPy : вызов функций
    ToolsPy --> DbPy : get_connection()
    DbPy --> ProductsDB : SQL
    ServerPy ..> DbPy : init_db() через lifespan
```

---

## Структура проекта

```
.env                        # Переменные окружения
README.md                   # Документация
mcp_server/
├── server.py               # FastAPI MCP сервер, логирование → server.log
├── db.py                   # SQLite: инициализация, seed, подключение
├── tools.py                # Инструменты: товары, калькулятор, внешние API
├── products.db             # Создаётся автоматически при первом запуске
├── server.log              # Лог сервера
└── requirements.txt
telegram_bot/
├── bot.py                  # Логика бота, LLM tool calling, история, логирование → bot.log
├── config.py               # Конфигурация провайдеров из .env
├── mcp_client.py           # HTTP-клиент для /mcp/call
├── bot.log                 # Лог бота
└── requirements.txt
```

---

## Установка и запуск

### 1. Создать и активировать venv

```bash
python -m venv venv
venv\Scripts\activate
```

### 2. Установить зависимости

```bash
pip install -r mcp_server/requirements.txt
pip install -r telegram_bot/requirements.txt
```

### 3. Запустить MCP сервер (Терминал 1)

```bash
cd mcp_server
python .\server.py
```

Сервер запустится на `http://localhost:8000`.
При первом запуске создаётся `products.db` с 160 товарами по 8 категориям.
Лог пишется в `mcp_server/server.log`.

### 4. Запустить Telegram-бота (Терминал 2)

```bash
cd telegram_bot
python .\bot.py
```

Лог пишется в `telegram_bot/bot.log`.

### Прокси (если Telegram недоступен)

Раскомментировать в `.env`:
```env
TELEGRAM_PROXY_URL=socks5://127.0.0.1:1080
```
Установить: `pip install aiohttp-socks`

---

## База данных

Таблица `products`:

| Колонка  | Тип     | Описание             |
|----------|---------|----------------------|
| id       | INTEGER | Первичный ключ       |
| name     | TEXT    | Название товара      |
| category | TEXT    | Категория            |
| price    | REAL    | Цена (±10% от базы)  |
| quantity | INTEGER | Количество на складе |

Категории (8 шт., по 20 товаров): Электроника, Одежда, Продукты, Книги, Спорт, Дом, Игрушки, Косметика.

---

## MCP инструменты

Универсальный endpoint: `POST /mcp/call` с телом `{"tool": "...", "arguments": {...}}`

### Товары

| Инструмент                  | Параметры                                    | Описание                                        |
|-----------------------------|----------------------------------------------|-------------------------------------------------|
| `list_products`             | —                                            | Все товары (показывает первые 30 из 160)        |
| `find_product`              | `name: string`                               | Поиск по названию (LIKE %name%)                 |
| `find_products_by_category` | `category: string`                           | Поиск по категории (LIKE %category%)            |
| `get_product_by_id`         | `product_id: integer`                        | Товар по точному ID, 404 если не найден         |
| `find_similar_products`     | `product_id: integer`, `limit: integer (=5)` | Похожие из той же категории, сортировка по цене |
| `add_product`               | `name`, `category`, `price`, `quantity (=0)` | Добавить товар                                  |

### Утилиты

| Инструмент         | Параметры                                          | Описание                                                      |
|--------------------|----------------------------------------------------|---------------------------------------------------------------|
| `calculate`        | `expression: string`                               | AST-калькулятор без eval(). Операции: +−×÷**%//               |
| `get_crypto_price` | `coin_id: string`                                  | CoinGecko: цена в USD и RUB + изменение за 24ч                |
| `search_games`     | `query: string`, `page_size: integer (=5)`         | RAWG: название, дата, рейтинг, жанры, платформы               |
| `translate_text`   | `text`, `source_lang (=auto)`, `target_lang (=ru)` | LibreTranslate: fallback по 3 инстансам, follow_redirects=True |

---

## Telegram-бот

### Команды

| Команда     | Описание                                          |
|-------------|---------------------------------------------------|
| `/start`    | Приветствие, текущий провайдер/модель/температура |
| `/settings` | Выбор AI-провайдера и модели (inline keyboard)    |
| `/new`      | Очистить историю диалога                          |
| `/history`  | Показать последние 10 сообщений из истории        |

### AI-провайдеры

| # | Провайдер         | Переменная в .env | Модели                                                        |
|---|-------------------|-------------------|---------------------------------------------------------------|
| 1 | Z.AI              | `ZAI_API_KEY`     | GLM-4.7-Flash, GLM-4.5-Flash, GLM-4.7                        |
| 2 | ProxyAPI (OpenAI) | `PROXY_API_KEY`   | GPT-4.1 Nano, GPT-4.1 Mini, GPT-4o Mini, GPT-4o              |
| 3 | GenAPI            | `GEN_API_KEY`     | GPT-4.1 Mini, GPT-4o, Claude Sonnet 4.5, Gemini 2.5 Flash, DeepSeek Chat |

По умолчанию: ProxyAPI + GPT-4o Mini (температура 0.7).

### Примеры запросов

```
покажи все товары
найди чай
товары категории электроника
товар с ID 5
похожие на товар 5
добавь товар яблоки фрукты 120 50 штук
сколько будет 15 * 8 + 42
курс биткоина
найди игру witcher
переведи hello на русский
```

---

## Переменные окружения (.env)

```env
BOT_TOKEN=...                    # Telegram Bot Token
TELEGRAM_PROXY_URL=...           # Опционально: socks5://... или http://...
ZAI_API_KEY=...                  # Z.AI API Key
PROXY_API_KEY=...                # ProxyAPI Key
GEN_API_KEY=...                  # GenAPI Key
MCP_SERVER_URL=http://localhost:8000
```
