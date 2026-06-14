from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
    )


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
