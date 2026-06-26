from __future__ import annotations

import copy
import json
import shutil
from argparse import ArgumentTypeError
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from basic_mmo_rpg.storage.map_loader import tile_map_from_dict
from tools.map_editor.state import EditableMapState


@dataclass(slots=True)
class EditableMapDocument:
    """
    Хранит исходный JSON карты и изменяемое состояние тайлов редактора.
    """

    raw_map: dict[str, Any]
    state: EditableMapState


def load_editable_map(path: Path) -> EditableMapDocument:
    """
    Загружает JSON-карту и создает состояние редактора для слоя тайлов.
    """
    raw_map = read_map_dict(path)
    tile_map = tile_map_from_dict(raw_map)
    return EditableMapDocument(
        raw_map=raw_map,
        state=EditableMapState.from_tile_map(
            tile_map,
            raw_entities=_raw_entities(raw_map),
        ),
    )


def read_map_dict(path: Path) -> dict[str, Any]:
    """
    Читает JSON-файл карты как объект верхнего уровня.
    """
    with path.open("r", encoding="utf-8") as file:
        raw_map = json.load(file)
    if not isinstance(raw_map, dict):
        msg = "map JSON root must be an object"
        raise ValueError(msg)
    return raw_map


def parse_map_dimensions(value: str) -> tuple[int, int]:
    """
    Читает размер карты в формате WIDTHxHEIGHT.
    """
    normalized = value.lower().strip()
    if "x" not in normalized:
        msg = "map size must use WIDTHxHEIGHT format"
        raise ArgumentTypeError(msg)
    raw_width, raw_height = normalized.split("x", maxsplit=1)
    try:
        width = int(raw_width)
        height = int(raw_height)
    except ValueError as exc:
        msg = "map width and height must be integers"
        raise ArgumentTypeError(msg) from exc
    if width < 3 or height < 3:
        msg = "map width and height must be at least 3"
        raise ArgumentTypeError(msg)
    return width, height


def create_empty_map_from_template(
    template_path: Path,
    output_path: Path,
    width: int,
    height: int,
    fill_tile: str = ".",
    border_tile: str = "#",
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """
    Создает новую пустую карту указанного размера на основе legend из шаблона.
    """
    if width < 3 or height < 3:
        msg = "map width and height must be at least 3"
        raise ValueError(msg)
    if output_path.exists() and not overwrite:
        msg = f"map file already exists: {output_path}"
        raise FileExistsError(msg)

    template_map = read_map_dict(template_path)
    legend = copy.deepcopy(template_map.get("legend", {}))
    if not isinstance(legend, dict):
        msg = "template map legend must be an object"
        raise ValueError(msg)
    if fill_tile not in legend:
        msg = f"unknown fill tile key: {fill_tile!r}"
        raise ValueError(msg)
    if border_tile not in legend:
        msg = f"unknown border tile key: {border_tile!r}"
        raise ValueError(msg)

    tile_size = int(template_map.get("tile_size", 32))
    raw_map: dict[str, Any] = {
        "tile_size": tile_size,
        "spawn": [tile_size, tile_size],
        "legend": legend,
        "tiles": _empty_tile_rows(
            width=width,
            height=height,
            fill_tile=fill_tile,
            border_tile=border_tile,
        ),
        "entities": [],
    }
    tile_map_from_dict(raw_map)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(raw_map, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return raw_map


def editable_map_to_dict(
    raw_map: dict[str, Any],
    state: EditableMapState,
) -> dict[str, Any]:
    """
    Возвращает JSON-словарь карты с обновленным слоем tiles.
    """
    exported_map = copy.deepcopy(raw_map)
    exported_map["tiles"] = tile_rows_for_json(state)
    exported_map["entities"] = [entity.to_raw() for entity in state.entities]
    return exported_map


def tile_rows_for_json(state: EditableMapState) -> list[str]:
    """
    Преобразует изменяемые строки тайлов обратно в компактный JSON-формат.
    """
    if any(len(tile_key) != 1 for tile_key in state.definitions):
        msg = "tile rows can be saved as strings only when tile keys are one character"
        raise ValueError(msg)
    return ["".join(row) for row in state.tiles]


def save_editable_map(
    path: Path,
    raw_map: dict[str, Any],
    state: EditableMapState,
) -> dict[str, Any]:
    """
    Сохраняет карту в JSON и возвращает записанный словарь.
    """
    exported_map = editable_map_to_dict(raw_map, state)
    tile_map_from_dict(exported_map)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(exported_map, file, ensure_ascii=False, indent=2)
        file.write("\n")
    state.dirty = False
    return exported_map


def create_backup(path: Path) -> Path:
    """
    Создает резервную копию карты рядом с исходным файлом.
    """
    backup_path = available_backup_path(path)
    shutil.copy2(path, backup_path)
    return backup_path


def available_backup_path(path: Path) -> Path:
    """
    Возвращает свободный путь для резервной копии карты.
    """
    base_backup_path = path.with_name(f"{path.name}.bak")
    if not base_backup_path.exists():
        return base_backup_path

    index = 1
    while True:
        candidate = path.with_name(f"{path.name}.bak.{index}")
        if not candidate.exists():
            return candidate
        index += 1


def _raw_entities(raw_map: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Возвращает raw entity-объекты из JSON-карты.
    """
    raw_entities = raw_map.get("entities", [])
    if not isinstance(raw_entities, list):
        return []
    return [entity for entity in raw_entities if isinstance(entity, dict)]


def _empty_tile_rows(
    width: int,
    height: int,
    fill_tile: str,
    border_tile: str,
) -> list[str]:
    """
    Создает строки тайлов для новой карты с solid-периметром.
    """
    rows: list[str] = []
    for tile_y in range(height):
        row = "".join(
            border_tile
            if tile_x == 0 or tile_y == 0 or tile_x == width - 1 or tile_y == height - 1
            else fill_tile
            for tile_x in range(width)
        )
        rows.append(row)
    return rows
