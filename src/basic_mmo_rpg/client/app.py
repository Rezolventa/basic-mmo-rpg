from __future__ import annotations

import argparse
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import pygame

from basic_mmo_rpg.client.camera import Camera
from basic_mmo_rpg.client.network import NetworkClient
from basic_mmo_rpg.client.rendering import Renderer
from basic_mmo_rpg.client.ui import ChatLine, TimedText
from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState, move_player
from basic_mmo_rpg.shared.protocol import (
    ProtocolError,
    ServerMessageType,
    player_snapshots_from_payload,
)
from basic_mmo_rpg.storage.map_loader import load_tile_map

DEFAULT_MAP_PATH = Path(__file__).resolve().parents[3] / "assets" / "maps" / "starter_map.json"
DEFAULT_SERVER_URL = "ws://127.0.0.1:8765"
WINDOW_SIZE = (960, 640)
PLAYER_ID = "local-player"
LOCAL_RECONCILE_RATE = 8.0
LOCAL_RECONCILE_DEAD_ZONE = 3.0
LOCAL_SNAP_DISTANCE = 96.0
REMOTE_INTERPOLATION_RATE = 14.0
REMOTE_INTERPOLATION_DEAD_ZONE = 0.25
REMOTE_SNAP_DISTANCE = 128.0
FLOATING_TEXT_SECONDS = 3.0
MAX_CHAT_LOG_MESSAGES = 50
MAX_CHAT_INPUT_LENGTH = 160


@dataclass(slots=True)
class RemotePlayerView:
    """
    Хранит отображаемое и целевое состояние удаленного игрока для интерполяции.
    """

    name: str
    rendered: PlayerState
    target: PlayerState

    def set_target(self, name: str, target: PlayerState) -> None:
        """
        Обновляет целевое authoritative-состояние удаленного игрока.
        """
        self.name = name
        self.target = target

    def update(self, delta_seconds: float) -> None:
        """
        Плавно приближает отображаемое состояние к последнему server snapshot-у.
        """
        self.rendered = _smooth_player_toward(
            current=self.rendered,
            target=self.target,
            delta_seconds=delta_seconds,
            rate=REMOTE_INTERPOLATION_RATE,
            snap_distance=REMOTE_SNAP_DISTANCE,
            dead_zone=REMOTE_INTERPOLATION_DEAD_ZONE,
        )


