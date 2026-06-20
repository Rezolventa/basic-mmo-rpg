from __future__ import annotations

import asyncio
import contextlib
import random
import time
from pathlib import Path
from typing import NoReturn

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from basic_mmo_rpg.domain.equipment import MAIN_HAND_SLOT, Equipment
from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.inventory import (
    FISH_ITEM_ID,
    FISHING_ROD_ITEM_ID,
    GOLD_ITEM_ID,
    LOG_ITEM_ID,
    LUMBER_AXE_ITEM_ID,
    PICKAXE_ITEM_ID,
    STONE_ITEM_ID,
)
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState
from basic_mmo_rpg.server.app import MultiplayerServer
from basic_mmo_rpg.server.world import MultiplayerWorld
from basic_mmo_rpg.shared.protocol import (
    ClientMessageType,
    ProtocolMessage,
    ServerMessageType,
    chat_sent_payload,
    decode_message,
    encode_message,
    equip_item_requested_payload,
    equipment_from_payload,
    interact_requested_payload,
    interact_tile_requested_payload,
    inventory_items_from_payload,
    join_request_payload,
    movement_intent_to_payload,
    players_from_snapshot_payload,
    unequip_item_requested_payload,
)
from basic_mmo_rpg.storage.characters import CharacterRepository
from basic_mmo_rpg.storage.map_loader import tile_map_from_dict


def _open_map() -> object:
    """
    Возвращает открытую карту для websocket-интеграционного теста.
    """
    return _open_map_with_entities()


def _open_map_with_entities(
    npc_position: list[int] | None = None,
    interaction_radius: int = 64,
) -> object:
    """
    Возвращает открытую карту с опциональным NPC для websocket-тестов.
    """
    raw_map: dict[str, object] = {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            "..........",
            "..........",
            "..........",
            "..........",
        ],
    }
    if npc_position is not None:
        raw_map["entities"] = [
            {
                "id": "npc-funday",
                "kind": "npc",
                "name": "Funday",
                "position": npc_position,
                "size": [24, 30],
                "interaction_radius": interaction_radius,
                "dialogue": "Иди и поймай мне рыбу",
                "solid": True,
            }
        ]
    return raw_map


def _open_map_with_water() -> object:
    """
    Возвращает открытую карту с водой рядом со spawn-ом для тестов рыбалки.
    """
    return {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "~": {"name": "water", "solid": True, "color": [43, 91, 151]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            "..........",
            "..~.......",
            "..........",
            "..........",
        ],
    }


def _open_map_with_tree() -> object:
    """
    Возвращает открытую карту с деревом рядом со spawn-ом для тестов рубки.
    """
    return {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "T": {"name": "tree", "solid": True, "color": [39, 88, 50]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            "..........",
            "..T.......",
            "..........",
            "..........",
        ],
    }


def _open_map_with_rock() -> object:
    """
    Возвращает открытую карту с камнем рядом со spawn-ом для тестов добычи.
    """
    return {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "R": {"name": "rock", "solid": True, "color": [102, 106, 112]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            "..........",
            "..R.......",
            "..........",
            "..........",
        ],
    }


def _open_map_with_water_and_tree() -> object:
    """
    Возвращает открытую карту с водой и деревом рядом со spawn-ом.
    """
    return {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "~": {"name": "water", "solid": True, "color": [43, 91, 151]},
            "T": {"name": "tree", "solid": True, "color": [39, 88, 50]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            "..........",
            "..~.......",
            "..T.......",
            "..........",
        ],
    }


def _open_map_with_jack_lumber() -> object:
    """
    Возвращает открытую карту с NPC Jack Lumber рядом со spawn-ом.
    """
    raw_map: dict[str, object] = {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            "..........",
            "..........",
            "..........",
            "..........",
        ],
        "entities": [
            {
                "id": "npc-jack-lumber",
                "kind": "npc",
                "name": "Jack Lumber",
                "position": [64, 32],
                "size": [24, 30],
                "interaction_radius": 64,
                "dialogue": "Наруби немного древесины",
                "solid": True,
            }
        ],
    }
    return raw_map


def _open_map_with_kopai() -> object:
    """
    Возвращает открытую карту с NPC Kopai рядом со spawn-ом.
    """
    raw_map: dict[str, object] = {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            "..........",
            "..........",
            "..........",
            "..........",
        ],
        "entities": [
            {
                "id": "npc-kopai",
                "kind": "npc",
                "name": "Kopai",
                "position": [64, 32],
                "size": [24, 30],
                "interaction_radius": 64,
                "dialogue": "Накопай мне чего-нибудь",
                "solid": True,
            }
        ],
    }
    return raw_map


def test_websocket_server_accepts_two_clients_and_broadcasts_movement(tmp_path: Path) -> None:
    """
    Проверяет websocket-сценарий с двумя клиентами и серверной обработкой движения.
    """
    asyncio.run(_websocket_server_smoke(tmp_path))


def test_server_cleans_up_player_when_initial_send_fails(tmp_path: Path) -> None:
    """
    Проверяет, что сервер удаляет игрока, если соединение падает во время первого send.
    """
    asyncio.run(_initial_send_failure_smoke(tmp_path))


def test_websocket_server_restores_saved_position_on_reconnect(tmp_path: Path) -> None:
    """
    Проверяет, что повторный вход тем же именем восстанавливает сохраненную позицию.
    """
    asyncio.run(_reconnect_restores_position_smoke(tmp_path))


def test_websocket_server_kicks_old_session_for_duplicate_name(tmp_path: Path) -> None:
    """
    Проверяет, что повторный вход тем же именем отключает старую сессию.
    """
    asyncio.run(_duplicate_name_kicks_old_session_smoke(tmp_path))


def test_websocket_server_broadcasts_chat_messages(tmp_path: Path) -> None:
    """
    Проверяет, что сервер принимает сообщение чата и рассылает его клиентам.
    """
    asyncio.run(_chat_broadcast_smoke(tmp_path))


