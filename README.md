# Basic MMO RPG

Стартовый 2D online RPG / UO-like prototype на Python.

Текущий этап: MVP 2, где два или больше клиента подключаются к authoritative websocket-серверу, отправляют намерения движения и получают подтвержденные позиции игроков.

## Быстрый запуск

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

В первом терминале запусти сервер:

```powershell
python -m basic_mmo_rpg.server.app
```

Во втором и третьем терминалах запусти клиентов:

```powershell
python -m basic_mmo_rpg.client.app --server ws://127.0.0.1:8765
```

Локальный одиночный режим все еще доступен:

```powershell
python -m basic_mmo_rpg.client.app
```

Управление: `WASD` или стрелки. Закрытие клиента: `Esc` или закрыть окно. Остановка сервера: `Ctrl+C`.

## Запуск из PyCharm

Для клиента можно создать Python-конфигурацию:

```text
Script path: <project root>\scripts\run_client.py
Working directory: <project root>
Python interpreter: <project root>\.venv\Scripts\python.exe
Parameters: --server ws://127.0.0.1:8765
```

Для сервера:

```text
Script path: <project root>\scripts\run_server.py
Working directory: <project root>
Python interpreter: <project root>\.venv\Scripts\python.exe
```

## Проверки

```powershell
python -m pytest
python -m ruff check .
python -m mypy src
```

## Структура

```text
src/basic_mmo_rpg/
  client/   pygame-ce: ввод, камера, рендер, UI, websocket-клиент
  domain/   чистая игровая логика: карта, геометрия, движение, коллизии
  server/   asyncio/websockets authoritative-сервер и серверное состояние мира
  shared/   JSON-протокол сообщений между клиентом и сервером
  storage/  загрузка/сохранение данных, сейчас JSON-карта
assets/maps/
  starter_map.json
scripts/
  run_client.py
  run_server.py
tests/
```

## Сетевая модель

Клиент отправляет только намерение движения:

```text
client -> server: move_requested
```

Сервер хранит список игроков, применяет движение через доменную функцию `move_player`, проверяет коллизии и рассылает snapshot мира:

```text
server -> client: connection_accepted
server -> client: world_snapshot
```

Клиент не решает, где реально находится персонаж в online-режиме; он рисует состояние, полученное от сервера.
