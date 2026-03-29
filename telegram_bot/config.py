"""
config.py — конфигурация бота из .env файла.
"""
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# MCP Server
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000")

# AI Провайдеры (те же, что в ai_direct.py)
PROVIDERS = {
    "1": {
        "name": "Z.AI",
        "api_key": os.getenv("ZAI_API_KEY", ""),
        "base_url": "https://api.z.ai/api/paas/v4/",
        "models": {
            "1": {"id": "glm-4.7-flash", "label": "GLM-4.7-Flash", "max_tokens": 4096},
            "2": {"id": "glm-4.5-flash", "label": "GLM-4.5-Flash", "max_tokens": 4096},
            "3": {"id": "glm-4.7",       "label": "GLM-4.7",       "max_tokens": 8192},
        },
    },
    "2": {
        "name": "ProxyAPI (OpenAI)",
        "api_key": os.getenv("PROXY_API_KEY", ""),
        "base_url": "https://api.proxyapi.ru/openai/v1",
        "models": {
            "1": {"id": "gpt-4.1-nano",  "label": "GPT-4.1 Nano",  "max_tokens": 32768},
            "2": {"id": "gpt-4.1-mini",  "label": "GPT-4.1 Mini",  "max_tokens": 32768},
            "3": {"id": "gpt-4o-mini",   "label": "GPT-4o Mini",   "max_tokens": 16384},
            "4": {"id": "gpt-4o",        "label": "GPT-4o",        "max_tokens": 16384},
        },
    },
    "3": {
        "name": "GenAPI",
        "api_key": os.getenv("GEN_API_KEY", ""),
        "base_url": "https://proxy.gen-api.ru/v1",
        "models": {
            "1": {"id": "gpt-4-1-mini",      "label": "GPT-4.1 Mini",      "max_tokens": 32768},
            "2": {"id": "gpt-4o",            "label": "GPT-4o",            "max_tokens": 16384},
            "3": {"id": "claude-sonnet-4-5", "label": "Claude Sonnet 4.5", "max_tokens": 8192},
            "4": {"id": "gemini-2-5-flash",  "label": "Gemini 2.5 Flash",  "max_tokens": 8192},
            "5": {"id": "deepseek-chat",     "label": "DeepSeek Chat",     "max_tokens": 8192},
        },
    },
}

# Дефолтный провайдер и модель
DEFAULT_PROVIDER = "2"
DEFAULT_MODEL = "3"
DEFAULT_TEMPERATURE = 0.7
