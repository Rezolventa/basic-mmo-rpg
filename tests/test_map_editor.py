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
from tools.map_editor.viewport import Viewport


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


def test_editable_map_state_duplicates_selected_creature() -> None:
    """
    Проверяет копирование выбранной creature-entity с новым уникальным id.
    """
    document = load_editable_map(Path("assets/maps/starter_map.json"))
    state = document.state
    original_count = len(state.entities)
    original = state.entity_by_id("creature-boar")

    assert original is not None
    original_position = original.position
    state.select_entity("creature-boar")
    first_duplicate = state.duplicate_selected_creature()
    state.select_entity("creature-boar")
    second_duplicate = state.duplicate_selected_creature()
    exported = editable_map_to_dict(document.raw_map, state)
    exported_ids = [entity["id"] for entity in exported["entities"]]

    assert first_duplicate is not None
    assert first_duplicate.entity_id == "creature-boar-copy"
    assert first_duplicate.kind == "creature"
    assert first_duplicate.position != original_position
    assert second_duplicate is not None
    assert second_duplicate.entity_id == "creature-boar-copy-2"
    assert state.selected_entity_id == "creature-boar-copy-2"
    assert state.dirty
    assert len(state.entities) == original_count + 2
    assert len(document.raw_map["entities"]) == original_count
    assert "creature-boar-copy" not in [
        entity["id"]
        for entity in document.raw_map["entities"]
    ]
    assert exported_ids[-2:] == ["creature-boar-copy", "creature-boar-copy-2"]


def test_editable_map_state_does_not_duplicate_npc() -> None:
    """
    Проверяет, что копирование доступно только creature-entity, а не NPC.
    """
    document = load_editable_map(Path("assets/maps/starter_map.json"))
    state = document.state
    original_count = len(state.entities)

    state.select_entity("npc-funday")
    duplicate = state.duplicate_selected_creature()

    assert duplicate is None
    assert state.selected_entity_id == "npc-funday"
    assert len(state.entities) == original_count
    assert not state.dirty


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


def test_save_editable_map_preserves_new_tile_metadata(tmp_path: Path) -> None:
    source_path = Path("assets/maps/starter_map.json")
    target_path = tmp_path / "map.json"
    target_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    document = load_editable_map(target_path)

    document.state.select_tile("C")
    document.state.paint_tile(1, 1)
    saved_map = save_editable_map(target_path, document.raw_map, document.state)
    reloaded = load_editable_map(target_path)

    assert saved_map["legend"]["T"]["sprites"] == [
        "tiles/tree_deciduous_1.png",
        "tiles/tree_deciduous_2.png",
        "tiles/tree_deciduous_3.png",
        "tiles/tree_deciduous_4.png",
        "tiles/tree_conifer_1.png",
        "tiles/tree_conifer_2.png",
        "tiles/tree_conifer_3.png",
        "tiles/tree_conifer_4.png",
    ]
    assert saved_map["legend"]["T"]["collision_rect"] == [9, 18, 14, 14]
    assert saved_map["legend"]["R"]["sprites"] == [
        "tiles/rock_1.png",
        "tiles/rock_2.png",
        "tiles/rock_3.png",
    ]
    assert saved_map["legend"]["R"]["collision_rect"] == [5, 8, 22, 20]
    assert saved_map["legend"]["C"]["sprites"] == ["tiles/cave_wall_1.png"]
    assert reloaded.state.tile_at(1, 1) == "C"
    assert reloaded.state.definitions["T"].collision_rect == (9, 18, 14, 14)
    assert reloaded.state.definitions["R"].collision_rect == (5, 8, 22, 20)
    assert reloaded.state.definitions["C"].sprites == ("tiles/cave_wall_1.png",)


