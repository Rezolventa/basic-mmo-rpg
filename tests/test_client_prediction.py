from __future__ import annotations

from collections import deque
from dataclasses import replace
from types import SimpleNamespace

import pygame

from basic_mmo_rpg.client.app import (
    GameClient,
    RemotePlayerView,
    WorldEntityView,
    _smooth_player_toward,
)
from basic_mmo_rpg.client.rendering import Renderer
from basic_mmo_rpg.client.ui import InventoryPanelHit
from basic_mmo_rpg.domain.entities import (
    BodyComponent,
    CombatComponent,
    EntityKind,
    IdentityComponent,
    WorldEntity,
)
from basic_mmo_rpg.domain.equipment import MAIN_HAND_SLOT, Equipment
from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.inventory import FISHING_ROD_ITEM_ID, ItemStack
from basic_mmo_rpg.domain.movement import PlayerState
from basic_mmo_rpg.shared.protocol import (
    combat_event_payload,
    equipment_updated_payload,
    inventory_updated_payload,
)
from basic_mmo_rpg.storage.map_loader import tile_map_from_dict


def test_local_authoritative_snapshot_creates_correction_offset() -> None:
    """
    Проверяет, что snapshot локального игрока создает плавную коррекцию prediction-а.
    """
    client = _client_without_pygame(PlayerState(entity_id="p1", position=Vec2(100, 0)))

    client._receive_authoritative_local_player(PlayerState(entity_id="p1", position=Vec2(80, 0)))
    client._reconcile_local_player(0.05)

    assert 80 < client.player.position.x < 100
    assert client.local_correction_offset.length < 20


def test_local_authoritative_snapshot_snaps_large_error() -> None:
    """
    Проверяет, что большая ошибка prediction-а исправляется мгновенным snap-ом.
    """
    client = _client_without_pygame(PlayerState(entity_id="p1", position=Vec2(0, 0)))

    client._receive_authoritative_local_player(PlayerState(entity_id="p1", position=Vec2(200, 0)))

    assert client.player.position == Vec2(200, 0)
    assert client.local_correction_offset == Vec2(0, 0)


def test_remote_player_view_interpolates_to_snapshot_target() -> None:
    """
    Проверяет, что удаленный игрок плавно движется к позиции из server snapshot-а.
    """
    view = RemotePlayerView(
        name="Bob",
        rendered=PlayerState(entity_id="p2", position=Vec2(0, 0)),
        target=PlayerState(entity_id="p2", position=Vec2(30, 0)),
    )

    view.update(1 / 60)

    assert 0 < view.rendered.position.x < 30


def test_world_entity_view_interpolates_to_snapshot_target() -> None:
    """
    Проверяет, что world-entity плавно движется к позиции из server snapshot-а.
    """
    entity = _attackable_dummy()
    target = replace(entity, body=replace(entity.body, position=Vec2(96, 32)))
    view = WorldEntityView(rendered=entity, target=target)

    view.update(1 / 60)

    assert entity.position.x < view.rendered.position.x < target.position.x
    assert view.rendered.position.y == target.position.y


def test_world_entity_view_updates_state_without_snapping_position() -> None:
    """
    Проверяет, что новое состояние entity применяется без мгновенного snap-а позиции.
    """
    entity = _attackable_dummy()
    target = replace(
        entity,
        body=replace(entity.body, position=Vec2(96, 32)),
        combat=replace(entity.combat, hit_points=12) if entity.combat is not None else None,
    )
    view = WorldEntityView(rendered=entity, target=entity)

    view.set_target(target)

    assert view.rendered.position == entity.position
    assert view.rendered.hit_points == 12
    assert view.target.position == Vec2(96, 32)


def test_world_entity_view_snaps_when_entity_becomes_visible() -> None:
    """
    Проверяет, что respawn entity не протаскивается из старой invisible-позиции.
    """
    entity = _attackable_dummy()
    hidden = replace(
        entity,
        body=replace(entity.body, position=Vec2(64, 32), visible=False),
    )
    respawned = replace(
        entity,
        body=replace(entity.body, position=Vec2(96, 32), visible=True),
    )
    view = WorldEntityView(rendered=hidden, target=hidden)

    view.set_target(respawned)

    assert view.rendered.position == respawned.position
    assert view.rendered.visible is True


