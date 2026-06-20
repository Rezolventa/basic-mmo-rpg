from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from basic_mmo_rpg.domain.entities import EntityKind, WorldEntity
from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.tiles import TileDefinition, TileMap


def load_tile_map(path: Path) -> TileMap:
    """
    Загружает тайловую карту из JSON-файла.
    """
    with path.open("r", encoding="utf-8") as file:
        raw_map = json.load(file)
    return tile_map_from_dict(raw_map)


def tile_map_from_dict(raw_map: dict[str, Any]) -> TileMap:
    """
    Создает доменную тайловую карту из словаря с данными карты.
    """
    tile_size = int(raw_map["tile_size"])
    legend = raw_map["legend"]
    raw_tiles = raw_map["tiles"]
    spawn_x, spawn_y = raw_map.get("spawn", [tile_size, tile_size])

    definitions = {
        key: TileDefinition(
            key=key,
            name=str(value["name"]),
            solid=bool(value["solid"]),
            color=_parse_color(value["color"]),
        )
        for key, value in legend.items()
    }
    tiles = tuple(tuple(row) for row in raw_tiles)

    return TileMap(
        tile_size=tile_size,
        tiles=tiles,
        definitions=definitions,
        spawn=Vec2(float(spawn_x), float(spawn_y)),
        entities=_parse_entities(raw_map.get("entities", [])),
    )


def _parse_entities(raw_entities: object) -> tuple[WorldEntity, ...]:
    """
    Проверяет и преобразует список объектов карты в доменные сущности.
    """
    if not isinstance(raw_entities, list):
        msg = "entities must be a list"
        raise ValueError(msg)
    return tuple(_parse_entity(raw_entity) for raw_entity in raw_entities)


def _parse_entity(raw_entity: object) -> WorldEntity:
    """
    Проверяет и преобразует один объект карты в доменную сущность.
    """
    if not isinstance(raw_entity, dict):
        msg = "map entity must be an object"
        raise ValueError(msg)

    raw_kind = _str_field(raw_entity, "kind")
    try:
        kind = EntityKind(raw_kind)
    except ValueError as exc:
        msg = f"unsupported map entity kind: {raw_kind!r}"
        raise ValueError(msg) from exc

    width, height = _parse_size(raw_entity.get("size", [22, 28]))
    return WorldEntity(
        entity_id=_str_field(raw_entity, "id"),
        kind=kind,
        name=_str_field(raw_entity, "name"),
        position=_parse_vec2(raw_entity.get("position")),
        width=width,
        height=height,
        interaction_radius=_positive_number_field(raw_entity, "interaction_radius", 64.0),
        dialogue=str(raw_entity.get("dialogue", "")),
        solid=_bool_field(raw_entity, "solid", True),
        is_open=_optional_bool_field(raw_entity, "is_open"),
        hit_points=_optional_positive_int_field(raw_entity, "hit_points"),
        max_hit_points=_optional_positive_int_field(raw_entity, "max_hit_points"),
        has_wool=_optional_bool_field(raw_entity, "has_wool"),
    )


def _str_field(raw_entity: dict[str, Any], key: str) -> str:
    """
    Читает непустое строковое поле объекта карты.
    """
    value = raw_entity.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"map entity {key} must be a non-empty string"
        raise ValueError(msg)
    return value.strip()


def _parse_vec2(raw_position: object) -> Vec2:
    """
    Проверяет и преобразует пару координат в `Vec2`.
    """
    if not isinstance(raw_position, list) or len(raw_position) != 2:
        msg = "map entity position must be a two-item list"
        raise ValueError(msg)
    x, y = raw_position
    if not isinstance(x, int | float) or not isinstance(y, int | float):
        msg = "map entity position coordinates must be numbers"
        raise ValueError(msg)
    return Vec2(float(x), float(y))


def _parse_size(raw_size: object) -> tuple[int, int]:
    """
    Проверяет и преобразует размер объекта карты.
    """
    if not isinstance(raw_size, list) or len(raw_size) != 2:
        msg = "map entity size must be a two-item list"
        raise ValueError(msg)
    width, height = raw_size
    if not isinstance(width, int) or not isinstance(height, int):
        msg = "map entity size must contain integers"
        raise ValueError(msg)
    if width <= 0 or height <= 0:
        msg = "map entity size must be positive"
        raise ValueError(msg)
    return width, height


def _positive_number_field(
    raw_entity: dict[str, Any],
    key: str,
    default: float,
) -> float:
    """
    Читает положительное числовое поле объекта карты.
    """
    value = raw_entity.get(key, default)
    if not isinstance(value, int | float):
        msg = f"map entity {key} must be a number"
        raise ValueError(msg)
    if value <= 0:
        msg = f"map entity {key} must be positive"
        raise ValueError(msg)
    return float(value)


def _bool_field(raw_entity: dict[str, Any], key: str, default: bool) -> bool:
    """
    Читает boolean-поле объекта карты.
    """
    value = raw_entity.get(key, default)
    if not isinstance(value, bool):
        msg = f"map entity {key} must be a boolean"
        raise ValueError(msg)
    return value


def _optional_bool_field(raw_entity: dict[str, Any], key: str) -> bool | None:
    """
    Читает необязательное boolean-поле объекта карты.
    """
    value = raw_entity.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        msg = f"map entity {key} must be a boolean"
        raise ValueError(msg)
    return value


def _optional_positive_int_field(raw_entity: dict[str, Any], key: str) -> int | None:
    """
    Читает необязательное положительное целочисленное поле объекта карты.
    """
    value = raw_entity.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"map entity {key} must be an integer"
        raise ValueError(msg)
    if value <= 0:
        msg = f"map entity {key} must be positive"
        raise ValueError(msg)
    return value


def _parse_color(raw_color: list[int]) -> tuple[int, int, int]:
    """
    Проверяет и преобразует список RGB-каналов в кортеж цвета.
    """
    if len(raw_color) != 3:
        msg = f"RGB color must have exactly 3 channels, got {raw_color!r}"
        raise ValueError(msg)

    red, green, blue = (int(channel) for channel in raw_color)
    channels = (red, green, blue)
    if any(channel < 0 or channel > 255 for channel in channels):
        msg = f"RGB color channels must be between 0 and 255, got {raw_color!r}"
        raise ValueError(msg)
    return channels
