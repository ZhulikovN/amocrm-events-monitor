import logging
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from app.amocrm_client import AmoCRMClient

logger = logging.getLogger(__name__)


class LatencyChecker:
    """
    Класс для замера latency (пинга) API amoCRM и сохранения результатов в SQLite.

    Структура таблицы:
        latency (
            timestamp TEXT (UTC),
            latency_ms INTEGER
        )
    """

    def __init__(self, db_path: str = "./db/latency.sqlite") -> None:
        """
        Инициализация LatencyChecker.

        Args:
            db_path: Путь к файлу базы данных SQLite
        """
        if not Path(db_path).is_absolute():
            base_path = Path(__file__).parent.parent
            self.db_path = str(base_path / db_path)
        else:
            self.db_path = db_path

        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self._init_database()

    def _init_database(self) -> None:
        """Инициализация базы данных и создание таблицы."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS latency (
                    timestamp TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL
                )
                """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_latency_timestamp
                ON latency(timestamp)
                """)

            conn.commit()
            conn.close()

            logger.info("База данных инициализирована: %s", self.db_path)

        except Exception as e:
            logger.error("Ошибка при инициализации базы данных: %s", e)
            raise

    async def measure_latency(self) -> int:
        """
        Замер latency (времени отклика) API amoCRM.

        Выполняет запрос к /api/v4/account и измеряет время ответа.

        Returns:
            int: Время отклика в миллисекундах

        Raises:
            Exception: При ошибках запроса
        """
        client = AmoCRMClient()

        try:
            logger.debug("Начало замера latency...")
            start_time = time.time()

            await client.get_account_info()

            end_time = time.time()
            latency_ms = int((end_time - start_time) * 1000)

            logger.info("Замер latency выполнен: %s мс", latency_ms)
            return latency_ms

        except Exception as e:
            logger.error("Ошибка при замере latency: %s", e)
            raise

    def save_latency(self, latency_ms: int, timestamp: datetime | None = None) -> None:
        """
        Сохранение результата замера latency в базу данных.

        Args:
            latency_ms: Время отклика в миллисекундах
            timestamp: Временная метка (по умолчанию текущее время UTC)

        Raises:
            Exception: При ошибках записи в БД
        """
        if timestamp is None:
            timestamp = datetime.now(UTC)

        timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                "INSERT INTO latency (timestamp, latency_ms) VALUES (?, ?)",
                (timestamp_str, latency_ms),
            )

            conn.commit()
            conn.close()

            logger.info("Latency сохранен в БД: %s мс в %s", latency_ms, timestamp_str)

        except Exception as e:
            logger.error("Ошибка при сохранении latency в БД: %s", e)
            raise

    async def measure_and_save(self) -> int:
        """
        Замер latency и сохранение результата в БД.

        Returns:
            int: Время отклика в миллисекундах

        Raises:
            Exception: При ошибках замера или сохранения
        """
        latency_ms = await self.measure_latency()
        self.save_latency(latency_ms)
        return latency_ms

    def get_max_latency_for_date(self, date: str) -> tuple[str, int] | None:
        """
        Получение максимального latency за указанную дату.

        Args:
            date: Дата в формате YYYY-MM-DD

        Returns:
            tuple[str, int] | None: Кортеж (timestamp, max_latency_ms) или None если данных нет
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT timestamp, latency_ms
                FROM latency
                WHERE date(timestamp) = ?
                ORDER BY latency_ms DESC
                LIMIT 1
                """,
                (date,),
            )

            result = cursor.fetchone()
            conn.close()

            if result:
                timestamp_str, latency_ms = result
                logger.info("Максимальный latency за %s: %s мс в %s", date, latency_ms, timestamp_str)
                return timestamp_str, latency_ms

            logger.info("Нет данных о latency за дату %s", date)
            return None

        except Exception as e:
            logger.error("Ошибка при получении максимального latency: %s", e)
            raise

    def delete_latency_for_date(self, date: str) -> int:
        """
        Удаление записей latency за указанную дату.

        Args:
            date: Дата в формате YYYY-MM-DD

        Returns:
            int: Количество удаленных записей
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                DELETE FROM latency
                WHERE date(timestamp) = ?
                """,
                (date,),
            )

            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()

            logger.info("Удалено записей latency за %s: %s", date, deleted_count)
            return deleted_count

        except Exception as e:
            logger.error("Ошибка при удалении записей latency: %s", e)
            raise

    def get_all_latency_for_date(self, date: str) -> list[tuple[str, int]]:
        """
        Получение всех замеров latency за указанную дату.

        Args:
            date: Дата в формате YYYY-MM-DD

        Returns:
            list[tuple[str, int]]: Список кортежей (timestamp, latency_ms)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT timestamp, latency_ms
                FROM latency
                WHERE date(timestamp) = ?
                ORDER BY timestamp
                """,
                (date,),
            )

            results = cursor.fetchall()
            conn.close()

            logger.info("Получено замеров latency за %s: %s", date, len(results))
            return results

        except Exception as e:
            logger.error("Ошибка при получении замеров latency: %s", e)
            raise
