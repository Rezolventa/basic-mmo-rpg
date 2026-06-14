from __future__ import annotations

import argparse
from pathlib import Path

import pygame

from basic_mmo_rpg.client.camera import Camera
from basic_mmo_rpg.client.rendering import Renderer
from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState, move_player
from basic_mmo_rpg.storage.map_loader import load_tile_map

DEFAULT_MAP_PATH = Path(__file__).resolve().parents[3] / "assets" / "maps" / "starter_map.json"
WINDOW_SIZE = (960, 640)
PLAYER_ID = "local-player"


class GameClient:
    """
    Управляет локальным pygame-клиентом и основным игровым циклом.
    """

    def __init__(self, map_path: Path) -> None:
        """
        Инициализирует окно, карту, игрока, камеру и рендерер.
        """
        pygame.init()
        pygame.display.set_caption("Basic MMO RPG - local MVP")

        self.screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.tile_map = load_tile_map(map_path)
        self.player = PlayerState(
            entity_id=PLAYER_ID,
            position=self.tile_map.spawn,
        )
        self.camera = Camera()
        self.renderer = Renderer(self.tile_map)

    def run(self) -> None:
        """
        Запускает главный игровой цикл до выхода пользователя.
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

        pygame.quit()

    def _update(self, delta_seconds: float) -> None:
        """
        Обновляет состояние игрока и положение камеры за один кадр.
        """
        pressed = pygame.key.get_pressed()
        intent = MovementIntent(
            up=pressed[pygame.K_w] or pressed[pygame.K_UP],
            down=pressed[pygame.K_s] or pressed[pygame.K_DOWN],
            left=pressed[pygame.K_a] or pressed[pygame.K_LEFT],
            right=pressed[pygame.K_d] or pressed[pygame.K_RIGHT],
        )
        self.player = move_player(self.player, intent, delta_seconds, self.tile_map)

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
        self.renderer.draw(self.screen, self.camera, self.player)
        pygame.display.flip()


def parse_args() -> argparse.Namespace:
    """
    Разбирает аргументы командной строки для запуска клиента.
    """
    parser = argparse.ArgumentParser(description="Run the local 2D RPG client prototype.")
    parser.add_argument(
        "--map",
        type=Path,
        default=DEFAULT_MAP_PATH,
        help=f"Path to a prototype JSON map. Defaults to {DEFAULT_MAP_PATH}.",
    )
    return parser.parse_args()


def main() -> None:
    """
    Создает клиент с параметрами командной строки и запускает его.
    """
    args = parse_args()
    GameClient(args.map).run()


if __name__ == "__main__":
    main()
