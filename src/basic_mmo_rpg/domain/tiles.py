from __future__ import annotations

import hashlib
import json
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
    sprites: tuple[str, ...] = ()
    sprite_offset: tuple[int, int] = (0, 0)
    sprite_offsets: tuple[tuple[int, int], ...] = ()
    collision_rect: tuple[int, int, int, int] | None = None


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
        for definition in self.definitions.values():
            collision_rect = definition.collision_rect
            if collision_rect is None:
                continue
            offset_x, offset_y, width, height = collision_rect
            if width <= 0 or height <= 0:
                msg = "tile collision_rect size must be positive"
                raise ValueError(msg)
            if (
                offset_x < 0
                or offset_y < 0
                or offset_x + width > self.tile_size
                or offset_y + height > self.tile_size
            ):
                msg = "tile collision_rect must fit inside tile_size"
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
    def fingerprint(self) -> str:
        """
        Возвращает короткий стабильный отпечаток содержимого карты для проверки client/server sync.
        """
        encoded = json.dumps(
            _tile_map_fingerprint_payload(self),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]

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

    def tile_coordinates_at(self, position: Vec2) -> tuple[int, int] | None:
        """
        Возвращает координаты тайла под мировой позицией или `None` за пределами карты.
        """
        tile_x = floor(position.x / self.tile_size)
        tile_y = floor(position.y / self.tile_size)
        if not self.in_bounds(tile_x, tile_y):
            return None
        return tile_x, tile_y

    def tile_rect(self, tile_x: int, tile_y: int) -> Rect:
        """
        Возвращает прямоугольник тайла в мировых координатах.
        """
        if not self.in_bounds(tile_x, tile_y):
            msg = f"tile coordinates out of bounds: ({tile_x}, {tile_y})"
            raise IndexError(msg)
        return Rect(
            x=tile_x * self.tile_size,
            y=tile_y * self.tile_size,
            width=self.tile_size,
            height=self.tile_size,
        )

    def tile_collision_rect(self, tile_x: int, tile_y: int) -> Rect | None:
        """
        Возвращает прямоугольник коллизии тайла или `None` для проходимого тайла.
        """
        if not self.in_bounds(tile_x, tile_y):
            msg = f"tile coordinates out of bounds: ({tile_x}, {tile_y})"
            raise IndexError(msg)
        tile_key = self.tile_at(tile_x, tile_y)
        definition = self.definitions[tile_key]
        if not definition.solid:
            return None
        if definition.collision_rect is None:
            return self.tile_rect(tile_x, tile_y)
        offset_x, offset_y, width, height = definition.collision_rect
        return Rect(
            x=tile_x * self.tile_size + offset_x,
            y=tile_y * self.tile_size + offset_y,
            width=width,
            height=height,
        )

    def tile_name_at(self, tile_x: int, tile_y: int) -> str:
        """
        Возвращает доменное имя тайла по координатам тайловой сетки.
        """
        tile_key = self.tile_at(tile_x, tile_y)
        return self.definitions[tile_key].name

    def is_solid_tile(self, tile_x: int, tile_y: int) -> bool:
        """
        Проверяет, является ли тайл непроходимым.
        """
        if not self.in_bounds(tile_x, tile_y):
            return True
        tile_key = self.tile_at(tile_x, tile_y)
        return self.definitions[tile_key].solid

    def is_water_tile(self, tile_x: int, tile_y: int) -> bool:
        """
        Проверяет, является ли тайл водой.
        """
        return self.has_tile_name(tile_x, tile_y, "water")

    def is_tree_tile(self, tile_x: int, tile_y: int) -> bool:
        """
        Проверяет, является ли тайл деревом.
        """
        return self.has_tile_name(tile_x, tile_y, "tree")

    def is_rock_tile(self, tile_x: int, tile_y: int) -> bool:
        """
        Проверяет, является ли тайл камнем для добычи.
        """
        return self.has_tile_name(tile_x, tile_y, "rock")

    def is_mineable_tile(self, tile_x: int, tile_y: int) -> bool:
        """
        Проверяет Mining-тайл.
        """
        if not self.in_bounds(tile_x, tile_y):
            return False
        return self.tile_name_at(tile_x, tile_y) in {"rock", "cave wall"}

    def has_tile_name(self, tile_x: int, tile_y: int, name: str) -> bool:
        """
        Проверяет, имеет ли тайл указанное доменное имя.
        """
        if not self.in_bounds(tile_x, tile_y):
            return False
        return self.tile_name_at(tile_x, tile_y) == name

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
                tile_collision_rect = self.tile_collision_rect(tile_x, tile_y)
                if tile_collision_rect is not None and rect.intersects(tile_collision_rect):
                    return True
        return False


def _tile_map_fingerprint_payload(tile_map: TileMap) -> dict[str, object]:
    return {
        "tile_size": tile_map.tile_size,
        "spawn": [tile_map.spawn.x, tile_map.spawn.y],
        "legend": {
            key: {
                "name": definition.name,
                "solid": definition.solid,
                "color": list(definition.color),
                "sprites": list(definition.sprites),
                "sprite_offset": list(definition.sprite_offset),
                "sprite_offsets": [
                    list(sprite_offset) for sprite_offset in definition.sprite_offsets
                ],
                "collision_rect": (
                    None
                    if definition.collision_rect is None
                    else list(definition.collision_rect)
                ),
            }
            for key, definition in sorted(tile_map.definitions.items())
        },
        "tiles": ["".join(row) for row in tile_map.tiles],
        "entities": [
            _entity_fingerprint_payload(entity)
            for entity in sorted(tile_map.entities, key=lambda item: item.entity_id)
        ],
    }


def _entity_fingerprint_payload(entity: WorldEntity) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": entity.entity_id,
        "identity": {
            "kind": entity.identity.kind.value,
            "name": entity.identity.name,
            "destroyed_name": entity.identity.destroyed_name,
            "visual": entity.identity.visual,
            "destroyed_visual": entity.identity.destroyed_visual,
        },
        "body": {
            "position": [entity.body.position.x, entity.body.position.y],
            "size": [entity.body.width, entity.body.height],
            "solid": entity.body.solid,
            "visible": entity.body.visible,
        },
    }
    if entity.interaction is not None:
        payload["interaction"] = {
            "radius": entity.interaction.radius,
            "dialogue": entity.interaction.dialogue,
        }
    if entity.lootable is not None:
        payload["lootable"] = {
            "reward_item_id": entity.lootable.reward_item_id,
            "reward_quantity": entity.lootable.reward_quantity,
            "success_text": entity.lootable.success_text,
            "claim_policy": entity.lootable.claim_policy.value,
        }
    if entity.combat is not None:
        payload["combat"] = {
            "hit_points": entity.combat.hit_points,
            "max_hit_points": entity.combat.max_hit_points,
            "attackable": entity.combat.attackable,
            "destroyed": entity.combat.destroyed,
            "min_damage": entity.combat.min_damage,
            "max_damage": entity.combat.max_damage,
            "hit_chance": entity.combat.hit_chance,
            "attack_distance": entity.combat.attack_distance,
            "swing_cooldown_seconds": entity.combat.swing_cooldown_seconds,
        }
    if entity.respawn is not None:
        payload["respawn"] = {
            "seconds": entity.respawn.seconds,
            "remaining": entity.respawn.remaining,
        }
    if entity.gate is not None:
        payload["gate"] = {"is_open": entity.gate.is_open}
    if entity.shearable is not None:
        payload["shearable"] = {"has_wool": entity.shearable.has_wool}
    return payload
