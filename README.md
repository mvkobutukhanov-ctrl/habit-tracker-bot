# Habit Tracker Bot

Personal single-user Telegram bot for tracking 9 daily health/habit items. Single-screen interactive checklist with inline keyboard. Streak counter. SQLite persistence.

## Items tracked

1. Утренний душ
2. Ходьба с утра (25-30 мин)
3. Вода (12 стаканов по 200мл) — счётчик с прогресс-баром
4. Белок (150 г / день) — счётчик с шагами +10 / +20 / +50 и сбросом
5. Вечерняя прогулка
6. Без порно
7. Без мастурбации
8. Без коротких видео
9. Здоровый сон

День считается «закрытым», когда отмечены все 9 пунктов. Стрик = подряд закрытых дней.

## Стек

- Python 3.10+
- aiogram 3 (polling режим — не нужен HTTPS-эндпоинт)
- SQLite (один файл)

## Быстрый старт (локально)

```bash
python -m venv .venv
. .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# отредактировать .env: TG_BOT_TOKEN, AUTHOR_TG_ID
python bot.py
```

### Получить TG_BOT_TOKEN

Написать `@BotFather` в Telegram → `/newbot` → следовать инструкциям. Полученный токен положить в `.env`.

### Получить AUTHOR_TG_ID

Написать `@userinfobot` в Telegram. Он пришлёт твой числовой ID. Положить в `.env`.

## Команды бота

- `/start` или `/today` или просто любое сообщение → показать чек-лист на сегодня.
- `/history` → последние 7 дней одним сообщением.

Все взаимодействия с пунктами — через inline-кнопки под сообщением.

## Деплой

### Вариант 1: VPS + systemd

```ini
# /etc/systemd/system/habits-bot.service
[Unit]
Description=Habit Tracker Bot
After=network.target

[Service]
Type=simple
User=habits
WorkingDirectory=/home/habits/habit-tracker
Environment="PATH=/home/habits/habit-tracker/.venv/bin"
EnvironmentFile=/home/habits/habit-tracker/.env
ExecStart=/home/habits/habit-tracker/.venv/bin/python bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable habits-bot
sudo systemctl start habits-bot
sudo systemctl status habits-bot
journalctl -u habits-bot -f      # просмотр логов
```

### Вариант 2: Railway / Fly.io

Procfile:
```
worker: python bot.py
```

Положить env-vars через панель сервиса (`TG_BOT_TOKEN`, `AUTHOR_TG_ID`, `TZ`, `DB_PATH`).
Для Fly.io: примонтировать persistent volume по пути `DB_PATH`, иначе данные сотрутся при рестарте.

## Конфигурация

| Переменная       | По умолчанию       | Назначение                                    |
|------------------|--------------------|-----------------------------------------------|
| `TG_BOT_TOKEN`   | (обязательно)      | Токен бота от @BotFather                       |
| `AUTHOR_TG_ID`   | (обязательно)      | Telegram user ID единственного пользователя    |
| `TZ`             | `Europe/Moscow`    | Таймзона для границы суток и стриков           |
| `DB_PATH`        | `habits.db`        | Путь к SQLite-файлу                            |

## Тесты

```bash
python -m unittest test_storage -v
```

Покрывают логику storage: DayState, get/set, water/protein clamping, history, streaks.

## Известные ограничения MVP

- Один пользователь (AUTHOR_TG_ID). Чужие сообщения молча игнорируются.
- Нет push-уведомлений / напоминаний.
- Нет графиков / визуализаций (только текстовый /history).
- Нет экспорта данных. Если нужно — `sqlite3 habits.db .dump` напрямую.
- Список пунктов захардкожен. Изменить — править `bot.py` + `storage.py` + при необходимости миграция схемы.
- На минимальных контейнерах (Alpine) может отсутствовать tz-база; пакет `tzdata` в requirements закрывает этот случай.
