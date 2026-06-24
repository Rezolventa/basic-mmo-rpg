from __future__ import annotations

import pytest

from basic_mmo_rpg.domain.entities import (
    BodyComponent,
    CombatComponent,
    EntityKind,
    IdentityComponent,
    InteractionComponent,
    LootableComponent,
    LootClaimPolicy,
    RespawnComponent,
    WorldEntity,
)
from basic_mmo_rpg.domain.equipment import MAIN_HAND_SLOT, Equipment
from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.inventory import FISHING_ROD_ITEM_ID, ItemStack
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState
from basic_mmo_rpg.shared.protocol import (
    ClientMessageType,
    EntitySnapshot,
    InteractionTarget,
    PlayerSnapshot,
    ProtocolError,
    ProtocolMessage,
    attack_requested_payload,
    attack_target_from_payload,
    character_name_from_payload,
    chat_text_from_payload,
    combat_event_payload,
    decode_message,
    encode_message,
    entities_from_snapshot_payload,
    entity_snapshots_from_payload,
    equip_item_id_from_payload,
    equip_item_requested_payload,
    equipment_from_payload,
    equipment_slot_from_payload,
    equipment_updated_payload,
    interact_requested_payload,
    interact_tile_requested_payload,
    interaction_target_from_payload,
    inventory_items_from_payload,
    inventory_updated_payload,
    join_request_payload,
    movement_intent_from_payload,
    movement_intent_to_payload,
    player_snapshots_from_payload,
    players_from_snapshot_payload,
    respawn_requested_payload,
    unequip_item_requested_payload,
    world_snapshot_payload,
)


def test_protocol_message_round_trips_through_json() -> None:
    """
    Проверяет, что протокольное сообщение сериализуется и десериализуется через JSON.
    """
    message = ProtocolMessage(
        type=ClientMessageType.MOVE_REQUESTED,
        payload=movement_intent_to_payload(MovementIntent(right=True)),
    )

    decoded = decode_message(encode_message(message))

    assert decoded == message
    assert movement_intent_from_payload(decoded.payload) == MovementIntent(right=True)


def test_decode_message_rejects_invalid_shape() -> None:
    """
    Проверяет, что протокол отклоняет сообщение без корректной payload-структуры.
    """
    with pytest.raises(ProtocolError):
        decode_message('{"type":"move_requested","payload":[]}')


def test_world_snapshot_payload_round_trips_players() -> None:
    """
    Проверяет, что игроки сериализуются и восстанавливаются из payload snapshot-а.
    """
    player = PlayerState(entity_id="p1", position=Vec2(10, 20), speed=123, hit_points=12)
    snapshot = PlayerSnapshot(state=player, name="Alice")

    payload = world_snapshot_payload([snapshot])
    decoded_players = players_from_snapshot_payload(payload)
    decoded_snapshots = player_snapshots_from_payload(payload)

    assert decoded_players == [player]
    assert decoded_snapshots == [snapshot]


def test_world_snapshot_payload_round_trips_entities() -> None:
    """
    Проверяет, что объекты мира сериализуются и восстанавливаются из snapshot-а.
    """
    entity = WorldEntity(
        entity_id="npc-funday",
        kind=EntityKind.NPC,
        name="Funday",
        position=Vec2(64, 32),
        width=24,
        height=30,
        interaction_radius=64,
        solid=True,
    )
    payload = world_snapshot_payload([], [EntitySnapshot(state=entity)])

    assert entities_from_snapshot_payload(payload) == [entity]
    assert entity_snapshots_from_payload(payload) == [EntitySnapshot(state=entity)]


def test_world_snapshot_payload_round_trips_dynamic_entity_state() -> None:
    """
    Проверяет, что динамическое состояние калиток и creature-сущностей проходит через snapshot.
    """
    gate = WorldEntity(
        entity_id="gate-sheep-pen",
        kind=EntityKind.GATE,
        name="Калитка",
        position=Vec2(64, 32),
        width=32,
        height=32,
        solid=False,
        is_open=True,
    )
    sheep = WorldEntity(
        entity_id="creature-barbara",
        kind=EntityKind.CREATURE,
        name="Овца",
        position=Vec2(96, 32),
        width=28,
        height=28,
        hit_points=15,
        max_hit_points=15,
        has_wool=False,
    )
    lootable = WorldEntity(
        entity_id="lootable-training-dummy",
        identity=IdentityComponent(
            kind=EntityKind.OBJECT,
            name="Тренировочный манекен",
            destroyed_name="Разрушенный тренировочный манекен",
            visual="training_dummy",
        ),
        body=BodyComponent(position=Vec2(128, 32), width=24, height=34, solid=True),
        interaction=InteractionComponent(radius=64, dialogue=""),
        lootable=LootableComponent(
            reward_item_id="rusty_sword",
            reward_quantity=1,
            success_text="Вы вытащили Ржавый меч из манекена",
            claim_policy=LootClaimPolicy.ALWAYS,
        ),
        combat=CombatComponent(hit_points=20, max_hit_points=20),
        respawn=RespawnComponent(seconds=10),
    )

    payload = world_snapshot_payload(
        [],
        [
            EntitySnapshot(state=gate),
            EntitySnapshot(state=sheep),
            EntitySnapshot(state=lootable),
        ],
    )

    assert entities_from_snapshot_payload(payload) == [gate, sheep, lootable]


