import logging
from collections import Counter
from typing import Any

from app.settings import settings

logger = logging.getLogger(__name__)


class EventsProcessor:
    """
    Обработчик событий amoCRM.

    Выполняет:
    - Фильтрацию событий (исключение пользовательских действий)
    - Подсчет количества событий каждого типа
    - Определение TOP-N событий по количеству срабатываний
    """

    def __init__(self, top_limit: int | None = None) -> None:
        """
        Инициализация процессора событий.

        Args:
            top_limit: Количество топ событий для вывода (по умолчанию из настроек)
        """
        self.top_limit = top_limit or settings.TOP_EVENTS_LIMIT

    def filter_automated_events(
        self,
        events: list[dict[str, Any]],
        user_ids: list[int],
    ) -> list[dict[str, Any]]:
        """
        Фильтрация автоматических событий (исключение пользовательских действий).

        Исключает события, созданные пользователями (created_by в user_ids).
        Оставляет только события от автоматизаций, интеграций и системных процессов.

        Args:
            events: Список всех событий
            user_ids: Список ID пользователей аккаунта

        Returns:
            list[dict[str, Any]]: Список только автоматических событий
        """
        automated_events = []

        for event in events:
            created_by = event.get("created_by")

            if created_by is None or created_by not in user_ids:
                automated_events.append(event)

        logger.info(
            "Всего событий: %s, пользовательских: %s, автоматических: %s",
            len(events),
            len(events) - len(automated_events),
            len(automated_events),
        )

        return automated_events

    def count_event_types(self, events: list[dict[str, Any]]) -> dict[str, int]:
        """
        Подсчет количества событий каждого типа.

        Args:
            events: Список событий

        Returns:
            dict[str, int]: Словарь {тип_события: количество}
        """
        event_types = [event.get("type", "unknown") for event in events]

        type_counts = dict(Counter(event_types))

        logger.info("Найдено уникальных типов событий: %s", len(type_counts))
        logger.debug("Подсчет по типам: %s", type_counts)

        return type_counts

    def get_top_events(
        self,
        type_counts: dict[str, int],
        limit: int | None = None,
    ) -> list[tuple[str, int]]:
        """
        Получение TOP-N событий по количеству срабатываний.

        Args:
            type_counts: Словарь {тип_события: количество}
            limit: Количество топ событий (по умолчанию из self.top_limit)

        Returns:
            list[tuple[str, int]]: Список кортежей (тип_события, количество) отсортированный по убыванию
        """
        limit = limit or self.top_limit

        top_events = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:limit]

        logger.info("TOP-%s событий определен", limit)
        for i, (event_type, count) in enumerate(top_events, 1):
            logger.info("  %s. %s: %s", i, event_type, count)

        return top_events

    def process_events(
        self,
        events: list[dict[str, Any]],
        user_ids: list[int],
    ) -> list[tuple[str, int]]:
        """
        Полный цикл обработки событий.

        Выполняет фильтрацию, подсчет и определение TOP-N.

        Args:
            events: Список всех событий
            user_ids: Список ID пользователей

        Returns:
            list[tuple[str, int]]: TOP-N событий [(тип, количество), ...]
        """
        logger.info("Начало обработки событий...")

        automated_events = self.filter_automated_events(events, user_ids)

        if not automated_events:
            logger.warning("Не найдено автоматических событий")
            return []

        type_counts = self.count_event_types(automated_events)

        if not type_counts:
            logger.warning("Не найдено типов событий для подсчета")
            return []

        top_events = self.get_top_events(type_counts)

        logger.info("Обработка событий завершена")
        return top_events
