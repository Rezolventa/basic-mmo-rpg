from __future__ import annotations

from collections.abc import Iterable

import pygame

from basic_mmo_rpg.client.camera import Camera
from basic_mmo_rpg.domain.geometry import Rect, Vec2
from basic_mmo_rpg.domain.movement import PlayerState
from basic_mmo_rpg.domain.tiles import TileMap

BACKGROUND = (18, 20, 23)
GRID_LINE = (24, 26, 29)
PLAYER_BODY = (198, 64, 52)
PLAYER_TUNIC = (218, 191, 105)
PLAYER_OUTLINE = (36, 24, 22)
REMOTE_PLAYER_BODY = (61, 113, 196)
REMOTE_PLAYER_TUNIC = (132, 198, 225)


class Renderer:
    """
    Отрисовывает тайловую карту и сущности игроков средствами pygame.
    """

    def __init__(self, tile_map: TileMap) -> None:
        """
        Создает рендерер и подготавливает кэшированные поверхности тайлов карты.
        """
        self.tile_map = tile_map
        self.tile_surfaces = {
            key: self._create_tile_surface(definition.color)
            for key, definition in tile_map.definitions.items()
        }

    def draw(
        self,
        screen: pygame.Surface,
        camera: Camera,
        player: PlayerState,
        other_players: Iterable[PlayerState] = (),
    ) -> None:
        """
        Рисует полный игровой кадр на переданной поверхности.
        """
        screen.fill(BACKGROUND)
        self._draw_map(screen, camera)
        for other_player in other_players:
            self._draw_player(
                screen,
                camera,
                other_player,
                body_color=REMOTE_PLAYER_BODY,
                tunic_color=REMOTE_PLAYER_TUNIC,
            )
        self._draw_player(
            screen,
            camera,
            player,
            body_color=PLAYER_BODY,
            tunic_color=PLAYER_TUNIC,
        )

    def _draw_map(self, screen: pygame.Surface, camera: Camera) -> None:
        """
        Рисует видимую часть тайловой карты с учетом текущего смещения камеры.
        """
        tile_size = self.tile_map.tile_size
        viewport_width, viewport_height = screen.get_size()

        start_x = max(0, int(camera.offset.x // tile_size))
        start_y = max(0, int(camera.offset.y // tile_size))
        end_x = min(self.tile_map.width, int((camera.offset.x + viewport_width) // tile_size) + 2)
        end_y = min(self.tile_map.height, int((camera.offset.y + viewport_height) // tile_size) + 2)

        for tile_y in range(start_y, end_y):
            for tile_x in range(start_x, end_x):
                tile_key = self.tile_map.tile_at(tile_x, tile_y)
                surface = self.tile_surfaces[tile_key]
                world_position = Vec2(tile_x * tile_size, tile_y * tile_size)
                screen_position = camera.world_to_screen(world_position)
                screen.blit(surface, screen_position)

    def _draw_player(
        self,
        screen: pygame.Surface,
        camera: Camera,
        player: PlayerState,
        body_color: tuple[int, int, int],
        tunic_color: tuple[int, int, int],
    ) -> None:
        """
        Рисует одного игрока в экранных координатах с заданными цветами.
        """
        player_rect = player.rect
        screen_position = camera.world_to_screen(player.position)
        body = pygame.Rect(
            screen_position[0],
            screen_position[1],
            int(player_rect.width),
            int(player_rect.height),
        )
        pygame.draw.rect(screen, PLAYER_OUTLINE, body.inflate(4, 4), border_radius=3)
        pygame.draw.rect(screen, body_color, body, border_radius=3)

        tunic = pygame.Rect(body.left + 4, body.top + 10, body.width - 8, body.height - 12)
        pygame.draw.rect(screen, tunic_color, tunic, border_radius=2)

    def _create_tile_surface(self, base_color: tuple[int, int, int]) -> pygame.Surface:
        """
        Создает простую декоративную поверхность тайла на основе базового цвета.
        """
        size = self.tile_map.tile_size
        surface = pygame.Surface((size, size)).convert()
        surface.fill(base_color)

        darker = tuple(max(0, channel - 18) for channel in base_color)
        lighter = tuple(min(255, channel + 12) for channel in base_color)
        pygame.draw.line(surface, lighter, (0, 0), (size, 0))
        pygame.draw.line(surface, lighter, (0, 0), (0, size))
        pygame.draw.line(surface, darker, (0, size - 1), (size, size - 1))
        pygame.draw.line(surface, darker, (size - 1, 0), (size - 1, size))

        for dot_x, dot_y in ((7, 10), (21, 6), (15, 23)):
            pygame.draw.rect(surface, GRID_LINE, Rect(dot_x, dot_y, 2, 2).to_pygame())

        return surface
