from __future__ import annotations

from pathlib import Path

from basic_mmo_rpg.domain.entities import EntityKind
from basic_mmo_rpg.domain.geometry import Rect
from basic_mmo_rpg.storage.map_loader import load_tile_map


def test_starter_map_loads() -> None:
    """
    Проверяет, что стартовая карта загружается с ожидаемыми параметрами.
    """
    map_path = Path("assets/maps/starter_map.json")

    tile_map = load_tile_map(map_path)

    assert tile_map.width == 40
    assert tile_map.height == 20
    assert tile_map.tile_size == 32
    assert tile_map.is_solid_tile(0, 0)
    assert not tile_map.is_solid_tile(2, 2)
    assert len(tile_map.entities) == 1
    assert tile_map.entities[0].entity_id == "npc-funday"
    assert tile_map.entities[0].kind == EntityKind.NPC
    assert tile_map.entities[0].name == "Funday"
    assert tile_map.entities[0].dialogue == "Иди и поймай мне рыбу"


def test_rect_outside_map_is_blocked() -> None:
    """
    Проверяет, что прямоугольники за границами карты считаются заблокированными.
    """
    map_path = Path("assets/maps/starter_map.json")
    tile_map = load_tile_map(map_path)

    assert tile_map.is_rect_blocked(Rect(-1, 32, 20, 20))
    assert tile_map.is_rect_blocked(Rect(32, -1, 20, 20))
    assert tile_map.is_rect_blocked(Rect(tile_map.pixel_size.x - 10, 32, 20, 20))
