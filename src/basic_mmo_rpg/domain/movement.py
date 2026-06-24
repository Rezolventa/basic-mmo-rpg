from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from basic_mmo_rpg.domain.geometry import Rect, Vec2
from basic_mmo_rpg.domain.tiles import TileMap


@dataclass(frozen=True, slots=True)
class MovementIntent:
    """
    Описывает намерение игрока двигаться по направлениям.
    """

    up: bool = False
    down: bool = False
    left: bool = False
    right: bool = False

    def as_vector(self) -> Vec2:
        """
        Преобразует набор направлений в нормализованный вектор движения.
        """
        x = int(self.right) - int(self.left)
        y = int(self.down) - int(self.up)
        return Vec2(x, y).normalized()


@dataclass(frozen=True, slots=True)
class PlayerState:
    """
    Хранит доменное состояние игрока, нужное для движения и коллизий.
    """

    entity_id: str
    position: Vec2
    width: int = 22
    height: int = 28
    speed: float = 140.0
    hit_points: int = 30
    max_hit_points: int = 30

    @property
    def rect(self) -> Rect:
        """
        Возвращает прямоугольник игрока в мировых координатах.
        """
        return Rect(self.position.x, self.position.y, self.width, self.height)

    @property
    def center(self) -> Vec2:
        """
        Возвращает центр игрока в мировых координатах.
        """
        return self.rect.center

    @property
    def is_alive(self) -> bool:
        """
        Возвращает, может ли персонаж двигаться и действовать в runtime-мире.
        """
        return self.hit_points > 0


def move_player(
    player: PlayerState,
    intent: MovementIntent,
    delta_seconds: float,
    tile_map: TileMap,
    blockers: Iterable[Rect] = (),
) -> PlayerState:
    """
    Применяет намерение движения игрока с учетом скорости, времени и коллизий.
    """
    direction = intent.as_vector()
    if direction.length == 0 or delta_seconds <= 0:
        return player

    blocker_rects = tuple(blockers)
    distance = direction * (player.speed * delta_seconds)
    position = _move_axis(player, tile_map, Vec2(distance.x, 0), blocker_rects)
    moved_x = PlayerState(
        entity_id=player.entity_id,
        position=position,
        width=player.width,
        height=player.height,
        speed=player.speed,
        hit_points=player.hit_points,
        max_hit_points=player.max_hit_points,
    )
    position = _move_axis(moved_x, tile_map, Vec2(0, distance.y), blocker_rects)

    return PlayerState(
        entity_id=player.entity_id,
        position=position,
        width=player.width,
        height=player.height,
        speed=player.speed,
        hit_points=player.hit_points,
        max_hit_points=player.max_hit_points,
    )


def _move_axis(
    player: PlayerState,
    tile_map: TileMap,
    delta: Vec2,
    blockers: Iterable[Rect],
) -> Vec2:
    """
    Пытается сдвинуть игрока по одной оси и отменяет сдвиг при коллизии.
    """
    target_rect = player.rect.moved(delta)
    if tile_map.is_rect_blocked(target_rect, blockers):
        return player.position
    return player.position + delta
