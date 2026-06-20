from __future__ import annotations

from pathlib import Path

from basic_mmo_rpg.domain.entities import EntityKind
from basic_mmo_rpg.domain.geometry import Rect, Vec2
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
    entities = {entity.entity_id: entity for entity in tile_map.entities}
    assert len(entities) == 3
    assert entities["npc-funday"].kind == EntityKind.NPC
    assert entities["npc-funday"].name == "Funday"
    assert entities["npc-funday"].dialogue == "Иди и поймай мне рыбу"
    assert entities["npc-funday"].solid
    assert entities["npc-jack-lumber"].kind == EntityKind.NPC
    assert entities["npc-jack-lumber"].name == "Jack Lumber"
    assert entities["npc-jack-lumber"].dialogue == "Наруби немного древесины"
    assert entities["npc-jack-lumber"].solid
    assert entities["npc-kopai"].kind == EntityKind.NPC
    assert entities["npc-kopai"].name == "Kopai"
    assert entities["npc-kopai"].dialogue == "Накопай мне чего-нибудь"
    assert entities["npc-kopai"].solid
    assert tile_map.is_water_tile(8, 14)
    assert tile_map.is_tree_tile(5, 3)
    assert tile_map.is_rock_tile(4, 17)
    assert tile_map.tile_coordinates_at(Vec2(8 * 32 + 1, 14 * 32 + 1)) == (8, 14)
    assert tile_map.tile_rect(8, 14).left == 8 * 32


def test_rect_outside_map_is_blocked() -> None:
    """
    Проверяет, что прямоугольники за границами карты считаются заблокированными.
    """
    map_path = Path("assets/maps/starter_map.json")
    tile_map = load_tile_map(map_path)

    assert tile_map.is_rect_blocked(Rect(-1, 32, 20, 20))
    assert tile_map.is_rect_blocked(Rect(32, -1, 20, 20))
    assert tile_map.is_rect_blocked(Rect(tile_map.pixel_size.x - 10, 32, 20, 20))
