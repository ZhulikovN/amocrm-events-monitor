#!/usr/bin/env python3
"""
Скрипт для почасового замера latency API amoCRM.

Запускается автоматически каждый час через systemd timer (amocrm-ping-probe.timer).

Выполняет:
1. Инициализацию token manager
2. Замер latency через запрос к /api/v4/account
3. Сохранение результата в SQLite
"""

import asyncio
import logging
import sys

from app.latency_checker import LatencyChecker
from app.settings import settings
from app.token_manager import init_token_manager

logging.basicConfig(
    level=settings.log_level_value,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


async def main() -> None:
    """Основная функция для почасового замера latency."""
    try:
        logger.info("=" * 60)
        logger.info("Запуск почасового замера latency API amoCRM")
        logger.info("=" * 60)

        if settings.AMO_LONG_LIVE_TOKEN:
            logger.info("Используется долгосрочный токен (OAuth2 не требуется)")
        else:
            logger.info("Инициализация token manager (OAuth2)...")
            init_token_manager()

        checker = LatencyChecker()

        latency_ms = await checker.measure_and_save()

        logger.info("=" * 60)
        logger.info("Почасовой замер latency завершен успешно: %s мс", latency_ms)
        logger.info("=" * 60)

    except Exception as e:
        logger.error("Критическая ошибка при замере latency: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
