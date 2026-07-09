from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from basic_mmo_rpg.domain.equipment import (
    CHEST_SLOT,
    MAIN_HAND_SLOT,
    Equipment,
    EquipmentError,
    validate_equipment_slot,
)
from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.inventory import (
    InventoryLimitError,
    ItemStack,
    equipment_slot_for_item,
    item_definition_for,
    item_stack_for,
)
from basic_mmo_rpg.domain.skills import (
    INITIAL_SKILL_MAX,
    INITIAL_SKILL_MIN,
    SKILL_DEFINITIONS,
    CharacterSkill,
    apply_skill_gain,
    character_skill_for,
    skill_definition_for,
    validate_skill_value,
)


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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS character_equipment (
                    character_name TEXT PRIMARY KEY,
                    main_hand_item_id TEXT,
                    chest_item_id TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (character_name) REFERENCES characters(name)
                )
                """
            )
            self._ensure_equipment_columns(connection)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS character_loot_claims (
                    character_name TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (character_name, source_id),
                    FOREIGN KEY (character_name) REFERENCES characters(name)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS character_repeatable_quest_completions (
                    character_name TEXT NOT NULL,
                    quest_id TEXT NOT NULL,
                    completed_count INTEGER NOT NULL DEFAULT 0,
                    last_completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (character_name, quest_id),
                    FOREIGN KEY (character_name) REFERENCES characters(name)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS character_skills (
                    character_name TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    value_tenths INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (character_name, skill_id),
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
            return self._load_inventory(connection, name)

    def load_equipment(self, name: str) -> Equipment:
        """
        Загружает экипировку персонажа.
        """
        with self._connect() as connection:
            return self._load_equipment(connection, name)

    def load_skills(self, name: str) -> list[CharacterSkill]:
        """
        Загружает persistent-значения игровых скиллов персонажа.
        """
        with self._connect() as connection:
            return self._load_skills(connection, name)

    def ensure_character_skills(
        self,
        name: str,
        random_source: random.Random,
    ) -> list[CharacterSkill]:
        """
        Досоздает недостающие скиллы персонажа со стартовым случайным значением.
        """
        with self._connect() as connection:
            existing_ids = {skill.skill_id for skill in self._load_skills(connection, name)}
            for definition in SKILL_DEFINITIONS:
                if definition.skill_id in existing_ids:
                    continue
                initial_value = random_source.randint(INITIAL_SKILL_MIN, INITIAL_SKILL_MAX)
                self._set_skill_value(connection, name, definition.skill_id, initial_value)
            return self._load_skills(connection, name)

    def skill_value(self, name: str, skill_id: str) -> int:
        """
        Возвращает значение скилла персонажа в десятых долях процента.
        """
        skill_definition_for(skill_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT value_tenths
                FROM character_skills
                WHERE character_name = ? AND skill_id = ?
                """,
                (name, skill_id),
            ).fetchone()
        return int(row["value_tenths"]) if row is not None else 0

    def set_skill_value(
        self,
        name: str,
        skill_id: str,
        value_tenths: int,
    ) -> list[CharacterSkill]:
        """
        Записывает значение скилла персонажа.
        """
        skill_definition_for(skill_id)
        value_tenths = validate_skill_value(value_tenths)
        with self._connect() as connection:
            self._set_skill_value(connection, name, skill_id, value_tenths)
            return self._load_skills(connection, name)

    def increase_skill(
        self,
        name: str,
        skill_id: str,
        gain_tenths: int = 1,
    ) -> tuple[list[CharacterSkill], CharacterSkill, bool]:
        """
        Увеличивает скилл персонажа с учетом демо-ограничения.
        """
        skill_definition_for(skill_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT value_tenths
                FROM character_skills
                WHERE character_name = ? AND skill_id = ?
                """,
                (name, skill_id),
            ).fetchone()
            current_value = int(row["value_tenths"]) if row is not None else 0
            next_value = apply_skill_gain(current_value, gain_tenths)
            if next_value != current_value:
                self._set_skill_value(connection, name, skill_id, next_value)
            skills = self._load_skills(connection, name)
        return skills, character_skill_for(skill_id, next_value), next_value != current_value

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

    def item_quantity(self, name: str, item_id: str) -> int:
        """
        Возвращает количество указанного предмета в инвентаре персонажа.
        """
        with self._connect() as connection:
            return self._item_quantity(connection, name, item_id)

    def add_item(self, name: str, item_id: str, quantity: int = 1) -> list[ItemStack]:
        """
        Добавляет предмет в инвентарь персонажа и возвращает обновленный инвентарь.
        """
        if quantity <= 0:
            msg = "quantity must be positive"
            raise ValueError(msg)

        definition = item_definition_for(item_id)
        with self._connect() as connection:
            current_quantity = self._item_quantity(connection, name, item_id)
            next_quantity = current_quantity + quantity
            if next_quantity > definition.stack_limit:
                msg = f"item {item_id!r} stack limit exceeded"
                raise InventoryLimitError(msg)
            self._set_item_quantity(connection, name, item_id, next_quantity)
        return self.load_inventory(name)

    def remove_item(self, name: str, item_id: str, quantity: int = 1) -> list[ItemStack]:
        """
        Снимает предмет из инвентаря персонажа и возвращает обновленный инвентарь.
        """
        if quantity <= 0:
            msg = "quantity must be positive"
            raise ValueError(msg)

        with self._connect() as connection:
            current_quantity = self._item_quantity(connection, name, item_id)
            if current_quantity < quantity:
                msg = f"not enough item {item_id!r}"
                raise ValueError(msg)
            self._set_item_quantity(connection, name, item_id, current_quantity - quantity)
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

    def has_loot_claim(self, name: str, source_id: str) -> bool:
        """
        Проверяет, забирал ли персонаж награду из указанного источника.
        """
        with self._connect() as connection:
            return self._has_loot_claim(connection, name, source_id)

    def claim_loot_once(
        self,
        name: str,
        source_id: str,
        item_id: str,
        quantity: int = 1,
    ) -> tuple[list[ItemStack], bool]:
        """
        Атомарно выдает loot-награду один раз для пары персонаж-источник.
        """
        if quantity <= 0:
            msg = "quantity must be positive"
            raise ValueError(msg)

        definition = item_definition_for(item_id)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO character_loot_claims (
                    character_name,
                    source_id,
                    claimed_at
                )
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (name, source_id),
            )
            if cursor.rowcount == 0:
                return self._load_inventory(connection, name), False

            current_quantity = self._item_quantity(connection, name, item_id)
            next_quantity = current_quantity + quantity
            if next_quantity > definition.stack_limit:
                msg = f"item {item_id!r} stack limit exceeded"
                raise InventoryLimitError(msg)

            self._set_item_quantity(connection, name, item_id, next_quantity)
            return self._load_inventory(connection, name), True

    def equip_item(self, name: str, item_id: str) -> Equipment:
        """
        Экипирует предмет из инвентаря персонажа в подходящий слот.
        """
        slot = equipment_slot_for_item(item_id)
        if slot is None:
            msg = f"item {item_id!r} is not equippable"
            raise EquipmentError(msg)
        validate_equipment_slot(slot)

        with self._connect() as connection:
            if self._item_quantity(connection, name, item_id) <= 0:
                msg = f"item {item_id!r} is not in inventory"
                raise EquipmentError(msg)
            self._set_equipment_slot(connection, name, slot, item_id)
            return self._load_equipment(connection, name)

    def unequip_slot(self, name: str, slot: str) -> Equipment:
        """
        Снимает предмет из указанного слота экипировки.
        """
        validate_equipment_slot(slot)
        with self._connect() as connection:
            self._set_equipment_slot(connection, name, slot, None)
            return self._load_equipment(connection, name)

    def is_item_equipped(self, name: str, slot: str, item_id: str) -> bool:
        """
        Проверяет, экипирован ли предмет в указанном слоте.
        """
        validate_equipment_slot(slot)
        with self._connect() as connection:
            equipment = self._load_equipment(connection, name)
            if self._item_quantity(connection, name, item_id) <= 0:
                return False
            if slot == MAIN_HAND_SLOT:
                return equipment.main_hand == item_id
            if slot == CHEST_SLOT:
                return equipment.chest == item_id
            return False

    def exchange_items(
        self,
        name: str,
        cost_item_id: str,
        cost_quantity: int,
        reward_item_id: str,
        reward_quantity: int = 1,
    ) -> tuple[list[ItemStack], bool]:
        """
        Атомарно списывает один предмет и начисляет другой предмет.
        """
        if cost_quantity <= 0 or reward_quantity <= 0:
            msg = "exchange quantities must be positive"
            raise ValueError(msg)

        reward_definition = item_definition_for(reward_item_id)
        with self._connect() as connection:
            current_cost_quantity = self._item_quantity(connection, name, cost_item_id)
            if current_cost_quantity < cost_quantity:
                return self._load_inventory(connection, name), False

            current_reward_quantity = self._item_quantity(connection, name, reward_item_id)
            next_reward_quantity = current_reward_quantity + reward_quantity
            if next_reward_quantity > reward_definition.stack_limit:
                msg = f"item {reward_item_id!r} stack limit exceeded"
                raise InventoryLimitError(msg)

            self._set_item_quantity(
                connection,
                name,
                cost_item_id,
                current_cost_quantity - cost_quantity,
            )
            self._set_item_quantity(connection, name, reward_item_id, next_reward_quantity)
            return self._load_inventory(connection, name), True

    def complete_repeatable_quest_exchange(
        self,
        name: str,
        quest_id: str,
        cost_item_id: str,
        cost_quantity: int,
        reward_item_id: str,
        reward_quantity: int = 1,
    ) -> tuple[list[ItemStack], bool]:
        """
        Атомарно выполняет repeatable-квест обмена и записывает факт успешной сдачи.
        """
        if not quest_id:
            msg = "quest_id must be non-empty"
            raise ValueError(msg)
        if cost_quantity <= 0 or reward_quantity <= 0:
            msg = "exchange quantities must be positive"
            raise ValueError(msg)

        reward_definition = item_definition_for(reward_item_id)
        with self._connect() as connection:
            current_cost_quantity = self._item_quantity(connection, name, cost_item_id)
            if current_cost_quantity < cost_quantity:
                return self._load_inventory(connection, name), False

            current_reward_quantity = self._item_quantity(connection, name, reward_item_id)
            next_reward_quantity = current_reward_quantity + reward_quantity
            if next_reward_quantity > reward_definition.stack_limit:
                msg = f"item {reward_item_id!r} stack limit exceeded"
                raise InventoryLimitError(msg)

            self._set_item_quantity(
                connection,
                name,
                cost_item_id,
                current_cost_quantity - cost_quantity,
            )
            self._set_item_quantity(connection, name, reward_item_id, next_reward_quantity)
            connection.execute(
                """
                INSERT INTO character_repeatable_quest_completions (
                    character_name,
                    quest_id,
                    completed_count,
                    last_completed_at
                )
                VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(character_name, quest_id) DO UPDATE SET
                    completed_count = completed_count + 1,
                    last_completed_at = CURRENT_TIMESTAMP
                """,
                (name, quest_id),
            )
            return self._load_inventory(connection, name), True

    def repeatable_quest_completion_count(self, name: str, quest_id: str) -> int:
        """
        Возвращает число успешных сдач repeatable-квеста персонажем.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT completed_count
                FROM character_repeatable_quest_completions
                WHERE character_name = ? AND quest_id = ?
                """,
                (name, quest_id),
            ).fetchone()
        return int(row["completed_count"]) if row is not None else 0

    def _connect(self) -> sqlite3.Connection:
        """
        Открывает SQLite-соединение с удобным доступом к колонкам по имени.
        """
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _load_inventory(self, connection: sqlite3.Connection, name: str) -> list[ItemStack]:
        """
        Загружает инвентарь персонажа через существующее SQLite-соединение.
        """
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

    def _load_equipment(self, connection: sqlite3.Connection, name: str) -> Equipment:
        """
        Загружает экипировку персонажа через существующее SQLite-соединение.
        """
        row = connection.execute(
            """
            SELECT main_hand_item_id, chest_item_id
            FROM character_equipment
            WHERE character_name = ?
            """,
            (name,),
        ).fetchone()
        if row is None:
            return Equipment()
        main_hand = row["main_hand_item_id"]
        chest = row["chest_item_id"]
        return Equipment(
            main_hand=str(main_hand) if main_hand is not None else None,
            chest=str(chest) if chest is not None else None,
        )

    def _load_skills(
        self,
        connection: sqlite3.Connection,
        name: str,
    ) -> list[CharacterSkill]:
        """
        Загружает скиллы персонажа через существующее SQLite-соединение.
        """
        rows = connection.execute(
            """
            SELECT skill_id, value_tenths
            FROM character_skills
            WHERE character_name = ?
            """,
            (name,),
        ).fetchall()
        values = {str(row["skill_id"]): int(row["value_tenths"]) for row in rows}
        return [
            character_skill_for(definition.skill_id, values[definition.skill_id])
            for definition in SKILL_DEFINITIONS
            if definition.skill_id in values
        ]

    def _item_quantity(
        self,
        connection: sqlite3.Connection,
        name: str,
        item_id: str,
    ) -> int:
        """
        Возвращает количество предмета через существующее SQLite-соединение.
        """
        row = connection.execute(
            """
            SELECT quantity
            FROM inventory_items
            WHERE character_name = ? AND item_id = ?
            """,
            (name, item_id),
        ).fetchone()
        return int(row["quantity"]) if row is not None else 0

    def _has_loot_claim(
        self,
        connection: sqlite3.Connection,
        name: str,
        source_id: str,
    ) -> bool:
        """
        Проверяет loot-claim через существующее SQLite-соединение.
        """
        row = connection.execute(
            """
            SELECT 1
            FROM character_loot_claims
            WHERE character_name = ? AND source_id = ?
            """,
            (name, source_id),
        ).fetchone()
        return row is not None

    def _set_item_quantity(
        self,
        connection: sqlite3.Connection,
        name: str,
        item_id: str,
        quantity: int,
    ) -> None:
        """
        Записывает количество предмета через существующее SQLite-соединение.
        """
        if quantity <= 0:
            connection.execute(
                """
                DELETE FROM inventory_items
                WHERE character_name = ? AND item_id = ?
                """,
                (name, item_id),
            )
            return

        connection.execute(
            """
            INSERT INTO inventory_items (character_name, item_id, quantity, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(character_name, item_id) DO UPDATE SET
                quantity = excluded.quantity,
                updated_at = CURRENT_TIMESTAMP
            """,
            (name, item_id, quantity),
        )

    def _set_skill_value(
        self,
        connection: sqlite3.Connection,
        name: str,
        skill_id: str,
        value_tenths: int,
    ) -> None:
        """
        Записывает значение скилла через существующее SQLite-соединение.
        """
        connection.execute(
            """
            INSERT INTO character_skills (
                character_name,
                skill_id,
                value_tenths,
                updated_at
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(character_name, skill_id) DO UPDATE SET
                value_tenths = excluded.value_tenths,
                updated_at = CURRENT_TIMESTAMP
            """,
            (name, skill_id, value_tenths),
        )

    def _set_equipment_slot(
        self,
        connection: sqlite3.Connection,
        name: str,
        slot: str,
        item_id: str | None,
    ) -> None:
        """
        Записывает предмет в слот экипировки через существующее SQLite-соединение.
        """
        validate_equipment_slot(slot)
        column = _equipment_column_for_slot(slot)
        connection.execute(
            f"""
            INSERT INTO character_equipment (character_name, {column}, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(character_name) DO UPDATE SET
                {column} = excluded.{column},
                updated_at = CURRENT_TIMESTAMP
            """,
            (name, item_id),
        )

    def _ensure_equipment_columns(self, connection: sqlite3.Connection) -> None:
        """
        Добавляет новые слоты экипировки в существующую таблицу без пересоздания базы.
        """
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(character_equipment)")
        }
        if "chest_item_id" not in columns:
            connection.execute("ALTER TABLE character_equipment ADD COLUMN chest_item_id TEXT")


def _equipment_column_for_slot(slot: str) -> str:
    """
    Возвращает имя SQLite-колонки для поддерживаемого слота экипировки.
    """
    if slot == MAIN_HAND_SLOT:
        return "main_hand_item_id"
    if slot == CHEST_SLOT:
        return "chest_item_id"
    msg = f"unsupported equipment slot: {slot!r}"
    raise EquipmentError(msg)
