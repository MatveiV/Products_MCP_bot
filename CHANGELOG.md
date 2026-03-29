# Changelog

## [v1.0.0] — 2026-03-29

### Добавлено

**MCP Server (`mcp_server/`)**
- FastAPI сервер с lifespan-инициализацией БД
- SQLite база данных: таблица `products` (id, name, category, price, quantity)
- Автозаполнение 160 тестовыми товарами по 8 категориям при первом запуске
- Универсальный endpoint `POST /mcp/call` для вызова любого инструмента
- Endpoint `GET /mcp/schema` — JSON Schema всех инструментов
- Индивидуальные endpoints `POST /tools/{name}`
- Логирование в `server.log`

**Инструменты (`tools.py`)**
- `list_products` — список всех товаров
- `find_product` — поиск по названию (LIKE)
- `find_products_by_category` — поиск по категории (LIKE)
- `get_product_by_id` — товар по точному ID
- `find_similar_products` — похожие товары из той же категории по близости цены
- `add_product` — добавление товара с количеством на складе
- `calculate` — безопасный AST-калькулятор без `eval()`
- `get_crypto_price` — курс криптовалюты через CoinGecko API (USD + RUB + 24h change)
- `search_games` — поиск игр через RAWG API (рейтинг, жанры, платформы)
- `translate_text` — перевод через LibreTranslate с fallback по 3 публичным инстансам

**Telegram Bot (`telegram_bot/`)**
- aiogram 3 с long polling
- LLM function calling (OpenAI-compatible API)
- Поддержка 3 провайдеров: Z.AI, ProxyAPI (OpenAI), GenAPI
- Выбор провайдера и модели через `/settings` (inline keyboard)
- История диалога с автоматической обрезкой до 20 пар сообщений
- Команды: `/start`, `/settings`, `/new`, `/history`
- Разбивка длинных ответов на части (лимит Telegram 4096 символов)
- Поддержка прокси через `TELEGRAM_PROXY_URL` в `.env`
- Логирование в `bot.log`

**Документация**
- `README.md` с C4-диаграммами (System Context, Container, Component)
- UML-диаграммы (Sequence, Activity, Class) на Mermaid
- `.env.example` с описанием всех переменных
- `.gitignore` исключает `.env`, `*.db`, `*.log`, `venv/`
