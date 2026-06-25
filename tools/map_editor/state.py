from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from basic_mmo_rpg.domain.tiles import TileDefinition, TileMap


@dataclass(slots=True)
class EditableMapState:
    """
    Хранит изменяемый слой тайлов редактора без изменения доменной TileMap.
    """

    tile_size: int
    definitions: Mapping[str, TileDefinition]
    tiles: list[list[str]]
    selected_tile_key: str
    dirty: bool = False

    @classmethod
    def from_tile_map(cls, tile_map: TileMap) -> EditableMapState:
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
