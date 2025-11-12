# amocrm-events-monitor

Сервис автоматического мониторинга производительности и стабильности работы amoCRM.

## Описание

Проект предназначен для решения проблемы нестабильной работы amoCRM: задержки в интерфейсе, медленное срабатывание
автоматизаций, зависания системы. Сервис автоматически собирает данные о событиях и времени отклика API, позволяя:

- Определять типы событий, создающих наибольшую нагрузку на систему
- Выявлять временные периоды с максимальной нагрузкой
- Оценивать скорость отклика amoCRM (замер пинга API)
- Анализировать данные за разные периоды для выявления закономерностей

Все данные автоматически выгружаются в Google Sheets для удобного анализа и визуализации.

## Основная логика

Проект состоит из двух независимых процессов:

### 1. Почасовой замер пинга (`main_ping_probe.py`)

Запускается каждый час через systemd timer. Выполняет:

- Замер времени отклика amoCRM API (через запрос к `/api/v4/account`)
- Сохранение результата в локальную SQLite базу с timestamp

### 2. Ежедневный отчет (`main_daily_report.py`)

Запускается раз в сутки в 03:00 через systemd timer. Выполняет:

- Получение списка пользователей аккаунта
- Сбор всех событий за предыдущий день через API `/api/v4/events`
- Фильтрацию автоматических событий (исключение действий пользователей)
- Подсчет количества событий каждого типа
- Определение TOP-5 событий по количеству срабатываний
- Извлечение максимального пинга за день из базы данных
- Формирование и запись данных в Google Sheets
- Очистку обработанных данных пинга из базы

## Архитектура проекта

```
amocrm-events-monitor/
├── app/                          # Основной код приложения
│   ├── amocrm_client.py         # Клиент для работы с AmoCRM API
│   ├── events_processor.py      # Обработка и фильтрация событий
│   ├── http_client.py           # HTTP клиент с обработкой ошибок
│   ├── latency_checker.py       # Замер и хранение пинга
│   ├── main_daily_report.py     # Скрипт ежедневного отчета
│   ├── main_ping_probe.py       # Скрипт почасового замера пинга
│   ├── settings.py              # Настройки приложения
│   ├── sheets_writer.py         # Работа с Google Sheets API
│   └── token_manager.py         # Управление OAuth2 токенами
├── db/                           # База данных SQLite
│   └── latency.sqlite           # Хранение замеров пинга
├── etc/                          # Конфигурационные файлы
│   └── systemd/                 # Systemd unit файлы
│       ├── amocrm-ping-probe.service
│       ├── amocrm-ping-probe.timer
│       ├── amocrm-daily-report.service
│       ├── amocrm-daily-report.timer
│       └── README.md            # Инструкция по установке systemd
├── secrets/                      # Секретные данные (не в git)
│   └── service-account.json     # Google Cloud сервисный аккаунт
├── tests/                        # Тесты
│   ├── test_latency_checker/
│   ├── test_main_daily_report/
│   ├── test_sheets_writer/
│   └── test_real_integration.py # Полный интеграционный тест
├── .env                          # Переменные окружения (не в git)
├── pyproject.toml               # Зависимости Poetry
├── Makefile                      # Команды для разработки
└── README.md                     # Документация

```

## Описание модулей

### `amocrm_client.py`

Клиент для работы с AmoCRM API. Основные методы:

- `get_users()` - получение списка всех пользователей аккаунта через `/api/v4/users`
    - Возвращает список ID всех пользователей аккаунта
    - Используется для фильтрации событий: если событие создано пользователем из этого списка, оно считается ручным
      действием и исключается
    - Если `created_by` отсутствует или не входит в список пользователей, событие считается автоматическим

- `get_events(date_from, date_to)` - получение событий за указанный период через `/api/v4/events`
    - Постраничная загрузка всех событий (по 100 событий на страницу)
    - Фильтрация по временному диапазону через timestamp
    - Автоматическая обработка пагинации до получения всех событий

- `get_account_info()` - получение информации об аккаунте через `/api/v4/account`
    - Используется для замера времени отклика API (latency)
    - Легковесный запрос для проверки доступности и скорости ответа amoCRM

Поддерживает два режима авторизации:

- Долгосрочный токен (`AMO_LONG_LIVE_TOKEN`)
- OAuth2 с автоматическим обновлением токенов