def test_smooth_player_toward_keeps_current_position_without_elapsed_time() -> None:
    """
    Проверяет, что сглаживание не двигает игрока при нулевом delta_seconds.
    """
    current = PlayerState(entity_id="p2", position=Vec2(0, 0))
    target = PlayerState(entity_id="p2", position=Vec2(30, 0))

    smoothed = _smooth_player_toward(
        current=current,
        target=target,
        delta_seconds=0,
        rate=10,
        snap_distance=100,
        dead_zone=0,
    )

    assert smoothed == current


def test_client_applies_chat_message_to_log_and_bubble() -> None:
    """
    Проверяет, что клиент показывает серверное сообщение в журнале и над игроком.
    """
    client = object.__new__(GameClient)
    client.player_names = {}
    client.chat_lines = deque(maxlen=50)
    client.speech_bubbles = {}

    client._apply_chat_message(
        {
            "player_id": "p2",
            "name": "Bob",
            "text": "Привет",
            "created_at": 123.0,
        }
    )

    assert client.player_names["p2"] == "Bob"
    assert client.chat_lines[-1].text == "Привет"
    assert client.speech_bubbles["p2"].text == "Привет"


def test_chat_input_escape_cancels_input() -> None:
    """
    Проверяет, что Esc отменяет активный ввод чата.
    """
    client = object.__new__(GameClient)
    client.chat_input_active = True
    client.chat_input_text = "Черновик"

    client._handle_chat_input_key(SimpleNamespace(key=pygame.K_ESCAPE, unicode=""))

    assert client.chat_input_active is False
    assert client.chat_input_text == ""


def test_inventory_hotkey_toggles_inventory_panel() -> None:
    """
    Проверяет, что клавиша B показывает и скрывает инвентарь.
    """
    client = object.__new__(GameClient)
    client.chat_input_active = False
    client.inventory_visible = False

    client._handle_key_down(SimpleNamespace(key=pygame.K_b, unicode=""))
    assert client.inventory_visible is True

    client._handle_key_down(SimpleNamespace(key=pygame.K_b, unicode=""))
    assert client.inventory_visible is False


def test_combat_hotkey_toggles_mode_and_stops_attack() -> None:
    """
    Проверяет, что Tab включает боевой режим и при выключении сбрасывает auto-attack.
    """
    client = object.__new__(GameClient)
    network = _NetworkRecorder()
    client.chat_input_active = False
    client.inventory_visible = False
    client.combat_mode_active = False
    client.selected_attack_target_id = "lootable-training-dummy"
    client.hovered_attackable_entity_id = "lootable-training-dummy"
    client.network_client = network

    client._handle_key_down(SimpleNamespace(key=pygame.K_TAB, unicode=""))
    assert client.combat_mode_active is True
    assert network.stop_attack_requests == 0

    client._handle_key_down(SimpleNamespace(key=pygame.K_TAB, unicode=""))
    assert client.combat_mode_active is False
    assert client.selected_attack_target_id is None
    assert client.hovered_attackable_entity_id is None
    assert network.stop_attack_requests == 1


def test_combat_click_requests_attack_target() -> None:
    """
    Проверяет, что клик по attackable-объекту в боевом режиме выбирает цель.
    """
    client = object.__new__(GameClient)
    network = _NetworkRecorder()
    entity = _attackable_dummy()
    client.inventory_visible = False
    client.combat_mode_active = True
    client.camera = SimpleNamespace(screen_to_world=lambda position: Vec2(*position))
    client.world_entities = {entity.entity_id: entity}
    client.network_client = network

    client._handle_left_click((70, 40))

    assert client.selected_attack_target_id == entity.entity_id
    assert network.attack_targets == [entity.entity_id]


def test_dead_authoritative_player_opens_death_dialog_and_clears_attack() -> None:
    """
    Проверяет, что snapshot смерти включает окно смерти и сбрасывает боевую цель.
    """
    client = _client_without_pygame(PlayerState(entity_id="p1", position=Vec2(0, 0)))
    client.combat_mode_active = True
    client.hovered_attackable_entity_id = "creature-boar"
    client.selected_attack_target_id = "creature-boar"

    client._receive_authoritative_local_player(
        PlayerState(entity_id="p1", position=Vec2(0, 0), hit_points=0)
    )

    assert client.death_dialog_visible is True
    assert client.combat_mode_active is False
    assert client.hovered_attackable_entity_id is None
    assert client.selected_attack_target_id is None
    assert client.player.is_alive is False


def test_death_dialog_click_requests_respawn() -> None:
    """
    Проверяет, что кнопка окна смерти отправляет respawn_requested.
    """
    client = object.__new__(GameClient)
    network = _NetworkRecorder()
    client.death_dialog_visible = True
    client.screen = object()
    client.renderer = SimpleNamespace(
        respawn_button_hit_at_position=lambda screen, position: True
    )
    client.network_client = network

    client._handle_left_click((10, 10))

    assert network.respawn_requests == 1


def test_client_applies_interaction_result_to_log_and_entity_bubble() -> None:
    """
    Проверяет, что клиент показывает результат взаимодействия в журнале и над объектом.
    """
    client = object.__new__(GameClient)
    client.chat_lines = deque(maxlen=50)
    client.entity_speech_bubbles = {}
    client.world_entities = {
        "npc-funday": WorldEntity(
            entity_id="npc-funday",
            kind=EntityKind.NPC,
            name="Funday",
            position=Vec2(64, 32),
            width=24,
            height=30,
        )
    }

    client._apply_interaction_result(
        {
            "actor_id": "p1",
            "target_id": "npc-funday",
            "target_name": "Funday",
            "text": "Hello, developer",
            "created_at": 123.0,
        }
    )

    assert client.chat_lines[-1].name == "Funday"
    assert client.chat_lines[-1].text == "Hello, developer"
    assert client.entity_speech_bubbles["npc-funday"].text == "Hello, developer"


def test_client_applies_combat_event_to_log_and_entity_bubble() -> None:
    """
    Проверяет, что событие боя пишет журнал и floating text над целью.
    """
    client = object.__new__(GameClient)
    entity = _attackable_dummy()
    client.chat_lines = deque(maxlen=50)
    client.entity_speech_bubbles = {}
    client.speech_bubbles = {}
    client.player_names = {}
    client.world_entities = {entity.entity_id: entity}
    client.selected_attack_target_id = entity.entity_id

    client._apply_combat_event(
        combat_event_payload(
            actor_id="player-1",
            actor_name="Alice",
            target_id=entity.entity_id,
            target_name=entity.name,
            text="Вы атаковали Тренировочный манекен: -4",
            floating_text="-4",
            created_at=123.0,
            destroyed=True,
        )
    )

    assert client.chat_lines[-1].name == "Alice"
    assert client.chat_lines[-1].text == "Вы атаковали Тренировочный манекен: -4"
    assert client.entity_speech_bubbles[entity.entity_id].text == "-4"
    assert client.selected_attack_target_id is None


def test_client_can_show_interaction_bubble_without_journal_entry() -> None:
    """
    Проверяет, что результат взаимодействия может показываться пузырем без записи в журнал.
    """
    client = object.__new__(GameClient)
    client.chat_lines = deque(maxlen=50)
    client.entity_speech_bubbles = {}
    client.speech_bubbles = {}
    client.player_names = {}
    client.world_entities = {}

    client._apply_interaction_result(
        {
            "actor_id": "p1",
            "target_id": "p1",
            "target_name": "Alice",
            "text": "Нужна удочка",
            "created_at": 123.0,
            "add_to_journal": False,
        }
    )

    assert list(client.chat_lines) == []
    assert client.player_names["p1"] == "Alice"
    assert client.speech_bubbles["p1"].text == "Нужна удочка"


