from __future__ import annotations

from pathlib import Path

from basic_mmo_rpg.domain.geometry import Vec2
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
