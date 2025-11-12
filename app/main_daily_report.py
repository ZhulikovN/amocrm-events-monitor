#!/usr/bin/env python3
"""
Скрипт для ежедневного формирования отчёта по событиям amoCRM.

Запускается автоматически каждый день в 03:00 через systemd timer (amocrm-daily-report.timer).

Выполняет:
1. Определение даты отчёта (вчера)
2. Получение user_ids
3. Получение и обработка событий → TOP-5
4. Получение максимального latency из SQLite
5. Формирование данных для таблицы
6. Запись в Google Sheets
7. Удаление записей latency из SQLite
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from typing import Any

from app.amocrm_client import AmoCRMClient
from app.events_processor import EventsProcessor
from app.latency_checker import LatencyChecker
from app.settings import settings
from app.sheets_writer import sheets_writer
from app.token_manager import init_token_manager

logging.basicConfig(
    level=settings.log_level_value,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

EVENT_TYPE_NAMES: dict[str, str] = {
    "lead_added": "Новая сделка",
    "lead_deleted": "Сделка удалена",
    "lead_restored": "Сделка восстановлена",
    "lead_status_changed": "Изменение этапа продажи",
    "lead_linked": "Прикрепление сделки",
    "lead_unlinked": "Открепление сделки",
    "contact_added": "Новый контакт",
    "contact_deleted": "Контакт удален",
    "contact_restored": "Контакт восстановлен",
    "contact_linked": "Прикрепление контакта",
    "contact_unlinked": "Открепление контакта",
    "company_added": "Новая компания",
    "company_deleted": "Компания удалена",
    "company_restored": "Компания восстановлена",
    "company_linked": "Прикрепление компании",
    "company_unlinked": "Открепление компании",
    "customer_added": "Новый покупатель",
    "customer_deleted": "Покупатель удален",
    "customer_status_changed": "Изменение этапа покупателя",
    "customer_linked": "Прикрепление покупателя",
    "customer_unlinked": "Открепление покупателя",
    "task_added": "Новая задача",
    "task_deleted": "Задача удалена",
    "task_completed": "Завершение задачи",
    "task_type_changed": "Изменение типа задачи",
    "task_text_changed": "Изменение текста задачи",
    "task_deadline_changed": "Изменение даты исполнения задачи",
    "task_result_added": "Результат по задаче",
    "incoming_call": "Входящий звонок",
    "outgoing_call": "Исходящий звонок",
    "incoming_chat_message": "Входящее сообщение",
    "outgoing_chat_message": "Исходящее сообщение",
    "entity_direct_message": "Сообщение внутреннего чата",
    "incoming_sms": "Входящее SMS",
    "outgoing_sms": "Исходящее SMS",
    "entity_tag_added": "Теги добавлены",
    "entity_tag_deleted": "Теги убраны",
    "entity_linked": "Прикрепление",
    "entity_unlinked": "Открепление",
    "sale_field_changed": "Изменение поля Бюджет",
    "name_field_changed": "Изменение поля Название",
    "ltv_field_changed": "Сумма покупок",
    "custom_field_value_changed": "Изменение поля",
    "entity_responsible_changed": "Ответственный изменен",
    "robot_replied": "Ответ робота",
    "intent_identified": "Тема вопроса определена",
    "nps_rate_added": "Новая оценка NPS",
    "link_followed": "Переход по ссылке",
    "transaction_added": "Добавлена покупка",
    "common_note_added": "Новое примечание",
    "common_note_deleted": "Примечание удалено",
    "attachment_note_added": "Добавлен новый файл",
    "targeting_in_note_added": "Добавление в ретаргетинг",
    "targeting_out_note_added": "Удаление из ретаргетинга",
    "geo_note_added": "Новое примечание с гео-меткой",
    "service_note_added": "Новое системное примечание",
    "site_visit_note_added": "Заход на сайт",
    "message_to_cashier_note_added": "LifePay: Сообщение кассиру",
    "key_action_completed": "Ключевое действие",
    "entity_merged": "Выполнено объединение",
}


def format_date(date: datetime) -> str:
    """
    Форматирование даты для отчёта.

    Args:
        date: Дата для форматирования

    Returns:
        str: Дата в формате DD.MM.YYYY
    """
    return date.strftime("%d.%m.%Y")


def format_time(timestamp_str: str) -> str:
    """
    Форматирование времени из ISO timestamp.

    Args:
        timestamp_str: Timestamp в формате ISO (2025-01-15T18:23:00Z)

    Returns:
        str: Время в формате HH:MM
    """
    try:
        dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
        return dt.strftime("%H:%M")
    except Exception as e:
        logger.error("Ошибка при форматировании времени '%s': %s", timestamp_str, e)
        return timestamp_str


def get_event_name(event_type: str) -> str:
    """
    Получение русского названия типа события.

    Args:
        event_type: Тип события в формате AmoCRM (например, 'incoming_chat_message')

    Returns:
        str: Русское название события или исходный тип, если перевод не найден
    """
    return EVENT_TYPE_NAMES.get(event_type, event_type)


def prepare_report_data(
    report_date: datetime,
    top_events: list[tuple[str, int]],
    max_latency: tuple[str, int] | None,
) -> list[list[Any]]:
    """
    Подготовка данных для записи в Google Sheets.

    Формат выходного массива:
    [
        [<дата>, <событие_#1>, <count_#1>, <пинг>, <время_пинга>],
        [<дата>, <событие_#2>, <count_#2>, "", ""],
        [<дата>, <событие_#3>, <count_#3>, "", ""],
        [<дата>, <событие_#4>, <count_#4>, "", ""],
        [<дата>, <событие_#5>, <count_#5>, "", ""],
    ]

    Args:
        report_date: Дата отчёта
        top_events: Список кортежей (тип_события, количество)
        max_latency: Кортеж (timestamp, max_latency_ms) или None

    Returns:
        list[list[Any]]: Массив строк для записи в таблицу
    """
    date_str = format_date(report_date)
    rows: list[list[Any]] = []

    if not top_events:
        logger.warning("Нет событий для отчёта за %s", date_str)
        if max_latency:
            peak_time, latency_ms = max_latency
            rows.append([date_str, "Нет событий", 0, latency_ms, format_time(peak_time)])
        else:
            rows.append([date_str, "Нет событий", 0, "", ""])
        return rows

    for i, (event_type, count) in enumerate(top_events):
        event_name = get_event_name(event_type)
        if i == 0 and max_latency:
            peak_time, latency_ms = max_latency
            rows.append([date_str, event_name, count, latency_ms, format_time(peak_time)])
        else:
            rows.append([date_str, event_name, count, "", ""])

    logger.info("Подготовлено %s строк для отчёта за %s", len(rows), date_str)
    return rows


async def main() -> None:  # pylint: disable=too-many-locals
    """Основная функция для ежедневного формирования отчёта."""
    try:
        logger.info("=" * 80)
        logger.info("Запуск ежедневного формирования отчёта по событиям amoCRM")
        logger.info("=" * 80)

        yesterday = datetime.now().date() - timedelta(days=1)
        report_date = datetime.combine(yesterday, datetime.min.time())
        date_str = report_date.strftime("%Y-%m-%d")

        logger.info("Дата отчёта: %s", format_date(report_date))

        if settings.AMO_LONG_LIVE_TOKEN:
            logger.info("Используется долгосрочный токен (OAuth2 не требуется)")
        else:
            logger.info("Инициализация token manager (OAuth2)...")
            init_token_manager()

        logger.info("Получение списка пользователей...")
        amocrm_client = AmoCRMClient()
        user_ids = await amocrm_client.get_users()
        logger.info("Получено пользователей: %s", len(user_ids))

        logger.info("Получение событий за %s...", date_str)
        date_from = report_date
        date_to = datetime.combine(yesterday, datetime.max.time())
        events = await amocrm_client.get_events(date_from=date_from, date_to=date_to)
        logger.info("Получено событий: %s", len(events))

        logger.info("Обработка событий...")
        processor = EventsProcessor()
        top_events = processor.process_events(events, user_ids)

        if not top_events:
            logger.warning("Не найдено автоматических событий за %s", date_str)

        logger.info("Получение максимального latency из базы данных...")
        latency_checker = LatencyChecker()
        max_latency = latency_checker.get_max_latency_for_date(date_str)

        if max_latency:
            peak_time, latency_ms = max_latency
            logger.info("Максимальный latency: %s мс в %s", latency_ms, peak_time)
        else:
            logger.warning("Нет данных о latency за %s", date_str)

        logger.info("Формирование данных для таблицы...")
        report_rows = prepare_report_data(report_date, top_events, max_latency)

        logger.info("Сформировано строк для записи: %s", len(report_rows))
        for row in report_rows:
            logger.debug("  %s", row)

        headers = ["Дата", "Событие", "Кол-во", "Пиковая нагрузка (мс)", "Время пика"]
        await sheets_writer.ensure_headers(headers)

        logger.info("Запись данных в Google Sheets...")
        await sheets_writer.append_rows(report_rows)
        logger.info("Данные успешно записаны в таблицу")

        logger.info("Удаление обработанных данных latency из базы...")
        deleted_count = latency_checker.delete_latency_for_date(date_str)
        logger.info("Удалено записей latency: %s", deleted_count)

        logger.info("=" * 80)
        logger.info("Ежедневный отчёт сформирован успешно за %s", format_date(report_date))
        logger.info("Обработано событий: %s, TOP событий: %s", len(events), len(top_events))
        logger.info("=" * 80)

    except Exception as e:
        logger.error("Критическая ошибка при формировании отчёта: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