class GameClient:
    """
    Управляет pygame-клиентом, локальным рендером и опциональной сетевой игрой.
    """

    def __init__(
        self,
        map_path: Path,
        server_url: str | None = None,
        character_name: str | None = None,
    ) -> None:
        """
        Инициализирует окно, карту, состояние игрока, камеру, рендерер и сетевой режим.
        """
        if server_url is not None and character_name is None:
            msg = "character_name is required for multiplayer mode"
            raise ValueError(msg)

        pygame.init()
        window_title = (
            "Basic MMO RPG - multiplayer MVP" if server_url else "Basic MMO RPG - local MVP"
        )
        pygame.display.set_caption(window_title)

        self.screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.tile_map = load_tile_map(map_path)
        self.local_character_name = character_name or PLAYER_ID
        self.player = PlayerState(
            entity_id=PLAYER_ID,
            position=self.tile_map.spawn,
        )
        self.authoritative_player: PlayerState | None = None
        self.local_correction_offset = Vec2(0, 0)
        self.other_players: dict[str, RemotePlayerView] = {}
        self.local_player_id: str | None = PLAYER_ID
        self.player_names: dict[str, str] = {PLAYER_ID: self.local_character_name}
        self.chat_input_active = False
        self.chat_input_text = ""
        self.chat_journal_visible = False
        self.chat_lines: deque[ChatLine] = deque(maxlen=MAX_CHAT_LOG_MESSAGES)
        self.speech_bubbles: dict[str, TimedText] = {}
        self.name_tags: dict[str, TimedText] = {}
        self.camera = Camera()
        self.renderer = Renderer(self.tile_map)
        self.network_client = (
            NetworkClient(server_url, character_name=self.local_character_name)
            if server_url
            else None
        )

        if self.network_client is not None:
            self.local_player_id = None
            self.network_client.start()

    def run(self) -> None:
        """
        Запускает главный игровой цикл до выхода пользователя из клиента.
        """
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    self._handle_event(event)

            delta_seconds = min(self.clock.tick(60) / 1000.0, 0.05)
            self._update(delta_seconds)
            self._draw()

        if self.network_client is not None:
            self.network_client.stop()
        pygame.quit()

    def _update(self, delta_seconds: float) -> None:
        """
        Обновляет локальный ввод, состояние игрока и камеру за один кадр.
        """
        self._prune_timed_texts(time.monotonic())
        intent = self._read_movement_intent()
        if self.network_client is None:
            self.player = move_player(self.player, intent, delta_seconds, self.tile_map)
        else:
            self.network_client.send_movement_intent(intent)
            self._apply_network_messages()
            self._predict_local_player(intent, delta_seconds)
            self._reconcile_local_player(delta_seconds)
            self._update_remote_players(delta_seconds)

        viewport = Vec2(*self.screen.get_size())
        self.camera.follow(
            target=self.player.center,
            viewport_size=viewport,
            world_size=self.tile_map.pixel_size,
        )

    def _draw(self) -> None:
        """
        Отрисовывает текущий кадр и показывает его на экране.
        """
        other_players = [player_view.rendered for player_view in self.other_players.values()]
        self.renderer.draw(
            screen=self.screen,
            camera=self.camera,
            player=self.player,
            other_players=other_players,
            player_names=self.player_names,
            speech_bubbles=_timed_text_values(self.speech_bubbles),
            name_tags=_timed_text_values(self.name_tags),
            chat_lines=list(self.chat_lines),
            chat_input_active=self.chat_input_active,
            chat_input_text=self.chat_input_text,
            chat_journal_visible=self.chat_journal_visible,
        )
        pygame.display.flip()

    def _handle_event(self, event: pygame.event.Event) -> None:
        """
        Обрабатывает одно pygame-событие пользовательского ввода.
        """
        if event.type == pygame.KEYDOWN:
            self._handle_key_down(event)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._handle_left_click(event.pos)

    def _handle_key_down(self, event: pygame.event.Event) -> None:
        """
        Обрабатывает нажатие клавиши с учетом режима ввода чата.
        """
        if self.chat_input_active:
            self._handle_chat_input_key(event)
            return

        if event.key == pygame.K_RETURN:
            self.chat_input_active = True
            self.chat_input_text = ""
        elif event.key == pygame.K_j:
            self.chat_journal_visible = not self.chat_journal_visible

    def _handle_chat_input_key(self, event: pygame.event.Event) -> None:
        """
        Обрабатывает клавиши во время ввода сообщения чата.
        """
        if event.key == pygame.K_ESCAPE:
            self.chat_input_active = False
            self.chat_input_text = ""
            return
        if event.key == pygame.K_RETURN:
            self._send_chat_input()
            return
        if event.key == pygame.K_BACKSPACE:
            self.chat_input_text = self.chat_input_text[:-1]
            return

        if event.unicode and len(self.chat_input_text) < MAX_CHAT_INPUT_LENGTH:
            self.chat_input_text += event.unicode

    def _send_chat_input(self) -> None:
        """
        Отправляет набранное сообщение чата и закрывает строку ввода.
        """
        text = self.chat_input_text.strip()
        self.chat_input_active = False
        self.chat_input_text = ""
        if not text or self.network_client is None:
            return
        self.network_client.send_chat_message(text)

    def _handle_left_click(self, position: tuple[int, int]) -> None:
        """
        Показывает никнейм удаленного персонажа при клике по нему.
        """
        now = time.monotonic()
        for player_view in self.other_players.values():
            if self._player_screen_rect(player_view.rendered).collidepoint(position):
                self.name_tags[player_view.rendered.entity_id] = TimedText(
                    text=player_view.name,
                    expires_at=now + FLOATING_TEXT_SECONDS,
                )
                return

    def _read_movement_intent(self) -> MovementIntent:
        """
        Читает состояние клавиатуры и преобразует его в намерение движения.
        """
        if self.chat_input_active:
            return MovementIntent()

        pressed = pygame.key.get_pressed()
        return MovementIntent(
            up=pressed[pygame.K_w] or pressed[pygame.K_UP],
            down=pressed[pygame.K_s] or pressed[pygame.K_DOWN],
            left=pressed[pygame.K_a] or pressed[pygame.K_LEFT],
            right=pressed[pygame.K_d] or pressed[pygame.K_RIGHT],
        )

    def _apply_network_messages(self) -> None:
        """
        Применяет все сообщения сервера, полученные фоновым сетевым клиентом.
        """
        if self.network_client is None:
            return

        for message in self.network_client.drain_messages():
            if message.type == ServerMessageType.CONNECTION_ACCEPTED:
                player_id = message.payload.get("player_id")
                if isinstance(player_id, str):
                    self.local_player_id = player_id
                    name = message.payload.get("name")
                    if isinstance(name, str):
                        self.local_character_name = name
                    self.player_names[player_id] = self.local_character_name
            elif message.type == ServerMessageType.WORLD_SNAPSHOT:
                self._apply_world_snapshot(message.payload)
            elif message.type == ServerMessageType.CHAT_MESSAGE:
                self._apply_chat_message(message.payload)
            elif message.type == ServerMessageType.ENTITY_REMOVED:
                player_id = message.payload.get("id")
                if isinstance(player_id, str):
                    self.other_players.pop(player_id, None)
                    self.player_names.pop(player_id, None)
                    self.speech_bubbles.pop(player_id, None)
                    self.name_tags.pop(player_id, None)

    def _apply_world_snapshot(self, payload: dict[str, object]) -> None:
        """
        Обновляет состояния локального и удаленных игроков из authoritative snapshot-а.
        """
        try:
            snapshots = player_snapshots_from_payload(payload)
        except ProtocolError:
            return

        next_other_players: dict[str, PlayerState] = {}
        next_other_names: dict[str, str] = {}
        for snapshot in snapshots:
            player = snapshot.state
            self.player_names[player.entity_id] = snapshot.name
            if player.entity_id == self.local_player_id:
                self.local_character_name = snapshot.name
                self._receive_authoritative_local_player(player)
            else:
                next_other_players[player.entity_id] = player
                next_other_names[player.entity_id] = snapshot.name
        self._receive_remote_players(next_other_players, next_other_names)

    def _apply_chat_message(self, payload: dict[str, object]) -> None:
        """
        Добавляет серверное сообщение чата в журнал и показывает реплику над игроком.
        """
        player_id = payload.get("player_id")
        name = payload.get("name")
        text = payload.get("text")
        created_at = payload.get("created_at")
        if not isinstance(player_id, str) or not isinstance(name, str) or not isinstance(text, str):
            return
        if not isinstance(created_at, int | float):
            created_at = time.time()

        self.player_names[player_id] = name
        self.chat_lines.append(
            ChatLine(
                player_id=player_id,
                name=name,
                text=text,
                created_at=float(created_at),
            )
        )
        self.speech_bubbles[player_id] = TimedText(
            text=text,
            expires_at=time.monotonic() + FLOATING_TEXT_SECONDS,
        )

    def _predict_local_player(self, intent: MovementIntent, delta_seconds: float) -> None:
        """
        Сразу применяет локальный ввод игрока до получения подтверждения сервера.
        """
        self.player = move_player(self.player, intent, delta_seconds, self.tile_map)

    def _reconcile_local_player(self, delta_seconds: float) -> None:
        """
        Мягко подтягивает предсказанную позицию локального игрока к authoritative-позиции.
        """
        distance = self.local_correction_offset.length
        if distance <= LOCAL_RECONCILE_DEAD_ZONE or delta_seconds <= 0:
            self.local_correction_offset = Vec2(0, 0)
            return

        alpha = min(1.0, LOCAL_RECONCILE_RATE * delta_seconds)
        correction = self.local_correction_offset * alpha
        self.player = _player_with_position(self.player, self.player.position + correction)
        self.local_correction_offset = self.local_correction_offset - correction

    def _receive_authoritative_local_player(self, player: PlayerState) -> None:
        """
        Сохраняет authoritative-состояние локального игрока из server snapshot-а.
        """
        self.authoritative_player = player
        if self.player.entity_id != player.entity_id:
            self.player = player
            self.local_correction_offset = Vec2(0, 0)
            return

        difference = player.position - self.player.position
        distance = difference.length
        if distance >= LOCAL_SNAP_DISTANCE:
            self.player = player
            self.local_correction_offset = Vec2(0, 0)
        elif distance > LOCAL_RECONCILE_DEAD_ZONE:
            self.local_correction_offset = difference
        else:
            self.local_correction_offset = Vec2(0, 0)

    def _receive_remote_players(
        self,
        players: dict[str, PlayerState],
        names: dict[str, str],
    ) -> None:
        """
        Обновляет целевые состояния удаленных игроков и удаляет пропавшие сущности.
        """
        for player_id, player in players.items():
            if player_id in self.other_players:
                self.other_players[player_id].set_target(names[player_id], player)
            else:
                self.other_players[player_id] = RemotePlayerView(
                    name=names[player_id],
                    rendered=player,
                    target=player,
                )

        for player_id in set(self.other_players) - set(players):
            del self.other_players[player_id]

    def _update_remote_players(self, delta_seconds: float) -> None:
        """
        Обновляет интерполированные позиции всех удаленных игроков.
        """
        for player_view in self.other_players.values():
            player_view.update(delta_seconds)

    def _prune_timed_texts(self, now: float) -> None:
        """
        Удаляет истекшие временные реплики и никнеймы.
        """
        self.speech_bubbles = _active_timed_texts(self.speech_bubbles, now)
        self.name_tags = _active_timed_texts(self.name_tags, now)

    def _player_screen_rect(self, player: PlayerState) -> pygame.Rect:
        """
        Возвращает экранный прямоугольник игрока для обработки кликов.
        """
        x, y = self.camera.world_to_screen(player.position)
        return pygame.Rect(x, y, player.width, player.height)


