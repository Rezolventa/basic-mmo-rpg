from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ClientMessageType(StrEnum):
    """
    Перечисляет типы сообщений, которые клиент может отправить серверу.
    """

    MOVE_REQUESTED = "move_requested"
    CHAT_SENT = "chat_sent"
    INTERACT_REQUESTED = "interact_requested"


class ServerMessageType(StrEnum):
    """
    Перечисляет типы сообщений, которые сервер может отправить клиенту.
    """

    WORLD_SNAPSHOT = "world_snapshot"
    PLAYER_MOVED = "player_moved"
    CHAT_MESSAGE = "chat_message"
    ENTITY_SPAWNED = "entity_spawned"
    INVENTORY_UPDATED = "inventory_updated"


@dataclass(frozen=True, slots=True)
class ProtocolMessage:
    """
    Хранит тип и полезную нагрузку сетевого сообщения.
    """

    type: str
    payload: dict[str, Any]

    def to_json_dict(self) -> dict[str, Any]:
        """
        Преобразует сообщение в словарь, пригодный для JSON-сериализации.
        """
        return {"type": self.type, "payload": self.payload}
