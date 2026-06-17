from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import floor
from types import MappingProxyType

from basic_mmo_rpg.domain.entities import WorldEntity
from basic_mmo_rpg.domain.geometry import Rect, Vec2

EDGE_EPSILON = 0.0001


@dataclass(frozen=True, slots=True)
class TileDefinition:
    """
    Описывает свойства одного типа тайла на карте.
    """

    key: str
    name: str
    solid: bool
    color: tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class TileMap:
    """
    Хранит тайловую карту и выполняет проверки проходимости.
    """

    tile_size: int
    tiles: tuple[tuple[str, ...], ...]
    definitions: Mapping[str, TileDefinition]
    spawn: Vec2
    entities: tuple[WorldEntity, ...] = ()

    def __post_init__(self) -> None:
        """
        Проверяет целостность карты после создания объекта.
        """
        if self.tile_size <= 0:
            msg = "tile_size must be positive"
            raise ValueError(msg)
        if not self.tiles:
            msg = "map must have at least one row"
            raise ValueError(msg)

        row_width = len(self.tiles[0])
        if row_width == 0:
            msg = "map rows must not be empty"
            raise ValueError(msg)

        for row in self.tiles:
            if len(row) != row_width:
                msg = "all map rows must have the same width"
                raise ValueError(msg)

        missing = {tile for row in self.tiles for tile in row if tile not in self.definitions}
        if missing:
            msg = f"map references unknown tile keys: {sorted(missing)!r}"
            raise ValueError(msg)

        entity_ids = [entity.entity_id for entity in self.entities]
        if len(entity_ids) != len(set(entity_ids)):
            msg = "map entities must have unique ids"
            raise ValueError(msg)
        for entity in self.entities:
            if self._is_rect_blocked_by_tiles(entity.rect):
                msg = f"map entity {entity.entity_id!r} overlaps blocked tiles or map bounds"
                raise ValueError(msg)

        object.__setattr__(self, "definitions", MappingProxyType(dict(self.definitions)))

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
    def pixel_size(self) -> Vec2:
        """
        Возвращает размер карты в пикселях.
        """
        return Vec2(self.width * self.tile_size, self.height * self.tile_size)

    @property
    def solid_entity_rects(self) -> tuple[Rect, ...]:
        """
        Возвращает прямоугольники коллизионных объектов карты.
        """
        return tuple(entity.rect for entity in self.entities if entity.solid)

    def in_bounds(self, tile_x: int, tile_y: int) -> bool:
        """
        Проверяет, находится ли тайл внутри границ карты.
        """
        return 0 <= tile_x < self.width and 0 <= tile_y < self.height

    def tile_at(self, tile_x: int, tile_y: int) -> str:
        """
        Возвращает ключ тайла по координатам тайловой сетки.
        """
        if not self.in_bounds(tile_x, tile_y):
            msg = f"tile coordinates out of bounds: ({tile_x}, {tile_y})"
            raise IndexError(msg)
        return self.tiles[tile_y][tile_x]

    def is_solid_tile(self, tile_x: int, tile_y: int) -> bool:
        """
        Проверяет, является ли тайл непроходимым.
        """
        if not self.in_bounds(tile_x, tile_y):
            return True
        tile_key = self.tile_at(tile_x, tile_y)
        return self.definitions[tile_key].solid

    def is_rect_blocked(self, rect: Rect, blockers: Iterable[Rect] = ()) -> bool:
        """
        Проверяет, пересекается ли прямоугольник с препятствием или границей мира.
        """
        if self._is_rect_blocked_by_tiles(rect):
            return True
        return any(rect.intersects(blocker) for blocker in blockers)

    def _is_rect_blocked_by_tiles(self, rect: Rect) -> bool:
        """
        Проверяет, пересекается ли прямоугольник с тайловыми препятствиями.
        """
        if rect.left < 0 or rect.top < 0:
            return True
        if rect.right > self.pixel_size.x or rect.bottom > self.pixel_size.y:
            return True

        left = floor(rect.left / self.tile_size)
        right = floor((rect.right - EDGE_EPSILON) / self.tile_size)
        top = floor(rect.top / self.tile_size)
        bottom = floor((rect.bottom - EDGE_EPSILON) / self.tile_size)

        for tile_y in range(top, bottom + 1):
            for tile_x in range(left, right + 1):
                if self.is_solid_tile(tile_x, tile_y):
                    return True
        return False
