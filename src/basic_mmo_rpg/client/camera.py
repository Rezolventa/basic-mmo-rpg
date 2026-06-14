from __future__ import annotations

from dataclasses import dataclass

from basic_mmo_rpg.domain.geometry import Vec2


@dataclass(slots=True)
class Camera:
    """
    Хранит смещение камеры и преобразует координаты мира в экранные координаты.
    """

    offset: Vec2 = Vec2(0, 0)

    def follow(self, target: Vec2, viewport_size: Vec2, world_size: Vec2) -> None:
        """
        Перемещает камеру за целью с учетом размеров экрана и границ мира.
        """
        max_x = max(0.0, world_size.x - viewport_size.x)
        max_y = max(0.0, world_size.y - viewport_size.y)
        wanted_x = target.x - viewport_size.x / 2
        wanted_y = target.y - viewport_size.y / 2
        self.offset = Vec2(
            x=min(max(wanted_x, 0.0), max_x),
            y=min(max(wanted_y, 0.0), max_y),
        )

    def world_to_screen(self, position: Vec2) -> tuple[int, int]:
        """
        Переводит мировую позицию в позицию относительно текущего экрана.
        """
        return int(position.x - self.offset.x), int(position.y - self.offset.y)