### `events_processor.py`

Обработчик событий amoCRM:

- `filter_automated_events(events, user_ids)` - фильтрация автоматических событий
    - Исключает события, где `created_by` присутствует в списке `user_ids`
    - Оставляет только события от роботов, интеграций и системных процессов

- `count_event_types(events)` - подсчет количества событий каждого типа

- `get_top_events(event_counts, limit)` - получение TOP-N событий по количеству

- `process_events(events, user_ids)` - полный цикл обработки (фильтрация + подсчет + топ)

### `latency_checker.py`

Управление замерами пинга API:

- `measure_latency()` - замер времени отклика API (запрос к `/api/v4/account`)
- `save_latency(latency_ms, timestamp)` - сохранение замера в SQLite
- `measure_and_save()` - комбинированный метод для замера и сохранения
- `get_max_latency_for_date(date)` - получение максимального пинга за дату
- `get_all_latency_for_date(date)` - получение всех замеров за дату
- `delete_latency_for_date(date)` - удаление обработанных данных

База данных SQLite создается автоматически при первом запуске.

### `sheets_writer.py`

Работа с Google Sheets API:

- `append_rows(rows)` - добавление строк в конец таблицы
- `ensure_headers(headers)` - проверка и установка заголовков
- `get_row_count()` - получение количества строк в таблице

Использует сервисный аккаунт Google Cloud для авторизации.

### `token_manager.py`

Управление OAuth2 токенами amoCRM:

- `init_token_manager()` - инициализация token manager с первичным получением токенов
- Автоматическое обновление access token при истечении
- Хранение токенов в файловой системе через библиотеку `amocrm`

Используется только если не указан `AMO_LONG_LIVE_TOKEN`.

### `main_daily_report.py`

Главный скрипт ежедневного отчета. Логика работы:

1. Определение даты отчета (вчерашний день)
2. Инициализация OAuth2 (если требуется)
3. **Получение списка пользователей** через `/api/v4/users`
    - Запрашивается полный список ID пользователей аккаунта
    - Эти ID используются для отделения ручных действий от автоматических событий
4. Загрузка событий за вчерашний день (00:00 - 23:59:59) через `/api/v4/events`
5. **Фильтрация и обработка событий**
    - Проверка поля `created_by` каждого события
    - Если `created_by` есть в списке пользователей → событие создано вручную → **исключается**
    - Если `created_by` отсутствует или не в списке → событие автоматическое → **включается в отчет**
    - Подсчет количества событий каждого типа
    - Определение TOP-5 событий
6. Получение максимального пинга из базы
7. Формирование данных для таблицы
8. Запись в Google Sheets
9. Удаление обработанных данных пинга

**Ключевой принцип фильтрации:**
События создаются либо пользователями (через интерфейс amoCRM), либо автоматическими процессами (роботы, интеграции,
API).
AmoCRM указывает создателя в поле `created_by` - если это ID реального пользователя, событие исключается из анализа.
Таким образом собираются только события от автоматизаций, которые и создают основную нагрузку на систему.

### `main_ping_probe.py`

Скрипт почасового замера пинга. Логика работы:

1. Инициализация OAuth2 (если требуется)
2. Замер времени отклика API
3. Сохранение результата в SQLite с текущим timestamp

## Установка

### Предварительные требования

- Python 3.12+
- Poetry для управления зависимостями
- Systemd (для автоматического запуска)
- Доступ к amoCRM API (интеграция или долгосрочный токен)
- Google Cloud сервисный аккаунт с доступом к Google Sheets API

### Шаг 1: Клонирование и установка зависимостей

```bash
# Создание директории и копирование проекта
sudo mkdir -p /opt/amocrm-events-monitor
sudo cp -r /path/to/project/* /opt/amocrm-events-monitor/

# Переход в директорию проекта
cd /opt/amocrm-events-monitor

# Установка зависимостей через Poetry
poetry install
```

### Шаг 2: Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```bash
# AmoCRM настройки
AMO_BASE_URL=https://your-account.amocrm.ru
AMO_LONG_LIVE_TOKEN=your_long_live_token_here

# Если используется OAuth2 вместо долгосрочного токена:
# AMO_CLIENT_ID=your_client_id
# AMO_CLIENT_SECRET=your_client_secret
# AMO_REDIRECT_URI=https://example.com/oauth/callback
# AMO_AUTH_CODE=your_authorization_code