def test_websocket_server_equips_and_unequips_main_hand(tmp_path: Path) -> None:
    """
    Проверяет server-authoritative экипировку и снятие предмета в руке.
    """
    asyncio.run(_equipment_smoke(tmp_path))


def test_websocket_server_sends_interaction_result_only_to_actor(tmp_path: Path) -> None:
    """
    Проверяет, что результат взаимодействия с NPC получает только инициатор.
    """
    asyncio.run(_interaction_result_only_to_actor_smoke(tmp_path))


def test_websocket_server_ignores_interaction_when_target_is_too_far(tmp_path: Path) -> None:
    """
    Проверяет, что сервер молчит, если игрок слишком далеко от NPC.
    """
    asyncio.run(_interaction_too_far_smoke(tmp_path))


def test_websocket_server_fishing_requires_rod(tmp_path: Path) -> None:
    """
    Проверяет, что рыбалка без удочки показывает только локальный пузырь.
    """
    asyncio.run(_fishing_requires_rod_smoke(tmp_path))


def test_websocket_server_fishing_requires_equipped_rod(tmp_path: Path) -> None:
    """
    Проверяет, что удочка в инвентаре не заменяет удочку в руке.
    """
    asyncio.run(_fishing_requires_equipped_rod_smoke(tmp_path))


def test_websocket_server_fishing_success_adds_fish(tmp_path: Path) -> None:
    """
    Проверяет успешную рыбалку и сохранение рыбы в инвентаре.
    """
    asyncio.run(_fishing_success_smoke(tmp_path))


def test_websocket_server_fishing_failure_only_sends_result(tmp_path: Path) -> None:
    """
    Проверяет неудачную рыбалку без изменения инвентаря.
    """
    asyncio.run(_fishing_failure_smoke(tmp_path))


def test_websocket_server_funday_exchanges_fish_for_gold(tmp_path: Path) -> None:
    """
    Проверяет обмен двух рыб на Gold при взаимодействии с Funday.
    """
    asyncio.run(_funday_exchange_smoke(tmp_path))


def test_websocket_server_funday_grants_rod_before_exchange(tmp_path: Path) -> None:
    """
    Проверяет, что Funday сначала выдает удочку, даже если у игрока уже есть рыба.
    """
    asyncio.run(_funday_grants_rod_before_exchange_smoke(tmp_path))


def test_websocket_server_fishing_stack_overflow_is_handled(tmp_path: Path) -> None:
    """
    Проверяет, что полный стак рыбы не обрывает соединение во время рыбалки.
    """
    asyncio.run(_fishing_stack_overflow_smoke(tmp_path))


def test_websocket_server_exchange_stack_overflow_is_handled(tmp_path: Path) -> None:
    """
    Проверяет, что полный стак Gold не обрывает соединение во время обмена.
    """
    asyncio.run(_exchange_stack_overflow_smoke(tmp_path))


def test_websocket_server_jack_lumber_grants_axe(tmp_path: Path) -> None:
    """
    Проверяет, что Jack Lumber выдает топор, если у игрока его еще нет.
    """
    asyncio.run(_jack_lumber_grants_axe_smoke(tmp_path))


def test_websocket_server_lumberjacking_requires_axe(tmp_path: Path) -> None:
    """
    Проверяет, что рубка без топора показывает только локальный пузырь.
    """
    asyncio.run(_lumberjacking_requires_axe_smoke(tmp_path))


def test_websocket_server_lumberjacking_success_adds_log(tmp_path: Path) -> None:
    """
    Проверяет успешную рубку дерева и сохранение бревна в инвентаре.
    """
    asyncio.run(_lumberjacking_success_smoke(tmp_path))


def test_websocket_server_gathering_cooldown_is_shared_between_resources(
    tmp_path: Path,
) -> None:
    """
    Проверяет, что рыбалка ставит cooldown и для немедленной рубки дерева.
    """
    asyncio.run(_gathering_shared_cooldown_smoke(tmp_path))


def test_websocket_server_jack_lumber_exchanges_logs_for_gold(tmp_path: Path) -> None:
    """
    Проверяет обмен пяти бревен на Gold при взаимодействии с Jack Lumber.
    """
    asyncio.run(_jack_lumber_exchange_smoke(tmp_path))


def test_websocket_server_jack_lumber_grants_axe_before_exchange(tmp_path: Path) -> None:
    """
    Проверяет, что Jack Lumber сначала выдает топор, даже если у игрока уже есть бревна.
    """
    asyncio.run(_jack_lumber_grants_axe_before_exchange_smoke(tmp_path))


def test_websocket_server_kopai_grants_pickaxe(tmp_path: Path) -> None:
    """
    Проверяет, что Kopai выдает кирку, если у игрока ее еще нет.
    """
    asyncio.run(_kopai_grants_pickaxe_smoke(tmp_path))


def test_websocket_server_mining_requires_pickaxe(tmp_path: Path) -> None:
    """
    Проверяет, что добыча камня без кирки показывает только локальный пузырь.
    """
    asyncio.run(_mining_requires_pickaxe_smoke(tmp_path))


def test_websocket_server_mining_success_adds_stone(tmp_path: Path) -> None:
    """
    Проверяет успешную добычу камня и сохранение камня в инвентаре.
    """
    asyncio.run(_mining_success_smoke(tmp_path))


def test_websocket_server_mining_failure_only_sends_result(tmp_path: Path) -> None:
    """
    Проверяет неудачную добычу камня без изменения инвентаря.
    """
    asyncio.run(_mining_failure_smoke(tmp_path))


def test_websocket_server_kopai_exchanges_stones_for_gold(tmp_path: Path) -> None:
    """
    Проверяет обмен трех камней на Gold при взаимодействии с Kopai.
    """
    asyncio.run(_kopai_exchange_smoke(tmp_path))


