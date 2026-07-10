from __future__ import annotations

import pytest

from basic_mmo_rpg.domain.skills import (
    DEMO_SKILL_CAP,
    apply_skill_gain,
    fishing_action_seconds,
    fishing_success_chance,
    healing_action_seconds,
    healing_max_points,
    healing_min_points,
    healing_success_chance,
    lumberjacking_double_log_chance,
    lumberjacking_success_chance,
    mining_iron_ore_chance,
    mining_success_chance,
    skill_gain_chance,
    tailoring_cloth_success_chance,
)


def test_mining_formula_scales_success_and_ore_chance() -> None:
    """
    Проверяет ключевые точки формулы Mining для успеха и железной руды.
    """
    assert mining_success_chance(0) == pytest.approx(0.2)
    assert mining_success_chance(DEMO_SKILL_CAP) == pytest.approx(0.7)
    assert mining_iron_ore_chance(199) == pytest.approx(0.0)
    assert mining_iron_ore_chance(200) == pytest.approx(0.1)
    assert mining_iron_ore_chance(DEMO_SKILL_CAP) == pytest.approx(0.5)


def test_lumberjacking_formula_scales_success_and_double_drop() -> None:
    """
    Проверяет ключевые точки формулы Lumberjacking.
    """
    assert lumberjacking_success_chance(0) == pytest.approx(0.3)
    assert lumberjacking_success_chance(DEMO_SKILL_CAP) == pytest.approx(0.8)
    assert lumberjacking_double_log_chance(149) == pytest.approx(0.0)
    assert lumberjacking_double_log_chance(150) == pytest.approx(0.1)
    assert lumberjacking_double_log_chance(DEMO_SKILL_CAP) == pytest.approx(0.5)


def test_fishing_formula_scales_success_and_action_speed() -> None:
    """
    Проверяет ключевые точки формулы Fishing.
    """
    assert fishing_success_chance(0) == pytest.approx(0.3)
    assert fishing_success_chance(DEMO_SKILL_CAP) == pytest.approx(0.8)
    assert fishing_action_seconds(150) == pytest.approx(2.0)
    assert fishing_action_seconds(DEMO_SKILL_CAP) == pytest.approx(1.5)


def test_tailoring_formula_scales_cloth_success() -> None:
    """
    Проверяет ключевые точки формулы Tailoring для ткани.
    """
    assert tailoring_cloth_success_chance(0) == pytest.approx(0.5)
    assert tailoring_cloth_success_chance(150) == pytest.approx(0.5)
    assert tailoring_cloth_success_chance(DEMO_SKILL_CAP) == pytest.approx(1.0)


def test_healing_formula_scales_bandage_use() -> None:
    """
    Проверяет шанс, скорость и границы лечения бинтом.
    """
    assert healing_success_chance(0) == pytest.approx(0.3)
    assert healing_success_chance(150) == pytest.approx(0.3)
    assert healing_success_chance(DEMO_SKILL_CAP) == pytest.approx(0.8)
    assert healing_action_seconds(150) == pytest.approx(2.0)
    assert healing_action_seconds(DEMO_SKILL_CAP) == pytest.approx(1.5)
    assert healing_min_points(99) == 1
    assert healing_min_points(100) == 2
    assert healing_min_points(DEMO_SKILL_CAP) == 5
    assert healing_max_points(99) == 3
    assert healing_max_points(100) == 6
    assert healing_max_points(150) == 8
    assert healing_max_points(200) == 10
    assert healing_max_points(250) == 12
    assert healing_max_points(300) == 15
    assert healing_max_points(DEMO_SKILL_CAP) == 15


def test_skill_gain_chance_and_cap() -> None:
    """
    Проверяет шанс прокачки и демо-ограничение 40.0%.
    """
    assert skill_gain_chance(0) == pytest.approx(1.0)
    assert skill_gain_chance(150) == pytest.approx(1.0)
    assert skill_gain_chance(399) == pytest.approx(0.25)
    assert skill_gain_chance(DEMO_SKILL_CAP) == pytest.approx(0.0)
    assert apply_skill_gain(399) == DEMO_SKILL_CAP
    assert apply_skill_gain(DEMO_SKILL_CAP) == DEMO_SKILL_CAP