# Google Sheets настройки
SHEETS_ID=your_google_sheet_id_from_url
GOOGLE_SERVICE_ACCOUNT_PATH=./secrets/service-account.json

# Дополнительные настройки
TOP_EVENTS_LIMIT=5
TIMEZONE=UTC
LOG_LEVEL=INFO
```

#### Получение амoCRM токена

**Вариант 1: Долгосрочный токен (рекомендуется)**

1. Зайдите в настройки amoCRM → Интеграции → Создать интеграцию
2. Получите долгосрочный токен (действует до отзыва)
3. Укажите его в `AMO_LONG_LIVE_TOKEN`

**Вариант 2: OAuth2**

1. Создайте интеграцию в amoCRM
2. Получите `CLIENT_ID`, `CLIENT_SECRET`, `REDIRECT_URI`
3. Получите authorization code через OAuth2 flow
4. Укажите все параметры в `.env`

#### Настройка Google Sheets

1. Создайте проект в Google Cloud Console
2. Включите Google Sheets API
3. Создайте сервисный аккаунт
4. Скачайте JSON ключ и сохраните в `secrets/service-account.json`
5. Создайте Google Таблицу и предоставьте доступ сервисному аккаунту (email из JSON)
6. Скопируйте ID таблицы из URL и укажите в `SHEETS_ID`

### Шаг 3: Создание базы данных

База данных SQLite создается автоматически при первом запуске. Убедитесь, что директория `db/` существует:

```bash
mkdir -p /opt/amocrm-events-monitor/db
```

### Шаг 4: Тестовый запуск

Проверьте работоспособность скриптов вручную:

```bash
# Тест замера пинга
poetry run python app/main_ping_probe.py