def test_websocket_server_kopai_grants_pickaxe_before_exchange(tmp_path: Path) -> None:
    """
    Проверяет, что Kopai сначала выдает кирку, даже если у игрока уже есть камни.
    """
    asyncio.run(_kopai_grants_pickaxe_before_exchange_smoke(tmp_path))


async def _websocket_server_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер на временном порту и проверяет обмен snapshot-ами.
    """
    multiplayer_server = _server_for_test(tmp_path)

    async with serve(multiplayer_server._handle_connection, "127.0.0.1", 0) as websocket_server:
        sockets = websocket_server.sockets
        assert sockets is not None
        port = sockets[0].getsockname()[1]
        uri = f"ws://127.0.0.1:{port}"

        game_loop = asyncio.create_task(multiplayer_server._game_loop())
        try:
            async with connect(uri) as first_client, connect(uri) as second_client:
                await _send_join(first_client, "Alice")
                await _send_join(second_client, "Bob")
                first_id = await _recv_player_id(first_client)
                await _recv_player_id(second_client)

                initial_players = await _recv_snapshot(first_client, expected_players=2)
                initial_first = _find_player(initial_players, first_id)

                await first_client.send(
                    encode_message(
                        ProtocolMessage(
                            type=ClientMessageType.MOVE_REQUESTED,
                            payload=movement_intent_to_payload(MovementIntent(right=True)),
                        )
                    )
                )

                moved_first = await _recv_moved_player(first_client, first_id, initial_first)

                assert moved_first.position.x > initial_first.position.x
        finally:
            game_loop.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await game_loop


async def _initial_send_failure_smoke(tmp_path: Path) -> None:
    """
    Имитирует падение websocket-а на connection_accepted и проверяет cleanup.
    """
    multiplayer_server = _server_for_test(tmp_path)

    with pytest.raises(ConnectionError):
        await multiplayer_server._handle_connection(_FailingWebSocket())

    assert multiplayer_server.world.players == {}
    assert multiplayer_server.connections == {}


async def _reconnect_restores_position_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет восстановление позиции после disconnect/reconnect.
    """
    multiplayer_server = _server_for_test(tmp_path)

    async with _running_test_server(multiplayer_server) as uri:
        async with connect(uri) as first_client:
            await _send_join(first_client, "Alice")
            first_id = await _recv_player_id(first_client)
            initial_players = await _recv_snapshot(first_client, expected_players=1)
            initial_player = _find_player(initial_players, first_id)

            await first_client.send(
                encode_message(
                    ProtocolMessage(
                        type=ClientMessageType.MOVE_REQUESTED,
                        payload=movement_intent_to_payload(MovementIntent(right=True)),
                    )
                )
            )
            moved_player = await _recv_moved_player(
                first_client,
                first_id,
                initial_player,
                expected_players=1,
            )

        await _wait_for_world_player_count(multiplayer_server, expected_players=0)

        async with connect(uri) as second_client:
            await _send_join(second_client, "Alice")
            second_id = await _recv_player_id(second_client)
            restored_players = await _recv_snapshot(second_client, expected_players=1)
            restored_player = _find_player(restored_players, second_id)

        assert restored_player.position.x >= moved_player.position.x
        assert restored_player.position.y == moved_player.position.y


async def _duplicate_name_kicks_old_session_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет, что одна активная сессия соответствует одному имени.
    """
    multiplayer_server = _server_for_test(tmp_path)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)

        async with connect(uri) as second_client:
            await _send_join(second_client, "Alice")
            second_id = await _recv_player_id(second_client)
            error = await _recv_message_type(first_client, ServerMessageType.ERROR)
            players = await _recv_snapshot(second_client, expected_players=1)

        assert first_id != second_id
        assert error.payload.get("message") == "character connected elsewhere"
        assert [player.entity_id for player in players] == [second_id]


async def _chat_broadcast_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет доставку chat_message второму клиенту.
    """
    multiplayer_server = _server_for_test(tmp_path)

    async with _running_test_server(multiplayer_server) as uri:
        async with connect(uri) as first_client, connect(uri) as second_client:
            await _send_join(first_client, "Alice")
            await _send_join(second_client, "Bob")
            first_id = await _recv_player_id(first_client)
            await _recv_player_id(second_client)
            initial_inventory = await _recv_message_type(
                first_client,
                ServerMessageType.INVENTORY_UPDATED,
            )
            assert inventory_items_from_payload(initial_inventory.payload) == []

            await first_client.send(
                encode_message(
                    ProtocolMessage(
                        type=ClientMessageType.CHAT_SENT,
                        payload=chat_sent_payload("Привет"),
                    )
                )
            )
            message = await _recv_message_type(second_client, ServerMessageType.CHAT_MESSAGE)

        assert message.payload["player_id"] == first_id
        assert message.payload["name"] == "Alice"
        assert message.payload["text"] == "Привет"
        assert isinstance(message.payload["created_at"], int | float)


