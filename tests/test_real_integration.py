#!/usr/bin/env python3
"""
Интеграционный тест для проверки работы всего проекта с реальными данными.

Этот тест проверяет:
1. Получение списка пользователей
2. Получение событий за последний час
3. Фильтрацию автоматических событий
4. Подсчёт TOP-5 событий
5. Измерение latency
6. Сохранение в SQLite
7. Получение максимального latency
8. Формирование данных для отчёта

НЕ проверяет (требует дополнительной настройки):
- Запись в Google Sheets (нужен доступ к таблице)
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.amocrm_client import AmoCRMClient
from app.events_processor import EventsProcessor
from app.latency_checker import LatencyChecker
from app.main_daily_report import format_date, format_time, prepare_report_data
from app.settings import settings
from app.sheets_writer import sheets_writer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


async def _test_users():
    """Тест получения списка пользователей."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("ТЕСТ 1: ПОЛУЧЕНИЕ СПИСКА ПОЛЬЗОВАТЕЛЕЙ")
    logger.info("=" * 80)
    
    try:
        client = AmoCRMClient()
        user_ids = await client.get_users()
        
        logger.info("Успешно получено пользователей: %s", len(user_ids))
        logger.info("   User IDs: %s", user_ids[:10] if len(user_ids) > 10 else user_ids)
        
        return True, user_ids
    except Exception as e:
        logger.error("Ошибка при получении пользователей: %s", e, exc_info=True)
        return False, []


async def _test_events(user_ids):
    """Тест получения и обработки событий."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("ТЕСТ 2: ПОЛУЧЕНИЕ И ОБРАБОТКА СОБЫТИЙ")
    logger.info("=" * 80)
    
    try:
        client = AmoCRMClient()
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        
        logger.info("Период: %s - %s", one_hour_ago.strftime("%Y-%m-%d %H:%M"), now.strftime("%Y-%m-%d %H:%M"))
        
        events = await client.get_events(date_from=one_hour_ago, date_to=now)
        
        logger.info("Получено событий за последний час: %s", len(events))
        
        if events:
            logger.info("   Примеры событий:")
            for i, event in enumerate(events[:3], 1):
                logger.info("   %s. Тип: %s, ID: %s, created_by: %s", 
                           i, event.get('type'), event.get('id'), event.get('created_by'))
        
        processor = EventsProcessor()
        top_events = processor.process_events(events, user_ids)
        
        logger.info("TOP-%s автоматических событий:", settings.TOP_EVENTS_LIMIT)
        for i, (event_type, count) in enumerate(top_events, 1):
            logger.info("   %s. %s: %s раз", i, event_type, count)
        
        return True, events, top_events
    except Exception as e:
        logger.error("Ошибка при получении событий: %s", e, exc_info=True)
        return False, [], []


async def _test_latency():
    """Тест измерения latency."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("ТЕСТ 3: ИЗМЕРЕНИЕ LATENCY")
    logger.info("=" * 80)
    
    try:
        checker = LatencyChecker()
        
        latencies = []
        for i in range(3):
            latency_ms = await checker.measure_latency()
            latencies.append(latency_ms)
            logger.info("   Попытка %s: %s мс", i + 1, latency_ms)
        
        avg_latency = sum(latencies) / len(latencies)
        logger.info("Средняя latency: %.0f мс", avg_latency)
        
        return True, latencies
    except Exception as e:
        logger.error("Ошибка при измерении latency: %s", e, exc_info=True)
        return False, []


async def _test_latency_save_and_retrieve():
    """Тест сохранения и получения latency из базы."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("ТЕСТ 4: СОХРАНЕНИЕ И ПОЛУЧЕНИЕ LATENCY")
    logger.info("=" * 80)
    
    try:
        checker = LatencyChecker()
        
        logger.info("Сохранение замера latency...")
        latency_ms = await checker.measure_and_save()
        logger.info("Сохранен latency: %s мс", latency_ms)
        
        today = datetime.now().strftime("%Y-%m-%d")
        all_latencies = checker.get_all_latency_for_date(today)
        
        logger.info("Всего замеров за сегодня: %s", len(all_latencies))
        if all_latencies:
            logger.info("   Последние 3 замера:")
            for i, (timestamp, latency) in enumerate(all_latencies[-3:], 1):
                logger.info("   %s. %s мс в %s", i, latency, format_time(timestamp))
        
        max_latency = checker.get_max_latency_for_date(today)
        if max_latency:
            timestamp, latency = max_latency
            logger.info("Максимальный latency за сегодня: %s мс в %s", latency, format_time(timestamp))
        
        return True, max_latency
    except Exception as e:
        logger.error("Ошибка при работе с базой: %s", e, exc_info=True)
        return False, None


def _test_report_preparation(top_events, max_latency):
    """Тест подготовки данных для отчёта."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("ТЕСТ 5: ПОДГОТОВКА ДАННЫХ ДЛЯ ОТЧЁТА")
    logger.info("=" * 80)
    
    try:
        report_date = datetime.now()
        report_rows = prepare_report_data(report_date, top_events, max_latency)
        
        logger.info("Сформировано строк для отчёта: %s", len(report_rows))
        logger.info("")
        logger.info("   ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР ОТЧЁТА:")
        logger.info("   " + "-" * 76)
        logger.info("   | %-10s | %-25s | %-6s | %-10s | %-8s |", 
                   "Дата", "Событие", "Кол-во", "Пинг (мс)", "Время")
        logger.info("   " + "-" * 76)
        
        for row in report_rows:
            date, event, count, ping, time = row
            logger.info("   | %-10s | %-25s | %-6s | %-10s | %-8s |",
                       date, event[:25], count, ping, time)
        
        logger.info("   " + "-" * 76)
        
        return True, report_rows
    except Exception as e:
        logger.error("Ошибка при подготовке отчёта: %s", e, exc_info=True)
        return False, []


