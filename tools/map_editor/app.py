from __future__ import annotations

import argparse
from pathlib import Path

import pygame

from tools.map_editor.map_io import create_backup, load_editable_map, save_editable_map
from tools.map_editor.rendering import MapViewerRenderer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAP_PATH = PROJECT_ROOT / "assets" / "maps" / "starter_map.json"
TARGET_FPS = 60
NUMBER_KEY_TO_INDEX = {
    pygame.K_1: 0,
    pygame.K_2: 1,
    pygame.K_3: 2,
    pygame.K_4: 3,
    pygame.K_5: 4,
    pygame.K_6: 5,
    pygame.K_7: 6,
    pygame.K_8: 7,
    pygame.K_9: 8,
    pygame.K_KP1: 0,
    pygame.K_KP2: 1,
    pygame.K_KP3: 2,
    pygame.K_KP4: 3,
    pygame.K_KP5: 4,
    pygame.K_KP6: 5,
    pygame.K_KP7: 6,
    pygame.K_KP8: 7,
    pygame.K_KP9: 8,
}


class MapViewerApp:
    """
    Запускает pygame-редактор тайловой карты.
    """

    def __init__(self, map_path: Path) -> None:
        self.map_path = map_path
        self.document = load_editable_map(map_path)
        self.state = self.document.state

        pygame.init()
        pygame.display.set_caption(f"Basic MMO RPG Map Editor - {map_path.name}")
        self.renderer = MapViewerRenderer(self.state, map_path)
        self.screen = pygame.display.set_mode(
            self.renderer.initial_window_size(),
            pygame.RESIZABLE,
        )
        self.clock = pygame.time.Clock()
        self.hovered_tile: tuple[int, int] | None = None
        self.painting = False
        self.backup_created = False

    def run(self) -> None:
        """
        Выполняет главный цикл редактора до закрытия окна.
        """
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEMOTION:
                    self._update_hovered_tile(event.pos)
                    if self.painting:
                        self._paint_at_screen_position(event.pos)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._handle_mouse_button_down(event.button, event.pos)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self.painting = False
                elif event.type == pygame.KEYDOWN:
                    self._handle_keydown(event.key, event.mod)

            self._update_hovered_tile(pygame.mouse.get_pos())
            self.renderer.draw(self.screen, self.hovered_tile)
            pygame.display.flip()
            self.clock.tick(TARGET_FPS)

        pygame.quit()

    def _update_hovered_tile(self, mouse_position: tuple[int, int]) -> None:
        self.hovered_tile = self.renderer.tile_at_screen_position(mouse_position, self.screen)

    def _handle_keydown(self, key: int, modifiers: int) -> None:
        if key == pygame.K_s and modifiers & pygame.KMOD_CTRL:
            self._save_map()
            return
        tile_index = NUMBER_KEY_TO_INDEX.get(key)
        if tile_index is None:
            return
        self.state.select_tile_by_index(tile_index)

    def _handle_mouse_button_down(self, button: int, position: tuple[int, int]) -> None:
        if button == 1:
            self.painting = True
            self._paint_at_screen_position(position)
            return
        if button == 3:
            self._pick_tile_at_screen_position(position)

    def _paint_at_screen_position(self, position: tuple[int, int]) -> None:
        tile = self.renderer.tile_at_screen_position(position, self.screen)
        if tile is None:
            return
        tile_x, tile_y = tile
        self.state.paint_tile(tile_x, tile_y)

    def _pick_tile_at_screen_position(self, position: tuple[int, int]) -> None:
        tile = self.renderer.tile_at_screen_position(position, self.screen)
        if tile is None:
            return
        tile_x, tile_y = tile
        self.state.pick_tile(tile_x, tile_y)

    def _save_map(self) -> None:
        if not self.state.dirty:
            return
        if not self.backup_created:
            create_backup(self.map_path)
            self.backup_created = True
        self.document.raw_map = save_editable_map(
            path=self.map_path,
            raw_map=self.document.raw_map,
            state=self.state,
        )


def build_parser() -> argparse.ArgumentParser:
    """
    Создает CLI-парсер для запуска редактора.
    """
    parser = argparse.ArgumentParser(description="Open the tile map editor.")
    parser.add_argument(
        "--map",
        type=Path,
        default=DEFAULT_MAP_PATH,
        help="Path to the JSON tile map.",
    )
    return parser


def main() -> None:
    """
    Точка входа редактора тайловой карты.
    """
    args = build_parser().parse_args()
    MapViewerApp(args.map).run()
