from __future__ import annotations

import copy
import json
from pathlib import Path

from basic_mmo_rpg.domain.entities import EntityKind
from basic_mmo_rpg.domain.geometry import Rect, Vec2
from basic_mmo_rpg.storage.map_loader import load_tile_map, tile_map_from_dict


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
    assert len(entities) == 9
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
    assert entities["npc-fogu"].kind == EntityKind.NPC
    assert entities["npc-fogu"].name == "Fogu"
    assert entities["npc-fogu"].dialogue == "Постриги мою Барбару"
    assert entities["npc-fogu"].solid
    assert entities["gate-sheep-pen"].kind == EntityKind.GATE
    assert entities["gate-sheep-pen"].name == "Калитка"
    assert entities["gate-sheep-pen"].solid
    assert entities["gate-sheep-pen"].is_open is False
    assert entities["creature-barbara"].kind == EntityKind.CREATURE
    assert entities["creature-barbara"].name == "Овца"
    assert entities["creature-barbara"].width == 20
    assert entities["creature-barbara"].height == 20
    assert entities["creature-barbara"].hit_points == 15
    assert entities["creature-barbara"].max_hit_points == 15
    assert entities["creature-barbara"].has_wool is True
    assert entities["object-player-respawn"].kind == EntityKind.OBJECT
    assert entities["object-player-respawn"].visual == "respawn_cross"
    assert not entities["object-player-respawn"].solid
    assert entities["creature-boar"].kind == EntityKind.CREATURE
    assert entities["creature-boar"].name == "Кабан"
    assert entities["creature-boar"].visual == "boar"
    assert entities["creature-boar"].is_attackable
    assert entities["creature-boar"].hit_points == 18
    assert entities["creature-boar"].max_hit_points == 18
    assert entities["creature-boar"].combat is not None
    assert entities["creature-boar"].combat.min_damage == 2
    assert entities["creature-boar"].combat.max_damage == 4
    assert entities["creature-boar"].combat.hit_chance == 0.75
    assert entities["creature-boar"].respawn is not None
    assert entities["creature-boar"].respawn.seconds == 60
    assert entities["lootable-training-dummy"].kind == EntityKind.OBJECT
    assert entities["lootable-training-dummy"].name == "Тренировочный манекен"
    assert entities["lootable-training-dummy"].solid
    assert entities["lootable-training-dummy"].lootable is not None
    assert entities["lootable-training-dummy"].is_attackable
    assert entities["lootable-training-dummy"].hit_points == 20
    assert entities["lootable-training-dummy"].max_hit_points == 20
    assert entities["lootable-training-dummy"].respawn is not None
    assert entities["lootable-training-dummy"].respawn.seconds == 10
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


def test_map_fingerprint_changes_when_entity_position_changes() -> None:
    """
    Проверяет, что отпечаток карты учитывает позиции объектов мира.
    """
    source_path = Path("assets/maps/starter_map.json")
    raw_map = json.loads(source_path.read_text(encoding="utf-8"))
    moved_map = copy.deepcopy(raw_map)
    moved_map["entities"][0]["components"]["body"]["position"][0] += 32

    original_fingerprint = tile_map_from_dict(raw_map).fingerprint
    moved_fingerprint = tile_map_from_dict(moved_map).fingerprint

    assert len(original_fingerprint) == 16
    assert original_fingerprint != moved_fingerprint
