from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from basic_mmo_rpg.domain.geometry import Rect, Vec2


class EntityKind(StrEnum):
    """
    Перечисляет типы неигровых сущностей мира.
    """

    NPC = "npc"


@dataclass(frozen=True, slots=True)
class WorldEntity:
    """
    Хранит доменное состояние объекта мира, с которым можно взаимодействовать.
    """

    entity_id: str
    kind: EntityKind
    name: str
    position: Vec2
    width: int
    height: int
    interaction_radius: float = 64.0
    dialogue: str = ""
    solid: bool = True

    @property
    def rect(self) -> Rect:
        """
        Возвращает прямоугольник объекта в мировых координатах.
        """
        return Rect(self.position.x, self.position.y, self.width, self.height)

    @property
    def center(self) -> Vec2:
        """
        Возвращает центр объекта в мировых координатах.
        """
        return self.rect.center
