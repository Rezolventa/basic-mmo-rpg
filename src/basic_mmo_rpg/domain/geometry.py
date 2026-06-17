from __future__ import annotations

from dataclasses import dataclass
from math import hypot


@dataclass(frozen=True, slots=True)
class Vec2:
    """
    Представляет двумерный вектор или координату в мире.
    """

    x: float
    y: float

    def __add__(self, other: Vec2) -> Vec2:
        """
        Складывает два двумерных вектора.
        """
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        """
        Вычитает один двумерный вектор из другого.
        """
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vec2:
        """
        Умножает двумерный вектор на скаляр.
        """
        return Vec2(self.x * scalar, self.y * scalar)

    @property
    def length(self) -> float:
        """
        Возвращает длину двумерного вектора.
        """
        return hypot(self.x, self.y)

    def normalized(self) -> Vec2:
        """
        Возвращает нормализованную копию вектора или нулевой вектор.
        """
        length = self.length
        if length == 0:
            return Vec2(0, 0)
        return Vec2(self.x / length, self.y / length)


@dataclass(frozen=True, slots=True)
class Rect:
    """
    Представляет прямоугольник для доменной геометрии и коллизий.
    """

    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        """
        Возвращает левую границу прямоугольника.
        """
        return self.x

    @property
    def right(self) -> float:
        """
        Возвращает правую границу прямоугольника.
        """
        return self.x + self.width

    @property
    def top(self) -> float:
        """
        Возвращает верхнюю границу прямоугольника.
        """
        return self.y

    @property
    def bottom(self) -> float:
        """
        Возвращает нижнюю границу прямоугольника.
        """
        return self.y + self.height

    @property
    def center(self) -> Vec2:
        """
        Возвращает центр прямоугольника.
        """
        return Vec2(self.x + self.width / 2, self.y + self.height / 2)

    def moved(self, delta: Vec2) -> Rect:
        """
        Возвращает копию прямоугольника, смещенную на заданный вектор.
        """
        return Rect(self.x + delta.x, self.y + delta.y, self.width, self.height)

    def intersects(self, other: Rect) -> bool:
        """
        Проверяет, пересекается ли прямоугольник с другим прямоугольником.
        """
        return (
            self.left < other.right
            and self.right > other.left
            and self.top < other.bottom
            and self.bottom > other.top
        )

    def contains_point(self, point: Vec2) -> bool:
        """
        Проверяет, находится ли точка внутри прямоугольника.
        """
        return self.left <= point.x < self.right and self.top <= point.y < self.bottom

    def to_pygame(self) -> tuple[int, int, int, int]:
        """
        Преобразует прямоугольник в кортеж координат для pygame.
        """
        return int(self.x), int(self.y), int(self.width), int(self.height)
