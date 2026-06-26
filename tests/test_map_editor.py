from __future__ import annotations

from pathlib import Path

import pytest

from basic_mmo_rpg.storage.map_loader import load_tile_map
from tools.map_editor.map_io import (
    available_backup_path,
    create_backup,
    create_empty_map_from_template,
    editable_map_to_dict,
    load_editable_map,
    parse_map_dimensions,
    save_editable_map,
)
from tools.map_editor.state import EditableMapState


def test_editable_map_state_paints_without_mutating_source_map() -> None:
    """
    Проверяет, что рисование меняет только состояние редактора, а не игровую TileMap.
    """
    tile_map = load_tile_map(Path("assets/maps/starter_map.json"))
    state = EditableMapState.from_tile_map(tile_map)
    original_tile = tile_map.tile_at(1, 1)

    state.select_tile("~")
    changed = state.paint_tile(1, 1)

    assert changed
    assert state.dirty
    assert state.tile_at(1, 1) == "~"
    assert tile_map.tile_at(1, 1) == original_tile


def test_editable_map_state_pick_tile_selects_existing_tile() -> None:
    """
    Проверяет, что пипетка выбирает тайл из указанной клетки.
    """
    tile_map = load_tile_map(Path("assets/maps/starter_map.json"))
    state = EditableMapState.from_tile_map(tile_map)

    state.pick_tile(0, 0)

    assert state.selected_tile_key == "#"


def test_editable_map_state_moves_entity_without_mutating_raw_map() -> None:
    """
    Проверяет, что перемещение entity меняет только состояние редактора до экспорта.
    """
    document = load_editable_map(Path("assets/maps/starter_map.json"))
    original_raw_position = document.raw_map["entities"][0]["components"]["body"]["position"]
    entity = document.state.entity_by_id("npc-funday")
    target_position = (original_raw_position[0] + 7, original_raw_position[1] + 5)

    assert entity is not None
    moved = document.state.move_entity("npc-funday", *target_position)

    assert moved
    assert document.state.dirty
    assert entity.position == (float(target_position[0]), float(target_position[1]))
    raw_position = document.raw_map["entities"][0]["components"]["body"]["position"]
    assert raw_position == original_raw_position


def test_editable_map_state_snaps_entity_center_to_tile() -> None:
    """
    Проверяет, что Ctrl-snap ставит центр entity в центр тайла.
    """
    document = load_editable_map(Path("assets/maps/starter_map.json"))
    entity = document.state.entity_by_id("gate-sheep-pen")

    assert entity is not None
    snapped = document.state.snap_entity_center_to_tile("gate-sheep-pen", 20, 12)

    assert snapped
    assert entity.position == (640.0, 384.0)
    assert document.state.dirty


def test_editable_map_state_rejects_unknown_tile_selection() -> None:
    """
    Проверяет, что редактор не выбирает тайл вне legend.
    """
    tile_map = load_tile_map(Path("assets/maps/starter_map.json"))
    state = EditableMapState.from_tile_map(tile_map)

    with pytest.raises(ValueError, match="unknown tile key"):
        state.select_tile("missing")


def test_editable_map_to_dict_updates_only_tile_rows() -> None:
    """
    Проверяет, что экспорт редактора меняет только компактные строки tiles.
    """
    document = load_editable_map(Path("assets/maps/starter_map.json"))
    original_spawn = document.raw_map["spawn"]
    original_entities = document.raw_map["entities"]

    document.state.select_tile("~")
    document.state.paint_tile(1, 1)

    exported = editable_map_to_dict(document.raw_map, document.state)

    assert exported["tiles"][1][1] == "~"
    assert exported["spawn"] == original_spawn
    assert exported["entities"] == original_entities
    assert document.raw_map["tiles"][1][1] != "~"