async def _test_google_sheets_write(report_rows):
    """Тест записи в Google Sheets."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("ТЕСТ 6: ЗАПИСЬ В GOOGLE SHEETS")
    logger.info("=" * 80)
    
    try:
        logger.info("Получение текущего количества строк в таблице...")
        initial_count = await sheets_writer.get_row_count()
        logger.info("Количество строк до записи: %s", initial_count)
        
        headers = ["Дата", "Событие", "Кол-во", "Пиковая нагрузка (мс)", "Время пика"]
        logger.info("Проверка заголовков таблицы...")
        await sheets_writer.ensure_headers(headers)
        logger.info("Заголовки установлены")
        
        logger.info("Запись %s строк в Google Sheets...", len(report_rows))
        await sheets_writer.append_rows(report_rows)
        
        final_count = await sheets_writer.get_row_count()
        logger.info("Количество строк после записи: %s", final_count)
        
        added_rows = final_count - initial_count
        logger.info("Добавлено строк: %s", added_rows)
        
        if added_rows >= len(report_rows):
            logger.info("УСПЕШНО: Данные записаны в Google Sheets")
            logger.info("Таблица ID: %s", settings.SHEETS_ID)
            return True
        else:
            logger.error("ОШИБКА: Не все строки были добавлены")
            return False
            
    except Exception as e:
        logger.error("Ошибка при записи в Google Sheets: %s", e, exc_info=True)
        logger.error("")
        logger.error("Проверьте:")
        logger.error("1. SHEETS_ID в .env правильный")
        logger.error("2. Service account имеет доступ к таблице")
        logger.error("3. Файл service-account.json существует")
        return False


@pytest.mark.integration
async def test_full_integration():
    """Полный интеграционный тест проекта."""
    logger.info("=" * 80)
    logger.info("ПОЛНЫЙ ИНТЕГРАЦИОННЫЙ ТЕСТ ПРОЕКТА")
    logger.info("=" * 80)
    logger.info("")
    logger.info("Режим авторизации: %s", 
               "Долгосрочный токен" if settings.AMO_LONG_LIVE_TOKEN else "OAuth2")
    logger.info("Base URL: %s", settings.AMO_BASE_URL)
    logger.info("")
    
    results = {}
    
    success, user_ids = await _test_users()
    results["users"] = success
    
    if not success:
        logger.error("")
        logger.error("Тест пользователей не прошёл. Останавливаем тестирование.")
        return False
    
    success, events, top_events = await _test_events(user_ids)
    results["events"] = success
    
    success, latencies = await _test_latency()
    results["latency"] = success
    
    success, max_latency = await _test_latency_save_and_retrieve()
    results["database"] = success
    
    success, report_rows = _test_report_preparation(top_events, max_latency)
    results["report"] = success
    
    success = await _test_google_sheets_write(report_rows)
    results["google_sheets"] = success
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("ИТОГОВЫЙ ОТЧЁТ")
    logger.info("=" * 80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, success in results.items():
        status = "PASSED" if success else "FAILED"
        logger.info("%s - %s", status, test_name.upper())
    
    logger.info("")
    logger.info("Результат: %s/%s тестов пройдено (%.0f%%)", passed, total, (passed/total)*100)
    logger.info("")
    
    if passed == total:
        logger.info("=" * 80)
        logger.info("ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        logger.info("=" * 80)
        logger.info("")
        logger.info("Проект работает корректно!")
        logger.info("Можно запускать в production:")
        logger.info("   1. poetry run python app/main_ping_probe.py")
        logger.info("   2. poetry run python app/main_daily_report.py")
        logger.info("")
        logger.info("Или настроить systemd:")
        logger.info("   sudo systemctl enable --now amocrm-ping-probe.timer")
        logger.info("   sudo systemctl enable --now amocrm-daily-report.timer")
        return True
    else:
        logger.info("=" * 80)
        logger.info("НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
        logger.info("=" * 80)
        logger.info("")
        logger.info("Проверьте логи выше для деталей.")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_full_integration())
    sys.exit(0 if success else 1)

