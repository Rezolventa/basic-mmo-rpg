from __future__ import annotations

from pathlib import Path

import pytest

from basic_mmo_rpg.domain.equipment import MAIN_HAND_SLOT, EquipmentError
from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.inventory import (
    FISH_ITEM_ID,
    FISHING_ROD_ITEM_ID,
    GOLD_ITEM_ID,
    InventoryLimitError,
)
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

    with pytest.raises(InventoryLimitError):
        repository.add_item("Alice", FISHING_ROD_ITEM_ID)


def test_character_repository_removes_inventory_items(tmp_path: Path) -> None:
    """
    Проверяет списание предметов и удаление пустого стака из инвентаря.
    """
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    repository.initialize()
    repository.load_or_create("Alice", Vec2(32, 48))

    repository.add_item("Alice", FISH_ITEM_ID, quantity=2)
    first_inventory = repository.remove_item("Alice", FISH_ITEM_ID)
    second_inventory = repository.remove_item("Alice", FISH_ITEM_ID)

    assert first_inventory[0].item_id == FISH_ITEM_ID
    assert first_inventory[0].quantity == 1
    assert second_inventory == []

    with pytest.raises(ValueError):
        repository.remove_item("Alice", FISH_ITEM_ID)


def test_character_repository_exchanges_items_atomically(tmp_path: Path) -> None:
    """
    Проверяет атомарный обмен двух рыб на Gold.
    """
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    repository.initialize()
    repository.load_or_create("Alice", Vec2(32, 48))

    repository.add_item("Alice", FISH_ITEM_ID, quantity=3)
    inventory, exchanged = repository.exchange_items(
        name="Alice",
        cost_item_id=FISH_ITEM_ID,
        cost_quantity=2,
        reward_item_id=GOLD_ITEM_ID,
    )

    quantities = {item.item_id: item.quantity for item in inventory}
    assert exchanged is True
    assert quantities[FISH_ITEM_ID] == 1
    assert quantities[GOLD_ITEM_ID] == 1
    assert repository.item_quantity("Alice", FISH_ITEM_ID) == 1
    assert repository.item_quantity("Alice", GOLD_ITEM_ID) == 1


def test_character_repository_exchange_does_not_change_inventory_without_cost(
    tmp_path: Path,
) -> None:
    """
    Проверяет, что обмен без нужного количества предметов не меняет инвентарь.
    """
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    repository.initialize()
    repository.load_or_create("Alice", Vec2(32, 48))

    repository.add_item("Alice", FISH_ITEM_ID)
    inventory, exchanged = repository.exchange_items(
        name="Alice",
        cost_item_id=FISH_ITEM_ID,
        cost_quantity=2,
        reward_item_id=GOLD_ITEM_ID,
    )

    assert exchanged is False
    assert inventory[0].item_id == FISH_ITEM_ID
    assert inventory[0].quantity == 1
    assert repository.item_quantity("Alice", GOLD_ITEM_ID) == 0


def test_character_repository_exchange_rejects_reward_stack_overflow(tmp_path: Path) -> None:
    """
    Проверяет, что обмен не списывает предметы, если награда переполнит стак.
    """
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    repository.initialize()
    repository.load_or_create("Alice", Vec2(32, 48))

    repository.add_item("Alice", FISH_ITEM_ID, quantity=2)
    repository.add_item("Alice", GOLD_ITEM_ID, quantity=999)

    with pytest.raises(InventoryLimitError):
        repository.exchange_items(
            name="Alice",
            cost_item_id=FISH_ITEM_ID,
            cost_quantity=2,
            reward_item_id=GOLD_ITEM_ID,
        )

    assert repository.item_quantity("Alice", FISH_ITEM_ID) == 2
    assert repository.item_quantity("Alice", GOLD_ITEM_ID) == 999


def test_character_repository_persists_equipment(tmp_path: Path) -> None:
    """
    Проверяет сохранение и загрузку предмета в руке.
    """
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    repository.initialize()
    repository.load_or_create("Alice", Vec2(32, 48))
    repository.add_item("Alice", FISHING_ROD_ITEM_ID)

    equipment = repository.equip_item("Alice", FISHING_ROD_ITEM_ID)
    loaded_equipment = repository.load_equipment("Alice")

    assert equipment.main_hand == FISHING_ROD_ITEM_ID
    assert loaded_equipment == equipment
    assert repository.is_item_equipped("Alice", MAIN_HAND_SLOT, FISHING_ROD_ITEM_ID)


def test_character_repository_rejects_missing_or_non_equippable_item(tmp_path: Path) -> None:
    """
    Проверяет, что экипировать можно только доступный экипируемый предмет.
    """
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    repository.initialize()
    repository.load_or_create("Alice", Vec2(32, 48))
    repository.add_item("Alice", FISH_ITEM_ID)

    with pytest.raises(EquipmentError):
        repository.equip_item("Alice", FISHING_ROD_ITEM_ID)
    with pytest.raises(EquipmentError):
        repository.equip_item("Alice", FISH_ITEM_ID)

    assert repository.load_equipment("Alice").main_hand is None


def test_character_repository_unequips_slot(tmp_path: Path) -> None:
    """
    Проверяет снятие предмета из слота экипировки.
    """
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    repository.initialize()
    repository.load_or_create("Alice", Vec2(32, 48))
    repository.add_item("Alice", FISHING_ROD_ITEM_ID)
    repository.equip_item("Alice", FISHING_ROD_ITEM_ID)

    equipment = repository.unequip_slot("Alice", MAIN_HAND_SLOT)

    assert equipment.main_hand is None
    assert repository.load_equipment("Alice").main_hand is None