def test_client_finds_entity_strictly_under_cursor() -> None:
    """
    Проверяет выбор объекта мира по экранной позиции курсора.
    """
    client = object.__new__(GameClient)
    client.camera = SimpleNamespace(screen_to_world=lambda position: Vec2(*position))
    entity = WorldEntity(
        entity_id="npc-funday",
        kind=EntityKind.NPC,
        name="Funday",
        position=Vec2(64, 32),
        width=24,
        height=30,
    )
    client.world_entities = {entity.entity_id: entity}

    assert client._entity_at_screen_position((70, 40)) == entity
    assert client._entity_at_screen_position((88, 40)) is None
    assert client._entity_at_screen_position((70, 62)) is None
    assert client._entity_at_screen_position((20, 20)) is None


def test_client_finds_resource_tile_under_cursor() -> None:
    """
    Проверяет выбор ресурсного тайла по экранной позиции курсора.
    """
    client = object.__new__(GameClient)
    client.camera = SimpleNamespace(screen_to_world=lambda position: Vec2(*position))
    client.tile_map = tile_map_from_dict(
        {
            "tile_size": 32,
            "spawn": [32, 32],
            "legend": {
                ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
                "~": {"name": "water", "solid": True, "color": [43, 91, 151]},
                "T": {"name": "tree", "solid": True, "color": [39, 88, 50]},
                "R": {"name": "rock", "solid": True, "color": [102, 106, 112]},
            },
            "tiles": [
                ".....",
                "..~..",
                ".TR..",
            ],
        }
    )

    assert client._resource_tile_at_screen_position((40, 70)) == (1, 2)
    assert client._resource_tile_at_screen_position((70, 70)) == (2, 2)
    assert client._water_tile_at_screen_position((70, 40)) == (2, 1)
    assert client._water_tile_at_screen_position((40, 70)) is None
    assert client._water_tile_at_screen_position((40, 40)) is None
    assert client._resource_tile_at_screen_position((999, 999)) is None


def test_client_applies_inventory_update() -> None:
    """
    Проверяет, что клиент принимает authoritative-обновление инвентаря.
    """
    client = object.__new__(GameClient)
    client.inventory_items = []
    item = ItemStack(item_id=FISHING_ROD_ITEM_ID, display_name="Удочка", quantity=1)

    client._apply_inventory_updated(inventory_updated_payload([item]))

    assert client.inventory_items == [item]


def test_client_applies_equipment_update() -> None:
    """
    Проверяет, что клиент принимает authoritative-обновление экипировки.
    """
    client = object.__new__(GameClient)
    client.equipment = Equipment()

    client._apply_equipment_updated(
        equipment_updated_payload(Equipment(main_hand=FISHING_ROD_ITEM_ID))
    )

    assert client.equipment.main_hand == FISHING_ROD_ITEM_ID


def test_client_inventory_click_requests_equip() -> None:
    """
    Проверяет, что клик по предмету инвентаря отправляет запрос экипировки.
    """
    client = object.__new__(GameClient)
    network = _NetworkRecorder()
    client.screen = object()
    client.inventory_visible = True
    client.inventory_items = []
    client.equipment = Equipment()
    client.renderer = SimpleNamespace(
        inventory_hit_at_position=lambda screen, position, items: InventoryPanelHit(
            item_id=FISHING_ROD_ITEM_ID
        )
    )
    client.network_client = network

    client._handle_left_click((10, 10))

    assert network.equipped_items == [FISHING_ROD_ITEM_ID]
    assert network.unequipped_slots == []


