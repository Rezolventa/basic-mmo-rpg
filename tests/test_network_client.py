from __future__ import annotations

import asyncio
import contextlib
import time

from websockets.asyncio.server import serve

from basic_mmo_rpg.client.network import NetworkClient
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState
from basic_mmo_rpg.server.app import MultiplayerServer
from basic_mmo_rpg.server.world import MultiplayerWorld
from basic_mmo_rpg.shared.protocol import ServerMessageType, players_from_snapshot_payload
from basic_mmo_rpg.storage.map_loader import tile_map_from_dict


def _open_map() -> object:
    """
    Возвращает открытую карту для тестирования фонового сетевого клиента.
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


def test_network_client_connects_and_receives_authoritative_snapshots() -> None:
    """
    Проверяет, что NetworkClient подключается к серверу и получает snapshot-ы.
    """
    asyncio.run(_network_client_smoke())


async def _network_client_smoke() -> None:
    """
    Запускает сервер и проверяет обмен сообщениями через NetworkClient.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))
    multiplayer_server = MultiplayerServer(world=world, tick_rate=30.0, snapshot_rate=20.0)

    async with serve(multiplayer_server._handle_connection, "127.0.0.1", 0) as websocket_server:
        sockets = websocket_server.sockets
        assert sockets is not None
        port = sockets[0].getsockname()[1]
        network_client = NetworkClient(f"ws://127.0.0.1:{port}", reconnect_delay=0.1)
        game_loop = asyncio.create_task(multiplayer_server._game_loop())

        try:
            network_client.start()
            player_id = await _wait_for_player_id(network_client)
            initial_player = await _wait_for_player(network_client, player_id)

            network_client.send_movement_intent(MovementIntent(right=True))
            moved_player = await _wait_for_moved_player(network_client, player_id, initial_player)

            assert moved_player.position.x > initial_player.position.x
        finally:
            network_client.stop()
            game_loop.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await game_loop


async def _wait_for_player_id(network_client: NetworkClient) -> str:
    """
    Ждет, пока сетевой клиент получит назначенный id игрока.
    """
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        for message in network_client.drain_messages():
            if message.type != ServerMessageType.CONNECTION_ACCEPTED:
                continue
            player_id = message.payload.get("player_id")
            assert isinstance(player_id, str)
            return player_id
        await asyncio.sleep(0.01)

    msg = "NetworkClient did not receive player id in time"
    raise AssertionError(msg)


async def _wait_for_player(network_client: NetworkClient, player_id: str) -> PlayerState:
    """
    Ждет, пока snapshot будет содержать нужного игрока.
    """
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        for message in network_client.drain_messages():
            if message.type != ServerMessageType.WORLD_SNAPSHOT:
                continue
            for player in players_from_snapshot_payload(message.payload):
                if player.entity_id == player_id:
                    return player
        await asyncio.sleep(0.01)

    msg = "NetworkClient did not receive player snapshot in time"
    raise AssertionError(msg)


async def _wait_for_moved_player(
    network_client: NetworkClient,
    player_id: str,
    initial_player: PlayerState,
) -> PlayerState:
    """
    Ждет, пока snapshot покажет, что нужный игрок сдвинулся вправо.
    """
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        player = await _wait_for_player(network_client, player_id)
        if player.position.x > initial_player.position.x:
            return player

    msg = "NetworkClient did not receive moved player in time"
    raise AssertionError(msg)
