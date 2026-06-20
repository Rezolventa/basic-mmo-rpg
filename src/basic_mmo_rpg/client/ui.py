from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChatLine:
    """
    Хранит одну строку чата для клиентского журнала.
    """

    player_id: str
    name: str
    text: str
    created_at: float


@dataclass(frozen=True, slots=True)
class TimedText:
    """
    Хранит временный текст, который исчезает после указанного момента.
    """

    text: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class InventoryPanelHit:
    """
    Хранит результат попадания клика в панель инвентаря и paperdoll.
    """

    item_id: str | None = None
    slot: str | None = None
