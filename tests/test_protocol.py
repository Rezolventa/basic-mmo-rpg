from __future__ import annotations

from pathlib import Path

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
from basic_mmo_rpg.domain.equipment import CHEST_SLOT, MAIN_HAND_SLOT, Equipment
from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.inventory import FISHING_ROD_ITEM_ID, ItemStack
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState
from basic_mmo_rpg.domain.skills import FISHING_SKILL_ID, CharacterSkill
from basic_mmo_rpg.shared.protocol import (
    INTERACTION_PRESENTATION_BUBBLE,
    INTERACTION_PRESENTATION_FEED,
    ClientMessageType,
    EntitySnapshot,
    InteractionMenuOption,
    InteractionOptionSelection,
    InteractionTarget,
    PlayerSnapshot,
    ProtocolError,
    ProtocolMessage,
    VendorOffer,
    VendorPurchaseRequest,
    VendorWindow,
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
    interaction_menu_from_payload,
    interaction_menu_opened_payload,
    interaction_option_selected_payload,
    interaction_option_selection_from_payload,
    interaction_presentation_from_payload,
    interaction_result_payload,
    interaction_target_from_payload,
    inventory_items_from_payload,
    inventory_updated_payload,
    join_request_payload,
    map_fingerprint_from_payload,
    movement_intent_from_payload,
    movement_intent_to_payload,
    player_snapshots_from_payload,
    players_from_snapshot_payload,
    respawn_requested_payload,
    skills_from_payload,
    skills_updated_payload,
    tile_map_from_payload,
    tile_map_to_payload,
    unequip_item_requested_payload,
    vendor_buy_requested_payload,
    vendor_opened_payload,
    vendor_purchase_request_from_payload,
    vendor_window_from_payload,
    world_snapshot_payload,
)
from basic_mmo_rpg.storage.map_loader import load_tile_map


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
    player = PlayerState(
        entity_id="p1",
        position=Vec2(10, 20),
        speed=123,
        hit_points=12,
        busy=True,
        action="gathering",
    )
    snapshot = PlayerSnapshot(state=player, name="Alice")

    payload = world_snapshot_payload([snapshot])
    decoded_players = players_from_snapshot_payload(payload)
    decoded_snapshots = player_snapshots_from_payload(payload)

    assert decoded_players == [player]
    assert decoded_snapshots == [snapshot]


def test_interaction_result_payload_carries_presentation() -> None:
    """
    Проверяет, что результат взаимодействия явно сообщает способ отображения.
    """
    default_payload = interaction_result_payload(
        actor_id="p1",
        target_id="p1",
        target_name="Alice",
        text="Hello",
        created_at=123.0,
    )
    feed_payload = interaction_result_payload(
        actor_id="p1",
        target_id="p1",
        target_name="Alice",
        text="Hello",
        created_at=123.0,
        presentation=INTERACTION_PRESENTATION_FEED,
    )

    assert interaction_presentation_from_payload(default_payload) == INTERACTION_PRESENTATION_BUBBLE
    assert interaction_presentation_from_payload(feed_payload) == INTERACTION_PRESENTATION_FEED


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


def test_tile_map_payload_round_trips_server_map() -> None:
    """
    Проверяет, что серверная карта передается клиенту через протокол.
    """
    tile_map = load_tile_map(Path("assets/maps/starter_map.json"))

    restored = tile_map_from_payload(tile_map_to_payload(tile_map))

    assert restored.width == tile_map.width
    assert restored.height == tile_map.height
    assert restored.tile_size == tile_map.tile_size
    assert restored.fingerprint == tile_map.fingerprint
    assert restored.definitions["T"].sprites == tile_map.definitions["T"].sprites
    assert restored.definitions["T"].sprite_offset == tile_map.definitions["T"].sprite_offset
    assert restored.definitions["T"].sprite_offsets == tile_map.definitions["T"].sprite_offsets
    assert restored.definitions["T"].collision_rect == tile_map.definitions["T"].collision_rect
    assert restored.definitions["R"].sprites == tile_map.definitions["R"].sprites
    assert restored.definitions["R"].sprite_offset == tile_map.definitions["R"].sprite_offset
    assert restored.definitions["R"].sprite_offsets == tile_map.definitions["R"].sprite_offsets
    assert restored.definitions["R"].collision_rect == tile_map.definitions["R"].collision_rect
    assert restored.definitions["C"].sprites == tile_map.definitions["C"].sprites
    assert restored.definitions["C"].sprite_offset == tile_map.definitions["C"].sprite_offset
    assert restored.definitions["C"].sprite_offsets == tile_map.definitions["C"].sprite_offsets
    assert restored.definitions["C"].collision_rect == tile_map.definitions["C"].collision_rect
    assert len(restored.entities) == len(tile_map.entities)


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