async def _equipment_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет экипировку предмета через websocket.
    """
    multiplayer_server = _server_for_test(tmp_path)
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", FISHING_ROD_ITEM_ID)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        await _recv_player_id(first_client)

        inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )
        initial_equipment_message = await _recv_message_type(
            first_client,
            ServerMessageType.EQUIPMENT_UPDATED,
        )
        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.EQUIP_ITEM_REQUESTED,
                    payload=equip_item_requested_payload(FISHING_ROD_ITEM_ID),
                )
            )
        )
        equipped_message = await _recv_message_type(
            first_client,
            ServerMessageType.EQUIPMENT_UPDATED,
        )
        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.UNEQUIP_ITEM_REQUESTED,
                    payload=unequip_item_requested_payload(MAIN_HAND_SLOT),
                )
            )
        )
        unequipped_message = await _recv_message_type(
            first_client,
            ServerMessageType.EQUIPMENT_UPDATED,
        )

    assert inventory_items_from_payload(inventory_message.payload)[0].item_id == FISHING_ROD_ITEM_ID
    assert equipment_from_payload(initial_equipment_message.payload) == Equipment()
    assert equipment_from_payload(equipped_message.payload) == Equipment(
        main_hand=FISHING_ROD_ITEM_ID
    )
    assert equipment_from_payload(unequipped_message.payload) == Equipment()
    assert multiplayer_server.character_repository.load_equipment("Alice") == Equipment()


async def _interaction_result_only_to_actor_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет успешное взаимодействие с NPC.
    """
    multiplayer_server = _server_for_test(
        tmp_path,
        raw_map=_open_map_with_entities(npc_position=[64, 32]),
    )

    async with _running_test_server(multiplayer_server) as uri:
        async with connect(uri) as first_client, connect(uri) as second_client:
            await _send_join(first_client, "Alice")
            await _send_join(second_client, "Bob")
            first_id = await _recv_player_id(first_client)
            await _recv_player_id(second_client)

            await first_client.send(
                encode_message(
                    ProtocolMessage(
                        type=ClientMessageType.INTERACT_REQUESTED,
                        payload=interact_requested_payload("npc-funday"),
                    )
                )
            )
            message = await _recv_message_type(first_client, ServerMessageType.INTERACTION_RESULT)
            inventory_message = await _recv_message_type(
                first_client,
                ServerMessageType.INVENTORY_UPDATED,
            )
            await _assert_no_message_type(second_client, ServerMessageType.INTERACTION_RESULT)

        assert message.payload["actor_id"] == first_id
        assert message.payload["target_id"] == "npc-funday"
        assert message.payload["target_name"] == "Funday"
        assert message.payload["text"] == "Иди и поймай мне рыбу"
        inventory = inventory_items_from_payload(inventory_message.payload)
        persisted_inventory = multiplayer_server.character_repository.load_inventory("Alice")
        assert len(inventory) == 1
        assert inventory[0].item_id == FISHING_ROD_ITEM_ID
        assert inventory[0].quantity == 1
        assert persisted_inventory == inventory


async def _interaction_too_far_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет отсутствие ответа при слишком большой дистанции.
    """
    multiplayer_server = _server_for_test(
        tmp_path,
        raw_map=_open_map_with_entities(npc_position=[220, 32], interaction_radius=16),
    )

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        await _recv_player_id(first_client)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_requested_payload("npc-funday"),
                )
            )
        )
        await _assert_no_message_type(first_client, ServerMessageType.INTERACTION_RESULT)


async def _fishing_requires_rod_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет ответ на рыбалку без удочки.
    """
    multiplayer_server = _server_for_test(tmp_path, raw_map=_open_map_with_water())

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_tile_requested_payload(2, 1),
                )
            )
        )
        message = await _recv_message_type(first_client, ServerMessageType.INTERACTION_RESULT)

    assert message.payload["actor_id"] == first_id
    assert message.payload["target_id"] == first_id
    assert message.payload["target_name"] == "Alice"
    assert message.payload["text"] == "Нужна удочка в руке"
    assert message.payload["add_to_journal"] is False
    assert multiplayer_server.character_repository.load_inventory("Alice") == []


async def _fishing_requires_equipped_rod_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет отказ, если удочка лежит в инвентаре, а не в руке.
    """
    multiplayer_server = _server_for_test(tmp_path, raw_map=_open_map_with_water())
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", FISHING_ROD_ITEM_ID)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        await _recv_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_tile_requested_payload(2, 1),
                )
            )
        )
        message = await _recv_message_type(first_client, ServerMessageType.INTERACTION_RESULT)

    assert message.payload["actor_id"] == first_id
    assert message.payload["target_id"] == first_id
    assert message.payload["target_name"] == "Alice"
    assert message.payload["text"] == "Нужна удочка в руке"
    assert message.payload["add_to_journal"] is False
    assert multiplayer_server.character_repository.item_quantity("Alice", FISH_ITEM_ID) == 0


async def _fishing_success_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет успешное получение рыбы из водного тайла.
    """
    multiplayer_server = _server_for_test(
        tmp_path,
        raw_map=_open_map_with_water(),
        random_source=random.Random(1),
    )
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", FISHING_ROD_ITEM_ID)
    multiplayer_server.character_repository.equip_item("Alice", FISHING_ROD_ITEM_ID)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        await _recv_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_tile_requested_payload(2, 1),
                )
            )
        )
        inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )
        result_message = await _recv_message_type(
            first_client,
            ServerMessageType.INTERACTION_RESULT,
        )

    inventory = inventory_items_from_payload(inventory_message.payload)
    quantities = {item.item_id: item.quantity for item in inventory}
    assert result_message.payload["actor_id"] == first_id
    assert result_message.payload["target_id"] == first_id
    assert result_message.payload["text"] == "Вы поймали рыбу"
    assert result_message.payload["add_to_journal"] is True
    assert quantities[FISHING_ROD_ITEM_ID] == 1
    assert quantities[FISH_ITEM_ID] == 1
    assert multiplayer_server.character_repository.item_quantity("Alice", FISH_ITEM_ID) == 1


