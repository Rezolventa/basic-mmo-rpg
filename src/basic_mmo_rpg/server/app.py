from __future__ import annotations

import argparse
import asyncio
import contextlib
import time
import uuid
from pathlib import Path

from websockets.asyncio.server import ServerConnection, serve

from basic_mmo_rpg.server.world import MultiplayerWorld
from basic_mmo_rpg.shared.protocol import (
    ClientMessageType,
    ProtocolError,
    ProtocolMessage,
    ServerMessageType,
    decode_message,
    encode_message,
    movement_intent_from_payload,
)
from basic_mmo_rpg.storage.map_loader import load_tile_map

DEFAULT_MAP_PATH = Path(__file__).resolve().parents[3] / "assets" / "maps" / "starter_map.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TICK_RATE = 30.0
DEFAULT_SNAPSHOT_RATE = 20.0


class MultiplayerServer:
    """
    Принимает websocket-клиентов и связывает сетевые сообщения с authoritative-миром.
    """

    def __init__(
        self,
        world: MultiplayerWorld,
        tick_rate: float = DEFAULT_TICK_RATE,
        snapshot_rate: float = DEFAULT_SNAPSHOT_RATE,
    ) -> None:
        """
        Инициализирует состояние сервера, настройки таймингов и хранилище подключений.
        """
        self.world = world
        self.tick_rate = tick_rate
        self.snapshot_rate = snapshot_rate
        self.connections: dict[str, ServerConnection] = {}

    async def run(self, host: str, port: int) -> None:
        """
        Запускает websocket-listener и authoritative-цикл симуляции.
        """
        async with serve(self._handle_connection, host, port):
            print(f"Server listening on ws://{host}:{port}")
            await self._game_loop()

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        """
        Регистрирует одного websocket-клиента и обрабатывает его входящие сообщения.
        """
        player_id = self._new_player_id()
        self.world.add_player(player_id)
        self.connections[player_id] = websocket

        try:
            await self._send(
                websocket,
                ProtocolMessage(
                    type=ServerMessageType.CONNECTION_ACCEPTED,
                    payload={"player_id": player_id},
                ),
            )
            await self._broadcast_snapshot()

            async for raw_message in websocket:
                await self._handle_raw_message(player_id, raw_message)
        finally:
            self.world.remove_player(player_id)
            self.connections.pop(player_id, None)
            await self._broadcast(
                ProtocolMessage(
                    type=ServerMessageType.ENTITY_REMOVED,
                    payload={"id": player_id},
                )
            )
            await self._broadcast_snapshot()

    async def _handle_raw_message(self, player_id: str, raw_message: str | bytes) -> None:
        """
        Декодирует и применяет одно клиентское сообщение подключенного игрока.
        """
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")

        try:
            message = decode_message(raw_message)
            if message.type == ClientMessageType.MOVE_REQUESTED:
                self.world.set_intent(player_id, movement_intent_from_payload(message.payload))
        except (ProtocolError, UnicodeDecodeError) as exc:
            await self._send_error(player_id, str(exc))

    async def _game_loop(self) -> None:
        """
        Продвигает мир с фиксированной частотой тиков и периодически рассылает snapshot-ы.
        """
        tick_interval = 1.0 / self.tick_rate
        snapshot_interval = 1.0 / self.snapshot_rate
        previous_time = time.monotonic()
        snapshot_elapsed = 0.0

        while True:
            await asyncio.sleep(tick_interval)
            current_time = time.monotonic()
            delta_seconds = min(current_time - previous_time, 0.1)
            previous_time = current_time

            self.world.tick(delta_seconds)
            snapshot_elapsed += delta_seconds

            if snapshot_elapsed >= snapshot_interval:
                snapshot_elapsed = 0.0
                await self._broadcast_snapshot()

    async def _broadcast_snapshot(self) -> None:
        """
        Отправляет текущий authoritative snapshot мира всем подключенным клиентам.
        """
        if not self.connections:
            return

        await self._broadcast(
            ProtocolMessage(
                type=ServerMessageType.WORLD_SNAPSHOT,
                payload=self.world.snapshot_payload(),
            )
        )

    async def _broadcast(self, message: ProtocolMessage) -> None:
        """
        Отправляет одно протокольное сообщение всем текущим подключенным клиентам.
        """
        sends = [self._send(connection, message) for connection in list(self.connections.values())]
        if sends:
            await asyncio.gather(*sends, return_exceptions=True)

    async def _send(self, websocket: ServerConnection, message: ProtocolMessage) -> None:
        """
        Отправляет одно закодированное протокольное сообщение одному websocket-клиенту.
        """
        await websocket.send(encode_message(message))

    async def _send_error(self, player_id: str, error_message: str) -> None:
        """
        Отправляет ответ с протокольной ошибкой одному подключенному клиенту.
        """
        websocket = self.connections.get(player_id)
        if websocket is None:
            return

        await self._send(
            websocket,
            ProtocolMessage(
                type=ServerMessageType.ERROR,
                payload={"message": error_message},
            ),
        )

    def _new_player_id(self) -> str:
        """
        Создает короткий уникальный id для нового подключенного игрока.
        """
        return f"player-{uuid.uuid4().hex[:8]}"


def parse_args() -> argparse.Namespace:
    """
    Разбирает аргументы командной строки для multiplayer-сервера.
    """
    parser = argparse.ArgumentParser(description="Run the authoritative 2D RPG server.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host/IP for the websocket server.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Websocket server port.")
    parser.add_argument(
        "--map",
        type=Path,
        default=DEFAULT_MAP_PATH,
        help=f"Path to a prototype JSON map. Defaults to {DEFAULT_MAP_PATH}.",
    )
    parser.add_argument("--tick-rate", type=float, default=DEFAULT_TICK_RATE)
    parser.add_argument("--snapshot-rate", type=float, default=DEFAULT_SNAPSHOT_RATE)
    return parser.parse_args()


async def async_main(args: argparse.Namespace) -> None:
    """
    Создает мир и асинхронно запускает multiplayer-сервер.
    """
    tile_map = load_tile_map(args.map)
    server = MultiplayerServer(
        world=MultiplayerWorld(tile_map=tile_map),
        tick_rate=args.tick_rate,
        snapshot_rate=args.snapshot_rate,
    )
    await server.run(args.host, args.port)


def main() -> None:
    """
    Запускает multiplayer-сервер до остановки пользователем.
    """
    args = parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
