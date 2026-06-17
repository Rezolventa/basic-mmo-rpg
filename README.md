# Basic MMO RPG

Стартовый 2D online RPG / UO-like prototype на Python.

Текущий этап: MVP 4, где несколько клиентов подключаются к authoritative websocket-серверу, входят по имени персонажа, видят друг друга, общаются в чате, восстанавливают сохраненную позицию после reconnect-а и могут взаимодействовать с NPC.

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
python -m basic_mmo_rpg.client.app --server ws://127.0.0.1:8765 --name Alice
python -m basic_mmo_rpg.client.app --server ws://127.0.0.1:8765 --name Bob
```

Управление: `WASD` или стрелки. `Enter` открывает ввод чата, повторный `Enter` отправляет сообщение, `Esc` отменяет активный ввод. `J` показывает/скрывает журнал последних сообщений текущей сессии. Наведение курсора на NPC показывает его имя, `F` отправляет запрос взаимодействия с объектом строго под курсором. Клик по другому персонажу показывает его никнейм на 3 секунды. Закрытие клиента сейчас только через крестик окна. Остановка сервера: `Ctrl+C`.

На стартовой карте внутри помещения стоит NPC `Funday`. Если персонаж находится не дальше 64 пикселей и курсор наведен на NPC, `Funday` отвечает `Hello, developer`; реплика появляется над NPC и попадает в журнал сообщений.

По умолчанию сервер хранит позиции персонажей в `data/game.sqlite3`. Локальные SQLite-файлы игнорируются git-ом.

## Запуск из PyCharm

Для клиента можно создать Python-конфигурацию:

```text
Script path: <project root>\scripts\run_client.py
Working directory: <project root>
Python interpreter: <project root>\.venv\Scripts\python.exe
Parameters: --server ws://127.0.0.1:8765 --name Alice
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
  domain/   чистая игровая логика: карта, геометрия, сущности мира, движение, коллизии
  server/   asyncio/websockets authoritative-сервер и серверное состояние мира
  shared/   JSON-протокол сообщений между клиентом и сервером
  storage/  загрузка JSON-карты и сохранение персонажей в SQLite
assets/maps/
  starter_map.json
scripts/
  run_client.py
  run_server.py
tests/
```

## Сетевая модель

Клиент сначала отправляет имя персонажа, а дальше отправляет намерения движения, сообщения чата и запросы взаимодействия:

```text
client -> server: join_requested
client -> server: move_requested
client -> server: chat_sent
client -> server: interact_requested
```

Сервер хранит активные сессии, кикает старое подключение при повторном входе тем же именем, применяет движение через доменную функцию `move_player`, проверяет коллизии с тайлами и объектами, проверяет дистанцию взаимодействия, сохраняет позиции в SQLite и рассылает snapshot мира:

```text
server -> client: connection_accepted
server -> client: world_snapshot
server -> client: chat_message
server -> client: interaction_result
server -> client: entity_removed
```

Клиент не решает, где реально находится персонаж в online-режиме; он рисует состояние, полученное от сервера.
