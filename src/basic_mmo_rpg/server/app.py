from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from websockets.asyncio.server import ServerConnection, serve

from basic_mmo_rpg.domain.entities import EntityKind
from basic_mmo_rpg.server.world import MultiplayerWorld
from basic_mmo_rpg.shared.protocol import (
    ClientMessageType,
    ProtocolError,
    ProtocolMessage,
    ServerMessageType,
    character_name_from_payload,
    chat_message_payload,
    chat_text_from_payload,
    decode_message,
    encode_message,
    interaction_result_payload,
    interaction_target_from_payload,
    movement_intent_from_payload,
)
from basic_mmo_rpg.storage.characters import CharacterRepository
from basic_mmo_rpg.storage.map_loader import load_tile_map

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MAP_PATH = PROJECT_ROOT / "assets" / "maps" / "starter_map.json"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "game.sqlite3"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TICK_RATE = 30.0
DEFAULT_SNAPSHOT_RATE = 20.0
DEFAULT_SAVE_INTERVAL = 5.0
JOIN_TIMEOUT_SECONDS = 5.0

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PlayerSession:
    """
    Хранит связь websocket-сессии с активным персонажем.
    """

    session_id: str
    player_id: str
    character_name: str
    websocket: ServerConnection


class MultiplayerServer:
    """
    Принимает websocket-клиентов и связывает сетевые сообщения с authoritative-миром.
    """

    def __init__(
        self,
        world: MultiplayerWorld,
        character_repository: CharacterRepository,
        tick_rate: float = DEFAULT_TICK_RATE,
        snapshot_rate: float = DEFAULT_SNAPSHOT_RATE,
        save_interval: float = DEFAULT_SAVE_INTERVAL,
    ) -> None:
        """
        Инициализирует состояние сервера, настройки таймингов и хранилище подключений.
        """
        self.world = world
        self.character_repository = character_repository
        self.tick_rate = tick_rate
        self.snapshot_rate = snapshot_rate
        self.save_interval = save_interval
        self.connections: dict[str, ServerConnection] = {}
        self.sessions: dict[str, PlayerSession] = {}
        self.active_character_sessions: dict[str, str] = {}

    async def run(self, host: str, port: int) -> None:
        """
        Запускает websocket-listener и authoritative-цикл симуляции.
        """
        async with serve(self._handle_connection, host, port):
            logger.info("Server listening on ws://%s:%s", host, port)
            await self._game_loop()

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        """
        Авторизует websocket-клиента по имени персонажа и обрабатывает его сообщения.
        """
        session: PlayerSession | None = None
        try:
            character_name = await self._receive_join_request(websocket)
            await self._kick_existing_character(character_name)
            session = self._create_session(websocket, character_name)

            await self._send(
                websocket,
                ProtocolMessage(
                    type=ServerMessageType.CONNECTION_ACCEPTED,
                    payload={
                        "player_id": session.player_id,
                        "name": session.character_name,
                    },
                ),
            )
            await self._broadcast_snapshot()

            async for raw_message in websocket:
                await self._handle_raw_message(session, raw_message)
        finally:
            if session is not None:
                await self._cleanup_session(session)

    async def _receive_join_request(self, websocket: ServerConnection) -> str:
        """
        Получает первое join_requested-сообщение и возвращает имя персонажа.
        """
        try:
            raw_message = await asyncio.wait_for(websocket.recv(), timeout=JOIN_TIMEOUT_SECONDS)
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8")
            message = decode_message(raw_message)
            if message.type != ClientMessageType.JOIN_REQUESTED:
                msg = "first message must be join_requested"
                raise ProtocolError(msg)
            return character_name_from_payload(message.payload)
        except (ProtocolError, UnicodeDecodeError, TimeoutError) as exc:
            await self._send_protocol_error(websocket, str(exc))
            logger.warning("Join rejected: %s", exc)
            raise

    def _create_session(self, websocket: ServerConnection, character_name: str) -> PlayerSession:
        """
        Создает активную сессию персонажа и добавляет его в мир.
        """
        player_id = self._new_player_id()
        session_id = uuid.uuid4().hex
        character = self.character_repository.load_or_create(
            name=character_name,
            default_position=self.world.tile_map.spawn,
        )
        self.world.add_player(player_id, character_name, character.position)

        session = PlayerSession(
            session_id=session_id,
            player_id=player_id,
            character_name=character_name,
            websocket=websocket,
        )
        self.sessions[session_id] = session
        self.active_character_sessions[character_name] = session_id
        self.connections[player_id] = websocket
        logger.info("Player joined: name=%s player_id=%s", character_name, player_id)
        return session

    async def _kick_existing_character(self, character_name: str) -> None:
        """
        Отключает старую сессию персонажа, если он уже находится в мире.
        """
        session_id = self.active_character_sessions.get(character_name)
        if session_id is None:
            return

        session = self.sessions.get(session_id)
        if session is None:
            self.active_character_sessions.pop(character_name, None)
            return

        self._save_session_position(session)
        self._remove_session_state(session)
        logger.info("Player kicked by reconnect: name=%s", character_name)
        with contextlib.suppress(Exception):
            await self._send(
                session.websocket,
                ProtocolMessage(
                    type=ServerMessageType.ERROR,
                    payload={"message": "character connected elsewhere"},
                ),
            )
        with contextlib.suppress(Exception):
            await session.websocket.close(code=4000, reason="character connected elsewhere")
        await self._broadcast_removed(session)
        await self._broadcast_snapshot()

    async def _cleanup_session(self, session: PlayerSession) -> None:
        """
        Сохраняет позицию и удаляет сессию, если она все еще актуальна.
        """
        if self.active_character_sessions.get(session.character_name) != session.session_id:
            return

        self._save_session_position(session)
        self._remove_session_state(session)
        logger.info("Player left: name=%s player_id=%s", session.character_name, session.player_id)
        await self._broadcast_removed(session)
        await self._broadcast_snapshot()

    def _remove_session_state(self, session: PlayerSession) -> None:
        """
        Удаляет runtime-состояние активной сессии из сервера и мира.
        """
        self.world.remove_player(session.player_id)
        self.connections.pop(session.player_id, None)
        self.sessions.pop(session.session_id, None)
        self.active_character_sessions.pop(session.character_name, None)

    def _save_session_position(self, session: PlayerSession) -> None:
        """
        Сохраняет текущую позицию персонажа, если он еще есть в мире.
        """
        player = self.world.players.get(session.player_id)
        if player is None:
            return
        self.character_repository.save_position(session.character_name, player.position)
        logger.debug(
            "Player position saved: name=%s x=%.2f y=%.2f",
            session.character_name,
            player.position.x,
            player.position.y,
        )

    async def _handle_raw_message(
        self,
        session: PlayerSession,
        raw_message: str | bytes,
    ) -> None:
        """
        Декодирует и применяет одно клиентское сообщение подключенного игрока.
        """
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")

        try:
            message = decode_message(raw_message)
            if message.type == ClientMessageType.MOVE_REQUESTED:
                self.world.set_intent(
                    session.player_id,
                    movement_intent_from_payload(message.payload),
                )
            elif message.type == ClientMessageType.CHAT_SENT:
                await self._handle_chat_message(session, message.payload)
            elif message.type == ClientMessageType.INTERACT_REQUESTED:
                await self._handle_interaction(session, message.payload)
        except (ProtocolError, UnicodeDecodeError) as exc:
            await self._send_error(session.player_id, str(exc))
            logger.warning("Protocol error from %s: %s", session.character_name, exc)

    async def _handle_chat_message(
        self,
        session: PlayerSession,
        payload: dict[str, object],
    ) -> None:
        """
        Проверяет сообщение чата и рассылает его всем клиентам.
        """
        text = chat_text_from_payload(payload)
        logger.info("Chat: %s: %s", session.character_name, text)
        await self._broadcast(
            ProtocolMessage(
                type=ServerMessageType.CHAT_MESSAGE,
                payload=chat_message_payload(
                    player_id=session.player_id,
                    name=session.character_name,
                    text=text,
                    created_at=time.time(),
                ),
            )
        )

    async def _handle_interaction(
        self,
        session: PlayerSession,
        payload: dict[str, object],
    ) -> None:
        """
        Проверяет запрос взаимодействия и отправляет результат только инициатору.
        """
        target_id = interaction_target_from_payload(payload)
        player = self.world.players.get(session.player_id)
        target = self.world.get_entity(target_id)
        if player is None or target is None:
            logger.info(
                "Interaction ignored: name=%s target_id=%s reason=missing_target",
                session.character_name,
                target_id,
            )
            return
        if target.kind != EntityKind.NPC:
            logger.info(
                "Interaction ignored: name=%s target_id=%s reason=unsupported_kind",
                session.character_name,
                target_id,
            )
            return

        distance = (player.center - target.center).length
        if distance > target.interaction_radius:
            logger.info(
                "Interaction ignored: name=%s target_id=%s distance=%.2f radius=%.2f",
                session.character_name,
                target_id,
                distance,
                target.interaction_radius,
            )
            return

        logger.info(
            "Interaction accepted: name=%s target_id=%s",
            session.character_name,
            target_id,
        )
        await self._send(
            session.websocket,
            ProtocolMessage(
                type=ServerMessageType.INTERACTION_RESULT,
                payload=interaction_result_payload(
                    actor_id=session.player_id,
                    target_id=target.entity_id,
                    target_name=target.name,
                    text=target.dialogue,
                    created_at=time.time(),
                ),
            ),
        )

    async def _game_loop(self) -> None:
        """
        Продвигает мир с фиксированной частотой тиков и периодически рассылает snapshot-ы.
        """
        tick_interval = 1.0 / self.tick_rate
        snapshot_interval = 1.0 / self.snapshot_rate
        previous_time = time.monotonic()
        snapshot_elapsed = 0.0
        save_elapsed = 0.0

        while True:
            await asyncio.sleep(tick_interval)
            current_time = time.monotonic()
            delta_seconds = min(current_time - previous_time, 0.1)
            previous_time = current_time

            self.world.tick(delta_seconds)
            snapshot_elapsed += delta_seconds
            save_elapsed += delta_seconds

            if snapshot_elapsed >= snapshot_interval:
                snapshot_elapsed = 0.0
                await self._broadcast_snapshot()
            if save_elapsed >= self.save_interval:
                save_elapsed = 0.0
                self._save_active_positions()

    def _save_active_positions(self) -> None:
        """
        Сохраняет позиции всех актуальных активных сессий.
        """
        for session_id in list(self.active_character_sessions.values()):
            session = self.sessions.get(session_id)
            if session is not None:
                self._save_session_position(session)

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

    async def _broadcast_removed(self, session: PlayerSession) -> None:
        """
        Рассылает событие удаления игрока из мира.
        """
        await self._broadcast(
            ProtocolMessage(
                type=ServerMessageType.ENTITY_REMOVED,
                payload={"id": session.player_id, "name": session.character_name},
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

        await self._send_protocol_error(websocket, error_message)

    async def _send_protocol_error(
        self,
        websocket: ServerConnection,
        error_message: str,
    ) -> None:
        """
        Отправляет протокольную ошибку конкретному websocket-клиенту.
        """
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
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=f"Path to SQLite database. Defaults to {DEFAULT_DATABASE_PATH}.",
    )
    parser.add_argument("--tick-rate", type=float, default=DEFAULT_TICK_RATE)
    parser.add_argument("--snapshot-rate", type=float, default=DEFAULT_SNAPSHOT_RATE)
    parser.add_argument("--save-interval", type=float, default=DEFAULT_SAVE_INTERVAL)
    return parser.parse_args()


async def async_main(args: argparse.Namespace) -> None:
    """
    Создает мир и асинхронно запускает multiplayer-сервер.
    """
    configure_logging()
    tile_map = load_tile_map(args.map)
    character_repository = CharacterRepository(args.database)
    character_repository.initialize()
    server = MultiplayerServer(
        world=MultiplayerWorld(tile_map=tile_map),
        character_repository=character_repository,
        tick_rate=args.tick_rate,
        snapshot_rate=args.snapshot_rate,
        save_interval=args.save_interval,
    )
    await server.run(args.host, args.port)


def configure_logging() -> None:
    """
    Настраивает простой вывод серверных логов в консоль.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    """
    Запускает multiplayer-сервер до остановки пользователем.
    """
    args = parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
