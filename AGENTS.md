# Agent Project Context

## Проект

Мы разрабатываем небольшой 2D online RPG / UO-like prototype на Python.

Это не попытка сразу сделать полноценную MMORPG. Цель текущего этапа - играбельный прототип для 2-10 друзей с чистой архитектурой и быстрыми MVP-итерациями.

## Текущий статус

Текущий этап: MVP 5.

Уже есть:

- pygame-клиент;
- asyncio/websockets authoritative-сервер;
- JSON-протокол сообщений;
- tile-map из JSON;
- движение игроков;
- camera;
- коллизии с тайлами и static entities;
- multiplayer для нескольких клиентов;
- client-side prediction для локального игрока;
- interpolation для других игроков;
- авторизация по имени персонажа;
- SQLite-сохранение позиции;
- reconnect с восстановлением позиции;
- чат;
- журнал сообщений текущей клиентской сессии;
- NPC `Funday` на стартовой карте;
- `interact_requested` по клавише `F`;
- серверная проверка дистанции взаимодействия;
- ответ NPC только инициатору взаимодействия;
- stack-based persistent inventory;
- UI инвентаря по клавише `B`;
- выдача предмета `Удочка` при взаимодействии с Funday, если у персонажа ее еще нет.

## Важное решение: локальный режим не поддерживаем

Локальную/offline-версию клиента больше не поддерживаем.

Клиент должен запускаться как multiplayer-client и подключаться к websocket-серверу. CLI-клиент требует `--name`; `--server` по умолчанию указывает на `ws://127.0.0.1:8765`.

Не добавлять новые gameplay-фичи только в локальный режим и не дублировать authoritative-логику на клиенте. Клиент может делать prediction/interpolation для UX, но источник истины - сервер.

## Стек

- Language: Python 3.12+
- Client: pygame-ce
- Server: Python asyncio
- Network: websockets over TCP
- Serialization v1: JSON
- Database v1: SQLite
- Map format сейчас: JSON, с перспективой Tiled `.tmx` или `.json`
- Tests: pytest
- Lint/format: ruff
- Type checking: mypy включен и должен проходить для `src`

## Архитектурные правила

Сервер authoritative:

- клиент отправляет намерения и запросы;
- сервер проверяет и применяет результат;
- клиент не решает, где реально находится персонаж;
- клиент не решает, успешно ли взаимодействие;
- клиент не решает, получил ли игрок предмет или прошел ли сквозь препятствие.

Примеры сообщений:

```text
client -> server: join_requested
client -> server: move_requested
client -> server: chat_sent
client -> server: interact_requested

server -> client: connection_accepted
server -> client: world_snapshot
server -> client: chat_message
server -> client: interaction_result
server -> client: inventory_updated
server -> client: entity_removed
server -> client: error
```

Разделение модулей:

- `client/` - pygame, ввод, камера, рендер, UI, websocket-клиент;
- `server/` - websocket server, игровые сессии, авторизация, рассылка событий;
- `shared/` - протокол сообщений, DTO/schema, сериализация;
- `domain/` - чистая игровая логика без pygame/websocket;
- `storage/` - загрузка карты и сохранение persistent-состояния.

## Правила реализации

- 2D only. 3D не рассматривается.
- Визуальный референс: Ultima Online, но без требования идеально повторять изометрию.
- Быстрый играбельный прототип важнее идеального движка.
- Новую игровую механику сначала проводить через server authoritative flow.
- Не расширять JSON-протокол ad hoc без helper-функций сериализации/валидации в `shared/protocol.py`.
- Если объект влияет на коллизии, учитывать его и на сервере, и в client-side prediction.
- SQLite-файлы, cache и runtime-артефакты не коммитить.
- Докстринги и поясняющие комментарии писать на русском.
- Имена модулей, классов, функций и переменных оставлять в обычном Python-стиле проекта.

## UX-правила текущего клиента

- `WASD` или стрелки - движение.
- `Enter` - начать ввод чата.
- Повторный `Enter` - отправить сообщение.
- `Esc` - отменить активный ввод чата.
- `J` - показать/скрыть журнал сообщений.
- `B` - показать/скрыть инвентарь.
- Клик по другому игроку - временно показать его никнейм.
- Наведение на NPC - показать имя NPC.
- `F` - отправить `interact_requested` для объекта строго под курсором.
- Клиент закрывается через крестик окна, не через `Esc`.

## Проверки перед сдачей

Запускать:

```powershell
python -m pytest
python -m ruff check .
python -m mypy src
```

Для клиентских изменений желательно дополнительно запускать headless smoke через dummy SDL video driver.

## Документы

- `README.md` - запуск, структура, текущая пользовательская модель.
- `TODO.md` - технический долг и ближайшие задачи.
- `pyproject.toml` - зависимости и настройки инструментов.
- `tests/` - executable specification текущего поведения.
