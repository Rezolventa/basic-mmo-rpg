from __future__ import annotations

import asyncio
import contextlib
import time

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState
from basic_mmo_rpg.server.app import MultiplayerServer
from basic_mmo_rpg.server.world import MultiplayerWorld
from basic_mmo_rpg.shared.protocol import (
    ClientMessageType,
    ProtocolMessage,
    ServerMessageType,
    decode_message,
    encode_message,
    movement_intent_to_payload,
    players_from_snapshot_payload,
)
from basic_mmo_rpg.storage.map_loader import tile_map_from_dict


def _open_map() -> object:
    """
    Возвращает открытую карту для websocket-интеграционного теста.
    """
    return {
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


def test_websocket_server_accepts_two_clients_and_broadcasts_movement() -> None:
    """
    Проверяет websocket-сценарий с двумя клиентами и серверной обработкой движения.
    """
    asyncio.run(_websocket_server_smoke())


async def _websocket_server_smoke() -> None:
    """
    Запускает сервер на временном порту и проверяет обмен snapshot-ами.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))
    multiplayer_server = MultiplayerServer(world=world, tick_rate=30.0, snapshot_rate=20.0)

    async with serve(multiplayer_server._handle_connection, "127.0.0.1", 0) as websocket_server:
        sockets = websocket_server.sockets
        assert sockets is not None
        port = sockets[0].getsockname()[1]
        uri = f"ws://127.0.0.1:{port}"

        game_loop = asyncio.create_task(multiplayer_server._game_loop())
        try:
            async with connect(uri) as first_client, connect(uri) as second_client:
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


async def _recv_moved_player(
    websocket: object,
    player_id: str,
    initial_player: PlayerState,
) -> PlayerState:
    """
    Получает snapshot-ы, пока нужный игрок не сдвинется вправо.
    """
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        players = await _recv_snapshot(websocket, expected_players=2)
        moved_player = _find_player(players, player_id)
        if moved_player.position.x > initial_player.position.x:
            return moved_player

    msg = "server did not broadcast moved player in time"
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
