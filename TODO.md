# TODO

## MVP Technical Debt

1. `src/basic_mmo_rpg/domain/movement.py`
   `move_player` / `_move_axis`: коллизия проверяется только в конечной точке движения. При большом `delta_seconds` или высокой скорости игрок может проскочить через стену.

2. `src/basic_mmo_rpg/storage/map_loader.py`
   `tile_map_from_dict`: загрузчик карты пока слишком доверяет JSON. Нет строгой проверки `spawn`, типов полей и проходимости стартовой позиции.

3. `src/basic_mmo_rpg/shared/protocol.py`
   `ProtocolMessage`: протокол пока заготовка: `type: str`, `payload: dict[str, Any]`, нет парсинга и валидации входящих сообщений.