async def _fishing_failure_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет неудачную попытку рыбалки.
    """
    multiplayer_server = _server_for_test(
        tmp_path,
        raw_map=_open_map_with_water(),
        random_source=random.Random(0),
    )
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", FISHING_ROD_ITEM_ID)
    multiplayer_server.character_repository.equip_item("Alice", FISHING_ROD_ITEM_ID)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        await _recv_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_tile_requested_payload(2, 1),
                )
            )
        )
        result_message = await _recv_message_type(
            first_client,
            ServerMessageType.INTERACTION_RESULT,
        )
        await _assert_no_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

    assert result_message.payload["actor_id"] == first_id
    assert result_message.payload["target_id"] == first_id
    assert result_message.payload["text"] == "Рыба сорвалась"
    assert result_message.payload["add_to_journal"] is True
    assert multiplayer_server.character_repository.item_quantity("Alice", FISH_ITEM_ID) == 0


async def _funday_exchange_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет сдачу двух рыб NPC Funday.
    """
    multiplayer_server = _server_for_test(
        tmp_path,
        raw_map=_open_map_with_entities(npc_position=[64, 32]),
    )
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", FISHING_ROD_ITEM_ID)
    multiplayer_server.character_repository.add_item("Alice", FISH_ITEM_ID, quantity=2)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        await _recv_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_requested_payload("npc-funday"),
                )
            )
        )
        result_message = await _recv_message_type(
            first_client,
            ServerMessageType.INTERACTION_RESULT,
        )
        inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )

    inventory = inventory_items_from_payload(inventory_message.payload)
    quantities = {item.item_id: item.quantity for item in inventory}
    assert result_message.payload["actor_id"] == first_id
    assert result_message.payload["target_id"] == "npc-funday"
    assert result_message.payload["target_name"] == "Funday"
    assert result_message.payload["text"] == "Отличная рыба. Держи Gold."
    assert quantities[FISHING_ROD_ITEM_ID] == 1
    assert quantities[GOLD_ITEM_ID] == 1
    assert FISH_ITEM_ID not in quantities
    assert multiplayer_server.character_repository.item_quantity("Alice", FISH_ITEM_ID) == 0
    assert multiplayer_server.character_repository.item_quantity("Alice", GOLD_ITEM_ID) == 1


async def _funday_grants_rod_before_exchange_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет приоритет выдачи удочки над обменом рыбы.
    """
    multiplayer_server = _server_for_test(
        tmp_path,
        raw_map=_open_map_with_entities(npc_position=[64, 32]),
    )
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", FISH_ITEM_ID, quantity=2)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        initial_inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_requested_payload("npc-funday"),
                )
            )
        )
        result_message = await _recv_message_type(
            first_client,
            ServerMessageType.INTERACTION_RESULT,
        )
        inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )

    initial_quantities = {
        item.item_id: item.quantity
        for item in inventory_items_from_payload(initial_inventory_message.payload)
    }
    quantities = {item.item_id: item.quantity for item in inventory_items_from_payload(
        inventory_message.payload
    )}
    assert result_message.payload["actor_id"] == first_id
    assert result_message.payload["target_id"] == "npc-funday"
    assert result_message.payload["text"] == "Иди и поймай мне рыбу"
    assert initial_quantities[FISH_ITEM_ID] == 2
    assert quantities[FISH_ITEM_ID] == 2
    assert quantities[FISHING_ROD_ITEM_ID] == 1
    assert GOLD_ITEM_ID not in quantities
    assert multiplayer_server.character_repository.item_quantity("Alice", FISH_ITEM_ID) == 2
    assert multiplayer_server.character_repository.item_quantity("Alice", GOLD_ITEM_ID) == 0


async def _fishing_stack_overflow_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет отказ рыбалки при полном стаке рыбы.
    """
    multiplayer_server = _server_for_test(
        tmp_path,
        raw_map=_open_map_with_water(),
        random_source=random.Random(1),
    )
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", FISHING_ROD_ITEM_ID)
    multiplayer_server.character_repository.equip_item("Alice", FISHING_ROD_ITEM_ID)
    multiplayer_server.character_repository.add_item("Alice", FISH_ITEM_ID, quantity=999)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        await _recv_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_tile_requested_payload(2, 1),
                )
            )
        )
        result_message = await _recv_message_type(
            first_client,
            ServerMessageType.INTERACTION_RESULT,
        )
        await _assert_no_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

    assert result_message.payload["actor_id"] == first_id
    assert result_message.payload["target_id"] == first_id
    assert result_message.payload["text"] == "Инвентарь полон"
    assert multiplayer_server.character_repository.item_quantity("Alice", FISH_ITEM_ID) == 999


async def _exchange_stack_overflow_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет отказ обмена при полном стаке Gold.
    """
    multiplayer_server = _server_for_test(
        tmp_path,
        raw_map=_open_map_with_entities(npc_position=[64, 32]),
    )
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", FISHING_ROD_ITEM_ID)
    multiplayer_server.character_repository.add_item("Alice", FISH_ITEM_ID, quantity=2)
    multiplayer_server.character_repository.add_item("Alice", GOLD_ITEM_ID, quantity=999)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        await _recv_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_requested_payload("npc-funday"),
                )
            )
        )
        result_message = await _recv_message_type(
            first_client,
            ServerMessageType.INTERACTION_RESULT,
        )
        await _assert_no_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

    assert result_message.payload["actor_id"] == first_id
    assert result_message.payload["target_id"] == "npc-funday"
    assert result_message.payload["text"] == "Инвентарь полон"
    assert multiplayer_server.character_repository.item_quantity("Alice", FISH_ITEM_ID) == 2
    assert multiplayer_server.character_repository.item_quantity("Alice", GOLD_ITEM_ID) == 999


async def _jack_lumber_grants_axe_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет успешное взаимодействие с Jack Lumber без топора.
    """
    multiplayer_server = _server_for_test(tmp_path, raw_map=_open_map_with_jack_lumber())

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_requested_payload("npc-jack-lumber"),
                )
            )
        )
        message = await _recv_message_type(first_client, ServerMessageType.INTERACTION_RESULT)
        inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )

    inventory = inventory_items_from_payload(inventory_message.payload)
    assert message.payload["actor_id"] == first_id
    assert message.payload["target_id"] == "npc-jack-lumber"
    assert message.payload["target_name"] == "Jack Lumber"
    assert message.payload["text"] == "Наруби немного древесины"
    assert len(inventory) == 1
    assert inventory[0].item_id == LUMBER_AXE_ITEM_ID
    assert inventory[0].quantity == 1
    assert multiplayer_server.character_repository.load_inventory("Alice") == inventory


