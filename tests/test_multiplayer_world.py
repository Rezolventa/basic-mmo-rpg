from __future__ import annotations

import random

from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.movement import MovementIntent
from basic_mmo_rpg.server.world import MultiplayerWorld
from basic_mmo_rpg.shared.protocol import (
    entities_from_snapshot_payload,
    players_from_snapshot_payload,
)
from basic_mmo_rpg.storage.map_loader import tile_map_from_dict


def _open_map() -> object:
    """
    Возвращает небольшую открытую карту для тестирования серверного мира.
    """
    return {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            "......",
            "......",
            "......",
            "......",
        ],
    }


def _open_map_with_gate_and_sheep() -> object:
    """
    Возвращает карту с калиткой и овцой для тестов runtime-сущностей.
    """
    return {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            ".....",
            ".....",
            ".....",
            ".....",
        ],
        "entities": [
            {
                "id": "gate-sheep-pen",
                "kind": "gate",
                "name": "Калитка",
                "position": [64, 32],
                "size": [32, 32],
                "interaction_radius": 64,
                "solid": True,
                "is_open": False,
            },
            {
                "id": "creature-barbara",
                "kind": "creature",
                "name": "Барбара",
                "position": [34, 66],
                "size": [20, 20],
                "interaction_radius": 64,
                "solid": True,
                "hit_points": 15,
                "max_hit_points": 15,
                "has_wool": True,
            },
        ],
    }


def _open_map_with_gate_in_sheep_path() -> object:
    """
    Возвращает карту, где открытая калитка стоит в выбранном пути овцы.
    """
    return {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            ".....",
            ".....",
            ".....",
            ".....",
        ],
        "entities": [
            {
                "id": "gate-sheep-pen",
                "kind": "gate",
                "name": "Калитка",
                "position": [64, 64],
                "size": [32, 32],
                "interaction_radius": 64,
                "solid": True,
                "is_open": False,
            },
            {
                "id": "creature-barbara",
                "kind": "creature",
                "name": "Барбара",
                "position": [34, 66],
                "size": [20, 20],
                "interaction_radius": 64,
                "solid": True,
                "hit_points": 15,
                "max_hit_points": 15,
                "has_wool": True,
            },
        ],
    }


def test_world_spawns_players_and_returns_snapshot() -> None:
    """
    Проверяет, что серверный мир добавляет игроков и отдает их в snapshot-е.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))

    first = world.add_player("p1", "Alice")
    second = world.add_player("p2", "Bob")
    players = players_from_snapshot_payload(world.snapshot_payload())

    assert first.entity_id == "p1"
    assert second.entity_id == "p2"
    assert {player.entity_id for player in players} == {"p1", "p2"}


def test_world_applies_latest_movement_intent_on_tick() -> None:
    """
    Проверяет, что серверный мир двигает игрока по последнему intent-у.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))
    player = world.add_player("p1", "Alice")

    world.set_intent("p1", MovementIntent(right=True))
    world.tick(0.5)

    assert world.players["p1"].position.x > player.position.x
    assert world.players["p1"].position.y == player.position.y


def test_world_removes_player_and_ignores_missing_intent() -> None:
    """
    Проверяет, что удаленный игрок исчезает и больше не принимает intent-ы.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))
    world.add_player("p1", "Alice")

    world.remove_player("p1")
    world.set_intent("p1", MovementIntent(right=True))
    world.tick(0.5)

    assert world.players == {}


def test_world_reuses_only_unoccupied_spawn_positions() -> None:
    """
    Проверяет, что новый игрок не появляется поверх оставшегося игрока после disconnect-а.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))

    first = world.add_player("p1", "Alice")
    second = world.add_player("p2", "Bob")
    world.remove_player("p1")
    third = world.add_player("p3", "Cara")

    assert first.position == third.position
    assert third.position != second.position


def test_world_toggles_gate_collision_state() -> None:
    """
    Проверяет, что открытая калитка перестает быть solid-сущностью.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map_with_gate_and_sheep()))

    closed_gate = world.get_entity("gate-sheep-pen")
    opened_gate = world.toggle_gate("gate-sheep-pen")
    closed_again = world.toggle_gate("gate-sheep-pen")

    assert closed_gate is not None
    assert opened_gate is not None
    assert closed_again is not None
    assert closed_gate.solid is True
    assert opened_gate.solid is False
    assert opened_gate.is_open is True
    assert closed_again.solid is True
    assert closed_again.is_open is False


def test_world_treats_gate_as_occupied_by_creature_pending_target() -> None:
    """
    Проверяет, что калитку нельзя закрыть перед уже движущейся в нее овцой.
    """
    world = MultiplayerWorld(
        tile_map=tile_map_from_dict(_open_map_with_gate_in_sheep_path()),
        random_source=random.Random(0),
    )
    opened_gate = world.toggle_gate("gate-sheep-pen")
    assert opened_gate is not None

    world.tick(2.0)
    world.tick(0.1)
    gate = world.get_entity("gate-sheep-pen")
    moving_sheep = world.get_entity("creature-barbara")

    assert gate is not None
    assert moving_sheep is not None
    assert gate.rect.intersects(moving_sheep.rect) is False
    assert world.is_gate_occupied("gate-sheep-pen") is True
    assert world.toggle_gate("gate-sheep-pen") is None
    assert world.get_entity("gate-sheep-pen") == opened_gate


def test_world_moves_creature_smoothly_between_tiles() -> None:
    """
    Проверяет, что овца плавно проходит к свободному соседнему тайлу.
    """
    world = MultiplayerWorld(
        tile_map=tile_map_from_dict(_open_map_with_gate_and_sheep()),
        random_source=random.Random(0),
    )
    sheep = world.get_entity("creature-barbara")
    assert sheep is not None

    world.tick(2.0)
    world.tick(1.0)
    halfway_sheep = world.get_entity("creature-barbara")
    world.tick(1.0)
    moved_sheep = world.get_entity("creature-barbara")

    assert halfway_sheep is not None
    assert moved_sheep is not None
    assert halfway_sheep.position == Vec2(sheep.position.x + 16, sheep.position.y)
    assert moved_sheep.position == Vec2(sheep.position.x + 32, sheep.position.y)


def test_world_keeps_creature_in_place_when_target_is_blocked() -> None:
    """
    Проверяет, что овца ждет на месте, если выбранный тайл занят.
    """
    world = MultiplayerWorld(
        tile_map=tile_map_from_dict(_open_map_with_gate_and_sheep()),
        random_source=random.Random(0),
    )
    sheep = world.get_entity("creature-barbara")
    assert sheep is not None
    world.add_player("p1", "Alice", position=Vec2(sheep.position.x + 32, sheep.position.y))

    world.tick(2.0)
    world.tick(2.0)
    blocked_sheep = world.get_entity("creature-barbara")

    assert blocked_sheep is not None
    assert blocked_sheep.position == sheep.position


def test_world_regrows_creature_wool_after_timer() -> None:
    """
    Проверяет, что шерсть овцы отрастает после server-side таймера.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map_with_gate_and_sheep()))

    sheared = world.mark_creature_sheared("creature-barbara", wool_regrow_seconds=30.0)
    world.tick(30.0)
    entities = {
        entity.entity_id: entity
        for entity in entities_from_snapshot_payload(world.snapshot_payload())
    }

    assert sheared is not None
    assert sheared.has_wool is False
    assert entities["creature-barbara"].has_wool is True
