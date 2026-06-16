from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pygame

from basic_mmo_rpg.client.camera import Camera
from basic_mmo_rpg.client.network import NetworkClient
from basic_mmo_rpg.client.rendering import Renderer
from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState, move_player
from basic_mmo_rpg.shared.protocol import (
    ProtocolError,
    ServerMessageType,
    players_from_snapshot_payload,
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


@dataclass(slots=True)
class RemotePlayerView:
    """
    Хранит отображаемое и целевое состояние удаленного игрока для интерполяции.
    """

    rendered: PlayerState
    target: PlayerState

    def set_target(self, target: PlayerState) -> None:
        """
        Обновляет целевое authoritative-состояние удаленного игрока.
        """
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

    def __init__(self, map_path: Path, server_url: str | None = None) -> None:
        """
        Инициализирует окно, карту, состояние игрока, камеру, рендерер и сетевой режим.
        """
        pygame.init()
        window_title = (
            "Basic MMO RPG - multiplayer MVP" if server_url else "Basic MMO RPG - local MVP"
        )
        pygame.display.set_caption(window_title)

        self.screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.tile_map = load_tile_map(map_path)
        self.player = PlayerState(
            entity_id=PLAYER_ID,
            position=self.tile_map.spawn,
        )
        self.authoritative_player: PlayerState | None = None
        self.local_correction_offset = Vec2(0, 0)
        self.other_players: dict[str, RemotePlayerView] = {}
        self.local_player_id: str | None = PLAYER_ID
        self.camera = Camera()
        self.renderer = Renderer(self.tile_map)
        self.network_client = NetworkClient(server_url) if server_url else None

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
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

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
        self.renderer.draw(self.screen, self.camera, self.player, other_players)
        pygame.display.flip()

    def _read_movement_intent(self) -> MovementIntent:
        """
        Читает состояние клавиатуры и преобразует его в намерение движения.
        """
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
            elif message.type == ServerMessageType.WORLD_SNAPSHOT:
                self._apply_world_snapshot(message.payload)

    def _apply_world_snapshot(self, payload: dict[str, object]) -> None:
        """
        Обновляет состояния локального и удаленных игроков из authoritative snapshot-а.
        """
        try:
            players = players_from_snapshot_payload(payload)
        except ProtocolError:
            return

        next_other_players: dict[str, PlayerState] = {}
        for player in players:
            if player.entity_id == self.local_player_id:
                self._receive_authoritative_local_player(player)
            else:
                next_other_players[player.entity_id] = player
        self._receive_remote_players(next_other_players)

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

    def _receive_remote_players(self, players: dict[str, PlayerState]) -> None:
        """
        Обновляет целевые состояния удаленных игроков и удаляет пропавшие сущности.
        """
        for player_id, player in players.items():
            if player_id in self.other_players:
                self.other_players[player_id].set_target(player)
            else:
                self.other_players[player_id] = RemotePlayerView(rendered=player, target=player)

        for player_id in set(self.other_players) - set(players):
            del self.other_players[player_id]

    def _update_remote_players(self, delta_seconds: float) -> None:
        """
        Обновляет интерполированные позиции всех удаленных игроков.
        """
        for player_view in self.other_players.values():
            player_view.update(delta_seconds)


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
    return parser.parse_args()


def main() -> None:
    """
    Создает клиент из аргументов командной строки и запускает его.
    """
    args = parse_args()
    GameClient(args.map, args.server).run()


if __name__ == "__main__":
    main()
