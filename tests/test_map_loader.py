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
    wooden_floor = tile_map.definitions["W"]
    assert wooden_floor.name == "wooden floor"
    assert not wooden_floor.solid
    assert wooden_floor.color == (120, 98, 72)
    assert tile_map.definitions["#"].sprites == (
        "tiles/wall_00.png",
        "tiles/wall_01.png",
        "tiles/wall_02.png",
        "tiles/wall_03.png",
        "tiles/wall_04.png",
        "tiles/wall_05.png",
        "tiles/wall_06.png",
        "tiles/wall_07.png",
        "tiles/wall_08.png",
        "tiles/wall_09.png",
        "tiles/wall_10.png",
        "tiles/wall_11.png",
        "tiles/wall_12.png",
        "tiles/wall_13.png",
        "tiles/wall_14.png",
        "tiles/wall_15.png",
    )
    assert tile_map.definitions["T"].sprites == (
        "tiles/tree_deciduous_1.png",
        "tiles/tree_deciduous_2.png",
        "tiles/tree_deciduous_3.png",
        "tiles/tree_deciduous_4.png",
        "tiles/tree_conifer_1.png",
        "tiles/tree_conifer_2.png",
        "tiles/tree_conifer_3.png",
        "tiles/tree_conifer_4.png",
    )
    assert tile_map.definitions["T"].sprite_offset == (0, 0)
    assert tile_map.definitions["T"].sprite_offsets == ()
    assert tile_map.definitions["T"].collision_rect == (9, 18, 14, 14)
    assert tile_map.definitions["R"].sprites == (
        "tiles/rock_1.png",
        "tiles/rock_2.png",
        "tiles/rock_3.png",
    )
    assert tile_map.definitions["R"].sprite_offset == (0, 0)
    assert tile_map.definitions["R"].sprite_offsets == ()
    assert tile_map.definitions["R"].collision_rect == (5, 8, 22, 20)
    assert tile_map.definitions["C"].name == "cave wall"
    assert tile_map.definitions["C"].sprites == ("tiles/cave_wall_1.png",)
    assert tile_map.definitions["C"].sprite_offset == (0, 0)
    assert tile_map.definitions["C"].sprite_offsets == ()
    assert tile_map.definitions["C"].collision_rect is None
    entities = {entity.entity_id: entity for entity in tile_map.entities}
    assert len(entities) == 12
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
    assert entities["npc-bjorn"].kind == EntityKind.NPC
    assert entities["npc-bjorn"].name == "Bjorn"
    assert entities["npc-bjorn"].solid
    assert entities["object-forge"].kind == EntityKind.OBJECT
    assert entities["object-forge"].name == "Горн"
    assert entities["object-forge"].visual == "forge"
    assert entities["object-forge"].solid
    assert entities["object-anvil"].kind == EntityKind.OBJECT
    assert entities["object-anvil"].name == "Наковальня"
    assert entities["object-anvil"].visual == "anvil"
    assert entities["object-anvil"].solid
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
    assert tile_map.is_mineable_tile(4, 17)
    assert tile_map.tile_collision_rect(5, 3) == Rect(169, 114, 14, 14)
    assert tile_map.tile_collision_rect(4, 17) == Rect(133, 552, 22, 20)
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


def test_cave_wall_tile_is_mineable_but_not_regular_rock() -> None:
    """
    Проверяет cave wall как Mining-тайл.
    """
    tile_map = tile_map_from_dict(
        {
            "tile_size": 32,
            "legend": {
                ".": {"name": "grass", "solid": False, "color": [55, 130, 73]},
                "C": {
                    "name": "cave wall",
                    "solid": True,
                    "color": [69, 74, 76],
                    "sprites": ["tiles/cave_wall_1.png"],
                },
            },
            "tiles": [
                "...",
                ".C.",
                "...",
            ],
        }
    )

    assert not tile_map.is_rock_tile(1, 1)
    assert tile_map.is_mineable_tile(1, 1)
    assert tile_map.definitions["C"].sprites == ("tiles/cave_wall_1.png",)
    assert tile_map.definitions["C"].sprite_offset == (0, 0)
    assert tile_map.definitions["C"].sprite_offsets == ()
    assert tile_map.definitions["C"].collision_rect is None


def test_tile_collision_rect_allows_rock_corners() -> None:
    """
    Проверяет, что rock блокирует центр тайла, но не его визуально пустые углы.
    """
    tile_map = tile_map_from_dict(
        {
            "tile_size": 32,
            "legend": {
                ".": {"name": "grass", "solid": False, "color": [55, 130, 73]},
                "R": {
                    "name": "rock",
                    "solid": True,
                    "color": [55, 130, 73],
                    "collision_rect": [5, 8, 22, 20],
                },
            },
            "tiles": [
                "...",
                ".R.",
                "...",
            ],
        }
    )

    assert not tile_map.is_rect_blocked(Rect(32, 32, 5, 8))
    assert tile_map.is_rect_blocked(Rect(40, 44, 8, 8))


def test_tile_collision_rect_allows_tree_canopy_and_corners() -> None:
    """
    Проверяет, что tree блокирует ствол, но не весь визуальный тайл кроны.
    """
    tile_map = tile_map_from_dict(
        {
            "tile_size": 32,
            "legend": {
                ".": {"name": "grass", "solid": False, "color": [55, 130, 73]},
                "T": {
                    "name": "tree",
                    "solid": True,
                    "color": [55, 130, 73],
                    "collision_rect": [9, 18, 14, 14],
                },
            },
            "tiles": [
                "...",
                ".T.",
                "...",
            ],
        }
    )

    assert not tile_map.is_rect_blocked(Rect(32, 32, 9, 18))
    assert tile_map.is_rect_blocked(Rect(42, 52, 6, 6))


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
