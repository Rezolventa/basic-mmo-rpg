from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from basic_mmo_rpg.domain.entities import EntityKind, WorldEntity
from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.inventory import ItemStack
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState


class ClientMessageType(StrEnum):
    """
    Перечисляет типы сообщений, которые клиент может отправить серверу.
    """

    JOIN_REQUESTED = "join_requested"
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
    INTERACTION_RESULT = "interaction_result"
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


@dataclass(frozen=True, slots=True)
class PlayerSnapshot:
    """
    Хранит сетевое представление игрока вместе с именем персонажа.
    """

    state: PlayerState
    name: str


@dataclass(frozen=True, slots=True)
class EntitySnapshot:
    """
    Хранит сетевое представление объекта мира.
    """

    state: WorldEntity


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


def join_request_payload(name: str) -> dict[str, Any]:
    """
    Создает payload запроса входа персонажа в мир.
    """
    return {"name": name}


def character_name_from_payload(payload: Mapping[str, Any]) -> str:
    """
    Извлекает и нормализует имя персонажа из payload-а сообщения.
    """
    raw_name = payload.get("name")
    if not isinstance(raw_name, str):
        msg = "character name must be a string"
        raise ProtocolError(msg)

    name = raw_name.strip()
    if not name:
        msg = "character name must not be empty"
        raise ProtocolError(msg)
    if len(name) > 24:
        msg = "character name must be at most 24 characters"
        raise ProtocolError(msg)
    return name


def chat_sent_payload(text: str) -> dict[str, Any]:
    """
    Создает payload клиентского сообщения чата.
    """
    return {"text": text}


def chat_text_from_payload(payload: Mapping[str, Any]) -> str:
    """
    Извлекает и проверяет текст сообщения чата из payload-а.
    """
    raw_text = payload.get("text")
    if not isinstance(raw_text, str):
        msg = "chat text must be a string"
        raise ProtocolError(msg)

    text = raw_text.strip()
    if not text:
        msg = "chat text must not be empty"
        raise ProtocolError(msg)
    if len(text) > 160:
        msg = "chat text must be at most 160 characters"
        raise ProtocolError(msg)
    return text


def chat_message_payload(
    player_id: str,
    name: str,
    text: str,
    created_at: float,
) -> dict[str, Any]:
    """
    Создает payload серверного сообщения чата.
    """
    return {
        "player_id": player_id,
        "name": name,
        "text": text,
        "created_at": created_at,
    }


def interact_requested_payload(target_id: str) -> dict[str, Any]:
    """
    Создает payload клиентского запроса взаимодействия с объектом мира.
    """
    return {"target_id": target_id}


def interaction_target_from_payload(payload: Mapping[str, Any]) -> str:
    """
    Извлекает id цели из payload-а запроса взаимодействия.
    """
    target_id = payload.get("target_id")
    if not isinstance(target_id, str) or not target_id:
        msg = "interaction target_id must be a non-empty string"
        raise ProtocolError(msg)
    return target_id


def interaction_result_payload(
    actor_id: str,
    target_id: str,
    target_name: str,
    text: str,
    created_at: float,
) -> dict[str, Any]:
    """
    Создает payload серверного результата взаимодействия.
    """
    return {
        "actor_id": actor_id,
        "target_id": target_id,
        "target_name": target_name,
        "text": text,
        "created_at": created_at,
    }


def inventory_item_to_payload(item: ItemStack) -> dict[str, Any]:
    """
    Преобразует стак предметов в JSON-готовый элемент payload-а инвентаря.
    """
    return {
        "item_id": item.item_id,
        "display_name": item.display_name,
        "quantity": item.quantity,
    }


def inventory_item_from_payload(payload: Mapping[str, Any]) -> ItemStack:
    """
    Создает стак предметов из одного элемента payload-а инвентаря.
    """
    item_id = payload.get("item_id")
    display_name = payload.get("display_name")
    quantity = payload.get("quantity")
    if not isinstance(item_id, str) or not item_id:
        msg = "inventory item_id must be a non-empty string"
        raise ProtocolError(msg)
    if not isinstance(display_name, str) or not display_name:
        msg = "inventory display_name must be a non-empty string"
        raise ProtocolError(msg)
    if not isinstance(quantity, int) or quantity <= 0:
        msg = "inventory quantity must be a positive integer"
        raise ProtocolError(msg)
    return ItemStack(item_id=item_id, display_name=display_name, quantity=quantity)


def inventory_updated_payload(items: list[ItemStack]) -> dict[str, Any]:
    """
    Создает payload серверного обновления инвентаря.
    """
    return {"items": [inventory_item_to_payload(item) for item in items]}


def inventory_items_from_payload(payload: Mapping[str, Any]) -> list[ItemStack]:
    """
    Извлекает список стаков предметов из payload-а обновления инвентаря.
    """
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        msg = "inventory items must be a list"
        raise ProtocolError(msg)

    items: list[ItemStack] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            msg = "inventory item must be an object"
            raise ProtocolError(msg)
        items.append(inventory_item_from_payload(raw_item))
    return items