# Тест ежедневного отчета
poetry run python app/main_daily_report.py
```

### Шаг 5: Настройка systemd

Скопируйте unit файлы в systemd:

```bash
sudo cp etc/systemd/*.service /etc/systemd/system/
sudo cp etc/systemd/*.timer /etc/systemd/system/
```

Перезагрузите systemd и включите таймеры:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now amocrm-ping-probe.timer
sudo systemctl enable --now amocrm-daily-report.timer
```

Проверьте статус:

```bash
# Список активных таймеров
systemctl list-timers

# Статус конкретных таймеров
systemctl status amocrm-ping-probe.timer
systemctl status amocrm-daily-report.timer
```

## Использование

### Автоматический запуск

После настройки systemd скрипты будут запускаться автоматически:

- **amocrm-ping-probe**: каждый час в начале часа (00:00, 01:00, 02:00, ...)
- **amocrm-daily-report**: каждый день в 03:00

### Ручной запуск

Для тестирования или внеплановой выгрузки:

```bash
# Запуск замера пинга
sudo systemctl start amocrm-ping-probe.service

# Запуск ежедневного отчета
sudo systemctl start amocrm-daily-report.service
```

Или напрямую через Poetry:

```bash
cd /opt/amocrm-events-monitor
poetry run python app/main_ping_probe.py
poetry run python app/main_daily_report.py
```

### Просмотр логов

Все логи записываются в systemd journal:

```bash
# Логи в реальном времени
journalctl -u amocrm-ping-probe.service -f
journalctl -u amocrm-daily-report.service -f

# Логи за последние 24 часа
journalctl -u amocrm-ping-probe.service --since "24 hours ago"
journalctl -u amocrm-daily-report.service --since "24 hours ago"

# Только ошибки
journalctl -u amocrm-daily-report.service -p err
```

## Формат данных в Google Sheets

Скрипт автоматически создает таблицу со следующими столбцами:

| Дата       | Событие               | Кол-во | Пиковая нагрузка (мс) | Время пика |
|------------|-----------------------|--------|-----------------------|------------|
| 12.11.2025 | Входящее сообщение    | 485    | 509                   | 13:51      |
| 12.11.2025 | Новая задача          | 340    |                       |            |
| 12.11.2025 | Ответственный изменен | 324    |                       |            |
| 12.11.2025 | Прикрепление          | 301    |                       |            |
| 12.11.2025 | Исходящее сообщение   | 256    |                       |            |

**Описание полей:**

- **Дата** - дата, за которую собраны данные (вчерашний день)
- **Событие** - тип события на русском языке (автоматически переводится из кода API)
- **Кол-во** - количество срабатываний данного типа события за день
- **Пиковая нагрузка (мс)** - максимальное время отклика API за день (только в первой строке)
- **Время пика** - время фиксации максимального пинга в формате HH:MM (только в первой строке)

## Разработка

### Команды Makefile

```bash
# Форматирование кода
make format

# Проверка линтером
make lint

# Запуск unit-тестов
make test

# Запуск unit-тестов с покрытием
make test-cov

# Запуск интеграционных тестов
make test-integration

# Полный интеграционный тест с реальным API
make test-full

# Форматирование + линтер
make dev
```

### Структура тестов

- `tests/test_latency_checker/` - unit-тесты замера пинга
- `tests/test_main_daily_report/` - unit-тесты формирования отчета
- `tests/test_sheets_writer/` - unit-тесты работы с Google Sheets
- `tests/test_real_integration.py` - полный интеграционный тест с реальным API

### Запуск тестов

```bash
# Unit-тесты (быстрые, с моками)
poetry run pytest ./tests -v -m "not integration"

# Интеграционные тесты (требуют настроенный .env)
poetry run pytest ./tests -v -m integration

# Полный интеграционный тест
poetry run python tests/test_real_integration.py
```

## Настройки

Все настройки определяются через переменные окружения в `.env` файле.

### Основные настройки

| Параметр                      | Описание               | Обязательный | По умолчанию                   |
|-------------------------------|------------------------|--------------|--------------------------------|
| `AMO_BASE_URL`                | URL amoCRM аккаунта    | Да           | -                              |
| `AMO_LONG_LIVE_TOKEN`         | Долгосрочный токен     | Нет*         | None                           |
| `SHEETS_ID`                   | ID Google таблицы      | Да           | -                              |
| `GOOGLE_SERVICE_ACCOUNT_PATH` | Путь к JSON ключу      | Нет          | ./secrets/service-account.json |
| `TOP_EVENTS_LIMIT`            | Количество топ событий | Нет          | 5                              |
| `TIMEZONE`                    | Часовой пояс           | Нет          | UTC                            |
| `LOG_LEVEL`                   | Уровень логирования    | Нет          | INFO                           |

*Обязателен либо `AMO_LONG_LIVE_TOKEN`, либо набор OAuth2 параметров

### OAuth2 настройки (если не используется долгосрочный токен)

| Параметр            | Описание                                           |
|---------------------|----------------------------------------------------|
| `AMO_CLIENT_ID`     | Client ID интеграции                               |
| `AMO_CLIENT_SECRET` | Client Secret интеграции                           |
| `AMO_REDIRECT_URI`  | Redirect URI из настроек интеграции                |
| `AMO_AUTH_CODE`     | Authorization code для первичного получения токена |

## Типы событий

Скрипт автоматически переводит коды событий amoCRM API в читаемые названия на русском:

- `incoming_chat_message` → Входящее сообщение
- `outgoing_chat_message` → Исходящее сообщение
- `task_added` → Новая задача
- `task_completed` → Завершение задачи
- `entity_responsible_changed` → Ответственный изменен
- `lead_status_changed` → Изменение этапа продажи
- `entity_linked` → Прикрепление
- `entity_tag_added` → Теги добавлены

И другие (полный список в `app/main_daily_report.py`, словарь `EVENT_TYPE_NAMES`).

## Устранение неполадок

### Проблема: Скрипт не запускается через systemd

**Решение:**

1. Проверьте логи: `journalctl -u amocrm-daily-report.service -n 50`
2. Проверьте права доступа: `ls -la /opt/amocrm-events-monitor`
3. Проверьте виртуальное окружение: `ls -la /opt/amocrm-events-monitor/.venv/bin/python`
4. Попробуйте запустить вручную от root:
   `sudo python /opt/amocrm-events-monitor/.venv/bin/python /opt/amocrm-events-monitor/app/main_daily_report.py`

## Поддержка

При возникновении проблем:

1. Проверьте логи через `journalctl`
2. Запустите полный интеграционный тест: `make test-full`
3. Проверьте переменные окружения в `.env`
4. Убедитесь, что все зависимости установлены: `poetry install`

## Контакты и автор

**Автор:** Nikita Zhulikov  
**Email:** zhulikovnikita884@gmail.com  
**GitHub:** https://github.com/ZhulikovN
