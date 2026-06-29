from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from basic_mmo_rpg.domain.entities import (
    BodyComponent,
    CombatComponent,
    EntityKind,
    GateComponent,
    IdentityComponent,
    InteractionComponent,
    LootableComponent,
    LootClaimPolicy,
    RespawnComponent,
    ShearableComponent,
    WorldEntity,
)
from basic_mmo_rpg.domain.equipment import MAIN_HAND_SLOT, Equipment, validate_equipment_slot
from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.inventory import ItemStack
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState
from basic_mmo_rpg.domain.tiles import TileDefinition, TileMap

INTERACTION_PRESENTATION_BUBBLE = "bubble"
INTERACTION_PRESENTATION_FEED = "feed"
INTERACTION_PRESENTATIONS = frozenset(
    {
        INTERACTION_PRESENTATION_BUBBLE,
        INTERACTION_PRESENTATION_FEED,
    }
)


class ClientMessageType(StrEnum):
    """
    Перечисляет типы сообщений, которые клиент может отправить серверу.
    """

    JOIN_REQUESTED = "join_requested"
    MOVE_REQUESTED = "move_requested"
    CHAT_SENT = "chat_sent"
    INTERACT_REQUESTED = "interact_requested"
    EQUIP_ITEM_REQUESTED = "equip_item_requested"
    UNEQUIP_ITEM_REQUESTED = "unequip_item_requested"
    ATTACK_REQUESTED = "attack_requested"
    STOP_ATTACK_REQUESTED = "stop_attack_requested"
    RESPAWN_REQUESTED = "respawn_requested"


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
    EQUIPMENT_UPDATED = "equipment_updated"
    COMBAT_EVENT = "combat_event"
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


@dataclass(frozen=True, slots=True)
class InteractionTarget:
    """
    Хранит цель клиентского запроса взаимодействия.
    """

    entity_id: str | None = None
    tile: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class AttackTarget:
    """
    Хранит цель клиентского запроса атаки.
    """

    entity_id: str


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


def join_request_payload(name: str, map_fingerprint: str | None = None) -> dict[str, Any]:
    """
    Создает payload запроса входа персонажа в мир.
    """
    payload: dict[str, Any] = {"name": name}
    if map_fingerprint is not None:
        payload["map_fingerprint"] = map_fingerprint
    return payload


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


def map_fingerprint_from_payload(payload: Mapping[str, Any]) -> str | None:
    """
    Извлекает необязательный отпечаток карты из join_requested payload-а.
    """
    raw_fingerprint = payload.get("map_fingerprint")
    if raw_fingerprint is None:
        return None
    if not isinstance(raw_fingerprint, str) or not raw_fingerprint.strip():
        msg = "map_fingerprint must be a non-empty string"
        raise ProtocolError(msg)
    return raw_fingerprint.strip()


def tile_map_to_payload(tile_map: TileMap) -> dict[str, Any]:
    """
    Преобразует карту сервера в JSON-готовый payload для клиента.
    """
    return {
        "tile_size": tile_map.tile_size,
        "spawn": [tile_map.spawn.x, tile_map.spawn.y],
        "legend": {
            key: {
                "name": definition.name,
                "solid": definition.solid,
                "color": list(definition.color),
            }
            for key, definition in tile_map.definitions.items()
        },
        "tiles": ["".join(row) for row in tile_map.tiles],
        "entities": [entity_to_payload(entity) for entity in tile_map.entities],
    }


