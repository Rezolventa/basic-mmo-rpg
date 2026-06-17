from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path
from typing import NoReturn

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

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
    interact_requested_payload,
    join_request_payload,
    movement_intent_to_payload,
    players_from_snapshot_payload,
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
                "dialogue": "Hello, developer",
                "solid": True,
            }
        ]
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
            await _assert_no_message_type(second_client, ServerMessageType.INTERACTION_RESULT)

        assert message.payload["actor_id"] == first_id
        assert message.payload["target_id"] == "npc-funday"
        assert message.payload["target_name"] == "Funday"
        assert message.payload["text"] == "Hello, developer"


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
