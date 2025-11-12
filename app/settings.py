import logging
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    """Настройки приложения для мониторинга событий amoCRM."""

    AMO_LONG_LIVE_TOKEN: str | None = Field(
        default=None,
        description="Долгосрочный токен amoCRM (если используется вместо OAuth2)",
    )

    AMO_BASE_URL: str = Field(
        ...,
        description="Базовый URL AmoCRM аккаунта (например: https://systemkov.amocrm.ru)",
    )

    AMO_CLIENT_ID: str = Field(
        default="",
        description="Client ID интеграции AmoCRM (для OAuth2)",
    )
    AMO_CLIENT_SECRET: str = Field(
        default="",
        description="Client Secret интеграции AmoCRM (для OAuth2)",
    )
    AMO_REDIRECT_URI: str = Field(
        default="https://example.com/oauth/callback",
        description="Redirect URI, указанный при создании интеграции AmoCRM (для OAuth2)",
    )
    AMO_AUTH_CODE: str = Field(
        default="",
        description="Authorization code для первичного получения токена (для OAuth2)",
    )

    SHEETS_ID: str = Field(
        ...,
        description="ID Google-таблицы (из URL)",
    )
    GOOGLE_SERVICE_ACCOUNT_PATH: str = Field(
        default="./secrets/service-account.json",
        description="Путь до JSON-файла сервисного аккаунта Google Cloud",
    )

    CRON_RUN_TIME: str = Field(
        default="03:00",
        description="Время запуска cron-задачи (формат HH:MM)",
    )
    TOP_EVENTS_LIMIT: int = Field(
        default=5,
        description="Количество топ событий для вывода в отчет",
    )
    TIMEZONE: str = Field(
        default="UTC",
        description="Часовой пояс для работы с датами и временем",
    )

    LOG_LEVEL: str = Field(default="INFO", description="Уровень логирования")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def log_level_value(self) -> int:
        """Возвращает числовой уровень логирования для logging.basicConfig."""
        return getattr(logging, self.LOG_LEVEL.upper(), logging.INFO)


settings = Settings()  # type: ignore[call-arg]

if not Path(settings.GOOGLE_SERVICE_ACCOUNT_PATH).is_absolute():
    base_path = Path(__file__).parent.parent
    settings.GOOGLE_SERVICE_ACCOUNT_PATH = str(base_path / settings.GOOGLE_SERVICE_ACCOUNT_PATH)
