from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState


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
    CONNECTION_ACCEPTED = "connection_accepted"
    PLAYER_MOVED = "player_moved"
    CHAT_MESSAGE = "chat_message"
    ENTITY_SPAWNED = "entity_spawned"
    ENTITY_REMOVED = "entity_removed"
    INVENTORY_UPDATED = "inventory_updated"
    ERROR = "error"


class ProtocolError(ValueError):
    """
    Сообщает, что сетевое сообщение не соответствует ожидаемой форме протокола.
    """


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


def encode_message(message: ProtocolMessage) -> str:
    """
    Сериализует протокольное сообщение в компактную JSON-строку.
    """
    return json.dumps(message.to_json_dict(), ensure_ascii=False, separators=(",", ":"))


def decode_message(raw_message: str) -> ProtocolMessage:
    """
    Разбирает JSON-строку в протокольное сообщение и проверяет верхнеуровневую форму.
    """
    try:
        decoded = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        msg = "message is not valid JSON"
        raise ProtocolError(msg) from exc

    if not isinstance(decoded, dict):
        msg = "message must be a JSON object"
        raise ProtocolError(msg)

    message_type = decoded.get("type")
    payload = decoded.get("payload")
    if not isinstance(message_type, str):
        msg = "message type must be a string"
        raise ProtocolError(msg)
    if not isinstance(payload, dict):
        msg = "message payload must be an object"
        raise ProtocolError(msg)

    return ProtocolMessage(type=message_type, payload=payload)


def movement_intent_to_payload(intent: MovementIntent) -> dict[str, Any]:
    """
    Преобразует намерение движения в JSON-готовый payload сообщения.
    """
    return {
        "up": intent.up,
        "down": intent.down,
        "left": intent.left,
        "right": intent.right,
    }


def movement_intent_from_payload(payload: Mapping[str, Any]) -> MovementIntent:
    """
    Создает намерение движения из декодированного payload-а клиентского сообщения.
    """
    return MovementIntent(
        up=_bool_field(payload, "up"),
        down=_bool_field(payload, "down"),
        left=_bool_field(payload, "left"),
        right=_bool_field(payload, "right"),
    )


def player_to_payload(player: PlayerState) -> dict[str, Any]:
    """
    Преобразует состояние игрока в JSON-готовый элемент payload-а snapshot-а.
    """
    return {
        "id": player.entity_id,
        "x": player.position.x,
        "y": player.position.y,
        "width": player.width,
        "height": player.height,
        "speed": player.speed,
    }


def player_from_payload(payload: Mapping[str, Any]) -> PlayerState:
    """
    Создает состояние игрока из одного декодированного элемента payload-а snapshot-а.
    """
    entity_id = payload.get("id")
    if not isinstance(entity_id, str):
        msg = "player id must be a string"
        raise ProtocolError(msg)

    return PlayerState(
        entity_id=entity_id,
        position=Vec2(
            x=_number_field(payload, "x"),
            y=_number_field(payload, "y"),
        ),
        width=int(_number_field(payload, "width")),
        height=int(_number_field(payload, "height")),
        speed=_number_field(payload, "speed"),
    )


def players_from_snapshot_payload(payload: Mapping[str, Any]) -> list[PlayerState]:
    """
    Извлекает состояния игроков из декодированного payload-а snapshot-а мира.
    """
    raw_players = payload.get("players")
    if not isinstance(raw_players, list):
        msg = "world snapshot players must be a list"
        raise ProtocolError(msg)

    players: list[PlayerState] = []
    for raw_player in raw_players:
        if not isinstance(raw_player, dict):
            msg = "world snapshot player item must be an object"
            raise ProtocolError(msg)
        players.append(player_from_payload(raw_player))
    return players


def world_snapshot_payload(players: list[PlayerState]) -> dict[str, Any]:
    """
    Преобразует состояния игроков в JSON-готовый payload snapshot-а мира.
    """
    return {"players": [player_to_payload(player) for player in players]}


def _bool_field(payload: Mapping[str, Any], key: str) -> bool:
    """
    Читает boolean-поле из payload-а сообщения и отклоняет другие типы поля.
    """
    value = payload.get(key, False)
    if not isinstance(value, bool):
        msg = f"{key} must be a boolean"
        raise ProtocolError(msg)
    return value


def _number_field(payload: Mapping[str, Any], key: str) -> float:
    """
    Читает числовое поле из payload-а сообщения и отклоняет другие типы поля.
    """
    value = payload.get(key)
    if not isinstance(value, int | float):
        msg = f"{key} must be a number"
        raise ProtocolError(msg)
    return float(value)
