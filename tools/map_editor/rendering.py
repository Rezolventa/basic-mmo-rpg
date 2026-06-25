from __future__ import annotations

from pathlib import Path

import pygame

from tools.map_editor.state import EditableMapState

BACKGROUND = (18, 20, 23)
GRID_LINE = (24, 26, 29)
HOVER_FILL = (255, 255, 255, 35)
HOVER_BORDER = (245, 225, 118)
STATUS_BACKGROUND = (14, 16, 20)
STATUS_BORDER = (65, 72, 82)
PALETTE_BACKGROUND = (23, 26, 31)
PALETTE_SELECTED_BORDER = (245, 225, 118)
PALETTE_BORDER = (83, 91, 104)
TEXT_COLOR = (232, 236, 241)
MUTED_TEXT_COLOR = (166, 174, 184)
BOTTOM_PANEL_HEIGHT = 74
PALETTE_ROW_HEIGHT = 40
STATUS_ROW_HEIGHT = 34
MIN_WINDOW_SIZE = (640, 420)
MAX_INITIAL_WINDOW_SIZE = (1600, 920)


class MapViewerRenderer:
    """
    Рисует тайловую карту, сетку, палитру и строку состояния редактора.
    """

    def __init__(self, state: EditableMapState, map_path: Path) -> None:
        self.state = state
        self.map_path = map_path
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
    ) -> None:
        """
        Рисует текущий кадр редактора.
        """
        screen.fill(BACKGROUND)
        view_height = self._map_view_height(screen)
        self._draw_tiles(screen, view_height)
        self._draw_grid(screen, view_height)
        if hovered_tile is not None:
            self._draw_hovered_tile(screen, hovered_tile, view_height)
        self._draw_palette(screen)
        self._draw_status_bar(screen, hovered_tile)

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
        tile_x = x // tile_size
        tile_y = y // tile_size
        if not self.state.in_bounds(tile_x, tile_y):
            return None
        return tile_x, tile_y

    def _draw_tiles(self, screen: pygame.Surface, view_height: int) -> None:
        tile_size = self.state.tile_size
        width = min(self.state.width, screen.get_width() // tile_size + 1)
        height = min(self.state.height, view_height // tile_size + 1)

        for tile_y in range(height):
            for tile_x in range(width):
                tile_key = self.state.tile_at(tile_x, tile_y)
                definition = self.state.definitions[tile_key]
                pygame.draw.rect(
                    screen,
                    definition.color,
                    pygame.Rect(
                        tile_x * tile_size,
                        tile_y * tile_size,
                        tile_size,
                        tile_size,
                    ),
                )

    def _draw_grid(self, screen: pygame.Surface, view_height: int) -> None:
        tile_size = self.state.tile_size
        map_width = min(self.state.pixel_width, screen.get_width())
        map_height = min(self.state.pixel_height, view_height)

        for x in range(0, map_width + 1, tile_size):
            pygame.draw.line(screen, GRID_LINE, (x, 0), (x, map_height))
        for y in range(0, map_height + 1, tile_size):
            pygame.draw.line(screen, GRID_LINE, (0, y), (map_width, y))

    def _draw_hovered_tile(
        self,
        screen: pygame.Surface,
        tile: tuple[int, int],
        view_height: int,
    ) -> None:
        tile_x, tile_y = tile
        tile_size = self.state.tile_size
        rect = pygame.Rect(tile_x * tile_size, tile_y * tile_size, tile_size, tile_size)
        if rect.top >= view_height:
            return

        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        overlay.fill(HOVER_FILL)
        screen.blit(overlay, rect.topleft)
        pygame.draw.rect(screen, HOVER_BORDER, rect, width=2)

    def _draw_status_bar(
        self,
        screen: pygame.Surface,
        hovered_tile: tuple[int, int] | None,
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
            f"| selected={self.state.selected_tile_key!r}"
        )
        if self.state.dirty:
            left_text = f"{left_text} | unsaved"
        left_surface = self.small_font.render(left_text, True, MUTED_TEXT_COLOR)
        screen.blit(left_surface, (10, rect.top + 9))

        detail = "Tile: outside map"
        if hovered_tile is not None:
            tile_x, tile_y = hovered_tile
            tile_key = self.state.tile_at(tile_x, tile_y)
            definition = self.state.definitions[tile_key]
            solid = "solid" if definition.solid else "walkable"
            detail = (
                f"Tile: ({tile_x}, {tile_y}) key={tile_key!r} "
                f"name={definition.name!r} {solid}"
            )
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

    def _map_view_height(self, screen: pygame.Surface) -> int:
        return max(0, screen.get_height() - BOTTOM_PANEL_HEIGHT)
