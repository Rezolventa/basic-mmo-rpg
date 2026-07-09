from __future__ import annotations

from dataclasses import dataclass

MINING_SKILL_ID = "mining"
LUMBERJACKING_SKILL_ID = "lumberjacking"
FISHING_SKILL_ID = "fishing"

SKILL_VALUE_MIN = 0
SKILL_VALUE_MAX = 1000
DEMO_SKILL_CAP = 400
INITIAL_SKILL_MIN = 0
INITIAL_SKILL_MAX = 99
SKILL_GAIN_STEP = 1
FULL_SPEED_SKILL_VALUE = 150
GAIN_SLOWDOWN_START = 150
GAIN_SLOWDOWN_END = 399


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    """
    Описывает неизменяемые свойства игрового скилла персонажа.
    """

    skill_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class CharacterSkill:
    """
    Хранит значение скилла персонажа в десятых долях процента.
    """

    skill_id: str
    display_name: str
    value_tenths: int

    @property
    def percent(self) -> float:
        """
        Возвращает значение скилла как процент с одной десятичной долей.
        """
        return self.value_tenths / 10


SKILL_DEFINITIONS: tuple[SkillDefinition, ...] = (
    SkillDefinition(skill_id=MINING_SKILL_ID, display_name="Горное дело"),
    SkillDefinition(skill_id=LUMBERJACKING_SKILL_ID, display_name="Рубка леса"),
    SkillDefinition(skill_id=FISHING_SKILL_ID, display_name="Рыбалка"),
)
SKILL_DEFINITIONS_BY_ID = {
    definition.skill_id: definition for definition in SKILL_DEFINITIONS
}


def skill_definition_for(skill_id: str) -> SkillDefinition:
    """
    Возвращает описание скилла по id.
    """
    try:
        return SKILL_DEFINITIONS_BY_ID[skill_id]
    except KeyError as exc:
        msg = f"unknown skill id: {skill_id!r}"
        raise ValueError(msg) from exc


def character_skill_for(skill_id: str, value_tenths: int) -> CharacterSkill:
    """
    Создает отображаемое состояние скилла персонажа.
    """
    definition = skill_definition_for(skill_id)
    return CharacterSkill(
        skill_id=definition.skill_id,
        display_name=definition.display_name,
        value_tenths=validate_skill_value(value_tenths),
    )


def validate_skill_value(value_tenths: int) -> int:
    """
    Проверяет, что значение скилла находится в общем диапазоне 0.0%-100.0%.
    """
    if value_tenths < SKILL_VALUE_MIN or value_tenths > SKILL_VALUE_MAX:
        msg = f"skill value must be between {SKILL_VALUE_MIN} and {SKILL_VALUE_MAX}"
        raise ValueError(msg)
    return value_tenths


def format_skill_percent(value_tenths: int) -> str:
    """
    Форматирует значение скилла для игровых сообщений.
    """
    return f"{value_tenths / 10:.1f}%"


def mining_success_chance(value_tenths: int) -> float:
    """
    Возвращает шанс успешной добычи из rock-тайла для Mining.
    """
    failure_chance = _linear_by_demo_cap(value_tenths, start=0.8, end=0.3)
    return 1.0 - failure_chance


def mining_iron_ore_chance(value_tenths: int) -> float:
    """
    Возвращает шанс железной руды при успешной добыче Mining.
    """
    effective_value = min(value_tenths, DEMO_SKILL_CAP)
    if effective_value < 200:
        return 0.0
    return _linear(
        value=effective_value,
        start_value=200,
        end_value=DEMO_SKILL_CAP,
        start_result=0.1,
        end_result=0.5,
    )


def lumberjacking_success_chance(value_tenths: int) -> float:
    """
    Возвращает шанс успешной рубки дерева для Lumberjacking.
    """
    failure_chance = _linear_by_demo_cap(value_tenths, start=0.7, end=0.2)
    return 1.0 - failure_chance


def lumberjacking_double_log_chance(value_tenths: int) -> float:
    """
    Возвращает шанс получить два бревна при успешной рубке.
    """
    effective_value = min(value_tenths, DEMO_SKILL_CAP)
    if effective_value < FULL_SPEED_SKILL_VALUE:
        return 0.0
    return _linear(
        value=effective_value,
        start_value=FULL_SPEED_SKILL_VALUE,
        end_value=DEMO_SKILL_CAP,
        start_result=0.1,
        end_result=0.5,
    )


def fishing_success_chance(value_tenths: int) -> float:
    """
    Возвращает шанс успешной рыбалки для Fishing.
    """
    failure_chance = _linear_by_demo_cap(value_tenths, start=0.7, end=0.2)
    return 1.0 - failure_chance


def fishing_action_seconds(value_tenths: int) -> float:
    """
    Возвращает длительность подготовки рыбалки с учетом Fishing.
    """
    effective_value = min(value_tenths, DEMO_SKILL_CAP)
    if effective_value <= FULL_SPEED_SKILL_VALUE:
        return 2.0
    return _linear(
        value=effective_value,
        start_value=FULL_SPEED_SKILL_VALUE,
        end_value=DEMO_SKILL_CAP,
        start_result=2.0,
        end_result=1.5,
    )


def skill_gain_chance(value_tenths: int) -> float:
    """
    Возвращает шанс роста скилла после валидного применения.
    """
    if value_tenths >= DEMO_SKILL_CAP:
        return 0.0
    if value_tenths <= GAIN_SLOWDOWN_START:
        return 1.0
    return _linear(
        value=value_tenths,
        start_value=GAIN_SLOWDOWN_START,
        end_value=GAIN_SLOWDOWN_END,
        start_result=1.0,
        end_result=0.25,
    )


def apply_skill_gain(value_tenths: int, gain_tenths: int = SKILL_GAIN_STEP) -> int:
    """
    Применяет прирост скилла с демо-ограничением 40.0%.
    """
    validate_skill_value(value_tenths)
    if gain_tenths < 0:
        msg = "skill gain must be non-negative"
        raise ValueError(msg)
    return min(DEMO_SKILL_CAP, value_tenths + gain_tenths)


def _linear_by_demo_cap(value_tenths: int, start: float, end: float) -> float:
    effective_value = min(max(value_tenths, SKILL_VALUE_MIN), DEMO_SKILL_CAP)
    return _linear(
        value=effective_value,
        start_value=SKILL_VALUE_MIN,
        end_value=DEMO_SKILL_CAP,
        start_result=start,
        end_result=end,
    )


def _linear(
    value: int,
    start_value: int,
    end_value: int,
    start_result: float,
    end_result: float,
) -> float:
    if end_value <= start_value:
        msg = "linear range end must be greater than start"
        raise ValueError(msg)
    clamped = min(max(value, start_value), end_value)
    progress = (clamped - start_value) / (end_value - start_value)
    return start_result + (end_result - start_result) * progress
