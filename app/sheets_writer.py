import asyncio
import logging
import threading
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from app.settings import settings

logger = logging.getLogger(__name__)


class SheetsWriter:
    """
    Класс для записи данных в Google Sheets.

    Использует gspread и service account для авторизации.
    Все операции выполняются через asyncio.to_thread для неблокирующей работы.
    """

    def __init__(self) -> None:
        """Инициализация клиента Google Sheets."""
        self.spreadsheet_id = settings.SHEETS_ID
        self._client: gspread.Client | None = None
        self._worksheet: gspread.Worksheet | None = None
        self._init_lock = threading.Lock()

    def _get_credentials(self) -> Credentials:
        """
        Получение credentials из service account JSON файла.

        Returns:
            Credentials: Google OAuth2 credentials

        Raises:
            FileNotFoundError: Если файл service account не найден
        """
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        try:
            return Credentials.from_service_account_file(  # type: ignore[no-any-return,no-untyped-call]
                settings.GOOGLE_SERVICE_ACCOUNT_PATH,
                scopes=scopes,
            )
        except FileNotFoundError as e:
            logger.error("Файл service account не найден: %s", settings.GOOGLE_SERVICE_ACCOUNT_PATH)
            raise FileNotFoundError(f"Service account файл не найден: {settings.GOOGLE_SERVICE_ACCOUNT_PATH}") from e

    def _get_worksheet(self) -> gspread.Worksheet:
        """
        Получение worksheet объекта.

        Использует double-checked locking для thread-safety.

        Returns:
            gspread.Worksheet: Объект листа таблицы

        Raises:
            gspread.SpreadsheetNotFound: Если таблица не найдена
            gspread.WorksheetNotFound: Если лист не найден
        """
        if self._worksheet is None:
            with self._init_lock:
                if self._worksheet is None:
                    if self._client is None:
                        credentials = self._get_credentials()
                        self._client = gspread.authorize(credentials)
                        logger.info("Авторизация в Google Sheets выполнена")

                    spreadsheet = self._client.open_by_key(self.spreadsheet_id)
                    logger.info("Открыта таблица: %s", spreadsheet.title)

                    self._worksheet = spreadsheet.sheet1
                    logger.info("Получен лист: %s", self._worksheet.title)

        return self._worksheet

    async def append_rows(self, rows: list[list[Any]]) -> None:
        """
        Добавление строк в конец таблицы.

        Args:
            rows: Список строк для добавления. Каждая строка - список значений.

        Raises:
            Exception: При ошибках записи в Google Sheets
        """
        if not rows:
            logger.warning("Попытка добавить пустой список строк")
            return

        try:
            logger.info("Добавление %s строк в Google Sheets...", len(rows))

            def _append() -> None:
                worksheet = self._get_worksheet()
                worksheet.append_rows(rows, value_input_option="USER_ENTERED")  # type: ignore[arg-type]

            await asyncio.to_thread(_append)

            logger.info("Успешно добавлено %s строк в таблицу", len(rows))

        except Exception as e:
            logger.error("Ошибка при добавлении строк в Google Sheets: %s", e, exc_info=True)
            raise

    async def ensure_headers(self, headers: list[str]) -> None:
        """
        Проверка и установка заголовков таблицы.

        Если первая строка пустая или не совпадает с ожидаемыми заголовками,
        устанавливает правильные заголовки.

        Args:
            headers: Список заголовков колонок

        Raises:
            Exception: При ошибках работы с Google Sheets
        """
        try:
            logger.info("Проверка заголовков таблицы...")

            def _check_and_set_headers() -> None:
                worksheet = self._get_worksheet()
                existing_headers = worksheet.row_values(1)

                if not existing_headers or existing_headers != headers:
                    logger.info("Установка заголовков: %s", headers)
                    worksheet.update([headers], "A1")
                    logger.info("Заголовки установлены")
                else:
                    logger.info("Заголовки уже установлены корректно")

            await asyncio.to_thread(_check_and_set_headers)

        except Exception as e:
            logger.error("Ошибка при проверке заголовков: %s", e, exc_info=True)
            raise

    async def get_row_count(self) -> int:
        """
        Получение количества строк в таблице.

        Returns:
            int: Количество строк (включая заголовки)

        Raises:
            Exception: При ошибках работы с Google Sheets
        """
        try:

            def _get_count() -> int:
                worksheet = self._get_worksheet()
                return len(worksheet.get_all_values())

            row_count: int = await asyncio.to_thread(_get_count)
            logger.debug("Количество строк в таблице: %s", row_count)
            return row_count

        except Exception as e:
            logger.error("Ошибка при получении количества строк: %s", e)
            raise


sheets_writer = SheetsWriter()