def tile_map_from_payload(payload: Mapping[str, Any]) -> TileMap:
    """
    Восстанавливает карту клиента из payload-а, присланного сервером.
    """
    tile_size = _positive_int_field(payload, "tile_size")
    spawn = _vec2_from_payload(payload.get("spawn"), "map spawn")
    raw_legend = payload.get("legend")
    if not isinstance(raw_legend, Mapping):
        msg = "map legend must be an object"
        raise ProtocolError(msg)
    definitions: dict[str, TileDefinition] = {}
    for key, value in raw_legend.items():
        tile_key = _tile_key(key)
        definition_payload = _map_payload(value, "tile definition")
        definitions[tile_key] = TileDefinition(
            key=tile_key,
            name=_string_field(definition_payload, "name"),
            solid=_bool_field(definition_payload, "solid"),
            color=_color_from_payload(definition_payload.get("color")),
        )

    raw_tiles = payload.get("tiles")
    if not isinstance(raw_tiles, list):
        msg = "map tiles must be a list"
        raise ProtocolError(msg)
    tiles: list[tuple[str, ...]] = []
    for row in raw_tiles:
        if not isinstance(row, str) or not row:
            msg = "map tile rows must be non-empty strings"
            raise ProtocolError(msg)
        tiles.append(tuple(row))

    raw_entities = payload.get("entities", [])
    if not isinstance(raw_entities, list):
        msg = "map entities must be a list"
        raise ProtocolError(msg)
    entities = tuple(
        entity_from_payload(_map_payload(entity, "map entity"))
        for entity in raw_entities
    )

    return TileMap(
        tile_size=tile_size,
        tiles=tuple(tiles),
        definitions=definitions,
        spawn=spawn,
        entities=entities,
    )


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


def interact_tile_requested_payload(tile_x: int, tile_y: int) -> dict[str, Any]:
    """
    Создает payload клиентского запроса взаимодействия с тайлом карты.
    """
    return {"target_tile": [tile_x, tile_y]}


def interaction_target_from_payload(payload: Mapping[str, Any]) -> InteractionTarget:
    """
    Извлекает цель из payload-а запроса взаимодействия.
    """
    target_id = payload.get("target_id")
    target_tile = payload.get("target_tile")

    if target_id is not None and target_tile is not None:
        msg = "interaction target must contain only one target"
        raise ProtocolError(msg)
    if target_id is not None:
        if not isinstance(target_id, str) or not target_id:
            msg = "interaction target_id must be a non-empty string"
            raise ProtocolError(msg)
        return InteractionTarget(entity_id=target_id)
    if target_tile is not None:
        return InteractionTarget(tile=_tile_from_payload(target_tile))

    msg = "interaction target is required"
    raise ProtocolError(msg)


def attack_requested_payload(target_id: str) -> dict[str, Any]:
    """
    Создает payload клиентского запроса атаки объекта мира.
    """
    return {"target_id": target_id}


def attack_target_from_payload(payload: Mapping[str, Any]) -> AttackTarget:
    """
    Извлекает цель из payload-а запроса атаки.
    """
    target_id = payload.get("target_id")
    if not isinstance(target_id, str) or not target_id:
        msg = "attack target_id must be a non-empty string"
        raise ProtocolError(msg)
    return AttackTarget(entity_id=target_id)


def stop_attack_requested_payload() -> dict[str, Any]:
    """
    Создает payload клиентского запроса остановки auto-attack.
    """
    return {}


def respawn_requested_payload() -> dict[str, Any]:
    """
    Создает payload клиентского запроса возрождения персонажа.
    """
    return {}


def interaction_result_payload(
    actor_id: str,
    target_id: str,
    target_name: str,
    text: str,
    created_at: float,
    add_to_journal: bool = True,
    presentation: str = INTERACTION_PRESENTATION_BUBBLE,
) -> dict[str, Any]:
    """
    Создает payload серверного результата взаимодействия.
    """
    if presentation not in INTERACTION_PRESENTATIONS:
        msg = f"unsupported interaction presentation: {presentation!r}"
        raise ValueError(msg)
    return {
        "actor_id": actor_id,
        "target_id": target_id,
        "target_name": target_name,
        "text": text,
        "created_at": created_at,
        "add_to_journal": add_to_journal,
        "presentation": presentation,
    }


def interaction_presentation_from_payload(payload: Mapping[str, Any]) -> str:
    """
    Извлекает способ отображения результата взаимодействия.
    """
    presentation = payload.get("presentation", INTERACTION_PRESENTATION_BUBBLE)
    if not isinstance(presentation, str) or presentation not in INTERACTION_PRESENTATIONS:
        msg = "interaction presentation must be 'bubble' or 'feed'"
        raise ProtocolError(msg)
    return presentation


