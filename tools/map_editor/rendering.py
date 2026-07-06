from __future__ import annotations

from math import floor
from pathlib import Path

import pygame

from tools.map_editor.state import EditableMapState
from tools.map_editor.viewport import Viewport

BACKGROUND = (18, 20, 23)
GRID_LINE = (24, 26, 29)
HOVER_FILL = (255, 255, 255, 35)
HOVER_BORDER = (245, 225, 118)
STATUS_BACKGROUND = (14, 16, 20)
STATUS_BORDER = (65, 72, 82)
HELP_BACKGROUND = (12, 14, 18, 225)
HELP_BORDER = (245, 225, 118)
PALETTE_BACKGROUND = (23, 26, 31)
PALETTE_SELECTED_BORDER = (245, 225, 118)
PALETTE_BORDER = (83, 91, 104)
ENTITY_FILL = (88, 120, 166, 95)
ENTITY_SOLID_FILL = (161, 116, 74, 110)
ENTITY_BORDER = (188, 207, 232)
ENTITY_HOVER_BORDER = (245, 225, 118)
ENTITY_SELECTED_BORDER = (220, 60, 72)
SCROLLBAR_TRACK = (33, 37, 44, 170)
SCROLLBAR_THUMB = (135, 145, 160, 210)
TEXT_COLOR = (232, 236, 241)
MUTED_TEXT_COLOR = (166, 174, 184)
SCROLLBAR_SIZE = 8
BOTTOM_PANEL_HEIGHT = 74
PALETTE_ROW_HEIGHT = 40
STATUS_ROW_HEIGHT = 34
MIN_WINDOW_SIZE = (640, 420)
MAX_INITIAL_WINDOW_SIZE = (1600, 920)
HELP_LINES = (
    "F1 - toggle hotkeys",
    "1..9 - select tile",
    "LMB - paint / drag entity",
    "RMB - pick tile",
    "Ctrl + drag entity - snap to tile center",
    "Ctrl+D - duplicate selected creature",
    "Mouse wheel - vertical scroll",
    "Shift + wheel - horizontal scroll",
    "Arrows / WASD - scroll map",
    "Middle mouse - drag viewport",
    "Z - toggle 1x / 0.5x zoom",
    "Ctrl+S - save map",
)


class MapEditorRenderer:
    """
    Рисует тайловую карту, сетку, палитру и строку состояния редактора.
    """

    def __init__(self, state: EditableMapState, map_path: Path, viewport: Viewport) -> None:
        self.state = state
        self.map_path = map_path
        self.viewport = viewport
        self.font = pygame.font.SysFont("arial", 16)
        self.small_font = pygame.font.SysFont("arial", 14)

    def initial_window_size(self) -> tuple[int, int]:
        """
        Возвращает стартовый размер окна под карту без масштабирования.
        """
        map_width = self.state.pixel_width
        map_height = self.state.pixel_height + BOTTOM_PANEL_HEIGHT
        width = min(MAX_INITIAL_WINDOW_SIZE[0], max(MIN_WINDOW_SIZE[0], map_width))
        height = min(MAX_INITIAL_WINDOW_SIZE[1], max(MIN_WINDOW_SIZE[1], map_height))
        return width, height

    def draw(
        self,
        screen: pygame.Surface,
        hovered_tile: tuple[int, int] | None,
        status_message: str = "",
        help_visible: bool = False,
    ) -> None:
        """
        Рисует текущий кадр редактора.
        """
        screen.fill(BACKGROUND)
        view_height = self._map_view_height(screen)
        self._draw_tiles(screen, view_height)
        self._draw_grid(screen, view_height)
        self._draw_entities(screen, view_height, hovered_tile)
        if hovered_tile is not None:
            self._draw_hovered_tile(screen, hovered_tile, view_height)
        self._draw_scrollbars(screen, view_height)
        if help_visible:
            self._draw_help_overlay(screen)
        self._draw_palette(screen)
        self._draw_status_bar(screen, hovered_tile, status_message)

    def tile_at_screen_position(
        self,
        position: tuple[int, int],
        screen: pygame.Surface,
    ) -> tuple[int, int] | None:
        """
        Возвращает координаты тайла под курсором или None вне области карты.
        """
        x, y = position
        if x < 0 or y < 0 or y >= self._map_view_height(screen):
            return None
        tile_size = self.state.tile_size
        world_x, world_y = self.viewport.screen_to_world(x, y)
        tile_x = floor(world_x / tile_size)
        tile_y = floor(world_y / tile_size)
        if not self.state.in_bounds(tile_x, tile_y):
            return None
        return tile_x, tile_y

    def world_position_at_screen_position(self, position: tuple[int, int]) -> tuple[float, float]:
        """
        Возвращает мировую позицию карты под экранной точкой.
        """
        return self.viewport.screen_to_world(position[0], position[1])

    def entity_at_screen_position(
        self,
        position: tuple[int, int],
        screen: pygame.Surface,
    ) -> str | None:
        """
        Возвращает id entity под курсором или None.
        """
        x, y = position
        if y < 0 or y >= self._map_view_height(screen):
            return None
        world_x, world_y = self.viewport.screen_to_world(x, y)
        entity = self.state.entity_at_point(world_x, world_y)
        return entity.entity_id if entity is not None else None

    def _draw_tiles(self, screen: pygame.Surface, view_height: int) -> None:
        tile_size = self.state.tile_size
        start_x = max(0, floor(self.viewport.offset_x / tile_size))
        start_y = max(0, floor(self.viewport.offset_y / tile_size))
        end_x = min(
            self.state.width,
            floor(
                (self.viewport.offset_x + self.viewport.visible_world_width(screen.get_width()))
                / tile_size
            )
            + 2,
        )
        end_y = min(
            self.state.height,
            floor(
                (self.viewport.offset_y + self.viewport.visible_world_height(view_height))
                / tile_size
            )
            + 2,
        )

        for tile_y in range(start_y, end_y):
            for tile_x in range(start_x, end_x):
                tile_key = self.state.tile_at(tile_x, tile_y)
                definition = self.state.definitions[tile_key]
                rect = self._world_rect_to_screen(
                    tile_x * tile_size,
                    tile_y * tile_size,
                    tile_size,
                    tile_size,
                )
                pygame.draw.rect(
                    screen,
                    definition.color,
                    rect,
                )

    def _draw_grid(self, screen: pygame.Surface, view_height: int) -> None:
        tile_size = self.state.tile_size
        start_x = max(0, floor(self.viewport.offset_x / tile_size))
        start_y = max(0, floor(self.viewport.offset_y / tile_size))
        end_x = min(
            self.state.width,
            floor(
                (self.viewport.offset_x + self.viewport.visible_world_width(screen.get_width()))
                / tile_size
            )
            + 2,
        )
        end_y = min(
            self.state.height,
            floor(
                (self.viewport.offset_y + self.viewport.visible_world_height(view_height))
                / tile_size
            )
            + 2,
        )

        for tile_x in range(start_x, end_x + 1):
            screen_x, _ = self.viewport.world_to_screen(tile_x * tile_size, 0)
            pygame.draw.line(screen, GRID_LINE, (screen_x, 0), (screen_x, view_height))
        for tile_y in range(start_y, end_y + 1):
            _, screen_y = self.viewport.world_to_screen(0, tile_y * tile_size)
            pygame.draw.line(screen, GRID_LINE, (0, screen_y), (screen.get_width(), screen_y))

    def _draw_hovered_tile(
        self,
        screen: pygame.Surface,
        tile: tuple[int, int],
        view_height: int,
    ) -> None:
        tile_x, tile_y = tile
        tile_size = self.state.tile_size
        rect = self._world_rect_to_screen(
            tile_x * tile_size,
            tile_y * tile_size,
            tile_size,
            tile_size,
        )
        if rect.top >= view_height:
            return

        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        overlay.fill(HOVER_FILL)
        screen.blit(overlay, rect.topleft)
        pygame.draw.rect(screen, HOVER_BORDER, rect, width=2)

    def _draw_entities(
        self,
        screen: pygame.Surface,
        view_height: int,
        hovered_tile: tuple[int, int] | None,
    ) -> None:
        hovered_entity_id = None
        if hovered_tile is not None:
            mouse_x, mouse_y = pygame.mouse.get_pos()
            world_x, world_y = self.viewport.screen_to_world(mouse_x, mouse_y)
            entity = self.state.entity_at_point(world_x, world_y)
            hovered_entity_id = entity.entity_id if entity is not None else None

        for entity in self.state.entities:
            left, top = entity.position
            width, height = entity.size
            rect = self._world_rect_to_screen(left, top, width, height)
            if rect.top >= view_height or rect.bottom < 0:
                continue
            fill_color = ENTITY_SOLID_FILL if entity.solid else ENTITY_FILL
            border_color = ENTITY_BORDER
            border_width = 1
            if entity.entity_id == hovered_entity_id:
                border_color = ENTITY_HOVER_BORDER
                border_width = 2
            if entity.entity_id == self.state.selected_entity_id:
                border_color = ENTITY_SELECTED_BORDER
                border_width = 3

            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            overlay.fill(fill_color)
            screen.blit(overlay, rect.topleft)
            pygame.draw.rect(screen, border_color, rect, width=border_width)

            if entity.entity_id == self.state.selected_entity_id:
                label = self.small_font.render(entity.entity_id, True, TEXT_COLOR)
                label_y = max(0, rect.top - self.small_font.get_linesize())
                screen.blit(label, (rect.left, label_y))

    def _draw_status_bar(
        self,
        screen: pygame.Surface,
        hovered_tile: tuple[int, int] | None,
        status_message: str,
    ) -> None:
        rect = pygame.Rect(
            0,
            screen.get_height() - STATUS_ROW_HEIGHT,
            screen.get_width(),
            STATUS_ROW_HEIGHT,
        )
        pygame.draw.rect(screen, STATUS_BACKGROUND, rect)
        pygame.draw.line(screen, STATUS_BORDER, rect.topleft, rect.topright)

        left_text = (
            f"Map: {self.map_path.name} | {self.state.width}x{self.state.height} "
            f"| zoom={self.viewport.zoom:g}x | selected={self.state.selected_tile_key!r}"
        )
        selected_entity = self.state.selected_entity()
        if selected_entity is not None:
            left, top = selected_entity.position
            left_text = (
                f"{left_text} | entity={selected_entity.label} "
                f"at=({left:g}, {top:g})"
            )
        if self.state.dirty:
            left_text = f"{left_text} | unsaved"
        left_surface = self.small_font.render(left_text, True, MUTED_TEXT_COLOR)
        screen.blit(left_surface, (10, rect.top + 9))

        detail = status_message or "Tile: outside map"
        if hovered_tile is not None:
            tile_x, tile_y = hovered_tile
            tile_key = self.state.tile_at(tile_x, tile_y)
            definition = self.state.definitions[tile_key]
            solid = "solid" if definition.solid else "walkable"
            tile_detail = (
                f"Tile: ({tile_x}, {tile_y}) key={tile_key!r} "
                f"name={definition.name!r} {solid}"
            )
            detail = f"{status_message} | {tile_detail}" if status_message else tile_detail
        detail_surface = self.font.render(detail, True, TEXT_COLOR)
        detail_x = max(10, screen.get_width() - detail_surface.get_width() - 10)
        screen.blit(detail_surface, (detail_x, rect.top + 7))

    def _draw_palette(self, screen: pygame.Surface) -> None:
        rect = pygame.Rect(
            0,
            screen.get_height() - BOTTOM_PANEL_HEIGHT,
            screen.get_width(),
            PALETTE_ROW_HEIGHT,
        )
        pygame.draw.rect(screen, PALETTE_BACKGROUND, rect)
        pygame.draw.line(screen, STATUS_BORDER, rect.topleft, rect.topright)

        x = 10
        y = rect.top + 7
        for index, (tile_key, definition) in enumerate(self.state.definitions.items(), start=1):
            label = f"{index}: {tile_key} {definition.name}"
            label_surface = self.small_font.render(label, True, TEXT_COLOR)
            swatch_size = 20
            entry_width = swatch_size + 8 + label_surface.get_width() + 16
            if x + entry_width > screen.get_width() - 10:
                break

            swatch_rect = pygame.Rect(x, y + 3, swatch_size, swatch_size)
            border_color = (
                PALETTE_SELECTED_BORDER
                if tile_key == self.state.selected_tile_key
                else PALETTE_BORDER
            )
            pygame.draw.rect(screen, definition.color, swatch_rect)
            pygame.draw.rect(screen, border_color, swatch_rect, width=2)
            screen.blit(label_surface, (swatch_rect.right + 8, y + 4))

            if tile_key == self.state.selected_tile_key:
                entry_rect = pygame.Rect(x - 4, rect.top + 5, entry_width, 30)
                pygame.draw.rect(screen, PALETTE_SELECTED_BORDER, entry_rect, width=1)

            x += entry_width

    def _draw_scrollbars(self, screen: pygame.Surface, view_height: int) -> None:
        if self.state.pixel_height > self.viewport.visible_world_height(view_height):
            self._draw_vertical_scrollbar(screen, view_height)
        if self.state.pixel_width > self.viewport.visible_world_width(screen.get_width()):
            self._draw_horizontal_scrollbar(screen, view_height)

    def _draw_help_overlay(self, screen: pygame.Surface) -> None:
        line_surfaces = [self.small_font.render(line, True, TEXT_COLOR) for line in HELP_LINES]
        width = max(surface.get_width() for surface in line_surfaces) + 24
        line_height = self.small_font.get_linesize()
        height = len(line_surfaces) * line_height + 42
        rect = pygame.Rect(12, 12, width, height)

        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill(HELP_BACKGROUND)
        screen.blit(panel, rect.topleft)
        pygame.draw.rect(screen, HELP_BORDER, rect, width=1)

        title_surface = self.font.render("Hotkeys", True, HELP_BORDER)
        screen.blit(title_surface, (rect.left + 10, rect.top + 8))
        y = rect.top + 30
        for surface in line_surfaces:
            screen.blit(surface, (rect.left + 10, y))
            y += line_height

    def _draw_vertical_scrollbar(self, screen: pygame.Surface, view_height: int) -> None:
        track_rect = pygame.Rect(
            screen.get_width() - SCROLLBAR_SIZE,
            0,
            SCROLLBAR_SIZE,
            view_height,
        )
        track = pygame.Surface(track_rect.size, pygame.SRCALPHA)
        track.fill(SCROLLBAR_TRACK)
        screen.blit(track, track_rect.topleft)

        visible_height = self.viewport.visible_world_height(view_height)
        max_offset = max(1.0, self.state.pixel_height - visible_height)
        thumb_height = max(
            28,
            int(view_height * min(1.0, visible_height / self.state.pixel_height)),
        )
        thumb_top = int(
            self.viewport.offset_y / max_offset * max(0, view_height - thumb_height)
        )
        thumb_rect = pygame.Rect(
            track_rect.left,
            thumb_top,
            SCROLLBAR_SIZE,
            thumb_height,
        )
        thumb = pygame.Surface(thumb_rect.size, pygame.SRCALPHA)
        thumb.fill(SCROLLBAR_THUMB)
        screen.blit(thumb, thumb_rect.topleft)

    def _draw_horizontal_scrollbar(self, screen: pygame.Surface, view_height: int) -> None:
        track_rect = pygame.Rect(
            0,
            view_height - SCROLLBAR_SIZE,
            screen.get_width(),
            SCROLLBAR_SIZE,
        )
        track = pygame.Surface(track_rect.size, pygame.SRCALPHA)
        track.fill(SCROLLBAR_TRACK)
        screen.blit(track, track_rect.topleft)

        visible_width = self.viewport.visible_world_width(screen.get_width())
        max_offset = max(1.0, self.state.pixel_width - visible_width)
        thumb_width = max(
            28,
            int(screen.get_width() * min(1.0, visible_width / self.state.pixel_width)),
        )
        thumb_left = int(
            self.viewport.offset_x / max_offset * max(0, screen.get_width() - thumb_width)
        )
        thumb_rect = pygame.Rect(
            thumb_left,
            track_rect.top,
            thumb_width,
            SCROLLBAR_SIZE,
        )
        thumb = pygame.Surface(thumb_rect.size, pygame.SRCALPHA)
        thumb.fill(SCROLLBAR_THUMB)
        screen.blit(thumb, thumb_rect.topleft)

    def map_view_height(self, screen: pygame.Surface) -> int:
        """
        Возвращает высоту области карты без нижней панели.
        """
        return self._map_view_height(screen)

    def _map_view_height(self, screen: pygame.Surface) -> int:
        return max(0, screen.get_height() - BOTTOM_PANEL_HEIGHT)

    def _world_rect_to_screen(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> pygame.Rect:
        left, top = self.viewport.world_to_screen(x, y)
        right, bottom = self.viewport.world_to_screen(x + width, y + height)
        return pygame.Rect(left, top, max(1, right - left), max(1, bottom - top))