async def _lumberjacking_requires_axe_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет ответ на рубку без топора.
    """
    multiplayer_server = _server_for_test(tmp_path, raw_map=_open_map_with_tree())

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_tile_requested_payload(2, 1),
                )
            )
        )
        message = await _recv_message_type(first_client, ServerMessageType.INTERACTION_RESULT)

    assert message.payload["actor_id"] == first_id
    assert message.payload["target_id"] == first_id
    assert message.payload["target_name"] == "Alice"
    assert message.payload["text"] == "Нужен топор в руке"
    assert message.payload["add_to_journal"] is False
    assert multiplayer_server.character_repository.load_inventory("Alice") == []


async def _lumberjacking_success_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет успешное получение бревна из тайла дерева.
    """
    multiplayer_server = _server_for_test(tmp_path, raw_map=_open_map_with_tree())
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", LUMBER_AXE_ITEM_ID)
    multiplayer_server.character_repository.equip_item("Alice", LUMBER_AXE_ITEM_ID)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        await _recv_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_tile_requested_payload(2, 1),
                )
            )
        )
        inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )
        result_message = await _recv_message_type(
            first_client,
            ServerMessageType.INTERACTION_RESULT,
        )

    inventory = inventory_items_from_payload(inventory_message.payload)
    quantities = {item.item_id: item.quantity for item in inventory}
    assert result_message.payload["actor_id"] == first_id
    assert result_message.payload["target_id"] == first_id
    assert result_message.payload["text"] == "Вы нарубили древесины"
    assert result_message.payload["add_to_journal"] is True
    assert quantities[LUMBER_AXE_ITEM_ID] == 1
    assert quantities[LOG_ITEM_ID] == 1
    assert multiplayer_server.character_repository.item_quantity("Alice", LOG_ITEM_ID) == 1


async def _gathering_shared_cooldown_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет общий cooldown между рыбалкой и рубкой.
    """
    multiplayer_server = _server_for_test(
        tmp_path,
        raw_map=_open_map_with_water_and_tree(),
        random_source=random.Random(1),
    )
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", FISHING_ROD_ITEM_ID)
    multiplayer_server.character_repository.add_item("Alice", LUMBER_AXE_ITEM_ID)
    multiplayer_server.character_repository.equip_item("Alice", FISHING_ROD_ITEM_ID)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        await _recv_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_tile_requested_payload(2, 1),
                )
            )
        )
        await _recv_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)
        fishing_result = await _recv_message_type(
            first_client,
            ServerMessageType.INTERACTION_RESULT,
        )
        multiplayer_server.character_repository.equip_item("Alice", LUMBER_AXE_ITEM_ID)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_tile_requested_payload(2, 2),
                )
            )
        )
        await _assert_no_message_type(first_client, ServerMessageType.INTERACTION_RESULT)

    assert fishing_result.payload["actor_id"] == first_id
    assert fishing_result.payload["text"] == "Вы поймали рыбу"
    assert multiplayer_server.character_repository.item_quantity("Alice", FISH_ITEM_ID) == 1
    assert multiplayer_server.character_repository.item_quantity("Alice", LOG_ITEM_ID) == 0


async def _jack_lumber_exchange_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет сдачу пяти бревен NPC Jack Lumber.
    """
    multiplayer_server = _server_for_test(tmp_path, raw_map=_open_map_with_jack_lumber())
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", LUMBER_AXE_ITEM_ID)
    multiplayer_server.character_repository.add_item("Alice", LOG_ITEM_ID, quantity=5)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        await _recv_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_requested_payload("npc-jack-lumber"),
                )
            )
        )
        result_message = await _recv_message_type(
            first_client,
            ServerMessageType.INTERACTION_RESULT,
        )
        inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )

    inventory = inventory_items_from_payload(inventory_message.payload)
    quantities = {item.item_id: item.quantity for item in inventory}
    assert result_message.payload["actor_id"] == first_id
    assert result_message.payload["target_id"] == "npc-jack-lumber"
    assert result_message.payload["target_name"] == "Jack Lumber"
    assert result_message.payload["text"] == "Отличная древесина. Держи Gold."
    assert quantities[LUMBER_AXE_ITEM_ID] == 1
    assert quantities[GOLD_ITEM_ID] == 1
    assert LOG_ITEM_ID not in quantities
    assert multiplayer_server.character_repository.item_quantity("Alice", LOG_ITEM_ID) == 0
    assert multiplayer_server.character_repository.item_quantity("Alice", GOLD_ITEM_ID) == 1


async def _jack_lumber_grants_axe_before_exchange_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет приоритет выдачи топора над обменом бревен.
    """
    multiplayer_server = _server_for_test(tmp_path, raw_map=_open_map_with_jack_lumber())
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", LOG_ITEM_ID, quantity=5)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        initial_inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_requested_payload("npc-jack-lumber"),
                )
            )
        )
        result_message = await _recv_message_type(
            first_client,
            ServerMessageType.INTERACTION_RESULT,
        )
        inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )

    initial_quantities = {
        item.item_id: item.quantity
        for item in inventory_items_from_payload(initial_inventory_message.payload)
    }
    quantities = {
        item.item_id: item.quantity
        for item in inventory_items_from_payload(inventory_message.payload)
    }
    assert result_message.payload["actor_id"] == first_id
    assert result_message.payload["target_id"] == "npc-jack-lumber"
    assert result_message.payload["text"] == "Наруби немного древесины"
    assert initial_quantities[LOG_ITEM_ID] == 5
    assert quantities[LOG_ITEM_ID] == 5
    assert quantities[LUMBER_AXE_ITEM_ID] == 1
    assert GOLD_ITEM_ID not in quantities
    assert multiplayer_server.character_repository.item_quantity("Alice", LOG_ITEM_ID) == 5
    assert multiplayer_server.character_repository.item_quantity("Alice", GOLD_ITEM_ID) == 0


async def _kopai_grants_pickaxe_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет успешное взаимодействие с Kopai без кирки.
    """
    multiplayer_server = _server_for_test(tmp_path, raw_map=_open_map_with_kopai())

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_requested_payload("npc-kopai"),
                )
            )
        )
        message = await _recv_message_type(first_client, ServerMessageType.INTERACTION_RESULT)
        inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )

    inventory = inventory_items_from_payload(inventory_message.payload)
    assert message.payload["actor_id"] == first_id
    assert message.payload["target_id"] == "npc-kopai"
    assert message.payload["target_name"] == "Kopai"
    assert message.payload["text"] == "Накопай мне чего-нибудь"
    assert len(inventory) == 1
    assert inventory[0].item_id == PICKAXE_ITEM_ID
    assert inventory[0].quantity == 1
    assert multiplayer_server.character_repository.load_inventory("Alice") == inventory


