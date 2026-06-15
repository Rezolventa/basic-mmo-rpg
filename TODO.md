# TODO

## MVP Technical Debt

1. `src/basic_mmo_rpg/domain/movement.py`
   `move_player` / `_move_axis`: коллизия проверяется только в конечной точке движения. При большом `delta_seconds` или высокой скорости игрок может проскочить через стену.

2. `src/basic_mmo_rpg/storage/map_loader.py`
   `tile_map_from_dict`: загрузчик карты пока слишком доверяет JSON. Нет строгой проверки `spawn`, типов полей и проходимости стартовой позиции.

3. `src/basic_mmo_rpg/shared/protocol.py`
   Протокол уже умеет JSON encode/decode и минимальную проверку формы сообщения, но пока нет строгих схем для каждого типа сообщения и версионирования протокола.

4. `src/basic_mmo_rpg/server/world.py`
   Spawn игроков пока простой и не учитывает занятые позиции другими игроками.

5. `src/basic_mmo_rpg/client/app.py`
   Для локального игрока нужен client-side prediction: клиент должен сразу применять ввод локально, отправлять intent на сервер и мягко корректировать позицию по authoritative snapshot-ам.

6. `src/basic_mmo_rpg/client/app.py`
   Для других игроков нужна interpolation: клиент должен плавно вести удаленные сущности от предыдущей позиции к новой позиции из server snapshot-а, чтобы движение не выглядело ступенчатым.