def test_editable_map_to_dict_exports_entity_positions() -> None:
    """
    Проверяет, что экспорт карты включает обновленные raw entity.
    """
    document = load_editable_map(Path("assets/maps/starter_map.json"))
    original_raw_position = document.raw_map["entities"][0]["components"]["body"]["position"]
    target_position = [original_raw_position[0] + 7, original_raw_position[1] + 5]

    document.state.move_entity("npc-funday", target_position[0], target_position[1])
    exported = editable_map_to_dict(document.raw_map, document.state)

    assert exported["entities"][0]["components"]["body"]["position"] == target_position
    raw_position = document.raw_map["entities"][0]["components"]["body"]["position"]
    assert raw_position == original_raw_position


def test_save_editable_map_rejects_entity_on_blocked_tile(tmp_path: Path) -> None:
    """
    Проверяет, что сохранение не записывает карту с entity на solid-тайле.
    """
    source_path = Path("assets/maps/starter_map.json")
    target_path = tmp_path / "map.json"
    original_text = source_path.read_text(encoding="utf-8")
    target_path.write_text(original_text, encoding="utf-8")
    document = load_editable_map(target_path)
    document.state.move_entity("npc-funday", 0, 0)

    with pytest.raises(ValueError, match="overlaps blocked tiles"):
        save_editable_map(target_path, document.raw_map, document.state)

    assert target_path.read_text(encoding="utf-8") == original_text


def test_save_editable_map_writes_json_and_clears_dirty(tmp_path: Path) -> None:
    """
    Проверяет сохранение карты в JSON-файл и сброс dirty-флага.
    """
    source_path = Path("assets/maps/starter_map.json")
    target_path = tmp_path / "map.json"
    target_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    document = load_editable_map(target_path)
    document.state.select_tile("~")
    document.state.paint_tile(1, 1)

    saved_map = save_editable_map(target_path, document.raw_map, document.state)
    reloaded = load_editable_map(target_path)

    assert not document.state.dirty
    assert saved_map["tiles"][1][1] == "~"
    assert reloaded.state.tile_at(1, 1) == "~"


def test_create_backup_uses_available_backup_path(tmp_path: Path) -> None:
    """
    Проверяет, что backup не затирает уже существующую резервную копию.
    """
    map_path = tmp_path / "map.json"
    map_path.write_text("current", encoding="utf-8")
    first_backup = available_backup_path(map_path)
    first_backup.write_text("previous", encoding="utf-8")

    backup_path = create_backup(map_path)

    assert backup_path.name == "map.json.bak.1"
    assert backup_path.read_text(encoding="utf-8") == "current"
    assert first_backup.read_text(encoding="utf-8") == "previous"


def test_parse_map_dimensions_reads_width_and_height() -> None:
    """
    Проверяет чтение размера новой карты из CLI-формата.
    """
    assert parse_map_dimensions("60x35") == (60, 35)


def test_create_empty_map_from_template_writes_valid_map(tmp_path: Path) -> None:
    """
    Проверяет создание новой карты с legend из starter-map.
    """
    target_path = tmp_path / "new_map.json"

    raw_map = create_empty_map_from_template(
        template_path=Path("assets/maps/starter_map.json"),
        output_path=target_path,
        width=5,
        height=4,
    )
    document = load_editable_map(target_path)

    assert raw_map["tiles"] == [
        "#####",
        "#...#",
        "#...#",
        "#####",
    ]
    assert raw_map["entities"] == []
    assert document.state.width == 5
    assert document.state.height == 4
    assert document.state.tile_at(1, 1) == "."


def test_create_empty_map_from_template_refuses_existing_file(tmp_path: Path) -> None:
    """
    Проверяет, что создание новой карты не перезаписывает файл без явного флага.
    """
    target_path = tmp_path / "new_map.json"
    target_path.write_text("already here", encoding="utf-8")

    with pytest.raises(FileExistsError):
        create_empty_map_from_template(
            template_path=Path("assets/maps/starter_map.json"),
            output_path=target_path,
            width=5,
            height=4,
        )
