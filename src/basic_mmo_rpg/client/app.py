from __future__ import annotations

import argparse
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
        self.other_players: dict[str, PlayerState] = {}
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
        self.renderer.draw(self.screen, self.camera, self.player, self.other_players.values())
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
                self.player = player
            else:
                next_other_players[player.entity_id] = player
        self.other_players = next_other_players


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
