from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class EditableEntity:
    """
    Хранит raw JSON entity и дает универсальный доступ к базовым полям редактора.
    """

    raw: dict[str, Any]

    @classmethod
    def from_raw(cls, raw_entity: dict[str, Any]) -> EditableEntity:
        """
        Создает редактируемую entity без привязки к конкретному gameplay-компоненту.
        """
        return cls(raw=copy.deepcopy(raw_entity))

    @property
    def entity_id(self) -> str:
        """
        Возвращает id entity из JSON-карты.
        """
        value = self.raw.get("id", "")
        return value if isinstance(value, str) else ""

    @property
    def kind(self) -> str:
        """
        Возвращает широкую категорию entity.
        """
        identity = self._component("identity")
        if identity is not None:
            value = identity.get("kind", "")
            return value if isinstance(value, str) else ""
        value = self.raw.get("kind", "")
        return value if isinstance(value, str) else ""

    @property
    def name(self) -> str:
        """
        Возвращает отображаемое имя entity.
        """
        identity = self._component("identity")
        if identity is not None:
            value = identity.get("name", "")
            return value if isinstance(value, str) else ""
        value = self.raw.get("name", "")
        return value if isinstance(value, str) else ""

    @property
    def position(self) -> tuple[float, float]:
        """
        Возвращает позицию верхнего левого угла entity в пикселях.
        """
        raw_position = self._body_field("position")
        if (
            isinstance(raw_position, list)
            and len(raw_position) == 2
            and isinstance(raw_position[0], int | float)
            and isinstance(raw_position[1], int | float)
        ):
            return float(raw_position[0]), float(raw_position[1])
        return 0.0, 0.0

    @property
    def size(self) -> tuple[int, int]:
        """
        Возвращает размер entity в пикселях.
        """
        raw_size = self._body_field("size")
        if (
            isinstance(raw_size, list)
            and len(raw_size) == 2
            and isinstance(raw_size[0], int)
            and isinstance(raw_size[1], int)
        ):
            return raw_size[0], raw_size[1]
        return 22, 28

    @property
    def solid(self) -> bool:
        """
        Возвращает, является ли entity препятствием.
        """
        value = self._body_field("solid")
        return value if isinstance(value, bool) else True

    @property
    def visible(self) -> bool:
        """
        Возвращает, видима ли entity по данным карты.
        """
        value = self._body_field("visible")
        return value if isinstance(value, bool) else True

    @property
    def label(self) -> str:
        """
        Возвращает короткую подпись entity для UI редактора.
        """
        if self.name:
            return f"{self.entity_id} ({self.name})"
        return self.entity_id

    def contains_point(self, x: float, y: float) -> bool:
        """
        Проверяет, попадает ли точка в прямоугольник entity.
        """
        left, top = self.position
        width, height = self.size
        return left <= x < left + width and top <= y < top + height

    def set_position(self, x: float, y: float) -> None:
        """
        Записывает новую позицию entity в raw JSON.
        """
        position = [_json_number(x), _json_number(y)]
        body = self._mutable_body_component()
        if body is not None:
            body["position"] = position
            return
        self.raw["position"] = position

    def to_raw(self) -> dict[str, Any]:
        """
        Возвращает JSON-ready копию entity.
        """
        return copy.deepcopy(self.raw)

    def _component(self, key: str) -> dict[str, Any] | None:
        components = self.raw.get("components")
        if not isinstance(components, dict):
            return None
        component = components.get(key)
        return component if isinstance(component, dict) else None

    def _body_field(self, key: str) -> object:
        body = self._component("body")
        if body is not None:
            return body.get(key)
        return self.raw.get(key)

    def _mutable_body_component(self) -> dict[str, Any] | None:
        components = self.raw.get("components")
        if not isinstance(components, dict):
            return None
        body = components.get("body")
        return body if isinstance(body, dict) else None


def _json_number(value: float) -> int | float:
    """
    Возвращает компактное JSON-число для координаты entity.
    """
    rounded = round(value, 3)
    if rounded.is_integer():
        return int(rounded)
    return rounded