def test_map_editor_renderer_loads_new_tile_sprites_without_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")

    import pygame

    from tools.map_editor.rendering import MapEditorRenderer

    pygame.init()
    try:
        document = load_editable_map(Path("assets/maps/starter_map.json"))
        renderer = MapEditorRenderer(
            document.state,
            Path("assets/maps/starter_map.json"),
            Viewport(),
        )
        screen = pygame.Surface((320, 240))

        renderer.draw(screen, hovered_tile=(1, 1))

        assert len(renderer.tile_sprites["T"]) == 8
        assert len(renderer.tile_sprites["R"]) == 3
        assert len(renderer.tile_sprites["C"]) == 1
    finally:
        pygame.quit()


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
    source_document = load_editable_map(Path("assets/maps/starter_map.json"))
    document = load_editable_map(target_path)

    assert raw_map["legend"]["W"]["name"] == "wooden floor"
    assert raw_map["legend"]["W"]["solid"] is False
    assert raw_map["legend"]["W"]["color"] == [120, 98, 72]
    assert raw_map["legend"]["T"]["collision_rect"] == [9, 18, 14, 14]
    assert raw_map["legend"]["R"]["collision_rect"] == [5, 8, 22, 20]
    assert raw_map["legend"]["C"]["name"] == "cave wall"
    assert raw_map["legend"]["C"]["sprites"] == ["tiles/cave_wall_1.png"]
    assert raw_map["tiles"] == [
        ".....",
        ".....",
        ".....",
        ".....",
    ]
    expected_entity_ids = {
        entity["id"]
        for entity in source_document.raw_map["entities"]
        if entity["components"]["identity"]["kind"] != "gate"
        and "gate" not in entity["components"]
    }
    entity_ids = {entity["id"] for entity in raw_map["entities"]}
    assert entity_ids == expected_entity_ids
    assert "gate-sheep-pen" not in entity_ids
    entity_positions = {
        entity["id"]: entity["components"]["body"]["position"]
        for entity in raw_map["entities"]
    }
    assert entity_positions["npc-funday"] == [0, 0]
    assert entity_positions["npc-jack-lumber"] == [32, 0]
    assert entity_positions["npc-kopai"] == [64, 0]
    assert entity_positions["npc-fogu"] == [96, 0]
    assert entity_positions["npc-bjorn"] == [128, 0]
    assert entity_positions["object-forge"] == [0, 32]
    assert entity_positions["object-anvil"] == [32, 32]
    assert entity_positions["creature-barbara"] == [64, 32]
    assert entity_positions["object-player-respawn"] == [96, 32]
    assert entity_positions["creature-boar"] == [128, 32]
    assert entity_positions["lootable-training-dummy"] == [0, 64]
    assert document.state.width == 5
    assert document.state.height == 4
    assert document.state.tile_at(0, 0) == "."
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


def test_viewport_scrolls_and_clamps_to_map_bounds() -> None:
    """
    Проверяет прокрутку viewport-а в пределах большой карты.
    """
    viewport = Viewport()

    viewport.scroll(
        5000,
        5000,
        map_width=3200,
        map_height=3200,
        view_width=960,
        view_height=640,
    )

    assert viewport.offset_x == 2240
    assert viewport.offset_y == 2560


def test_viewport_converts_between_screen_and_world_coordinates() -> None:
    """
    Проверяет перевод координат между экраном и картой.
    """
    viewport = Viewport(offset_x=320, offset_y=640)

    assert viewport.screen_to_world(10, 20) == (330, 660)
    assert viewport.world_to_screen(330, 660) == (10, 20)


def test_viewport_converts_coordinates_with_zoom() -> None:
    """
    Проверяет перевод координат при отдалении карты.
    """
    viewport = Viewport(offset_x=320, offset_y=640, zoom=0.5)

    assert viewport.screen_to_world(10, 20) == (340, 680)
    assert viewport.world_to_screen(340, 680) == (10, 20)


def test_viewport_zoom_clamps_using_visible_world_size() -> None:
    """
    Проверяет, что clamp учитывает масштаб viewport-а.
    """
    viewport = Viewport(offset_x=3000, offset_y=3000, zoom=0.5)

    viewport.clamp(
        map_width=3200,
        map_height=3200,
        view_width=960,
        view_height=640,
    )

    assert viewport.offset_x == 1280
    assert viewport.offset_y == 1920


def test_viewport_set_zoom_keeps_anchor_world_position() -> None:
    """
    Проверяет, что смена масштаба сохраняет мировую точку под экранным якорем.
    """
    viewport = Viewport(offset_x=1000, offset_y=1000, zoom=1.0)
    anchor_before = viewport.screen_to_world(480, 320)

    viewport.set_zoom_around_screen_point(
        0.5,
        480,
        320,
        map_width=3200,
        map_height=3200,
        view_width=960,
        view_height=640,
    )

    assert viewport.screen_to_world(480, 320) == anchor_before
