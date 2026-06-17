from __future__ import annotations

from basic_mmo_rpg.domain.geometry import Rect, Vec2


def test_rect_contains_point_uses_exclusive_right_and_bottom_edges() -> None:
    """
    Проверяет, что hit-test прямоугольника исключает правую и нижнюю границы.
    """
    rect = Rect(10, 20, 30, 40)

    assert rect.contains_point(Vec2(10, 20))
    assert rect.contains_point(Vec2(39.999, 59.999))
    assert not rect.contains_point(Vec2(40, 20))
    assert not rect.contains_point(Vec2(10, 60))