def _smooth_player_toward(
    current: PlayerState,
    target: PlayerState,
    delta_seconds: float,
    rate: float,
    snap_distance: float,
    dead_zone: float,
) -> PlayerState:
    """
    Возвращает состояние игрока, плавно сдвинутое от текущей позиции к целевой.
    """
    difference = target.position - current.position
    distance = difference.length
    if distance <= dead_zone or distance >= snap_distance:
        return target
    if delta_seconds <= 0:
        return current

    alpha = min(1.0, rate * delta_seconds)
    position = current.position + difference * alpha
    return _player_with_position(target, position)


def _player_with_position(player: PlayerState, position: Vec2) -> PlayerState:
    """
    Создает копию состояния игрока с новой позицией.
    """
    return PlayerState(
        entity_id=player.entity_id,
        position=position,
        width=player.width,
        height=player.height,
        speed=player.speed,
    )


def _active_timed_texts(texts: dict[str, TimedText], now: float) -> dict[str, TimedText]:
    """
    Возвращает только те временные тексты, срок жизни которых еще не истек.
    """
    return {
        player_id: timed_text
        for player_id, timed_text in texts.items()
        if timed_text.expires_at > now
    }


def _timed_text_values(texts: dict[str, TimedText]) -> dict[str, str]:
    """
    Преобразует временные тексты в словарь строк для рендерера.
    """
    return {player_id: timed_text.text for player_id, timed_text in texts.items()}


def parse_args() -> argparse.Namespace:
    """
    Разбирает аргументы командной строки для клиента.
    """
    parser = argparse.ArgumentParser(description="Run the 2D RPG client prototype.")
    parser.add_argument(
        "--map",
        type=Path,
        default=DEFAULT_MAP_PATH,
        help=f"Path to a prototype JSON map. Defaults to {DEFAULT_MAP_PATH}.",
    )
    parser.add_argument(
        "--server",
        default=None,
        help=f"Connect to a websocket server, for example {DEFAULT_SERVER_URL}.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Character name for multiplayer mode.",
    )
    args = parser.parse_args()
    if args.server is not None and args.name is None:
        parser.error("--name is required when --server is used")
    return args


def main() -> None:
    """
    Создает клиент из аргументов командной строки и запускает его.
    """
    args = parse_args()
    GameClient(args.map, args.server, args.name).run()


if __name__ == "__main__":
    main()
