from __future__ import annotations

from basic_mmo_rpg.domain.movement import MovementIntent
from basic_mmo_rpg.server.world import MultiplayerWorld
from basic_mmo_rpg.shared.protocol import players_from_snapshot_payload
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


def test_world_spawns_players_and_returns_snapshot() -> None:
    """
    Проверяет, что серверный мир добавляет игроков и отдает их в snapshot-е.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))

    first = world.add_player("p1")
    second = world.add_player("p2")
    players = players_from_snapshot_payload(world.snapshot_payload())

    assert first.entity_id == "p1"
    assert second.entity_id == "p2"
    assert {player.entity_id for player in players} == {"p1", "p2"}


def test_world_applies_latest_movement_intent_on_tick() -> None:
    """
    Проверяет, что серверный мир двигает игрока по последнему intent-у.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))
    player = world.add_player("p1")

    world.set_intent("p1", MovementIntent(right=True))
    world.tick(0.5)

    assert world.players["p1"].position.x > player.position.x
    assert world.players["p1"].position.y == player.position.y


def test_world_removes_player_and_ignores_missing_intent() -> None:
    """
    Проверяет, что удаленный игрок исчезает и больше не принимает intent-ы.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))
    world.add_player("p1")

    world.remove_player("p1")
    world.set_intent("p1", MovementIntent(right=True))
    world.tick(0.5)

    assert world.players == {}


def test_world_reuses_only_unoccupied_spawn_positions() -> None:
    """
    Проверяет, что новый игрок не появляется поверх оставшегося игрока после disconnect-а.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))

    first = world.add_player("p1")
    second = world.add_player("p2")
    world.remove_player("p1")
    third = world.add_player("p3")

    assert first.position == third.position
    assert third.position != second.position