def test_client_main_hand_click_requests_unequip() -> None:
    """
    Проверяет, что клик по занятому слоту руки отправляет запрос снятия предмета.
    """
    client = object.__new__(GameClient)
    network = _NetworkRecorder()
    client.screen = object()
    client.inventory_visible = True
    client.inventory_items = []
    client.equipment = Equipment(main_hand=FISHING_ROD_ITEM_ID)
    client.renderer = SimpleNamespace(
        inventory_hit_at_position=lambda screen, position, items: InventoryPanelHit(
            slot=MAIN_HAND_SLOT
        )
    )
    client.network_client = network

    client._handle_left_click((10, 10))

    assert network.equipped_items == []
    assert network.unequipped_slots == [MAIN_HAND_SLOT]


def test_client_inventory_empty_area_click_is_consumed() -> None:
    """
    Проверяет, что пустая область панели инвентаря не пропускает клик в мир.
    """
    client = object.__new__(GameClient)
    network = _NetworkRecorder()
    client.screen = object()
    client.inventory_items = []
    client.equipment = Equipment()
    client.renderer = SimpleNamespace(
        inventory_hit_at_position=lambda screen, position, items: InventoryPanelHit()
    )
    client.network_client = network

    assert client._handle_inventory_click((10, 10)) is True
    assert network.equipped_items == []
    assert network.unequipped_slots == []


def test_renderer_does_not_draw_gate_hover_name() -> None:
    """
    Проверяет, что hover по калитке не рисует подпись с именем.
    """
    renderer = object.__new__(Renderer)
    screen = pygame.Surface((100, 100))
    gate = WorldEntity(
        entity_id="gate-sheep-pen",
        kind=EntityKind.GATE,
        name="Калитка",
        position=Vec2(0, 0),
        width=32,
        height=32,
    )
    drawn_names: list[str] = []
    renderer._entity_screen_rect = lambda camera, entity: pygame.Rect(0, 0, 32, 32)
    renderer._draw_name_tag_above_rect = (
        lambda screen, body, name, y_offset: drawn_names.append(name)
    )

    renderer._draw_entity_floating_texts(
        screen=screen,
        camera=SimpleNamespace(),
        entities=[gate],
        speech_bubbles={},
        hovered_entity_id=gate.entity_id,
    )

    assert drawn_names == []


def _client_without_pygame(player: PlayerState) -> GameClient:
    """
    Создает объект клиента для тестирования сетевого сглаживания без pygame-инициализации.
    """
    client = object.__new__(GameClient)
    client.player = player
    client.authoritative_player = None
    client.local_correction_offset = Vec2(0, 0)
    return client


def _attackable_dummy() -> WorldEntity:
    """
    Создает attackable-тестовый манекен.
    """
    return WorldEntity(
        entity_id="lootable-training-dummy",
        identity=IdentityComponent(
            kind=EntityKind.OBJECT,
            name="Тренировочный манекен",
            visual="training_dummy",
        ),
        body=BodyComponent(position=Vec2(64, 32), width=24, height=34, solid=True),
        combat=CombatComponent(hit_points=20, max_hit_points=20, attackable=True),
    )


class _NetworkRecorder:
    """
    Запоминает equip/unequip-запросы клиента для UI-тестов.
    """

    def __init__(self) -> None:
        """
        Создает пустые списки отправленных запросов.
        """
        self.equipped_items: list[str] = []
        self.unequipped_slots: list[str] = []
        self.attack_targets: list[str] = []
        self.stop_attack_requests = 0
        self.respawn_requests = 0

    def send_equip_item_request(self, item_id: str) -> None:
        """
        Запоминает запрос экипировки предмета.
        """
        self.equipped_items.append(item_id)

    def send_unequip_item_request(self, slot: str) -> None:
        """
        Запоминает запрос снятия предмета.
        """
        self.unequipped_slots.append(slot)

    def send_attack_request(self, target_id: str) -> None:
        """
        Запоминает запрос выбора цели атаки.
        """
        self.attack_targets.append(target_id)

    def send_stop_attack_request(self) -> None:
        """
        Запоминает запрос остановки auto-attack.
        """
        self.stop_attack_requests += 1

    def send_respawn_request(self) -> None:
        """
        Запоминает запрос возрождения персонажа.
        """
        self.respawn_requests += 1
