from __future__ import annotations

from collections import deque
from types import SimpleNamespace

import pygame

from basic_mmo_rpg.client.app import GameClient, RemotePlayerView, _smooth_player_toward
from basic_mmo_rpg.domain.entities import EntityKind, WorldEntity
from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.inventory import FISHING_ROD_ITEM_ID, ItemStack
from basic_mmo_rpg.domain.movement import PlayerState
from basic_mmo_rpg.shared.protocol import inventory_updated_payload


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


def test_client_applies_interaction_result_to_log_and_entity_bubble() -> None:
    """
    Проверяет, что клиент показывает результат взаимодействия в журнале и над объектом.
    """
    client = object.__new__(GameClient)
    client.chat_lines = deque(maxlen=50)
    client.entity_speech_bubbles = {}

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


def test_client_applies_inventory_update() -> None:
    """
    Проверяет, что клиент принимает authoritative-обновление инвентаря.
    """
    client = object.__new__(GameClient)
    client.inventory_items = []
    item = ItemStack(item_id=FISHING_ROD_ITEM_ID, display_name="Удочка", quantity=1)

    client._apply_inventory_updated(inventory_updated_payload([item]))

    assert client.inventory_items == [item]


def _client_without_pygame(player: PlayerState) -> GameClient:
    """
    Создает объект клиента для тестирования сетевого сглаживания без pygame-инициализации.
    """
    client = object.__new__(GameClient)
    client.player = player
    client.authoritative_player = None
    client.local_correction_offset = Vec2(0, 0)
    return client
