from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.inventory import ItemStack, item_definition_for, item_stack_for


@dataclass(frozen=True, slots=True)
class CharacterRecord:
    """
    Хранит сохраненное состояние персонажа из SQLite.
    """

    name: str
    position: Vec2


class CharacterRepository:
    """
    Загружает и сохраняет persistent-состояние персонажей в SQLite.
    """

    def __init__(self, database_path: Path) -> None:
        """
        Инициализирует репозиторий с путем к SQLite-базе.
        """
        self.database_path = database_path

    def initialize(self) -> None:
        """
        Создает директорию базы и таблицу персонажей, если они еще не существуют.
        """
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS characters (
                    name TEXT PRIMARY KEY,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS inventory_items (
                    character_name TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (character_name, item_id),
                    FOREIGN KEY (character_name) REFERENCES characters(name)
                )
                """
            )

    def load_or_create(self, name: str, default_position: Vec2) -> CharacterRecord:
        """
        Загружает персонажа по имени или создает его с позицией по умолчанию.
        """
        with self._connect() as connection:
            row = connection.execute(
                "SELECT name, x, y FROM characters WHERE name = ?",
                (name,),
            ).fetchone()
            if row is not None:
                return CharacterRecord(
                    name=str(row["name"]),
                    position=Vec2(float(row["x"]), float(row["y"])),
                )

            connection.execute(
                """
                INSERT INTO characters (name, x, y, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (name, default_position.x, default_position.y),
            )
            return CharacterRecord(name=name, position=default_position)

    def save_position(self, name: str, position: Vec2) -> None:
        """
        Сохраняет текущую позицию персонажа.
        """
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO characters (name, x, y, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    x = excluded.x,
                    y = excluded.y,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, position.x, position.y),
            )

    def load_inventory(self, name: str) -> list[ItemStack]:
        """
        Загружает инвентарь персонажа как список стаков предметов.
        """
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT item_id, quantity
                FROM inventory_items
                WHERE character_name = ? AND quantity > 0
                ORDER BY item_id
                """,
                (name,),
            ).fetchall()
        return [item_stack_for(str(row["item_id"]), int(row["quantity"])) for row in rows]

    def has_item(self, name: str, item_id: str) -> bool:
        """
        Проверяет, есть ли у персонажа хотя бы один предмет с указанным id.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT quantity
                FROM inventory_items
                WHERE character_name = ? AND item_id = ? AND quantity > 0
                """,
                (name, item_id),
            ).fetchone()
        return row is not None

    def add_item(self, name: str, item_id: str, quantity: int = 1) -> list[ItemStack]:
        """
        Добавляет предмет в инвентарь персонажа и возвращает обновленный инвентарь.
        """
        if quantity <= 0:
            msg = "quantity must be positive"
            raise ValueError(msg)

        definition = item_definition_for(item_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT quantity
                FROM inventory_items
                WHERE character_name = ? AND item_id = ?
                """,
                (name, item_id),
            ).fetchone()
            current_quantity = int(row["quantity"]) if row is not None else 0
            next_quantity = current_quantity + quantity
            if next_quantity > definition.stack_limit:
                msg = f"item {item_id!r} stack limit exceeded"
                raise ValueError(msg)
            connection.execute(
                """
                INSERT INTO inventory_items (character_name, item_id, quantity, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(character_name, item_id) DO UPDATE SET
                    quantity = excluded.quantity,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, item_id, next_quantity),
            )
        return self.load_inventory(name)

    def add_item_if_absent(
        self,
        name: str,
        item_id: str,
        quantity: int = 1,
    ) -> tuple[list[ItemStack], bool]:
        """
        Добавляет предмет только если у персонажа еще нет такого item_id.
        """
        if self.has_item(name, item_id):
            return self.load_inventory(name), False
        return self.add_item(name, item_id, quantity), True

    def _connect(self) -> sqlite3.Connection:
        """
        Открывает SQLite-соединение с удобным доступом к колонкам по имени.
        """
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection
