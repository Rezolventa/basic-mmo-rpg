from __future__ import annotations

import argparse
from pathlib import Path

import pygame

from tools.map_editor.map_io import (
    create_backup,
    create_empty_map_from_template,
    load_editable_map,
    parse_map_dimensions,
    save_editable_map,
)
from tools.map_editor.rendering import MapEditorRenderer
from tools.map_editor.viewport import Viewport

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAP_PATH = PROJECT_ROOT / "assets" / "maps" / "starter_map.json"
TARGET_FPS = 60
WHEEL_SCROLL_PIXELS = 96
KEYBOARD_SCROLL_SPEED = 720.0
ZOOM_LEVELS = (1.0, 0.5)
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


class MapEditorApp:
    """
    Запускает pygame-редактор тайловой карты.
    """

    def __init__(self, map_path: Path) -> None:
        self.map_path = map_path
        self.document = load_editable_map(map_path)
        self.state = self.document.state

        pygame.init()
        pygame.display.set_caption(f"Basic MMO RPG Map Editor - {map_path.name}")
        self.viewport = Viewport()
        self.renderer = MapEditorRenderer(self.state, map_path, self.viewport)
        self.screen = pygame.display.set_mode(
            self.renderer.initial_window_size(),
            pygame.RESIZABLE,
        )
        self.clock = pygame.time.Clock()
        self.hovered_tile: tuple[int, int] | None = None
        self.painting = False
        self.dragging_entity_id: str | None = None
        self.entity_drag_offset = (0.0, 0.0)
        self.scrolling_view = False
        self.backup_created = False
        self.status_message = ""
        self.help_visible = False

    def run(self) -> None:
        """
        Выполняет главный цикл редактора до закрытия окна.
        """
        running = True
        delta_seconds = 1.0 / TARGET_FPS
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEMOTION:
                    self._update_hovered_tile(event.pos)
                    if self.scrolling_view:
                        self._scroll_view_by_mouse_drag(event.rel)
                    elif self.dragging_entity_id is not None:
                        self._drag_entity_at_screen_position(event.pos)
                    elif self.painting:
                        self._paint_at_screen_position(event.pos)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._handle_mouse_button_down(event.button, event.pos)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self.painting = False
                    self.dragging_entity_id = None
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 2:
                    self.scrolling_view = False
                elif event.type == pygame.MOUSEWHEEL:
                    self._handle_mouse_wheel(event.x, event.y)
                elif event.type == pygame.KEYDOWN:
                    self._handle_keydown(event.key, event.mod)

            self._handle_keyboard_scroll(delta_seconds)
            self._clamp_viewport()
            self._update_hovered_tile(pygame.mouse.get_pos())
            self.renderer.draw(
                self.screen,
                self.hovered_tile,
                self.status_message,
                self.help_visible,
            )
            pygame.display.flip()
            delta_seconds = self.clock.tick(TARGET_FPS) / 1000

        pygame.quit()

    def _update_hovered_tile(self, mouse_position: tuple[int, int]) -> None:
        self.hovered_tile = self.renderer.tile_at_screen_position(mouse_position, self.screen)

    def _handle_keydown(self, key: int, modifiers: int) -> None:
        if key == pygame.K_F1:
            self.help_visible = not self.help_visible
            return
        if key == pygame.K_z:
            self._toggle_zoom()
            return
        if key == pygame.K_s and modifiers & pygame.KMOD_CTRL:
            self._save_map()
            return
        tile_index = NUMBER_KEY_TO_INDEX.get(key)
        if tile_index is None:
            return
        self.state.select_tile_by_index(tile_index)

    def _handle_mouse_button_down(self, button: int, position: tuple[int, int]) -> None:
        if button == 1:
            if self._select_entity_at_screen_position(position):
                return
            self.state.select_entity(None)
            self.painting = True
            self._paint_at_screen_position(position)
            return
        if button == 3:
            self._pick_tile_at_screen_position(position)
            return
        if button == 2:
            self.scrolling_view = True

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
        self.status_message = ""

    def _select_entity_at_screen_position(self, position: tuple[int, int]) -> bool:
        entity_id = self.renderer.entity_at_screen_position(position, self.screen)
        if entity_id is None:
            return False
        entity = self.state.entity_by_id(entity_id)
        if entity is None:
            return False

        self.state.select_entity(entity_id)
        left, top = entity.position
        world_x, world_y = self.renderer.world_position_at_screen_position(position)
        self.dragging_entity_id = entity_id
        self.entity_drag_offset = (world_x - left, world_y - top)
        self.painting = False
        self.status_message = ""
        return True

    def _drag_entity_at_screen_position(self, position: tuple[int, int]) -> None:
        if self.dragging_entity_id is None:
            return
        if pygame.key.get_mods() & pygame.KMOD_CTRL:
            tile = self.renderer.tile_at_screen_position(position, self.screen)
            if tile is None:
                return
            tile_x, tile_y = tile
            self.state.snap_entity_center_to_tile(self.dragging_entity_id, tile_x, tile_y)
            return
        offset_x, offset_y = self.entity_drag_offset
        world_x, world_y = self.renderer.world_position_at_screen_position(position)
        x = world_x - offset_x
        y = world_y - offset_y
        self.state.move_entity(self.dragging_entity_id, x, y)

    def _handle_mouse_wheel(self, wheel_x: int, wheel_y: int) -> None:
        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
            delta_x = -wheel_y * WHEEL_SCROLL_PIXELS
            delta_y = 0
        else:
            delta_x = wheel_x * WHEEL_SCROLL_PIXELS
            delta_y = -wheel_y * WHEEL_SCROLL_PIXELS
        self._scroll_view(delta_x, delta_y)

    def _handle_keyboard_scroll(self, delta_seconds: float) -> None:
        if pygame.key.get_mods() & pygame.KMOD_CTRL:
            return
        pressed = pygame.key.get_pressed()
        delta_x = 0.0
        delta_y = 0.0
        distance = KEYBOARD_SCROLL_SPEED * delta_seconds
        if pressed[pygame.K_LEFT] or pressed[pygame.K_a]:
            delta_x -= distance
        if pressed[pygame.K_RIGHT] or pressed[pygame.K_d]:
            delta_x += distance
        if pressed[pygame.K_UP] or pressed[pygame.K_w]:
            delta_y -= distance
        if pressed[pygame.K_DOWN] or pressed[pygame.K_s]:
            delta_y += distance
        if delta_x != 0.0 or delta_y != 0.0:
            self._scroll_view(delta_x, delta_y)

    def _scroll_view_by_mouse_drag(self, relative_motion: tuple[int, int]) -> None:
        delta_x, delta_y = relative_motion
        self._scroll_view(-delta_x, -delta_y)

    def _scroll_view(self, delta_x: float, delta_y: float) -> None:
        self.viewport.scroll(
            delta_x,
            delta_y,
            map_width=self.state.pixel_width,
            map_height=self.state.pixel_height,
            view_width=self.screen.get_width(),
            view_height=self.renderer.map_view_height(self.screen),
        )

    def _clamp_viewport(self) -> None:
        self.viewport.clamp(
            map_width=self.state.pixel_width,
            map_height=self.state.pixel_height,
            view_width=self.screen.get_width(),
            view_height=self.renderer.map_view_height(self.screen),
        )

    def _toggle_zoom(self) -> None:
        next_zoom = ZOOM_LEVELS[1] if self.viewport.zoom == ZOOM_LEVELS[0] else ZOOM_LEVELS[0]
        self.viewport.set_zoom_around_screen_point(
            next_zoom,
            self.screen.get_width() // 2,
            self.renderer.map_view_height(self.screen) // 2,
            map_width=self.state.pixel_width,
            map_height=self.state.pixel_height,
            view_width=self.screen.get_width(),
            view_height=self.renderer.map_view_height(self.screen),
        )
        self.status_message = f"Zoom: {next_zoom:g}x"

    def _save_map(self) -> None:
        if not self.state.dirty:
            self.status_message = "No changes to save"
            return
        try:
            if not self.backup_created:
                create_backup(self.map_path)
                self.backup_created = True
            self.document.raw_map = save_editable_map(
                path=self.map_path,
                raw_map=self.document.raw_map,
                state=self.state,
            )
        except ValueError as exc:
            self.status_message = f"Save failed: {exc}"
            return
        self.status_message = "Saved"


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
    parser.add_argument(
        "--new",
        type=parse_map_dimensions,
        metavar="WIDTHxHEIGHT",
        help="Create a new empty map before opening it, for example 60x35.",
    )
    parser.add_argument(
        "--fill",
        default=".",
        help="Tile key for the inside of a new map.",
    )
    parser.add_argument(
        "--border",
        default="#",
        help="Tile key for the border of a new map.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow --new to overwrite an existing map file.",
    )
    return parser


def main() -> None:
    """
    Точка входа редактора тайловой карты.
    """
    args = build_parser().parse_args()
    if args.new is not None:
        width, height = args.new
        try:
            create_empty_map_from_template(
                template_path=DEFAULT_MAP_PATH,
                output_path=args.map,
                width=width,
                height=height,
                fill_tile=args.fill,
                border_tile=args.border,
                overwrite=args.overwrite,
            )
        except (FileExistsError, ValueError) as exc:
            raise SystemExit(f"Could not create map: {exc}") from exc
    MapEditorApp(args.map).run()