def combat_event_payload(
    actor_id: str,
    actor_name: str,
    target_id: str,
    target_name: str,
    text: str,
    floating_text: str,
    created_at: float,
    add_to_journal: bool = True,
    destroyed: bool = False,
) -> dict[str, Any]:
    """
    Создает payload серверного события боя.
    """
    return {
        "actor_id": actor_id,
        "actor_name": actor_name,
        "target_id": target_id,
        "target_name": target_name,
        "text": text,
        "floating_text": floating_text,
        "created_at": created_at,
        "add_to_journal": add_to_journal,
        "destroyed": destroyed,
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


def equip_item_requested_payload(item_id: str) -> dict[str, Any]:
    """
    Создает payload клиентского запроса экипировки предмета.
    """
    return {"item_id": item_id}


def equip_item_id_from_payload(payload: Mapping[str, Any]) -> str:
    """
    Извлекает item_id из payload-а запроса экипировки.
    """
    item_id = payload.get("item_id")
    if not isinstance(item_id, str) or not item_id:
        msg = "equipment item_id must be a non-empty string"
        raise ProtocolError(msg)
    return item_id


def unequip_item_requested_payload(slot: str = MAIN_HAND_SLOT) -> dict[str, Any]:
    """
    Создает payload клиентского запроса снятия предмета из слота.
    """
    return {"slot": slot}


def equipment_slot_from_payload(payload: Mapping[str, Any]) -> str:
    """
    Извлекает и проверяет слот экипировки из payload-а.
    """
    slot = payload.get("slot")
    if not isinstance(slot, str):
        msg = "equipment slot must be a string"
        raise ProtocolError(msg)
    try:
        return validate_equipment_slot(slot)
    except ValueError as exc:
        msg = str(exc)
        raise ProtocolError(msg) from exc


def equipment_updated_payload(equipment: Equipment) -> dict[str, Any]:
    """
    Создает payload серверного обновления экипировки.
    """
    return {"main_hand": equipment.main_hand}


def equipment_from_payload(payload: Mapping[str, Any]) -> Equipment:
    """
    Создает экипировку из payload-а серверного обновления.
    """
    main_hand = payload.get("main_hand")
    if main_hand is not None and (not isinstance(main_hand, str) or not main_hand):
        msg = "equipment main_hand must be a non-empty string or null"
        raise ProtocolError(msg)
    return Equipment(main_hand=main_hand)


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
        "hit_points": player.hit_points,
        "max_hit_points": player.max_hit_points,
        "busy": player.busy,
        "action": player.action,
    }


