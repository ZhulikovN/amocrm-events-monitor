import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.latency_checker import LatencyChecker


@pytest.fixture
def temp_db_path():
    """Создание временного файла базы данных для тестов."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_latency.sqlite")
        yield db_path


@pytest.fixture
def latency_checker(temp_db_path):
    """Создание экземпляра LatencyChecker с временной БД."""
    return LatencyChecker(db_path=temp_db_path)


class TestLatencyCheckerInit:
    """Тесты инициализации LatencyChecker."""

    def test_init_creates_database(self, temp_db_path):
        """Тест: инициализация создает файл базы данных."""
        checker = LatencyChecker(db_path=temp_db_path)
        
        assert os.path.exists(temp_db_path)
        assert checker.db_path == temp_db_path

    def test_init_creates_table(self, temp_db_path):
        """Тест: инициализация создает таблицу latency."""
        checker = LatencyChecker(db_path=temp_db_path)
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='latency'"
        )
        result = cursor.fetchone()
        
        conn.close()
        
        assert result is not None
        assert result[0] == "latency"

    def test_init_creates_index(self, temp_db_path):
        """Тест: инициализация создает индекс на timestamp."""
        checker = LatencyChecker(db_path=temp_db_path)
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_latency_timestamp'"
        )
        result = cursor.fetchone()
        
        conn.close()
        
        assert result is not None
        assert result[0] == "idx_latency_timestamp"

    def test_init_with_relative_path(self):
        """Тест: инициализация с относительным путем."""
        with tempfile.TemporaryDirectory() as tmpdir:
            relative_path = f"{tmpdir}/test_db/latency.sqlite"
            
            checker = LatencyChecker(db_path=relative_path)
            
            assert checker.db_path == relative_path
            assert os.path.exists(relative_path)


class TestSaveLatency:
    """Тесты сохранения latency в БД."""

    def test_save_latency_with_timestamp(self, latency_checker, temp_db_path):
        """Тест: сохранение latency с указанным timestamp."""
        latency_ms = 150
        timestamp = datetime(2025, 1, 15, 14, 30, 0)
        
        latency_checker.save_latency(latency_ms, timestamp)
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, latency_ms FROM latency")
        result = cursor.fetchone()
        conn.close()
        
        assert result is not None
        assert result[0] == "2025-01-15T14:30:00Z"
        assert result[1] == 150

    def test_save_latency_without_timestamp(self, latency_checker, temp_db_path):
        """Тест: сохранение latency без timestamp (автоматически UTC now)."""
        latency_ms = 200
        
        latency_checker.save_latency(latency_ms)
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, latency_ms FROM latency")
        result = cursor.fetchone()
        conn.close()
        
        assert result is not None
        assert result[1] == 200
        
        saved_timestamp = datetime.strptime(result[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        now = datetime.now(UTC)
        time_diff = abs((now - saved_timestamp).total_seconds())
        assert time_diff < 2

    def test_save_multiple_latency(self, latency_checker, temp_db_path):
        """Тест: сохранение нескольких записей latency."""
        test_data = [
            (100, datetime(2025, 1, 15, 10, 0, 0)),
            (150, datetime(2025, 1, 15, 11, 0, 0)),
            (200, datetime(2025, 1, 15, 12, 0, 0)),
        ]
        
        for latency_ms, timestamp in test_data:
            latency_checker.save_latency(latency_ms, timestamp)
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM latency")
        count = cursor.fetchone()[0]
        conn.close()
        
        assert count == 3


class TestGetMaxLatencyForDate:
    """Тесты получения максимального latency за дату."""

    def test_get_max_latency_single_record(self, latency_checker):
        """Тест: получение максимального latency при одной записи."""
        latency_checker.save_latency(150, datetime(2025, 1, 15, 14, 0, 0))
        
        result = latency_checker.get_max_latency_for_date("2025-01-15")
        
        assert result is not None
        assert result[0] == "2025-01-15T14:00:00Z"
        assert result[1] == 150

    def test_get_max_latency_multiple_records(self, latency_checker):
        """Тест: получение максимального latency из нескольких записей."""
        test_data = [
            (100, datetime(2025, 1, 15, 10, 0, 0)),
            (250, datetime(2025, 1, 15, 11, 0, 0)),
            (150, datetime(2025, 1, 15, 12, 0, 0)),
            (200, datetime(2025, 1, 15, 13, 0, 0)),
        ]
        
        for latency_ms, timestamp in test_data:
            latency_checker.save_latency(latency_ms, timestamp)
        
        result = latency_checker.get_max_latency_for_date("2025-01-15")
        
        assert result is not None
        assert result[0] == "2025-01-15T11:00:00Z"
        assert result[1] == 250

    def test_get_max_latency_different_dates(self, latency_checker):
        """Тест: фильтрация по дате при наличии записей за разные дни."""
        test_data = [
            (100, datetime(2025, 1, 14, 10, 0, 0)),
            (250, datetime(2025, 1, 15, 11, 0, 0)),
            (150, datetime(2025, 1, 15, 12, 0, 0)),
            (300, datetime(2025, 1, 16, 13, 0, 0)),
        ]
        
        for latency_ms, timestamp in test_data:
            latency_checker.save_latency(latency_ms, timestamp)
        
        result = latency_checker.get_max_latency_for_date("2025-01-15")
        
        assert result is not None
        assert result[0] == "2025-01-15T11:00:00Z"
        assert result[1] == 250

    def test_get_max_latency_no_data(self, latency_checker):
        """Тест: получение максимального latency когда нет данных за дату."""
        result = latency_checker.get_max_latency_for_date("2025-01-15")
        
        assert result is None


class TestDeleteLatencyForDate:
    """Тесты удаления записей latency за дату."""

    def test_delete_latency_single_date(self, latency_checker):
        """Тест: удаление всех записей за одну дату."""
        test_data = [
            (100, datetime(2025, 1, 15, 10, 0, 0)),
            (150, datetime(2025, 1, 15, 11, 0, 0)),
            (200, datetime(2025, 1, 15, 12, 0, 0)),
        ]
        
        for latency_ms, timestamp in test_data:
            latency_checker.save_latency(latency_ms, timestamp)
        
        deleted_count = latency_checker.delete_latency_for_date("2025-01-15")
        
        assert deleted_count == 3
        
        result = latency_checker.get_max_latency_for_date("2025-01-15")
        assert result is None

    def test_delete_latency_keeps_other_dates(self, latency_checker):
        """Тест: удаление не затрагивает записи других дат."""
        test_data = [
            (100, datetime(2025, 1, 14, 10, 0, 0)),
            (150, datetime(2025, 1, 15, 11, 0, 0)),
            (200, datetime(2025, 1, 15, 12, 0, 0)),
            (300, datetime(2025, 1, 16, 13, 0, 0)),
        ]
        
        for latency_ms, timestamp in test_data:
            latency_checker.save_latency(latency_ms, timestamp)
        
        deleted_count = latency_checker.delete_latency_for_date("2025-01-15")
        
        assert deleted_count == 2
        
        result_yesterday = latency_checker.get_max_latency_for_date("2025-01-14")
        assert result_yesterday is not None
        assert result_yesterday[0] == "2025-01-14T10:00:00Z"
        assert result_yesterday[1] == 100
        
        result_tomorrow = latency_checker.get_max_latency_for_date("2025-01-16")
        assert result_tomorrow is not None
        assert result_tomorrow[0] == "2025-01-16T13:00:00Z"
        assert result_tomorrow[1] == 300

    def test_delete_latency_no_data(self, latency_checker):
        """Тест: удаление когда нет данных за дату."""
        deleted_count = latency_checker.delete_latency_for_date("2025-01-15")
        
        assert deleted_count == 0


class TestGetAllLatencyForDate:
    """Тесты получения всех замеров latency за дату."""

    def test_get_all_latency_multiple_records(self, latency_checker):
        """Тест: получение всех записей за дату."""
        test_data = [
            (100, datetime(2025, 1, 15, 10, 0, 0)),
            (150, datetime(2025, 1, 15, 11, 0, 0)),
            (200, datetime(2025, 1, 15, 12, 0, 0)),
        ]
        
        for latency_ms, timestamp in test_data:
            latency_checker.save_latency(latency_ms, timestamp)
        
        results = latency_checker.get_all_latency_for_date("2025-01-15")
        
        assert len(results) == 3
        assert results[0][1] == 100
        assert results[1][1] == 150
        assert results[2][1] == 200

    def test_get_all_latency_ordered_by_timestamp(self, latency_checker):
        """Тест: результаты отсортированы по timestamp."""
        test_data = [
            (150, datetime(2025, 1, 15, 11, 0, 0)),
            (100, datetime(2025, 1, 15, 10, 0, 0)),
            (200, datetime(2025, 1, 15, 12, 0, 0)),
        ]
        
        for latency_ms, timestamp in test_data:
            latency_checker.save_latency(latency_ms, timestamp)
        
        results = latency_checker.get_all_latency_for_date("2025-01-15")
        
        assert results[0][0] == "2025-01-15T10:00:00Z"
        assert results[1][0] == "2025-01-15T11:00:00Z"
        assert results[2][0] == "2025-01-15T12:00:00Z"

    def test_get_all_latency_no_data(self, latency_checker):
        """Тест: получение всех записей когда нет данных."""
        results = latency_checker.get_all_latency_for_date("2025-01-15")
        
        assert len(results) == 0


class TestMeasureLatency:
    """Тесты замера latency."""

    @pytest.mark.asyncio
    async def test_measure_latency_returns_milliseconds(self, latency_checker):
        """Тест: замер latency возвращает значение в миллисекундах."""
        mock_client = AsyncMock()
        mock_client.get_account_info = AsyncMock()
        
        with patch("app.latency_checker.AmoCRMClient", return_value=mock_client):
            latency_ms = await latency_checker.measure_latency()
            
            assert isinstance(latency_ms, int)
            assert latency_ms >= 0

    @pytest.mark.asyncio
    async def test_measure_latency_calls_get_account_info(self, latency_checker):
        """Тест: замер latency вызывает get_account_info."""
        mock_client = AsyncMock()
        mock_client.get_account_info = AsyncMock()
        
        with patch("app.latency_checker.AmoCRMClient", return_value=mock_client):
            await latency_checker.measure_latency()
            
            mock_client.get_account_info.assert_called_once()


class TestMeasureAndSave:
    """Тесты комбинированного метода measure_and_save."""

    @pytest.mark.asyncio
    async def test_measure_and_save(self, latency_checker, temp_db_path):
        """Тест: measure_and_save замеряет и сохраняет latency."""
        mock_client = AsyncMock()
        mock_client.get_account_info = AsyncMock()
        
        with patch("app.latency_checker.AmoCRMClient", return_value=mock_client):
            latency_ms = await latency_checker.measure_and_save()
            
            assert isinstance(latency_ms, int)
            
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM latency")
            count = cursor.fetchone()[0]
            conn.close()
            
            assert count == 1


class TestComplexScenario:
    """Тесты сложных сценариев использования."""

    def test_full_day_cycle(self, latency_checker):
        """
        Тест: полный цикл работы за сутки.
        
        Сценарий:
        1. Сохранение почасовых замеров за день
        2. Получение максимального значения
        3. Удаление данных после обработки
        """
        test_date = "2025-01-15"
        hourly_data = [
            (50, datetime(2025, 1, 15, 0, 0, 0)),
            (60, datetime(2025, 1, 15, 1, 0, 0)),
            (45, datetime(2025, 1, 15, 2, 0, 0)),
            (70, datetime(2025, 1, 15, 3, 0, 0)),
            (55, datetime(2025, 1, 15, 4, 0, 0)),
            (65, datetime(2025, 1, 15, 5, 0, 0)),
            (80, datetime(2025, 1, 15, 6, 0, 0)),
            (75, datetime(2025, 1, 15, 7, 0, 0)),
            (90, datetime(2025, 1, 15, 8, 0, 0)),
            (95, datetime(2025, 1, 15, 9, 0, 0)),
            (120, datetime(2025, 1, 15, 10, 0, 0)),
            (85, datetime(2025, 1, 15, 11, 0, 0)),
            (70, datetime(2025, 1, 15, 12, 0, 0)),
        ]
        
        for latency_ms, timestamp in hourly_data:
            latency_checker.save_latency(latency_ms, timestamp)
        
        all_records = latency_checker.get_all_latency_for_date(test_date)
        assert len(all_records) == 13
        
        max_latency = latency_checker.get_max_latency_for_date(test_date)
        assert max_latency is not None
        assert max_latency[0] == "2025-01-15T10:00:00Z"
        assert max_latency[1] == 120
        
        deleted = latency_checker.delete_latency_for_date(test_date)
        assert deleted == 13
        
        after_delete = latency_checker.get_max_latency_for_date(test_date)
        assert after_delete is None