def test_interaction_menu_payloads_are_validated() -> None:
    """
    Проверяет payload-ы серверного NPC-окна и выбора его опции.
    """
    option = InteractionMenuOption(
        option_id="quest:funday_fish",
        label="Обменять Рыба x2 на Gold x1 (1/2)",
        kind="repeatable",
        enabled=False,
        progress="Рыба 1/2",
        disabled_reason="Нужно: Рыба 1/2",
    )
    payload = interaction_menu_opened_payload(
        entity_id="npc-funday",
        title="Funday",
        body="Иди и поймай мне рыбу",
        options=(option,),
    )

    menu = interaction_menu_from_payload(payload)
    selection = interaction_option_selection_from_payload(
        interaction_option_selected_payload("npc-funday", "quest:funday_fish")
    )

    assert menu.entity_id == "npc-funday"
    assert menu.options == (option,)
    assert selection == InteractionOptionSelection(
        entity_id="npc-funday",
        option_id="quest:funday_fish",
    )
    with pytest.raises(ProtocolError):
        interaction_menu_from_payload({"entity_id": "npc-funday", "title": "Funday"})
    with pytest.raises(ProtocolError):
        interaction_option_selection_from_payload({"entity_id": "npc-funday", "option_id": ""})


def test_vendor_payloads_are_validated() -> None:
    """
    Проверяет payload-ы окна торговца и запроса покупки.
    """
    offer = VendorOffer(
        offer_id="iron_chest_armor",
        item_id="iron_chest_armor",
        display_name="Железная кираса",
        price_item_id="gold",
        price_display_name="Gold",
        price_quantity=25,
        details="Броня +2",
    )
    payload = vendor_opened_payload(
        vendor_id="npc-bjorn",
        title="Bjorn",
        offers=(offer,),
    )

    vendor_window = vendor_window_from_payload(payload)
    request = vendor_purchase_request_from_payload(
        vendor_buy_requested_payload("npc-bjorn", "iron_chest_armor")
    )

    assert vendor_window == VendorWindow(
        vendor_id="npc-bjorn",
        title="Bjorn",
        offers=(offer,),
    )
    assert request == VendorPurchaseRequest(
        vendor_id="npc-bjorn",
        offer_id="iron_chest_armor",
    )
    with pytest.raises(ProtocolError):
        vendor_window_from_payload({"vendor_id": "npc-bjorn", "title": "Bjorn"})
    with pytest.raises(ProtocolError):
        vendor_purchase_request_from_payload({"vendor_id": "npc-bjorn", "offer_id": ""})


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


def test_skills_updated_payload_round_trips_skills() -> None:
    """
    Проверяет, что обновление скиллов сериализуется и валидируется протоколом.
    """
    skill = CharacterSkill(
        skill_id=FISHING_SKILL_ID,
        display_name="Рыбалка",
        value_tenths=123,
    )

    payload = skills_updated_payload([skill])

    assert skills_from_payload(payload) == [skill]
    with pytest.raises(ProtocolError):
        skills_from_payload({"skills": [{"skill_id": FISHING_SKILL_ID, "display_name": "x"}]})


def test_equipment_payloads_round_trip() -> None:
    """
    Проверяет payload-ы экипировки предмета, снятия слота и server update-а.
    """
    equipment = Equipment(main_hand=FISHING_ROD_ITEM_ID, chest="iron_chest_armor")

    assert equip_item_id_from_payload(
        equip_item_requested_payload(FISHING_ROD_ITEM_ID)
    ) == FISHING_ROD_ITEM_ID
    assert equipment_slot_from_payload(unequip_item_requested_payload()) == MAIN_HAND_SLOT
    assert equipment_slot_from_payload(unequip_item_requested_payload(CHEST_SLOT)) == CHEST_SLOT
    assert equipment_from_payload(equipment_updated_payload(equipment)) == equipment
    assert equipment_from_payload({"main_hand": None}) == Equipment()
    assert equipment_from_payload({"main_hand": None, "chest": None}) == Equipment()

    with pytest.raises(ProtocolError):
        equip_item_id_from_payload({"item_id": ""})
    with pytest.raises(ProtocolError):
        equipment_slot_from_payload({"slot": "head"})
    with pytest.raises(ProtocolError):
        equipment_from_payload({"main_hand": ""})
    with pytest.raises(ProtocolError):
        equipment_from_payload({"chest": ""})


def test_character_name_payload_is_trimmed_and_limited() -> None:
    """
    Проверяет нормализацию имени персонажа и базовые ограничения протокола входа.
    """
    assert character_name_from_payload(join_request_payload(" Alice ")) == "Alice"

    with pytest.raises(ProtocolError):
        character_name_from_payload(join_request_payload(""))
    with pytest.raises(ProtocolError):
        character_name_from_payload(join_request_payload("A" * 25))


def test_join_payload_can_include_map_fingerprint() -> None:
    """
    Проверяет необязательный отпечаток карты в запросе входа.
    """
    payload = join_request_payload("Alice", map_fingerprint="abc123")

    assert payload["map_fingerprint"] == "abc123"
    assert map_fingerprint_from_payload(payload) == "abc123"
    assert map_fingerprint_from_payload(join_request_payload("Alice")) is None
    with pytest.raises(ProtocolError):
        map_fingerprint_from_payload({"map_fingerprint": ""})


def test_chat_text_payload_is_trimmed_and_limited() -> None:
    """
    Проверяет нормализацию текста чата и базовые ограничения длины.
    """
    assert chat_text_from_payload({"text": " Привет "}) == "Привет"

    with pytest.raises(ProtocolError):
        chat_text_from_payload({"text": ""})
    with pytest.raises(ProtocolError):
        chat_text_from_payload({"text": "A" * 161})