def player_to_payload(player: PlayerState, name: str | None = None) -> dict[str, Any]:
    """
    Преобразует состояние игрока в JSON-готовый элемент payload-а snapshot-а.
    """
    return {
        "id": player.entity_id,
        "name": name or player.entity_id,
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


def player_snapshot_to_payload(snapshot: PlayerSnapshot) -> dict[str, Any]:
    """
    Преобразует сетевое представление игрока в payload snapshot-а.
    """
    return player_to_payload(snapshot.state, snapshot.name)


def player_snapshot_from_payload(payload: Mapping[str, Any]) -> PlayerSnapshot:
    """
    Создает сетевое представление игрока из payload-а snapshot-а.
    """
    name = payload.get("name")
    if not isinstance(name, str):
        msg = "player name must be a string"
        raise ProtocolError(msg)
    return PlayerSnapshot(state=player_from_payload(payload), name=name)


def entity_to_payload(entity: WorldEntity) -> dict[str, Any]:
    """
    Преобразует объект мира в JSON-готовый элемент payload-а snapshot-а.
    """
    return {
        "id": entity.entity_id,
        "kind": entity.kind.value,
        "name": entity.name,
        "x": entity.position.x,
        "y": entity.position.y,
        "width": entity.width,
        "height": entity.height,
        "interaction_radius": entity.interaction_radius,
        "solid": entity.solid,
    }


def entity_from_payload(payload: Mapping[str, Any]) -> WorldEntity:
    """
    Создает объект мира из одного декодированного элемента payload-а snapshot-а.
    """
    entity_id = payload.get("id")
    if not isinstance(entity_id, str):
        msg = "entity id must be a string"
        raise ProtocolError(msg)

    raw_kind = payload.get("kind")
    if not isinstance(raw_kind, str):
        msg = "entity kind must be a string"
        raise ProtocolError(msg)
    try:
        kind = EntityKind(raw_kind)
    except ValueError as exc:
        msg = f"unsupported entity kind: {raw_kind!r}"
        raise ProtocolError(msg) from exc

    name = payload.get("name")
    if not isinstance(name, str):
        msg = "entity name must be a string"
        raise ProtocolError(msg)

    return WorldEntity(
        entity_id=entity_id,
        kind=kind,
        name=name,
        position=Vec2(
            x=_number_field(payload, "x"),
            y=_number_field(payload, "y"),
        ),
        width=int(_number_field(payload, "width")),
        height=int(_number_field(payload, "height")),
        interaction_radius=_number_field(payload, "interaction_radius"),
        solid=_bool_field(payload, "solid"),
    )


def entity_snapshot_to_payload(snapshot: EntitySnapshot) -> dict[str, Any]:
    """
    Преобразует сетевое представление объекта мира в payload snapshot-а.
    """
    return entity_to_payload(snapshot.state)


def entity_snapshot_from_payload(payload: Mapping[str, Any]) -> EntitySnapshot:
    """
    Создает сетевое представление объекта мира из payload-а snapshot-а.
    """
    return EntitySnapshot(state=entity_from_payload(payload))


def player_snapshots_from_payload(payload: Mapping[str, Any]) -> list[PlayerSnapshot]:
    """
    Извлекает сетевые представления игроков из payload-а snapshot-а мира.
    """
    raw_players = payload.get("players")
    if not isinstance(raw_players, list):
        msg = "world snapshot players must be a list"
        raise ProtocolError(msg)

    snapshots: list[PlayerSnapshot] = []
    for raw_player in raw_players:
        if not isinstance(raw_player, dict):
            msg = "world snapshot player item must be an object"
            raise ProtocolError(msg)
        snapshots.append(player_snapshot_from_payload(raw_player))
    return snapshots


def entity_snapshots_from_payload(payload: Mapping[str, Any]) -> list[EntitySnapshot]:
    """
    Извлекает сетевые представления объектов мира из payload-а snapshot-а.
    """
    raw_entities = payload.get("entities", [])
    if not isinstance(raw_entities, list):
        msg = "world snapshot entities must be a list"
        raise ProtocolError(msg)

    snapshots: list[EntitySnapshot] = []
    for raw_entity in raw_entities:
        if not isinstance(raw_entity, dict):
            msg = "world snapshot entity item must be an object"
            raise ProtocolError(msg)
        snapshots.append(entity_snapshot_from_payload(raw_entity))
    return snapshots


def players_from_snapshot_payload(payload: Mapping[str, Any]) -> list[PlayerState]:
    """
    Извлекает состояния игроков из декодированного payload-а snapshot-а мира.
    """
    return [snapshot.state for snapshot in player_snapshots_from_payload(payload)]


def entities_from_snapshot_payload(payload: Mapping[str, Any]) -> list[WorldEntity]:
    """
    Извлекает объекты мира из декодированного payload-а snapshot-а.
    """
    return [snapshot.state for snapshot in entity_snapshots_from_payload(payload)]


def world_snapshot_payload(
    players: list[PlayerSnapshot],
    entities: list[EntitySnapshot] | None = None,
) -> dict[str, Any]:
    """
    Преобразует состояния игроков и объектов в JSON-готовый payload snapshot-а мира.
    """
    entity_snapshots = entities or []
    return {
        "players": [player_snapshot_to_payload(player) for player in players],
        "entities": [entity_snapshot_to_payload(entity) for entity in entity_snapshots],
    }


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
