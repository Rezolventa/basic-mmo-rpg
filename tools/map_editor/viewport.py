from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Viewport:
    """
    Хранит смещение видимой области карты в пикселях.
    """

    offset_x: float = 0.0
    offset_y: float = 0.0
    zoom: float = 1.0

    def scroll(
        self,
        delta_x: float,
        delta_y: float,
        *,
        map_width: int,
        map_height: int,
        view_width: int,
        view_height: int,
    ) -> None:
        """
        Сдвигает видимую область и ограничивает ее размерами карты.
        """
        self.offset_x += delta_x / self.zoom
        self.offset_y += delta_y / self.zoom
        self.clamp(
            map_width=map_width,
            map_height=map_height,
            view_width=view_width,
            view_height=view_height,
        )

    def clamp(
        self,
        *,
        map_width: int,
        map_height: int,
        view_width: int,
        view_height: int,
    ) -> None:
        """
        Не дает viewport выйти за пределы карты.
        """
        max_x = max(0.0, map_width - self.visible_world_width(view_width))
        max_y = max(0.0, map_height - self.visible_world_height(view_height))
        self.offset_x = min(max_x, max(0.0, self.offset_x))
        self.offset_y = min(max_y, max(0.0, self.offset_y))

    def set_zoom_around_screen_point(
        self,
        zoom: float,
        screen_x: int,
        screen_y: int,
        *,
        map_width: int,
        map_height: int,
        view_width: int,
        view_height: int,
    ) -> None:
        """
        Меняет масштаб, сохраняя мировую точку под указанной экранной точкой.
        """
        if zoom <= 0:
            msg = "viewport zoom must be positive"
            raise ValueError(msg)
        anchor_world_x, anchor_world_y = self.screen_to_world(screen_x, screen_y)
        self.zoom = zoom
        self.offset_x = anchor_world_x - screen_x / self.zoom
        self.offset_y = anchor_world_y - screen_y / self.zoom
        self.clamp(
            map_width=map_width,
            map_height=map_height,
            view_width=view_width,
            view_height=view_height,
        )

    def visible_world_width(self, view_width: int) -> float:
        """
        Возвращает ширину видимой области в мировых пикселях.
        """
        return view_width / self.zoom

    def visible_world_height(self, view_height: int) -> float:
        """
        Возвращает высоту видимой области в мировых пикселях.
        """
        return view_height / self.zoom

    def screen_to_world(self, x: int, y: int) -> tuple[float, float]:
        """
        Переводит экранные координаты в мировые координаты карты.
        """
        return x / self.zoom + self.offset_x, y / self.zoom + self.offset_y

    def world_to_screen(self, x: float, y: float) -> tuple[int, int]:
        """
        Переводит мировые координаты карты в экранные координаты.
        """
        return round((x - self.offset_x) * self.zoom), round((y - self.offset_y) * self.zoom)
