from __future__ import annotations

import copy
import json
import shutil
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
        state=EditableMapState.from_tile_map(tile_map),
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


def editable_map_to_dict(
    raw_map: dict[str, Any],
    state: EditableMapState,
) -> dict[str, Any]:
    """
    Возвращает JSON-словарь карты с обновленным слоем tiles.
    """
    exported_map = copy.deepcopy(raw_map)
    exported_map["tiles"] = tile_rows_for_json(state)
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
