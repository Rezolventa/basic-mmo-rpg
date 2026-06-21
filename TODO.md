# TODO

## MVP Technical Debt

1. `src/basic_mmo_rpg/domain/movement.py`
   `move_player` / `_move_axis`: коллизия проверяется только в конечной точке движения. При большом `delta_seconds` или высокой скорости игрок может проскочить через стену.

2. `src/basic_mmo_rpg/storage/map_loader.py`
   `tile_map_from_dict`: загрузчик карты пока слишком доверяет JSON. Нет строгой проверки `spawn`, типов полей и проходимости стартовой позиции.

3. `src/basic_mmo_rpg/shared/protocol.py`
   Протокол уже умеет JSON encode/decode и минимальную проверку формы сообщения, но пока нет строгих схем для каждого типа сообщения и версионирования протокола.

4. `src/basic_mmo_rpg/client/app.py`, `src/basic_mmo_rpg/client/rendering.py`
   Добавить прокрутку журнала сообщений чата: хранить текущий scroll offset, обрабатывать колесо мыши/клавиши при открытом журнале и отрисовывать нужный диапазон последних сообщений.

5. `src/basic_mmo_rpg/server/app.py`
   Проработать модель cooldown-а для gathering-а: сейчас cooldown общий для рыбалки, рубки и добычи камня на персонажа, но в будущем может понадобиться отдельная доменная модель действий, инструментов, interrupt-ов и anti-abuse правил.

6. `src/basic_mmo_rpg/domain/equipment.py`, `src/basic_mmo_rpg/storage/characters.py`
   Реализовать настоящий переезд экипированного предмета из инвентаря в слот paperdoll. Сейчас `main_hand` хранит ссылку на `item_id`, а стак предмета остается в инвентаре.

7. `src/basic_mmo_rpg/server/app.py`
   Уменьшить дистанцию атаки и взаимодействия до более адекватной melee-дистанции. Сейчас для первой боевой петли используется 64 px, чтобы не ломать существующие interaction-паттерны.

8. `src/basic_mmo_rpg/server/app.py`, `src/basic_mmo_rpg/domain/inventory.py`
   Вписать в боевку все предметы, которые можно взять в руку. Сейчас отдельные combat-параметры есть только у `Ржавый меч`, а остальные экипируемые предметы временно используют unarmed-атаку.