def player_from_payload(payload: Mapping[str, Any]) -> PlayerState:
    """
    Создает состояние игрока из одного декодированного элемента payload-а snapshot-а.
    """
    entity_id = payload.get("id")
    if not isinstance(entity_id, str):
        msg = "player id must be a string"
        raise ProtocolError(msg)

    hit_points = _optional_int_field(payload, "hit_points")
    max_hit_points = _optional_int_field(payload, "max_hit_points")
    if hit_points is None:
        hit_points = 30
    if max_hit_points is None:
        max_hit_points = 30
    if hit_points < 0:
        msg = "player hit_points must be non-negative"
        raise ProtocolError(msg)
    if max_hit_points <= 0:
        msg = "player max_hit_points must be positive"
        raise ProtocolError(msg)
    if hit_points > max_hit_points:
        msg = "player hit_points must not exceed max_hit_points"
        raise ProtocolError(msg)
    busy = _optional_bool_field(payload, "busy")
    action = _optional_string_field(payload, "action")

    return PlayerState(
        entity_id=entity_id,
        position=Vec2(
            x=_number_field(payload, "x"),
            y=_number_field(payload, "y"),
        ),
        width=int(_number_field(payload, "width")),
        height=int(_number_field(payload, "height")),
        speed=_number_field(payload, "speed"),
        hit_points=hit_points,
        max_hit_points=max_hit_points,
        busy=busy if busy is not None else False,
        action=action,
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
    Преобразует объект мира в JSON-готовый component-based элемент snapshot-а.
    """
    components: dict[str, Any] = {
        "identity": {
            "kind": entity.identity.kind.value,
            "name": entity.identity.name,
        },
        "body": {
            "position": [entity.body.position.x, entity.body.position.y],
            "size": [entity.body.width, entity.body.height],
            "solid": entity.body.solid,
            "visible": entity.body.visible,
        },
    }
    if entity.identity.destroyed_name is not None:
        components["identity"]["destroyed_name"] = entity.identity.destroyed_name
    if entity.identity.visual:
        components["identity"]["visual"] = entity.identity.visual
    if entity.interaction is not None:
        components["interaction"] = {
            "radius": entity.interaction.radius,
            "dialogue": entity.interaction.dialogue,
        }
    if entity.lootable is not None:
        components["lootable"] = {
            "reward_item_id": entity.lootable.reward_item_id,
            "reward_quantity": entity.lootable.reward_quantity,
            "success_text": entity.lootable.success_text,
            "claim_policy": entity.lootable.claim_policy.value,
        }
    if entity.combat is not None:
        components["combat"] = {
            "hit_points": entity.combat.hit_points,
            "max_hit_points": entity.combat.max_hit_points,
            "attackable": entity.combat.attackable,
            "destroyed": entity.combat.destroyed,
            "min_damage": entity.combat.min_damage,
            "max_damage": entity.combat.max_damage,
            "hit_chance": entity.combat.hit_chance,
            "attack_distance": entity.combat.attack_distance,
            "swing_cooldown_seconds": entity.combat.swing_cooldown_seconds,
        }
    if entity.respawn is not None:
        components["respawn"] = {
            "seconds": entity.respawn.seconds,
            "remaining": entity.respawn.remaining,
        }
    if entity.gate is not None:
        components["gate"] = {"is_open": entity.gate.is_open}
    if entity.shearable is not None:
        components["shearable"] = {"has_wool": entity.shearable.has_wool}
    return {"id": entity.entity_id, "components": components}


def entity_from_payload(payload: Mapping[str, Any]) -> WorldEntity:
    """
    Создает объект мира из одного декодированного элемента payload-а snapshot-а.
    """
    entity_id = payload.get("id")
    if not isinstance(entity_id, str):
        msg = "entity id must be a string"
        raise ProtocolError(msg)

    raw_components = payload.get("components")
    if raw_components is not None:
        if not isinstance(raw_components, Mapping):
            msg = "entity components must be an object"
            raise ProtocolError(msg)
        return _component_entity_from_payload(entity_id, raw_components)

    return _legacy_entity_from_payload(entity_id, payload)


def _component_entity_from_payload(
    entity_id: str,
    raw_components: Mapping[str, Any],
) -> WorldEntity:
    """
    Создает объект мира из component-based payload-а snapshot-а.
    """
    return WorldEntity(
        entity_id=entity_id,
        identity=_identity_component_from_payload(
            _required_component_payload(raw_components, "identity")
        ),
        body=_body_component_from_payload(_required_component_payload(raw_components, "body")),
        interaction=_optional_interaction_component_from_payload(
            raw_components.get("interaction")
        ),
        lootable=_optional_lootable_component_from_payload(raw_components.get("lootable")),
        combat=_optional_combat_component_from_payload(raw_components.get("combat")),
        respawn=_optional_respawn_component_from_payload(raw_components.get("respawn")),
        gate=_optional_gate_component_from_payload(raw_components.get("gate")),
        shearable=_optional_shearable_component_from_payload(raw_components.get("shearable")),
    )


def _legacy_entity_from_payload(
    entity_id: str,
    payload: Mapping[str, Any],
) -> WorldEntity:
    """
    Создает объект мира из старого плоского payload-а snapshot-а.
    """
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
        is_open=_optional_bool_field(payload, "is_open"),
        hit_points=_optional_int_field(payload, "hit_points"),
        max_hit_points=_optional_int_field(payload, "max_hit_points"),
        has_wool=_optional_bool_field(payload, "has_wool"),
    )


def _identity_component_from_payload(payload: Mapping[str, Any]) -> IdentityComponent:
    """
    Создает identity-компонент из payload-а snapshot-а.
    """
    raw_kind = payload.get("kind")
    if not isinstance(raw_kind, str):
        msg = "entity kind must be a string"
        raise ProtocolError(msg)
    try:
        kind = EntityKind(raw_kind)
    except ValueError as exc:
        msg = f"unsupported entity kind: {raw_kind!r}"
        raise ProtocolError(msg) from exc
    return IdentityComponent(
        kind=kind,
        name=_string_field(payload, "name"),
        destroyed_name=_optional_string_field(payload, "destroyed_name"),
        visual=_optional_string_field(payload, "visual") or "",
    )


def _body_component_from_payload(payload: Mapping[str, Any]) -> BodyComponent:
    """
    Создает body-компонент из payload-а snapshot-а.
    """
    position = _vec2_from_payload(payload.get("position"), "body position")
    width, height = _size_from_payload(payload.get("size"), "body size")
    visible = payload.get("visible", True)
    if not isinstance(visible, bool):
        msg = "body visible must be a boolean"
        raise ProtocolError(msg)
    return BodyComponent(
        position=position,
        width=width,
        height=height,
        solid=_bool_field(payload, "solid"),
        visible=visible,
    )


def _optional_interaction_component_from_payload(
    raw_component: Any,
) -> InteractionComponent | None:
    """
    Создает необязательный interaction-компонент из payload-а snapshot-а.
    """
    if raw_component is None:
        return None
    payload = _component_payload(raw_component, "interaction")
    dialogue = payload.get("dialogue", "")
    if not isinstance(dialogue, str):
        msg = "dialogue must be a string"
        raise ProtocolError(msg)
    return InteractionComponent(
        radius=_number_field(payload, "radius"),
        dialogue=dialogue,
    )


def _optional_lootable_component_from_payload(raw_component: Any) -> LootableComponent | None:
    """
    Создает необязательный lootable-компонент из payload-а snapshot-а.
    """
    if raw_component is None:
        return None
    payload = _component_payload(raw_component, "lootable")
    raw_policy = payload.get("claim_policy")
    if not isinstance(raw_policy, str):
        msg = "lootable claim_policy must be a string"
        raise ProtocolError(msg)
    try:
        claim_policy = LootClaimPolicy(raw_policy)
    except ValueError as exc:
        msg = f"unsupported lootable claim_policy: {raw_policy!r}"
        raise ProtocolError(msg) from exc
    return LootableComponent(
        reward_item_id=_string_field(payload, "reward_item_id"),
        reward_quantity=_positive_int_field(payload, "reward_quantity"),
        success_text=_string_field(payload, "success_text"),
        claim_policy=claim_policy,
    )


def _optional_combat_component_from_payload(raw_component: Any) -> CombatComponent | None:
    """
    Создает необязательный combat-компонент из payload-а snapshot-а.
    """
    if raw_component is None:
        return None
    payload = _component_payload(raw_component, "combat")
    min_damage = _optional_int_field(payload, "min_damage")
    max_damage = _optional_int_field(payload, "max_damage")
    hit_chance = _optional_number_field(payload, "hit_chance", 0.85)
    attack_distance = _optional_number_field(payload, "attack_distance", 64.0)
    swing_cooldown = _optional_number_field(payload, "swing_cooldown_seconds", 1.5)
    min_damage = 0 if min_damage is None else min_damage
    max_damage = 0 if max_damage is None else max_damage
    if min_damage < 0 or max_damage < 0 or max_damage < min_damage:
        msg = "combat damage range must be non-negative and ordered"
        raise ProtocolError(msg)
    if not 0.0 <= hit_chance <= 1.0:
        msg = "combat hit_chance must be between 0 and 1"
        raise ProtocolError(msg)
    if attack_distance <= 0:
        msg = "combat attack_distance must be positive"
        raise ProtocolError(msg)
    if swing_cooldown <= 0:
        msg = "combat swing_cooldown_seconds must be positive"
        raise ProtocolError(msg)
    return CombatComponent(
        hit_points=_non_negative_int_field(payload, "hit_points"),
        max_hit_points=_positive_int_field(payload, "max_hit_points"),
        attackable=_bool_field(payload, "attackable"),
        destroyed=_bool_field(payload, "destroyed"),
        min_damage=min_damage,
        max_damage=max_damage,
        hit_chance=hit_chance,
        attack_distance=attack_distance,
        swing_cooldown_seconds=swing_cooldown,
    )


def _optional_respawn_component_from_payload(raw_component: Any) -> RespawnComponent | None:
    """
    Создает необязательный respawn-компонент из payload-а snapshot-а.
    """
    if raw_component is None:
        return None
    payload = _component_payload(raw_component, "respawn")
    return RespawnComponent(
        seconds=_number_field(payload, "seconds"),
        remaining=_number_field(payload, "remaining"),
    )


def _optional_gate_component_from_payload(raw_component: Any) -> GateComponent | None:
    """
    Создает необязательный gate-компонент из payload-а snapshot-а.
    """
    if raw_component is None:
        return None
    payload = _component_payload(raw_component, "gate")
    return GateComponent(is_open=_bool_field(payload, "is_open"))


def _optional_shearable_component_from_payload(raw_component: Any) -> ShearableComponent | None:
    """
    Создает необязательный shearable-компонент из payload-а snapshot-а.
    """
    if raw_component is None:
        return None
    payload = _component_payload(raw_component, "shearable")
    return ShearableComponent(has_wool=_bool_field(payload, "has_wool"))


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


def _tile_key(raw_key: object) -> str:
    if not isinstance(raw_key, str) or not raw_key:
        msg = "map tile key must be a non-empty string"
        raise ProtocolError(msg)
    return raw_key


def _map_payload(raw_payload: object, name: str) -> Mapping[str, Any]:
    if not isinstance(raw_payload, Mapping):
        msg = f"{name} must be an object"
        raise ProtocolError(msg)
    return raw_payload


def _color_from_payload(raw_color: object) -> tuple[int, int, int]:
    if not isinstance(raw_color, list) or len(raw_color) != 3:
        msg = "map tile color must be a three-item list"
        raise ProtocolError(msg)

    channels: list[int] = []
    for channel in raw_color:
        if not isinstance(channel, int) or isinstance(channel, bool):
            msg = "map tile color channels must be integers"
            raise ProtocolError(msg)
        if channel < 0 or channel > 255:
            msg = "map tile color channels must be between 0 and 255"
            raise ProtocolError(msg)
        channels.append(channel)
    return channels[0], channels[1], channels[2]


def _required_component_payload(
    raw_components: Mapping[str, Any],
    key: str,
) -> Mapping[str, Any]:
    """
    Читает обязательный компонент entity payload-а.
    """
    return _component_payload(raw_components.get(key), key)


def _component_payload(raw_component: Any, key: str) -> Mapping[str, Any]:
    """
    Проверяет, что компонент entity payload-а является объектом.
    """
    if not isinstance(raw_component, Mapping):
        msg = f"entity {key} component must be an object"
        raise ProtocolError(msg)
    return raw_component


def _string_field(payload: Mapping[str, Any], key: str) -> str:
    """
    Читает непустое строковое поле из payload-а сообщения.
    """
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        msg = f"{key} must be a non-empty string"
        raise ProtocolError(msg)
    return value


def _optional_string_field(payload: Mapping[str, Any], key: str) -> str | None:
    """
    Читает необязательное непустое строковое поле из payload-а сообщения.
    """
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        msg = f"{key} must be a non-empty string"
        raise ProtocolError(msg)
    return value


def _vec2_from_payload(raw_value: Any, field_name: str) -> Vec2:
    """
    Читает пару координат из payload-а сообщения.
    """
    if not isinstance(raw_value, list) or len(raw_value) != 2:
        msg = f"{field_name} must be a two-item list"
        raise ProtocolError(msg)
    x, y = raw_value
    if (
        not isinstance(x, int | float)
        or isinstance(x, bool)
        or not isinstance(y, int | float)
        or isinstance(y, bool)
    ):
        msg = f"{field_name} coordinates must be numbers"
        raise ProtocolError(msg)
    return Vec2(float(x), float(y))


def _size_from_payload(raw_value: Any, field_name: str) -> tuple[int, int]:
    """
    Читает размер объекта из payload-а сообщения.
    """
    if not isinstance(raw_value, list) or len(raw_value) != 2:
        msg = f"{field_name} must be a two-item list"
        raise ProtocolError(msg)
    width, height = raw_value
    if not isinstance(width, int) or isinstance(width, bool):
        msg = f"{field_name} must contain integers"
        raise ProtocolError(msg)
    if not isinstance(height, int) or isinstance(height, bool):
        msg = f"{field_name} must contain integers"
        raise ProtocolError(msg)
    if width <= 0 or height <= 0:
        msg = f"{field_name} must be positive"
        raise ProtocolError(msg)
    return width, height


def _positive_int_field(payload: Mapping[str, Any], key: str) -> int:
    """
    Читает положительное целое число из payload-а сообщения.
    """
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"{key} must be an integer"
        raise ProtocolError(msg)
    if value <= 0:
        msg = f"{key} must be positive"
        raise ProtocolError(msg)
    return value


def _non_negative_int_field(payload: Mapping[str, Any], key: str) -> int:
    """
    Читает неотрицательное целое число из payload-а сообщения.
    """
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"{key} must be an integer"
        raise ProtocolError(msg)
    if value < 0:
        msg = f"{key} must be non-negative"
        raise ProtocolError(msg)
    return value


def _bool_field(payload: Mapping[str, Any], key: str) -> bool:
    """
    Читает boolean-поле из payload-а сообщения и отклоняет другие типы поля.
    """
    value = payload.get(key, False)
    if not isinstance(value, bool):
        msg = f"{key} must be a boolean"
        raise ProtocolError(msg)
    return value


def _optional_bool_field(payload: Mapping[str, Any], key: str) -> bool | None:
    """
    Читает необязательное boolean-поле из payload-а сообщения.
    """
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        msg = f"{key} must be a boolean"
        raise ProtocolError(msg)
    return value


def _optional_int_field(payload: Mapping[str, Any], key: str) -> int | None:
    """
    Читает необязательное целочисленное поле из payload-а сообщения.
    """
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"{key} must be an integer"
        raise ProtocolError(msg)
    return value


def _number_field(payload: Mapping[str, Any], key: str) -> float:
    """
    Читает числовое поле из payload-а сообщения и отклоняет другие типы поля.
    """
    value = payload.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        msg = f"{key} must be a number"
        raise ProtocolError(msg)
    return float(value)


def _optional_number_field(
    payload: Mapping[str, Any],
    key: str,
    default: float,
) -> float:
    """
    Читает необязательное числовое поле из payload-а сообщения.
    """
    value = payload.get(key, default)
    if not isinstance(value, int | float) or isinstance(value, bool):
        msg = f"{key} must be a number"
        raise ProtocolError(msg)
    return float(value)


def _tile_from_payload(raw_tile: Any) -> tuple[int, int]:
    """
    Читает координаты тайла из payload-а запроса взаимодействия.
    """
    if not isinstance(raw_tile, list) or len(raw_tile) != 2:
        msg = "interaction target_tile must be a two-item list"
        raise ProtocolError(msg)
    tile_x, tile_y = raw_tile
    if (
        not isinstance(tile_x, int)
        or isinstance(tile_x, bool)
        or not isinstance(tile_y, int)
        or isinstance(tile_y, bool)
    ):
        msg = "interaction target_tile coordinates must be integers"
        raise ProtocolError(msg)
    if tile_x < 0 or tile_y < 0:
        msg = "interaction target_tile coordinates must be non-negative"
        raise ProtocolError(msg)
    return tile_x, tile_y
