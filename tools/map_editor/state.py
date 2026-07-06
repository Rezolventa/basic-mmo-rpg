from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from basic_mmo_rpg.domain.tiles import TileDefinition, TileMap
from tools.map_editor.entities import EditableEntity

CREATURE_ENTITY_KIND = "creature"


@dataclass(slots=True)
class EditableMapState:
    """
    Хранит изменяемый слой тайлов редактора без изменения доменной TileMap.
    """

    tile_size: int
    definitions: Mapping[str, TileDefinition]
    tiles: list[list[str]]
    entities: list[EditableEntity]
    selected_tile_key: str
    selected_entity_id: str | None = None
    dirty: bool = False

    @classmethod
    def from_tile_map(
        cls,
        tile_map: TileMap,
        raw_entities: list[dict[str, Any]] | None = None,
    ) -> EditableMapState:
        """
        Создает состояние редактора из загруженной игровой карты.
        """
        tile_keys = tuple(tile_map.definitions.keys())
        if not tile_keys:
            msg = "editable map requires at least one tile definition"
            raise ValueError(msg)
        return cls(
            tile_size=tile_map.tile_size,
            definitions=tile_map.definitions,
            tiles=[list(row) for row in tile_map.tiles],
            entities=[
                EditableEntity.from_raw(raw_entity)
                for raw_entity in raw_entities or []
            ],
            selected_tile_key=tile_keys[0],
        )

    @property
    def width(self) -> int:
        """
        Возвращает ширину карты в тайлах.
        """
        return len(self.tiles[0])

    @property
    def height(self) -> int:
        """
        Возвращает высоту карты в тайлах.
        """
        return len(self.tiles)

    @property
    def pixel_width(self) -> int:
        """
        Возвращает ширину карты в пикселях.
        """
        return self.width * self.tile_size

    @property
    def pixel_height(self) -> int:
        """
        Возвращает высоту карты в пикселях.
        """
        return self.height * self.tile_size

    @property
    def tile_keys(self) -> tuple[str, ...]:
        """
        Возвращает ключи тайлов в порядке палитры.
        """
        return tuple(self.definitions.keys())

    def in_bounds(self, tile_x: int, tile_y: int) -> bool:
        """
        Проверяет, находится ли тайл внутри карты.
        """
        return 0 <= tile_x < self.width and 0 <= tile_y < self.height

    def tile_at(self, tile_x: int, tile_y: int) -> str:
        """
        Возвращает ключ тайла по координатам сетки.
        """
        if not self.in_bounds(tile_x, tile_y):
            msg = f"tile coordinates out of bounds: ({tile_x}, {tile_y})"
            raise IndexError(msg)
        return self.tiles[tile_y][tile_x]

    def select_tile(self, tile_key: str) -> None:
        """
        Выбирает тайл для последующего рисования.
        """
        if tile_key not in self.definitions:
            msg = f"unknown tile key: {tile_key!r}"
            raise ValueError(msg)
        self.selected_tile_key = tile_key

    def select_tile_by_index(self, tile_index: int) -> None:
        """
        Выбирает тайл по индексу палитры.
        """
        tile_keys = self.tile_keys
        if tile_index < 0 or tile_index >= len(tile_keys):
            return
        self.select_tile(tile_keys[tile_index])

    def pick_tile(self, tile_x: int, tile_y: int) -> None:
        """
        Выбирает тайл, который уже стоит в указанной клетке карты.
        """
        self.select_tile(self.tile_at(tile_x, tile_y))

    def paint_tile(self, tile_x: int, tile_y: int) -> bool:
        """
        Ставит выбранный тайл в указанную клетку и возвращает флаг изменения.
        """
        if not self.in_bounds(tile_x, tile_y):
            return False
        if self.tiles[tile_y][tile_x] == self.selected_tile_key:
            return False
        self.tiles[tile_y][tile_x] = self.selected_tile_key
        self.dirty = True
        return True

    def entity_at_point(self, x: float, y: float) -> EditableEntity | None:
        """
        Возвращает верхнюю entity под точкой или None.
        """
        for entity in reversed(self.entities):
            if entity.contains_point(x, y):
                return entity
        return None

    def selected_entity(self) -> EditableEntity | None:
        """
        Возвращает выбранную entity или None.
        """
        if self.selected_entity_id is None:
            return None
        return self.entity_by_id(self.selected_entity_id)

    def entity_by_id(self, entity_id: str) -> EditableEntity | None:
        """
        Возвращает entity по id.
        """
        return next(
            (entity for entity in self.entities if entity.entity_id == entity_id),
            None,
        )

    def select_entity(self, entity_id: str | None) -> None:
        """
        Выбирает entity по id или сбрасывает выбор.
        """
        if entity_id is None:
            self.selected_entity_id = None
            return
        if self.entity_by_id(entity_id) is None:
            msg = f"unknown entity id: {entity_id!r}"
            raise ValueError(msg)
        self.selected_entity_id = entity_id

    def duplicate_selected_creature(self) -> EditableEntity | None:
        """
        Дублирует выбранную creature-entity и сразу выбирает созданную копию.
        """
        entity = self.selected_entity()
        if entity is None or entity.kind != CREATURE_ENTITY_KIND:
            return None

        duplicate = EditableEntity.from_raw(entity.to_raw())
        duplicate.set_entity_id(self._next_copy_entity_id(entity.entity_id))
        duplicate_x, duplicate_y = self._duplicate_position_for(entity)
        duplicate.set_position(duplicate_x, duplicate_y)

        self.entities.append(duplicate)
        self.selected_entity_id = duplicate.entity_id
        self.dirty = True
        return duplicate

    def move_entity(self, entity_id: str, x: float, y: float) -> bool:
        """
        Перемещает entity и возвращает флаг изменения.
        """
        entity = self.entity_by_id(entity_id)
        if entity is None:
            return False
        if entity.position == (float(x), float(y)):
            return False
        entity.set_position(x, y)
        self.dirty = True
        return True

    def snap_entity_center_to_tile(
        self,
        entity_id: str,
        tile_x: int,
        tile_y: int,
    ) -> bool:
        """
        Притягивает центр entity к центру указанного тайла.
        """
        if not self.in_bounds(tile_x, tile_y):
            return False
        entity = self.entity_by_id(entity_id)
        if entity is None:
            return False
        width, height = entity.size
        center_x = tile_x * self.tile_size + self.tile_size / 2
        center_y = tile_y * self.tile_size + self.tile_size / 2
        return self.move_entity(
            entity_id,
            center_x - width / 2,
            center_y - height / 2,
        )

    def _next_copy_entity_id(self, entity_id: str) -> str:
        existing_ids = {entity.entity_id for entity in self.entities}
        base_id = f"{entity_id}-copy"
        if base_id not in existing_ids:
            return base_id

        index = 2
        while f"{base_id}-{index}" in existing_ids:
            index += 1
        return f"{base_id}-{index}"

    def _duplicate_position_for(self, entity: EditableEntity) -> tuple[float, float]:
        left, top = entity.position
        width, height = entity.size
        max_x = max(0.0, float(self.pixel_width - width))
        max_y = max(0.0, float(self.pixel_height - height))

        duplicate_x = min(left + self.tile_size, max_x)
        duplicate_y = min(top + self.tile_size, max_y)
        if (duplicate_x, duplicate_y) != (left, top):
            return duplicate_x, duplicate_y

        return max(0.0, left - self.tile_size), max(0.0, top - self.tile_size)
