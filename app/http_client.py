import logging
from typing import Any

import httpx
from amocrm.v2 import tokens
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.settings import settings

logger = logging.getLogger(__name__)


class AmoCRMHTTPClient:
    """
    Асинхронный HTTP-клиент для работы с API amoCRM.

    Автоматически:
    - Добавляет access_token в заголовки
    - Устанавливает таймауты
    - Повторяет запросы при временных ошибках (429, 500, 502, 503, 504)
    - Использует exponential backoff между попытками
    """

    def __init__(self) -> None:
        """Инициализация HTTP-клиента."""
        self.base_url = settings.AMO_BASE_URL.rstrip("/")
        self.timeout = httpx.Timeout(30.0, connect=10.0)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AmoCRMHTTPClient":
        """Вход в контекстный менеджер."""
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Выход из контекстного менеджера."""
        if self._client:
            await self._client.aclose()

    def _get_access_token(self) -> str:
        """
        Получение access_token из token manager.

        Returns:
            str: Access token для авторизации

        Raises:
            RuntimeError: Если токен недоступен
        """
        try:
            token = tokens.default_token_manager.get_access_token()
            if not token:
                raise RuntimeError("Access token недоступен")
            return str(token)
        except Exception as e:
            logger.error("Ошибка при получении access token: %s", e)
            raise

    def _get_headers(self) -> dict[str, str]:
        """
        Формирование заголовков для запроса.

        Поддерживает два режима:
        1. Долгосрочный токен (AMO_LONG_LIVE_TOKEN) - используется напрямую
        2. OAuth2 (через token manager) - получает access token автоматически

        Returns:
            dict[str, str]: Заголовки с Authorization
        """
        if settings.AMO_LONG_LIVE_TOKEN:
            logger.debug("Использование долгосрочного токена")
            return {
                "Authorization": f"Bearer {settings.AMO_LONG_LIVE_TOKEN}",
                "Content-Type": "application/json",
            }

        logger.debug("Использование OAuth2 token manager")
        access_token = self._get_access_token()
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Выполнение GET-запроса к API amoCRM.

        Args:
            endpoint: Путь к endpoint (например, "/api/v4/users")
            params: Query параметры

        Returns:
            dict[str, Any]: JSON-ответ от API

        Raises:
            httpx.HTTPStatusError: При ошибках HTTP
            httpx.RequestError: При сетевых ошибках
        """
        if not self._client:
            raise RuntimeError("HTTP-клиент не инициализирован. Используйте async with.")

        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        logger.debug("GET %s, params=%s", url, params)

        try:
            response = await self._client.get(url, headers=headers, params=params)

            if response.status_code in (429, 500, 502, 503, 504):
                logger.warning("Временная ошибка %s, повторяем запрос...", response.status_code)
                response.raise_for_status()

            response.raise_for_status()
            data = response.json()

            logger.debug("Успешный ответ от %s: %s записей", endpoint, len(data.get("_embedded", {})))
            return data  # type: ignore[no-any-return]

        except httpx.HTTPStatusError as e:
            logger.error("HTTP ошибка при запросе %s: %s - %s", url, e.response.status_code, e.response.text)
            raise
        except httpx.RequestError as e:
            logger.error("Сетевая ошибка при запросе %s: %s", url, e)
            raise