async def _mining_requires_pickaxe_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет ответ на добычу камня без кирки.
    """
    multiplayer_server = _server_for_test(tmp_path, raw_map=_open_map_with_rock())

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_tile_requested_payload(2, 1),
                )
            )
        )
        message = await _recv_message_type(first_client, ServerMessageType.INTERACTION_RESULT)

    assert message.payload["actor_id"] == first_id
    assert message.payload["target_id"] == first_id
    assert message.payload["target_name"] == "Alice"
    assert message.payload["text"] == "Нужна кирка в руке"
    assert message.payload["add_to_journal"] is False
    assert multiplayer_server.character_repository.load_inventory("Alice") == []


async def _mining_success_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет успешное получение камня из тайла rock.
    """
    multiplayer_server = _server_for_test(
        tmp_path,
        raw_map=_open_map_with_rock(),
        random_source=random.Random(1),
    )
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", PICKAXE_ITEM_ID)
    multiplayer_server.character_repository.equip_item("Alice", PICKAXE_ITEM_ID)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        await _recv_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_tile_requested_payload(2, 1),
                )
            )
        )
        inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )
        result_message = await _recv_message_type(
            first_client,
            ServerMessageType.INTERACTION_RESULT,
        )

    inventory = inventory_items_from_payload(inventory_message.payload)
    quantities = {item.item_id: item.quantity for item in inventory}
    assert result_message.payload["actor_id"] == first_id
    assert result_message.payload["target_id"] == first_id
    assert result_message.payload["text"] == "Вы добыли камень"
    assert result_message.payload["add_to_journal"] is True
    assert quantities[PICKAXE_ITEM_ID] == 1
    assert quantities[STONE_ITEM_ID] == 1
    assert multiplayer_server.character_repository.item_quantity("Alice", STONE_ITEM_ID) == 1


async def _mining_failure_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет неудачную попытку добычи камня.
    """
    multiplayer_server = _server_for_test(
        tmp_path,
        raw_map=_open_map_with_rock(),
        random_source=random.Random(0),
    )
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", PICKAXE_ITEM_ID)
    multiplayer_server.character_repository.equip_item("Alice", PICKAXE_ITEM_ID)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        await _recv_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_tile_requested_payload(2, 1),
                )
            )
        )
        result_message = await _recv_message_type(
            first_client,
            ServerMessageType.INTERACTION_RESULT,
        )
        await _assert_no_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

    assert result_message.payload["actor_id"] == first_id
    assert result_message.payload["target_id"] == first_id
    assert result_message.payload["text"] == "Не удалось добыть камень"
    assert result_message.payload["add_to_journal"] is True
    assert multiplayer_server.character_repository.item_quantity("Alice", STONE_ITEM_ID) == 0


async def _kopai_exchange_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет сдачу трех камней NPC Kopai.
    """
    multiplayer_server = _server_for_test(tmp_path, raw_map=_open_map_with_kopai())
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", PICKAXE_ITEM_ID)
    multiplayer_server.character_repository.add_item("Alice", STONE_ITEM_ID, quantity=3)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        await _recv_message_type(first_client, ServerMessageType.INVENTORY_UPDATED)

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_requested_payload("npc-kopai"),
                )
            )
        )
        result_message = await _recv_message_type(
            first_client,
            ServerMessageType.INTERACTION_RESULT,
        )
        inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )

    inventory = inventory_items_from_payload(inventory_message.payload)
    quantities = {item.item_id: item.quantity for item in inventory}
    assert result_message.payload["actor_id"] == first_id
    assert result_message.payload["target_id"] == "npc-kopai"
    assert result_message.payload["target_name"] == "Kopai"
    assert result_message.payload["text"] == "Отличный камень. Держи Gold."
    assert quantities[PICKAXE_ITEM_ID] == 1
    assert quantities[GOLD_ITEM_ID] == 1
    assert STONE_ITEM_ID not in quantities
    assert multiplayer_server.character_repository.item_quantity("Alice", STONE_ITEM_ID) == 0
    assert multiplayer_server.character_repository.item_quantity("Alice", GOLD_ITEM_ID) == 1


async def _kopai_grants_pickaxe_before_exchange_smoke(tmp_path: Path) -> None:
    """
    Запускает сервер и проверяет приоритет выдачи кирки над обменом камня.
    """
    multiplayer_server = _server_for_test(tmp_path, raw_map=_open_map_with_kopai())
    multiplayer_server.character_repository.load_or_create("Alice", Vec2(32, 32))
    multiplayer_server.character_repository.add_item("Alice", STONE_ITEM_ID, quantity=3)

    async with _running_test_server(multiplayer_server) as uri, connect(uri) as first_client:
        await _send_join(first_client, "Alice")
        first_id = await _recv_player_id(first_client)
        initial_inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )

        await first_client.send(
            encode_message(
                ProtocolMessage(
                    type=ClientMessageType.INTERACT_REQUESTED,
                    payload=interact_requested_payload("npc-kopai"),
                )
            )
        )
        result_message = await _recv_message_type(
            first_client,
            ServerMessageType.INTERACTION_RESULT,
        )
        inventory_message = await _recv_message_type(
            first_client,
            ServerMessageType.INVENTORY_UPDATED,
        )

    initial_quantities = {
        item.item_id: item.quantity
        for item in inventory_items_from_payload(initial_inventory_message.payload)
    }
    quantities = {
        item.item_id: item.quantity
        for item in inventory_items_from_payload(inventory_message.payload)
    }
    assert result_message.payload["actor_id"] == first_id
    assert result_message.payload["target_id"] == "npc-kopai"
    assert result_message.payload["text"] == "Накопай мне чего-нибудь"
    assert initial_quantities[STONE_ITEM_ID] == 3
    assert quantities[STONE_ITEM_ID] == 3
    assert quantities[PICKAXE_ITEM_ID] == 1
    assert GOLD_ITEM_ID not in quantities
    assert multiplayer_server.character_repository.item_quantity("Alice", STONE_ITEM_ID) == 3
    assert multiplayer_server.character_repository.item_quantity("Alice", GOLD_ITEM_ID) == 0


