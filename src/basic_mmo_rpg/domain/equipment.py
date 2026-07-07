from __future__ import annotations

from dataclasses import dataclass

MAIN_HAND_SLOT = "main_hand"
CHEST_SLOT = "chest"
EQUIPMENT_SLOTS = frozenset({MAIN_HAND_SLOT, CHEST_SLOT})


class EquipmentError(ValueError):
    """
    Сообщает о доменной ошибке операции с экипировкой.
    """


@dataclass(frozen=True, slots=True)
class Equipment:
    """
    Хранит экипировку персонажа.
    """

    main_hand: str | None = None
    chest: str | None = None


def validate_equipment_slot(slot: str) -> str:
    """
    Проверяет, что слот экипировки поддерживается текущей моделью.
    """
    if slot not in EQUIPMENT_SLOTS:
        msg = f"unsupported equipment slot: {slot!r}"
        raise EquipmentError(msg)
    return slot
