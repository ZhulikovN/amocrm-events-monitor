import logging
import os

from amocrm.v2 import tokens

from app.settings import settings

logger = logging.getLogger(__name__)


def init_token_manager() -> None:
    """
    Инициализация менеджера токенов AmoCRM.

    Устанавливает хранилище токенов в .amocrm_tokens/,
    выполняет первичную авторизацию при отсутствии токенов,
    дальнейшее обновление токенов выполняется автоматически.
    """
    subdomain = settings.AMO_BASE_URL

    BASE_DIR = os.path.dirname(os.path.dirname(__file__))
    token_dir = os.path.join(BASE_DIR, ".amocrm_tokens")

    os.makedirs(token_dir, exist_ok=True)

    tokens.default_token_manager(
        client_id=settings.AMO_CLIENT_ID,
        client_secret=settings.AMO_CLIENT_SECRET,
        subdomain=subdomain,
        redirect_url=settings.AMO_REDIRECT_URI,
        storage=tokens.FileTokensStorage(token_dir),
    )

    access_path = os.path.join(token_dir, "access_token.txt")
    refresh_path = os.path.join(token_dir, "refresh_token.txt")

    if os.path.exists(access_path) and os.path.exists(refresh_path):
        logger.info("Найдены сохранённые токены — используем их.")
    else:
        try:
            logger.info("Нет сохранённых токенов — инициализация через auth_code...")
            tokens.default_token_manager.init(code=settings.AMO_AUTH_CODE, skip_error=True)
            logger.info("Первичная инициализация выполнена, токены сохранены.")
        except Exception as e:
            logger.warning(
                "Не удалось инициализировать токены через auth_code: %s. Токены будут обновлены при первом запросе.", e
            )
