from __future__ import annotations

from pathlib import Path

import pytest

from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.inventory import FISHING_ROD_ITEM_ID
from basic_mmo_rpg.storage.characters import CharacterRepository


def test_character_repository_loads_creates_and_saves_position(tmp_path: Path) -> None:
    """
    Проверяет создание персонажа и сохранение его позиции в SQLite.
    """
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    repository.initialize()

    created = repository.load_or_create("Alice", Vec2(32, 48))
    repository.save_position("Alice", Vec2(96, 112))
    loaded = repository.load_or_create("Alice", Vec2(0, 0))

    assert created.name == "Alice"
    assert created.position == Vec2(32, 48)
    assert loaded.name == "Alice"
    assert loaded.position == Vec2(96, 112)


def test_character_repository_persists_inventory_items(tmp_path: Path) -> None:
    """
    Проверяет сохранение и загрузку предметов инвентаря в SQLite.
    """
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    repository.initialize()
    repository.load_or_create("Alice", Vec2(32, 48))

    inventory = repository.add_item("Alice", FISHING_ROD_ITEM_ID)
    loaded_inventory = repository.load_inventory("Alice")

    assert repository.has_item("Alice", FISHING_ROD_ITEM_ID)
    assert inventory == loaded_inventory
    assert loaded_inventory[0].item_id == FISHING_ROD_ITEM_ID
    assert loaded_inventory[0].display_name == "Удочка"
    assert loaded_inventory[0].quantity == 1


def test_character_repository_adds_item_if_absent_only_once(tmp_path: Path) -> None:
    """
    Проверяет явное правило выдачи предмета только при его отсутствии.
    """
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    repository.initialize()
    repository.load_or_create("Alice", Vec2(32, 48))

    first_inventory, first_granted = repository.add_item_if_absent("Alice", FISHING_ROD_ITEM_ID)
    second_inventory, second_granted = repository.add_item_if_absent("Alice", FISHING_ROD_ITEM_ID)

    assert first_granted is True
    assert second_granted is False
    assert first_inventory == second_inventory
    assert second_inventory[0].quantity == 1


def test_character_repository_rejects_stack_limit_overflow(tmp_path: Path) -> None:
    """
    Проверяет, что stack limit является инвариантом предмета, а не тихим правилом выдачи.
    """
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    repository.initialize()
    repository.load_or_create("Alice", Vec2(32, 48))

    repository.add_item("Alice", FISHING_ROD_ITEM_ID)

    with pytest.raises(ValueError):
        repository.add_item("Alice", FISHING_ROD_ITEM_ID)
