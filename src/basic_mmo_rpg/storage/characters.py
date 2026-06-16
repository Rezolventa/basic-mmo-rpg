from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from basic_mmo_rpg.domain.geometry import Vec2


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

    def _connect(self) -> sqlite3.Connection:
        """
        Открывает SQLite-соединение с удобным доступом к колонкам по имени.
        """
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection
