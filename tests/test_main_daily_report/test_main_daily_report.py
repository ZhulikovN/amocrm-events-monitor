import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.main_daily_report import (
    format_date,
    format_time,
    prepare_report_data,
    main,
)


class TestFormatFunctions:
    """Тесты для функций форматирования."""

    def test_format_date(self):
        """Тест форматирования даты в DD.MM.YYYY."""
        date = datetime(2025, 11, 11, 10, 30, 0)
        result = format_date(date)
        assert result == "11.11.2025"

    def test_format_date_single_digits(self):
        """Тест форматирования даты с однозначными числами."""
        date = datetime(2025, 1, 5, 10, 30, 0)
        result = format_date(date)
        assert result == "05.01.2025"

    def test_format_time_success(self):
        """Тест успешного форматирования времени."""
        timestamp = "2025-01-15T18:23:00Z"
        result = format_time(timestamp)
        assert result == "18:23"

    def test_format_time_midnight(self):
        """Тест форматирования времени для полуночи."""
        timestamp = "2025-01-15T00:00:00Z"
        result = format_time(timestamp)
        assert result == "00:00"

    def test_format_time_invalid(self):
        """Тест обработки невалидного timestamp."""
        timestamp = "invalid-timestamp"
        result = format_time(timestamp)
        assert result == "invalid-timestamp"


class TestPrepareReportData:
    """Тесты для функции prepare_report_data."""

    def test_prepare_report_data_full(self):
        """Тест подготовки данных с полным набором событий и latency."""
        report_date = datetime(2025, 11, 11)
        top_events = [
            ("Входящее сообщение", 116),
            ("Задача добавлена", 114),
            ("Смена ответственного", 109),
            ("Тег добавлен", 98),
            ("Контакт добавлен", 87),
        ]
        max_latency = ("2025-11-11T18:23:00Z", 72)

        result = prepare_report_data(report_date, top_events, max_latency)

        assert len(result) == 5
        assert result[0] == ["11.11.2025", "Входящее сообщение", 116, 72, "18:23"]
        assert result[1] == ["11.11.2025", "Задача добавлена", 114, "", ""]
        assert result[2] == ["11.11.2025", "Смена ответственного", 109, "", ""]
        assert result[3] == ["11.11.2025", "Тег добавлен", 98, "", ""]
        assert result[4] == ["11.11.2025", "Контакт добавлен", 87, "", ""]

    def test_prepare_report_data_no_latency(self):
        """Тест подготовки данных без latency."""
        report_date = datetime(2025, 11, 11)
        top_events = [
            ("Входящее сообщение", 116),
            ("Задача добавлена", 114),
        ]
        max_latency = None

        result = prepare_report_data(report_date, top_events, max_latency)

        assert len(result) == 2
        assert result[0] == ["11.11.2025", "Входящее сообщение", 116, "", ""]
        assert result[1] == ["11.11.2025", "Задача добавлена", 114, "", ""]

    def test_prepare_report_data_no_events_with_latency(self):
        """Тест подготовки данных без событий, но с latency."""
        report_date = datetime(2025, 11, 11)
        top_events = []
        max_latency = ("2025-11-11T18:23:00Z", 72)

        result = prepare_report_data(report_date, top_events, max_latency)

        assert len(result) == 1
        assert result[0] == ["11.11.2025", "Нет событий", 0, 72, "18:23"]

    def test_prepare_report_data_no_events_no_latency(self):
        """Тест подготовки данных без событий и без latency."""
        report_date = datetime(2025, 11, 11)
        top_events = []
        max_latency = None

        result = prepare_report_data(report_date, top_events, max_latency)

        assert len(result) == 1
        assert result[0] == ["11.11.2025", "Нет событий", 0, "", ""]

    def test_prepare_report_data_less_than_five_events(self):
        """Тест подготовки данных с менее чем 5 событиями."""
        report_date = datetime(2025, 11, 11)
        top_events = [
            ("Событие 1", 50),
            ("Событие 2", 40),
        ]
        max_latency = ("2025-11-11T15:00:00Z", 100)

        result = prepare_report_data(report_date, top_events, max_latency)

        assert len(result) == 2
        assert result[0] == ["11.11.2025", "Событие 1", 50, 100, "15:00"]
        assert result[1] == ["11.11.2025", "Событие 2", 40, "", ""]


