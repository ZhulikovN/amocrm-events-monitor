import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.sheets_writer import SheetsWriter, sheets_writer


class TestSheetsWriterUnit:
    """Unit-тесты для SheetsWriter с моками."""

    @pytest.fixture
    def writer(self):
        """Создание экземпляра SheetsWriter для тестов."""
        return SheetsWriter()

    def test_init(self, writer):
        """Тест инициализации SheetsWriter."""
        assert writer.spreadsheet_id is not None
        assert writer._client is None
        assert writer._worksheet is None
        assert writer._init_lock is not None

    @patch("app.sheets_writer.Credentials.from_service_account_file")
    def test_get_credentials_success(self, mock_credentials, writer):
        """Тест успешного получения credentials."""
        mock_creds = MagicMock()
        mock_credentials.return_value = mock_creds

        result = writer._get_credentials()

        assert result == mock_creds
        mock_credentials.assert_called_once()
        args, kwargs = mock_credentials.call_args
        assert "scopes" in kwargs
        assert "https://www.googleapis.com/auth/spreadsheets" in kwargs["scopes"]
        assert "https://www.googleapis.com/auth/drive" in kwargs["scopes"]

    @patch("app.sheets_writer.Credentials.from_service_account_file")
    def test_get_credentials_file_not_found(self, mock_credentials, writer):
        """Тест обработки ошибки, когда файл credentials не найден."""
        mock_credentials.side_effect = FileNotFoundError("File not found")

        with pytest.raises(FileNotFoundError) as exc_info:
            writer._get_credentials()

        assert "Service account файл не найден" in str(exc_info.value)

    @patch("app.sheets_writer.gspread.authorize")
    @patch.object(SheetsWriter, "_get_credentials")
    def test_get_worksheet_initialization(self, mock_get_credentials, mock_authorize, writer):
        """Тест инициализации worksheet при первом обращении."""
        mock_creds = MagicMock()
        mock_get_credentials.return_value = mock_creds

        mock_client = MagicMock()
        mock_authorize.return_value = mock_client

        mock_spreadsheet = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet

        mock_sheet = MagicMock()
        mock_sheet.title = "Лист1"
        mock_spreadsheet.sheet1 = mock_sheet

        result = writer._get_worksheet()

        assert result == mock_sheet
        assert writer._worksheet == mock_sheet
        assert writer._client == mock_client
        mock_get_credentials.assert_called_once()
        mock_authorize.assert_called_once_with(mock_creds)
        mock_client.open_by_key.assert_called_once_with(writer.spreadsheet_id)

    @patch.object(SheetsWriter, "_get_worksheet")
    @pytest.mark.asyncio
    async def test_append_rows_success(self, mock_get_worksheet, writer):
        """Тест успешного добавления строк."""
        mock_worksheet = MagicMock()
        mock_get_worksheet.return_value = mock_worksheet

        rows = [
            ["11.11.2025", "Событие 1", 100, 50, "10:00"],
            ["11.11.2025", "Событие 2", 90, "", ""],
        ]

        await writer.append_rows(rows)

        mock_worksheet.append_rows.assert_called_once_with(
            rows, value_input_option="USER_ENTERED"
        )

    @pytest.mark.asyncio
    async def test_append_rows_empty_list(self, writer):
        """Тест попытки добавить пустой список строк."""
        await writer.append_rows([])

    @patch.object(SheetsWriter, "_get_worksheet")
    @pytest.mark.asyncio
    async def test_append_rows_exception(self, mock_get_worksheet, writer):
        """Тест обработки ошибки при добавлении строк."""
        mock_worksheet = MagicMock()
        mock_worksheet.append_rows.side_effect = Exception("API Error")
        mock_get_worksheet.return_value = mock_worksheet

        rows = [["11.11.2025", "Событие 1", 100, 50, "10:00"]]

        with pytest.raises(Exception) as exc_info:
            await writer.append_rows(rows)

        assert "API Error" in str(exc_info.value)

    @patch.object(SheetsWriter, "_get_worksheet")
    @pytest.mark.asyncio
    async def test_ensure_headers_not_set(self, mock_get_worksheet, writer):
        """Тест установки заголовков, когда они не установлены."""
        mock_worksheet = MagicMock()
        mock_worksheet.row_values.return_value = []
        mock_get_worksheet.return_value = mock_worksheet

        headers = ["Дата", "Событие", "Кол-во", "Пиковая нагрузка (мс)", "Время пика"]

        await writer.ensure_headers(headers)

        mock_worksheet.update.assert_called_once_with([headers], "A1")

    @patch.object(SheetsWriter, "_get_worksheet")
    @pytest.mark.asyncio
    async def test_ensure_headers_already_set(self, mock_get_worksheet, writer):
        """Тест проверки заголовков, когда они уже установлены корректно."""
        headers = ["Дата", "Событие", "Кол-во", "Пиковая нагрузка (мс)", "Время пика"]

        mock_worksheet = MagicMock()
        mock_worksheet.row_values.return_value = headers
        mock_get_worksheet.return_value = mock_worksheet

        await writer.ensure_headers(headers)

        mock_worksheet.update.assert_not_called()

    @patch.object(SheetsWriter, "_get_worksheet")
    @pytest.mark.asyncio
    async def test_ensure_headers_different(self, mock_get_worksheet, writer):
        """Тест установки заголовков, когда они отличаются от ожидаемых."""
        mock_worksheet = MagicMock()
        mock_worksheet.row_values.return_value = ["Старый", "Заголовок"]
        mock_get_worksheet.return_value = mock_worksheet

        headers = ["Дата", "Событие", "Кол-во", "Пиковая нагрузка (мс)", "Время пика"]

        await writer.ensure_headers(headers)

        mock_worksheet.update.assert_called_once_with([headers], "A1")

    @patch.object(SheetsWriter, "_get_worksheet")
    @pytest.mark.asyncio
    async def test_get_row_count(self, mock_get_worksheet, writer):
        """Тест получения количества строк."""
        mock_worksheet = MagicMock()
        mock_worksheet.get_all_values.return_value = [
            ["header1", "header2"],
            ["row1", "data1"],
            ["row2", "data2"],
        ]
        mock_get_worksheet.return_value = mock_worksheet

        count = await writer.get_row_count()

        assert count == 3
        mock_worksheet.get_all_values.assert_called_once()


