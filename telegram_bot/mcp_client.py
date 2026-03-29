"""
mcp_client.py — HTTP-клиент для вызова MCP инструментов.
"""
import logging
import httpx
from config import MCP_SERVER_URL

logger = logging.getLogger(__name__)


async def call_tool(tool: str, arguments: dict = None) -> dict:
    """Вызывает MCP инструмент через HTTP POST /mcp/call."""
    payload = {"tool": tool, "arguments": arguments or {}}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{MCP_SERVER_URL}/mcp/call", json=payload)
        if not resp.is_success:
            logger.error("MCP call failed: tool=%s args=%s status=%s body=%s",
                         tool, arguments, resp.status_code, resp.text)
            # Пробрасываем читаемое сообщение об ошибке вместо сырого HTTP-исключения
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise ValueError(f"Ошибка MCP [{resp.status_code}]: {detail}")
        return resp.json().get("result", {})


async def get_schema() -> dict:
    """Получает MCP schema с сервера."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{MCP_SERVER_URL}/mcp/schema")
        resp.raise_for_status()
        return resp.json()