class TestMainIntegration:
    """
    Интеграционные тесты для функции main с моками зависимостей.

    Эти тесты проверяют полный процесс формирования отчёта,
    мокируя внешние зависимости (amoCRM API, SQLite, Google Sheets).
    """

    @pytest.mark.asyncio
    @patch("app.main_daily_report.settings")
    @patch("app.main_daily_report.init_token_manager")
    @patch("app.main_daily_report.AmoCRMClient")
    @patch("app.main_daily_report.EventsProcessor")
    @patch("app.main_daily_report.LatencyChecker")
    @patch("app.main_daily_report.sheets_writer")
    async def test_main_success_full_flow(
        self,
        mock_sheets_writer,
        mock_latency_checker_class,
        mock_processor_class,
        mock_amocrm_client_class,
        mock_init_token,
        mock_settings,
    ):
        """Тест успешного выполнения полного процесса формирования отчёта."""
        mock_settings.AMO_LONG_LIVE_TOKEN = None
        
        mock_amocrm_client = AsyncMock()
        mock_amocrm_client.get_users.return_value = [1, 2, 3]
        mock_amocrm_client.get_events.return_value = [
            {"id": 1, "type": "incoming_message", "created_by": None},
            {"id": 2, "type": "task_added", "created_by": None},
            {"id": 3, "type": "task_added", "created_by": None},
        ]
        mock_amocrm_client_class.return_value = mock_amocrm_client

        mock_processor = MagicMock()
        mock_processor.process_events.return_value = [
            ("task_added", 2),
            ("incoming_message", 1),
        ]
        mock_processor_class.return_value = mock_processor

        mock_latency_checker = MagicMock()
        mock_latency_checker.get_max_latency_for_date.return_value = (
            "2025-11-10T15:30:00Z",
            85,
        )
        mock_latency_checker.delete_latency_for_date.return_value = 24
        mock_latency_checker_class.return_value = mock_latency_checker

        mock_sheets_writer.ensure_headers = AsyncMock()
        mock_sheets_writer.append_rows = AsyncMock()

        await main()

        mock_init_token.assert_called_once()
        mock_amocrm_client.get_users.assert_called_once()
        mock_amocrm_client.get_events.assert_called_once()
        mock_processor.process_events.assert_called_once()
        mock_latency_checker.get_max_latency_for_date.assert_called_once()
        mock_sheets_writer.ensure_headers.assert_called_once()
        mock_sheets_writer.append_rows.assert_called_once()
        mock_latency_checker.delete_latency_for_date.assert_called_once()

        call_args = mock_sheets_writer.append_rows.call_args
        rows = call_args[0][0]
        assert len(rows) == 2
        assert rows[0][1] == "task_added"
        assert rows[0][3] == 85
        assert rows[1][3] == ""

    @pytest.mark.asyncio
    @patch("app.main_daily_report.init_token_manager")
    @patch("app.main_daily_report.AmoCRMClient")
    @patch("app.main_daily_report.EventsProcessor")
    @patch("app.main_daily_report.LatencyChecker")
    @patch("app.main_daily_report.sheets_writer")
    async def test_main_no_events(
        self,
        mock_sheets_writer,
        mock_latency_checker_class,
        mock_processor_class,
        mock_amocrm_client_class,
        mock_init_token,
    ):
        """Тест обработки случая, когда нет событий."""
        mock_amocrm_client = AsyncMock()
        mock_amocrm_client.get_users.return_value = [1, 2, 3]
        mock_amocrm_client.get_events.return_value = []
        mock_amocrm_client_class.return_value = mock_amocrm_client

        mock_processor = MagicMock()
        mock_processor.process_events.return_value = []
        mock_processor_class.return_value = mock_processor

        mock_latency_checker = MagicMock()
        mock_latency_checker.get_max_latency_for_date.return_value = (
            "2025-11-10T10:00:00Z",
            50,
        )
        mock_latency_checker.delete_latency_for_date.return_value = 24
        mock_latency_checker_class.return_value = mock_latency_checker

        mock_sheets_writer.ensure_headers = AsyncMock()
        mock_sheets_writer.append_rows = AsyncMock()

        await main()

        mock_sheets_writer.append_rows.assert_called_once()
        call_args = mock_sheets_writer.append_rows.call_args
        rows = call_args[0][0]
        assert len(rows) == 1
        assert rows[0][1] == "Нет событий"
        assert rows[0][2] == 0
        assert rows[0][3] == 50

    @pytest.mark.asyncio
    @patch("app.main_daily_report.init_token_manager")
    @patch("app.main_daily_report.AmoCRMClient")
    @patch("app.main_daily_report.EventsProcessor")
    @patch("app.main_daily_report.LatencyChecker")
    @patch("app.main_daily_report.sheets_writer")
    async def test_main_no_latency(
        self,
        mock_sheets_writer,
        mock_latency_checker_class,
        mock_processor_class,
        mock_amocrm_client_class,
        mock_init_token,
    ):
        """Тест обработки случая, когда нет данных о latency."""
        mock_amocrm_client = AsyncMock()
        mock_amocrm_client.get_users.return_value = [1, 2, 3]
        mock_amocrm_client.get_events.return_value = [
            {"id": 1, "type": "event1", "created_by": None},
        ]
        mock_amocrm_client_class.return_value = mock_amocrm_client

        mock_processor = MagicMock()
        mock_processor.process_events.return_value = [("event1", 1)]
        mock_processor_class.return_value = mock_processor

        mock_latency_checker = MagicMock()
        mock_latency_checker.get_max_latency_for_date.return_value = None
        mock_latency_checker.delete_latency_for_date.return_value = 0
        mock_latency_checker_class.return_value = mock_latency_checker

        mock_sheets_writer.ensure_headers = AsyncMock()
        mock_sheets_writer.append_rows = AsyncMock()

        await main()

        mock_sheets_writer.append_rows.assert_called_once()
        call_args = mock_sheets_writer.append_rows.call_args
        rows = call_args[0][0]
        assert len(rows) == 1
        assert rows[0][1] == "event1"
        assert rows[0][3] == ""
        assert rows[0][4] == ""

    @pytest.mark.asyncio
    @patch("app.main_daily_report.init_token_manager")
    @patch("app.main_daily_report.AmoCRMClient")
    @patch("sys.exit")
    async def test_main_error_handling(
        self, mock_exit, mock_amocrm_client_class, mock_init_token
    ):
        """Тест обработки критических ошибок."""
        mock_amocrm_client = AsyncMock()
        mock_amocrm_client.get_users.side_effect = Exception("API Error")
        mock_amocrm_client_class.return_value = mock_amocrm_client

        await main()

        mock_exit.assert_called_once_with(1)