def test_interaction_target_payload_is_validated() -> None:
    """
    Проверяет payload запроса взаимодействия с объектом мира.
    """
    assert interaction_target_from_payload(
        interact_requested_payload("npc-funday")
    ) == InteractionTarget(entity_id="npc-funday")

    assert interaction_target_from_payload(interact_tile_requested_payload(3, 4)) == (
        InteractionTarget(tile=(3, 4))
    )

    with pytest.raises(ProtocolError):
        interaction_target_from_payload({"target_id": ""})
    with pytest.raises(ProtocolError):
        interaction_target_from_payload({"target_id": "npc-funday", "target_tile": [3, 4]})
    with pytest.raises(ProtocolError):
        interaction_target_from_payload({"target_tile": [True, 4]})
    with pytest.raises(ProtocolError):
        interaction_target_from_payload({"target_tile": [-1, 4]})


def test_combat_payloads_are_validated() -> None:
    """
    Проверяет payload-ы выбора цели атаки и серверного события боя.
    """
    target = attack_target_from_payload(attack_requested_payload("lootable-training-dummy"))
    event = combat_event_payload(
        actor_id="player-1",
        actor_name="Alice",
        target_id="lootable-training-dummy",
        target_name="Тренировочный манекен",
        text="Вы атаковали Тренировочный манекен: -4",
        floating_text="-4",
        created_at=123.0,
        destroyed=False,
    )

    assert target.entity_id == "lootable-training-dummy"
    assert event["actor_id"] == "player-1"
    assert event["actor_name"] == "Alice"
    assert event["target_id"] == "lootable-training-dummy"
    assert event["floating_text"] == "-4"
    assert event["add_to_journal"] is True
    assert event["destroyed"] is False
    assert respawn_requested_payload() == {}
    with pytest.raises(ProtocolError):
        attack_target_from_payload({"target_id": ""})


def test_inventory_updated_payload_round_trips_items() -> None:
    """
    Проверяет, что обновление инвентаря сериализует и восстанавливает стаки предметов.
    """
    item = ItemStack(item_id=FISHING_ROD_ITEM_ID, display_name="Удочка", quantity=1)

    payload = inventory_updated_payload([item])

    assert inventory_items_from_payload(payload) == [item]


def test_equipment_payloads_round_trip() -> None:
    """
    Проверяет payload-ы экипировки предмета, снятия слота и server update-а.
    """
    equipment = Equipment(main_hand=FISHING_ROD_ITEM_ID)

    assert equip_item_id_from_payload(
        equip_item_requested_payload(FISHING_ROD_ITEM_ID)
    ) == FISHING_ROD_ITEM_ID
    assert equipment_slot_from_payload(unequip_item_requested_payload()) == MAIN_HAND_SLOT
    assert equipment_from_payload(equipment_updated_payload(equipment)) == equipment
    assert equipment_from_payload({"main_hand": None}) == Equipment()

    with pytest.raises(ProtocolError):
        equip_item_id_from_payload({"item_id": ""})
    with pytest.raises(ProtocolError):
        equipment_slot_from_payload({"slot": "head"})
    with pytest.raises(ProtocolError):
        equipment_from_payload({"main_hand": ""})


def test_character_name_payload_is_trimmed_and_limited() -> None:
    """
    Проверяет нормализацию имени персонажа и базовые ограничения протокола входа.
    """
    assert character_name_from_payload(join_request_payload(" Alice ")) == "Alice"

    with pytest.raises(ProtocolError):
        character_name_from_payload(join_request_payload(""))
    with pytest.raises(ProtocolError):
        character_name_from_payload(join_request_payload("A" * 25))


def test_chat_text_payload_is_trimmed_and_limited() -> None:
    """
    Проверяет нормализацию текста чата и базовые ограничения длины.
    """
    assert chat_text_from_payload({"text": " Привет "}) == "Привет"

    with pytest.raises(ProtocolError):
        chat_text_from_payload({"text": ""})
    with pytest.raises(ProtocolError):
        chat_text_from_payload({"text": "A" * 161})