class TestSheetsWriterIntegration:
    """
    Интеграционный тест для записи в Google Sheets.

    ВНИМАНИЕ: Этот тест требует:
    1. Корректно настроенный .env файл
    2. Валидный service-account.json
    3. Доступ к реальной Google Таблице
    4. Интернет-соединение

    Для запуска только этого теста:
    pytest tests/test_sheets_writer/test_sheets_writer.py::TestSheetsWriterIntegration -v
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_write_to_sheets(self):
        """
        Интеграционный тест записи данных в реальную Google Sheets.

        Этот тест:
        1. Проверяет/устанавливает заголовки
        2. Записывает тестовые данные
        3. Проверяет количество строк

        ВАЖНО: Тест помечен маркером @pytest.mark.integration
        Для его запуска нужно использовать:
        pytest -m integration
        """
        from datetime import datetime

        test_date = datetime.now().strftime("%d.%m.%Y")
        test_rows = [
            [test_date, "TEST: Событие 1", 100, 50, "10:00"],
            [test_date, "TEST: Событие 2", 90, "", ""],
            [test_date, "TEST: Событие 3", 80, "", ""],
            [test_date, "TEST: Событие 4", 70, "", ""],
            [test_date, "TEST: Событие 5", 60, "", ""],
        ]

        headers = ["Дата", "Событие", "Кол-во", "Пиковая нагрузка (мс)", "Время пика"]

        initial_count = await sheets_writer.get_row_count()

        await sheets_writer.ensure_headers(headers)

        await sheets_writer.append_rows(test_rows)

        final_count = await sheets_writer.get_row_count()

        assert final_count > initial_count, "Строки не были добавлены в таблицу"
        assert final_count >= initial_count + len(test_rows), "Не все строки были добавлены"