class TestMainRealIntegration:
    """
    Реальный интеграционный тест для main_daily_report.

    ВНИМАНИЕ: Этот тест требует:
    1. Корректно настроенный .env файл
    2. Валидные credentials для amoCRM
    3. Валидный service-account.json для Google Sheets
    4. Доступ к реальной Google Таблице
    5. Работающую SQLite базу с данными latency
    6. Интернет-соединение

    Для запуска только этого теста:
    pytest tests/test_main_daily_report/test_main_daily_report.py::TestMainRealIntegration -v -m integration
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    @patch("app.main_daily_report.AmoCRMClient")
    @patch("app.main_daily_report.EventsProcessor")
    @patch("app.main_daily_report.LatencyChecker")
    async def test_main_with_real_sheets_mocked_dependencies(
        self,
        mock_latency_checker_class,
        mock_processor_class,
        mock_amocrm_client_class,
    ):
        """
        Интеграционный тест с реальной записью в Google Sheets,
        но с мокированными amoCRM, EventsProcessor и LatencyChecker.

        Этот тест проверяет:
        1. Корректность интеграции с Google Sheets
        2. Правильность формирования данных
        3. Успешную запись в таблицу
        """
        from app.main_daily_report import main

        mock_amocrm_client = AsyncMock()
        mock_amocrm_client.get_users.return_value = [1, 2, 3, 4, 5]
        mock_amocrm_client.get_events.return_value = [
            {"id": i, "type": f"test_event_{i % 5 + 1}", "created_by": None}
            for i in range(50)
        ]
        mock_amocrm_client_class.return_value = mock_amocrm_client

        mock_processor = MagicMock()
        mock_processor.process_events.return_value = [
            ("TEST: Входящее сообщение", 20),
            ("TEST: Задача добавлена", 15),
            ("TEST: Смена ответственного", 10),
            ("TEST: Тег добавлен", 8),
            ("TEST: Контакт добавлен", 5),
        ]
        mock_processor_class.return_value = mock_processor

        mock_latency_checker = MagicMock()
        mock_latency_checker.get_max_latency_for_date.return_value = (
            "2025-11-10T14:45:00Z",
            95,
        )
        mock_latency_checker.delete_latency_for_date.return_value = 24
        mock_latency_checker_class.return_value = mock_latency_checker

        from app.sheets_writer import sheets_writer

        initial_count = await sheets_writer.get_row_count()

        await main()

        final_count = await sheets_writer.get_row_count()

        assert final_count > initial_count, "Строки не были добавлены в таблицу"
        assert final_count >= initial_count + 5, "Не все 5 строк были добавлены"

