# TODO

## MVP Technical Debt

1. `src/basic_mmo_rpg/domain/movement.py`
   `move_player` / `_move_axis`: коллизия проверяется только в конечной точке
   движения. При большом `delta_seconds` или высокой скорости, в том числе через
   ручную команду `/setspeed`, игрок может проскочить через стену.

2. `src/basic_mmo_rpg/storage/map_loader.py`
   `tile_map_from_dict`: загрузчик карты пока слишком доверяет JSON. Нет строгой
   проверки `spawn`, типов всех полей, дублей entity id и проходимости стартовой
   позиции.

3. `src/basic_mmo_rpg/shared/protocol.py`
   Протокол уже умеет JSON encode/decode и имеет helper-функции для текущих
   сообщений, включая vendor-flow, но пока нет единой строгой схемы/dispatch-валидации
   для каждого `ClientMessageType` и `ServerMessageType`, а также версионирования
   протокола.

4. `src/basic_mmo_rpg/client/app.py`, `src/basic_mmo_rpg/client/rendering.py`
   Добавить прокрутку журнала сообщений чата: хранить текущий scroll offset,
   обрабатывать колесо мыши/клавиши при открытом журнале и отрисовывать нужный
   диапазон последних сообщений.

5. `src/basic_mmo_rpg/server/app.py`
   Проработать модель cooldown-а для gathering-а: сейчас cooldown общий для
   рыбалки, рубки и добычи камня на персонажа, но в будущем может понадобиться
   отдельная доменная модель действий, инструментов, interrupt-ов и anti-abuse
   правил.

6. `src/basic_mmo_rpg/domain/equipment.py`, `src/basic_mmo_rpg/storage/characters.py`
   Реализовать настоящий перенос экипированного предмета из инвентаря в слот
   paperdoll. Сейчас `main_hand` и `chest` хранят ссылки на `item_id`, а стак
   предмета остается в инвентаре. Из-за этого несколько одинаковых предметов в
   одном стаке не различаются как отдельные экземпляры экипировки.

7. `src/basic_mmo_rpg/server/app.py`
   Уменьшить дистанцию атаки и взаимодействия до более адекватной melee-дистанции.
   Сейчас для первой боевой петли используется 64 px, чтобы не ломать существующие
   interaction-паттерны.

8. `src/basic_mmo_rpg/server/app.py`, `src/basic_mmo_rpg/domain/inventory.py`
   Вписать в боевку все предметы, которые можно взять в руку. Сейчас отдельные
   weapon-параметры есть только у `Ржавый меч`, а tutorial-инструменты в
   `main_hand` временно используют unarmed-атаку. Броня для `chest` уже работает
   отдельно через armor-параметр предмета.

9. `src/basic_mmo_rpg/server/world.py`, `src/basic_mmo_rpg/client/app.py`
   Углубить модель смерти и respawn-а игрока. Базовый runtime-flow уже есть:
   смерть скрывает персонажа, кнопка `Возродиться` переносит к объекту респауна и
   восстанавливает 50% HP. Дальше нужно решить persistent-состояние смерти,
   penalties, invulnerability после respawn-а и правила восстановления здоровья.

10. `src/basic_mmo_rpg/server/app.py`, `assets/maps/*.json`
    Сделать vendor/NPC-опции data-driven. Сейчас Bjorn, список vendor-offers и
    случайные реплики торговца заданы server-side таблицами по entity id, а в
    JSON-карте хранится только обычный NPC. Лучше перенести торговые офферы и
    набор фраз в component-based описание карты.

11. `src/basic_mmo_rpg/client/rendering.py`
    Улучшить UI vendor-окна: добавить явную кнопку покупки, состояние hover,
    отображение текущего количества Gold и более аккуратное отображение disabled
    reason. Сейчас покупка выполняется кликом по строке оффера.
