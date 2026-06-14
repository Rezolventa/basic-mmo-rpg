# Basic MMO RPG

Стартовый 2D online RPG / UO-like prototype на Python.

Текущий этап: локальный MVP, где один игрок ходит по маленькой tile-map с камерой и коллизиями. Доменная логика не зависит от `pygame`, чтобы позже переиспользовать ее на authoritative-сервере.

## Быстрый запуск

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m basic_mmo_rpg.client.app
```

Если используется не Windows:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m basic_mmo_rpg.client.app
```

Управление: `WASD` или стрелки. Закрытие: `Esc` или закрыть окно.

## Запуск из PyCharm

Если PyCharm не подхватывает модульный запуск, создай конфигурацию Python со следующими полями:

```text
Script path: <project root>\scripts\run_client.py
Working directory: <project root>
Python interpreter: <project root>\.venv\Scripts\python.exe
```

## Проверки

```bash
python -m pytest
python -m ruff check .
```

## Структура

```text
src/basic_mmo_rpg/
  client/   pygame-ce: ввод, камера, рендер, локальный игровой цикл
  domain/   чистая игровая логика: карта, геометрия, движение, коллизии
  server/   будущий asyncio/websockets authoritative-сервер
  shared/   будущие DTO/protocol-сообщения между клиентом и сервером
  storage/  загрузка/сохранение данных, сейчас JSON-карта
assets/maps/
  starter_map.json
tests/
```

## Архитектурное направление

Клиентский MVP сейчас применяет движение локально, но через чистую доменную функцию `move_player`. Следующий сетевой шаг: клиент будет отправлять намерение движения, сервер будет вызывать ту же доменную функцию, валидировать коллизии и рассылать подтвержденное состояние.
