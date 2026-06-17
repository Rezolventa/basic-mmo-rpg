from __future__ import annotations

from basic_mmo_rpg.domain.geometry import Rect, Vec2
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState, move_player
from basic_mmo_rpg.storage.map_loader import tile_map_from_dict


def _test_map() -> object:
    """
    Возвращает минимальную карту для тестирования движения игрока.
    """
    return {
        "tile_size": 32,
        "spawn": [4, 36],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            ".....",
            ".#...",
            ".....",
        ],
    }


def test_player_moves_on_empty_tiles() -> None:
    """
    Проверяет, что игрок перемещается по проходимым тайлам.
    """
    tile_map = tile_map_from_dict(_test_map())
    player = PlayerState(entity_id="p1", position=Vec2(96, 36), speed=64)

    moved = move_player(player, MovementIntent(right=True), 0.5, tile_map)

    assert moved.position == Vec2(128, 36)


def test_player_cannot_move_into_solid_tile() -> None:
    """
    Проверяет, что игрок не может пройти в непроходимый тайл.
    """
    tile_map = tile_map_from_dict(_test_map())
    player = PlayerState(entity_id="p1", position=Vec2(4, 36), speed=60)

    moved = move_player(player, MovementIntent(right=True), 0.5, tile_map)

    assert moved.position == player.position


def test_player_slides_along_blocked_axis() -> None:
    """
    Проверяет, что игрок скользит вдоль стены при диагональном движении.
    """
    tile_map = tile_map_from_dict(_test_map())
    player = PlayerState(entity_id="p1", position=Vec2(4, 36), speed=60)

    moved = move_player(player, MovementIntent(right=True, down=True), 0.5, tile_map)

    assert moved.position.x == player.position.x
    assert moved.position.y > player.position.y


def test_player_cannot_move_into_extra_blocker() -> None:
    """
    Проверяет, что игрок не может пройти через дополнительный коллизионный объект.
    """
    tile_map = tile_map_from_dict(_test_map())
    player = PlayerState(entity_id="p1", position=Vec2(32, 68), speed=32)
    blocker = Rect(64, 68, 24, 28)

    moved = move_player(player, MovementIntent(right=True), 1.0, tile_map, [blocker])

    assert moved.position == player.position