@contextlib.asynccontextmanager
async def _running_test_server(multiplayer_server: MultiplayerServer):
    """
    Запускает тестовый websocket-сервер и игровой цикл на время блока.
    """
    async with serve(multiplayer_server._handle_connection, "127.0.0.1", 0) as websocket_server:
        sockets = websocket_server.sockets
        assert sockets is not None
        port = sockets[0].getsockname()[1]
        game_loop = asyncio.create_task(multiplayer_server._game_loop())
        try:
            yield f"ws://127.0.0.1:{port}"
        finally:
            game_loop.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await game_loop


def _server_for_test(
    tmp_path: Path,
    raw_map: object | None = None,
    random_source: random.Random | None = None,
) -> MultiplayerServer:
    """
    Создает тестовый сервер с временной SQLite-базой.
    """
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    repository.initialize()
    return MultiplayerServer(
        world=MultiplayerWorld(tile_map=tile_map_from_dict(raw_map or _open_map())),
        character_repository=repository,
        tick_rate=30.0,
        snapshot_rate=20.0,
        random_source=random_source,
    )


class _FailingWebSocket:
    """
    Имитирует websocket, который падает при первой отправке сообщения.
    """

    async def recv(self) -> str:
        """
        Возвращает корректный join_requested перед падением отправки.
        """
        return encode_message(
            ProtocolMessage(
                type=ClientMessageType.JOIN_REQUESTED,
                payload=join_request_payload("Alice"),
            )
        )

    async def send(self, message: str) -> NoReturn:
        """
        Всегда выбрасывает ошибку соединения при отправке сообщения.
        """
        raise ConnectionError("connection closed before first server message")


async def _send_join(websocket: object, name: str) -> None:
    """
    Отправляет join_requested для тестового websocket-клиента.
    """
    await websocket.send(
        encode_message(
            ProtocolMessage(
                type=ClientMessageType.JOIN_REQUESTED,
                payload=join_request_payload(name),
            )
        )
    )


async def _recv_player_id(websocket: object) -> str:
    """
    Получает сообщение connection_accepted и возвращает назначенный id игрока.
    """
    message = decode_message(await websocket.recv())
    assert message.type == ServerMessageType.CONNECTION_ACCEPTED
    player_id = message.payload.get("player_id")
    assert isinstance(player_id, str)
    return player_id


async def _recv_snapshot(websocket: object, expected_players: int) -> list[PlayerState]:
    """
    Получает snapshot-ы мира, пока один из них не содержит ожидаемое число игроков.
    """
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        message = decode_message(await asyncio.wait_for(websocket.recv(), timeout=0.5))
        if message.type != ServerMessageType.WORLD_SNAPSHOT:
            continue
        players = players_from_snapshot_payload(message.payload)
        if len(players) >= expected_players:
            return players

    msg = "server did not broadcast a complete world snapshot in time"
    raise AssertionError(msg)


async def _recv_message_type(
    websocket: object,
    message_type: ServerMessageType,
) -> ProtocolMessage:
    """
    Получает сообщения, пока не придет сообщение нужного серверного типа.
    """
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        message = decode_message(await asyncio.wait_for(websocket.recv(), timeout=0.5))
        if message.type == message_type:
            return message

    msg = f"server did not send {message_type} in time"
    raise AssertionError(msg)


async def _assert_no_message_type(
    websocket: object,
    message_type: ServerMessageType,
) -> None:
    """
    Проверяет, что за короткое время websocket не получает сообщение нужного типа.
    """
    deadline = time.monotonic() + 0.25
    while time.monotonic() < deadline:
        try:
            raw_message = await asyncio.wait_for(websocket.recv(), timeout=0.05)
        except TimeoutError:
            continue
        message = decode_message(raw_message)
        if message.type == message_type:
            msg = f"server unexpectedly sent {message_type}"
            raise AssertionError(msg)


async def _recv_moved_player(
    websocket: object,
    player_id: str,
    initial_player: PlayerState,
    expected_players: int = 2,
) -> PlayerState:
    """
    Получает snapshot-ы, пока нужный игрок не сдвинется вправо.
    """
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        players = await _recv_snapshot(websocket, expected_players=expected_players)
        moved_player = _find_player(players, player_id)
        if moved_player.position.x > initial_player.position.x:
            return moved_player

    msg = "server did not broadcast moved player in time"
    raise AssertionError(msg)


async def _wait_for_world_player_count(
    multiplayer_server: MultiplayerServer,
    expected_players: int,
) -> None:
    """
    Ждет, пока runtime-мир сервера не будет содержать ожидаемое число игроков.
    """
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if len(multiplayer_server.world.players) == expected_players:
            return
        await asyncio.sleep(0.01)

    msg = f"server world did not reach {expected_players} players in time"
    raise AssertionError(msg)


def _find_player(players: list[PlayerState], player_id: str) -> PlayerState:
    """
    Возвращает игрока с нужным id из списка snapshot-а.
    """
    for player in players:
        if player.entity_id == player_id:
            return player

    msg = f"player {player_id!r} was not found in snapshot"
    raise AssertionError(msg)
