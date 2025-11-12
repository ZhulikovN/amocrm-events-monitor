import logging
from datetime import datetime, timedelta
from typing import Any

from app.http_client import AmoCRMHTTPClient

logger = logging.getLogger(__name__)


class AmoCRMClient:
    """
    Клиент для работы с API amoCRM.

    Предоставляет методы для:
    - Получения списка пользователей
    - Получения событий за период
    """

    def __init__(self) -> None:
        """Инициализация клиента."""
        self.http_client = AmoCRMHTTPClient()

    async def get_users(self) -> list[int]:
        """
        Получение списка ID пользователей из amoCRM.

        Returns:
            list[int]: Список user_ids

        Raises:
            Exception: При ошибках запроса
        """
        try:
            async with self.http_client as client:
                logger.info("Получение списка пользователей...")

                response = await client.get("/api/v4/users")

                users = response.get("_embedded", {}).get("users", [])
                user_ids = [user["id"] for user in users if "id" in user]

                logger.info("Получено пользователей: %s", len(user_ids))
                logger.debug("User IDs: %s", user_ids)

                return user_ids

        except Exception as e:
            logger.error("Ошибка при получении списка пользователей: %s", e)
            raise

    async def get_events(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Получение событий из amoCRM за указанный период.

        По умолчанию загружает события за вчерашние сутки.
        Использует постраничную загрузку для получения всех событий.

        Args:
            date_from: Начало периода (по умолчанию: вчера 00:00)
            date_to: Конец периода (по умолчанию: вчера 23:59:59)

        Returns:
            list[dict[str, Any]]: Список всех событий за период

        Raises:
            Exception: При ошибках запроса
        """
        if date_from is None or date_to is None:
            yesterday = datetime.now().date() - timedelta(days=1)
            date_from = datetime.combine(yesterday, datetime.min.time())
            date_to = datetime.combine(yesterday, datetime.max.time())

        timestamp_from = int(date_from.timestamp())
        timestamp_to = int(date_to.timestamp())

        logger.info(
            "Получение событий с %s по %s (timestamp: %s - %s)",
            date_from.isoformat(),
            date_to.isoformat(),
            timestamp_from,
            timestamp_to,
        )

        all_events: list[dict[str, Any]] = []
        page = 1
        limit = 100

        try:
            async with self.http_client as client:
                while True:
                    logger.debug("Загрузка страницы %s событий...", page)

                    params = {
                        "filter[created_at][from]": timestamp_from,
                        "filter[created_at][to]": timestamp_to,
                        "page": page,
                        "limit": limit,
                    }

                    response = await client.get("/api/v4/events", params=params)

                    events = response.get("_embedded", {}).get("events", [])

                    if not events:
                        logger.debug("Страница %s пуста, загрузка завершена", page)
                        break

                    all_events.extend(events)
                    logger.debug("Загружено событий на странице %s: %s", page, len(events))

                    links = response.get("_links", {})
                    if "next" not in links:
                        logger.debug("Следующей страницы нет, загрузка завершена")
                        break

                    page += 1

                logger.info("Всего загружено событий: %s", len(all_events))
                return all_events

        except Exception as e:
            logger.error("Ошибка при получении событий: %s", e)
            raise

    async def get_account_info(self) -> dict[str, Any]:
        """
        Получение информации об аккаунте amoCRM.

        Используется для замера latency (пинга) системы.

        Returns:
            dict[str, Any]: Информация об аккаунте

        Raises:
            Exception: При ошибках запроса
        """
        try:
            async with self.http_client as client:
                logger.debug("Запрос информации об аккаунте для замера latency...")
                response = await client.get("/api/v4/account")
                logger.debug("Получена информация об аккаунте")
                return response

        except Exception as e:
            logger.error("Ошибка при получении информации об аккаунте: %s", e)
            raise
