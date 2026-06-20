from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import pygame

from basic_mmo_rpg.client.camera import Camera
from basic_mmo_rpg.client.ui import ChatLine
from basic_mmo_rpg.domain.entities import WorldEntity
from basic_mmo_rpg.domain.geometry import Rect, Vec2
from basic_mmo_rpg.domain.inventory import ItemStack
from basic_mmo_rpg.domain.movement import PlayerState
from basic_mmo_rpg.domain.tiles import TileMap

BACKGROUND = (18, 20, 23)
GRID_LINE = (24, 26, 29)
PLAYER_BODY = (198, 64, 52)
PLAYER_TUNIC = (218, 191, 105)
PLAYER_OUTLINE = (36, 24, 22)
REMOTE_PLAYER_BODY = (61, 113, 196)
REMOTE_PLAYER_TUNIC = (132, 198, 225)
NPC_BODY = (76, 96, 74)
NPC_TUNIC = (197, 178, 112)
NPC_OUTLINE = (28, 35, 28)
HOVER_OUTLINE = (238, 216, 112)
WATER_HOVER_FILL = (112, 190, 235, 70)
WATER_HOVER_BORDER = (178, 226, 250)
TREE_HOVER_FILL = (204, 179, 89, 85)
TREE_HOVER_BORDER = (235, 209, 118)
ROCK_HOVER_FILL = (178, 184, 192, 85)
ROCK_HOVER_BORDER = (218, 224, 232)
TEXT_COLOR = (236, 238, 241)
MUTED_TEXT_COLOR = (180, 187, 196)
BUBBLE_BACKGROUND = (20, 22, 26)
BUBBLE_BORDER = (224, 225, 228)
PANEL_BACKGROUND = (16, 18, 22, 220)
INPUT_BACKGROUND = (12, 14, 18, 230)


class Renderer:
    """
    Отрисовывает тайловую карту, игроков и простой UI средствами pygame.
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
        self.font = pygame.font.SysFont("arial", 18)
        self.small_font = pygame.font.SysFont("arial", 15)

    def draw(
        self,
        screen: pygame.Surface,
        camera: Camera,
        player: PlayerState,
        other_players: Iterable[PlayerState] = (),
        world_entities: Iterable[WorldEntity] = (),
        player_names: Mapping[str, str] | None = None,
        speech_bubbles: Mapping[str, str] | None = None,
        name_tags: Mapping[str, str] | None = None,
        entity_speech_bubbles: Mapping[str, str] | None = None,
        hovered_entity_id: str | None = None,
        hovered_tile: tuple[int, int] | None = None,
        chat_lines: Sequence[ChatLine] = (),
        chat_input_active: bool = False,
        chat_input_text: str = "",
        chat_journal_visible: bool = False,
        inventory_items: Sequence[ItemStack] = (),
        inventory_visible: bool = False,
    ) -> None:
        """
        Рисует полный игровой кадр на переданной поверхности.
        """
        other_player_list = list(other_players)
        player_names = player_names or {}
        speech_bubbles = speech_bubbles or {}
        name_tags = name_tags or {}
        entity_speech_bubbles = entity_speech_bubbles or {}
        entity_list = list(world_entities)

        screen.fill(BACKGROUND)
        self._draw_map(screen, camera)
        if hovered_tile is not None:
            self._draw_hovered_tile(screen, camera, hovered_tile)
        for entity in entity_list:
            self._draw_entity(
                screen,
                camera,
                entity,
                hovered=entity.entity_id == hovered_entity_id,
            )
        for other_player in other_player_list:
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
        self._draw_floating_texts(
            screen=screen,
            camera=camera,
            players=[player, *other_player_list],
            player_names=player_names,
            speech_bubbles=speech_bubbles,
            name_tags=name_tags,
        )
        self._draw_entity_floating_texts(
            screen=screen,
            camera=camera,
            entities=entity_list,
            speech_bubbles=entity_speech_bubbles,
            hovered_entity_id=hovered_entity_id,
        )
        if chat_journal_visible:
            self._draw_chat_journal(screen, chat_lines)
        if inventory_visible:
            self._draw_inventory(screen, inventory_items)
        if chat_input_active:
            self._draw_chat_input(screen, chat_input_text)

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

    def _draw_hovered_tile(
        self,
        screen: pygame.Surface,
        camera: Camera,
        tile: tuple[int, int],
    ) -> None:
        """
        Рисует подсветку тайла под курсором.
        """
        tile_x, tile_y = tile
        tile_rect = self.tile_map.tile_rect(tile_x, tile_y)
        fill_color, border_color = self._hover_colors_for_tile(tile_x, tile_y)
        screen_position = camera.world_to_screen(Vec2(tile_rect.x, tile_rect.y))
        rect = pygame.Rect(
            screen_position[0],
            screen_position[1],
            int(tile_rect.width),
            int(tile_rect.height),
        )
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        overlay.fill(fill_color)
        screen.blit(overlay, rect.topleft)
        pygame.draw.rect(screen, border_color, rect, width=2)

    def _hover_colors_for_tile(
        self,
        tile_x: int,
        tile_y: int,
    ) -> tuple[tuple[int, int, int, int], tuple[int, int, int]]:
        """
        Возвращает цвета подсветки для ресурсного тайла.
        """
        if self.tile_map.is_tree_tile(tile_x, tile_y):
            return TREE_HOVER_FILL, TREE_HOVER_BORDER
        if self.tile_map.is_rock_tile(tile_x, tile_y):
            return ROCK_HOVER_FILL, ROCK_HOVER_BORDER
        return WATER_HOVER_FILL, WATER_HOVER_BORDER

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
        body = self._player_screen_rect(camera, player)
        pygame.draw.rect(screen, PLAYER_OUTLINE, body.inflate(4, 4), border_radius=3)
        pygame.draw.rect(screen, body_color, body, border_radius=3)

        tunic = pygame.Rect(body.left + 4, body.top + 10, body.width - 8, body.height - 12)
        pygame.draw.rect(screen, tunic_color, tunic, border_radius=2)

    def _draw_entity(
        self,
        screen: pygame.Surface,
        camera: Camera,
        entity: WorldEntity,
        hovered: bool,
    ) -> None:
        """
        Рисует один объект мира в экранных координатах.
        """
        body = self._entity_screen_rect(camera, entity)
        outline_color = HOVER_OUTLINE if hovered else NPC_OUTLINE
        pygame.draw.rect(screen, outline_color, body.inflate(6, 6), border_radius=3)
        pygame.draw.rect(screen, NPC_BODY, body, border_radius=3)

        tunic = pygame.Rect(body.left + 4, body.top + 9, body.width - 8, body.height - 11)
        pygame.draw.rect(screen, NPC_TUNIC, tunic, border_radius=2)
        face = pygame.Rect(body.left + 7, body.top + 4, body.width - 14, 7)
        pygame.draw.rect(screen, TEXT_COLOR, face, border_radius=2)

    def _draw_floating_texts(
        self,
        screen: pygame.Surface,
        camera: Camera,
        players: Sequence[PlayerState],
        player_names: Mapping[str, str],
        speech_bubbles: Mapping[str, str],
        name_tags: Mapping[str, str],
    ) -> None:
        """
        Рисует временные реплики и никнеймы над головами игроков.
        """
        players_by_id = {player.entity_id: player for player in players}
        for player_id, player in players_by_id.items():
            y_offset = 0
            if player_id in speech_bubbles:
                y_offset = self._draw_bubble(
                    screen,
                    camera,
                    player,
                    speech_bubbles[player_id],
                    y_offset,
                )
            if player_id in name_tags:
                self._draw_name_tag(
                    screen,
                    camera,
                    player,
                    name_tags[player_id] or player_names.get(player_id, player_id),
                    y_offset,
                )

    def _draw_entity_floating_texts(
        self,
        screen: pygame.Surface,
        camera: Camera,
        entities: Sequence[WorldEntity],
        speech_bubbles: Mapping[str, str],
        hovered_entity_id: str | None,
    ) -> None:
        """
        Рисует временные реплики и hover-имена над объектами мира.
        """
        for entity in entities:
            y_offset = 0
            body = self._entity_screen_rect(camera, entity)
            if entity.entity_id in speech_bubbles:
                y_offset = self._draw_bubble_above_rect(
                    screen,
                    body,
                    speech_bubbles[entity.entity_id],
                    y_offset,
                )
            if entity.entity_id == hovered_entity_id:
                self._draw_name_tag_above_rect(screen, body, entity.name, y_offset)

    def _draw_bubble(
        self,
        screen: pygame.Surface,
        camera: Camera,
        player: PlayerState,
        text: str,
        y_offset: int,
    ) -> int:
        """
        Рисует одну реплику над головой игрока и возвращает занятое смещение.
        """
        body = self._player_screen_rect(camera, player)
        return self._draw_bubble_above_rect(screen, body, text, y_offset)

    def _draw_bubble_above_rect(
        self,
        screen: pygame.Surface,
        body: pygame.Rect,
        text: str,
        y_offset: int,
    ) -> int:
        """
        Рисует реплику над прямоугольником и возвращает занятое смещение.
        """
        lines = self._wrap_text(text, max_width=260, font=self.font)
        line_surfaces = [self.font.render(line, True, TEXT_COLOR) for line in lines]
        width = max(surface.get_width() for surface in line_surfaces) + 16
        height = len(line_surfaces) * self.font.get_linesize() + 12
        anchor = self._floating_anchor_for_rect(body, height + y_offset)
        rect = pygame.Rect(anchor[0] - width // 2, anchor[1], width, height)

        pygame.draw.rect(screen, BUBBLE_BACKGROUND, rect, border_radius=6)
        pygame.draw.rect(screen, BUBBLE_BORDER, rect, width=1, border_radius=6)
        text_y = rect.top + 6
        for surface in line_surfaces:
            screen.blit(surface, (rect.centerx - surface.get_width() // 2, text_y))
            text_y += self.font.get_linesize()
        return y_offset + height + 4

    def _draw_name_tag(
        self,
        screen: pygame.Surface,
        camera: Camera,
        player: PlayerState,
        name: str,
        y_offset: int,
    ) -> None:
        """
        Рисует временный никнейм над головой игрока.
        """
        body = self._player_screen_rect(camera, player)
        self._draw_name_tag_above_rect(screen, body, name, y_offset)

    def _draw_name_tag_above_rect(
        self,
        screen: pygame.Surface,
        body: pygame.Rect,
        name: str,
        y_offset: int,
    ) -> None:
        """
        Рисует временное имя над прямоугольником.
        """
        surface = self.small_font.render(name, True, TEXT_COLOR)
        width = surface.get_width() + 10
        height = surface.get_height() + 6
        anchor = self._floating_anchor_for_rect(body, height + y_offset)
        rect = pygame.Rect(anchor[0] - width // 2, anchor[1], width, height)
        pygame.draw.rect(screen, INPUT_BACKGROUND, rect, border_radius=4)
        pygame.draw.rect(screen, BUBBLE_BORDER, rect, width=1, border_radius=4)
        screen.blit(surface, (rect.centerx - surface.get_width() // 2, rect.top + 3))

    def _draw_chat_journal(self, screen: pygame.Surface, chat_lines: Sequence[ChatLine]) -> None:
        """
        Рисует журнал последних сообщений чата.
        """
        width = min(520, screen.get_width() - 40)
        height = min(320, screen.get_height() - 90)
        panel = pygame.Surface((width, height), pygame.SRCALPHA)
        panel.fill(PANEL_BACKGROUND)
        screen.blit(panel, (20, 20))

        title = self.font.render("Журнал чата", True, TEXT_COLOR)
        screen.blit(title, (32, 30))
        visible_lines = list(chat_lines)[-12:]
        y = 58
        for line in visible_lines:
            text = f"{line.name}: {line.text}"
            for wrapped_line in self._wrap_text(text, max_width=width - 28, font=self.small_font):
                surface = self.small_font.render(wrapped_line, True, MUTED_TEXT_COLOR)
                screen.blit(surface, (32, y))
                y += self.small_font.get_linesize()
                if y > 20 + height - self.small_font.get_linesize():
                    return

    def _draw_chat_input(self, screen: pygame.Surface, chat_input_text: str) -> None:
        """
        Рисует строку ввода сообщения чата.
        """
        margin = 18
        height = 38
        rect = pygame.Rect(
            margin,
            screen.get_height() - height - margin,
            screen.get_width() - margin * 2,
            height,
        )
        pygame.draw.rect(screen, INPUT_BACKGROUND, rect, border_radius=5)
        pygame.draw.rect(screen, BUBBLE_BORDER, rect, width=1, border_radius=5)
        prefix = "> "
        visible_text = self._tail_to_width(
            text=chat_input_text,
            max_width=rect.width - 20 - self.font.size(prefix)[0],
            font=self.font,
        )
        text = f"{prefix}{visible_text}"
        surface = self.font.render(text, True, TEXT_COLOR)
        screen.blit(surface, (rect.left + 10, rect.centery - surface.get_height() // 2))

    def _draw_inventory(self, screen: pygame.Surface, items: Sequence[ItemStack]) -> None:
        """
        Рисует простую панель инвентаря.
        """
        width = 280
        height = min(320, screen.get_height() - 90)
        left = screen.get_width() - width - 20
        panel = pygame.Surface((width, height), pygame.SRCALPHA)
        panel.fill(PANEL_BACKGROUND)
        screen.blit(panel, (left, 20))

        title = self.font.render("Инвентарь", True, TEXT_COLOR)
        screen.blit(title, (left + 12, 30))

        if not items:
            empty = self.small_font.render("Пусто", True, MUTED_TEXT_COLOR)
            screen.blit(empty, (left + 12, 62))
            return

        y = 62
        for item in items:
            quantity_suffix = f" x{item.quantity}" if item.quantity > 1 else ""
            text = f"{item.display_name}{quantity_suffix}"
            surface = self.small_font.render(text, True, MUTED_TEXT_COLOR)
            screen.blit(surface, (left + 12, y))
            y += self.small_font.get_linesize() + 4
            if y > 20 + height - self.small_font.get_linesize():
                return

    def _player_screen_rect(self, camera: Camera, player: PlayerState) -> pygame.Rect:
        """
        Возвращает прямоугольник игрока в экранных координатах.
        """
        player_rect = player.rect
        screen_position = camera.world_to_screen(player.position)
        return pygame.Rect(
            screen_position[0],
            screen_position[1],
            int(player_rect.width),
            int(player_rect.height),
        )

    def _entity_screen_rect(self, camera: Camera, entity: WorldEntity) -> pygame.Rect:
        """
        Возвращает прямоугольник объекта мира в экранных координатах.
        """
        entity_rect = entity.rect
        screen_position = camera.world_to_screen(entity.position)
        return pygame.Rect(
            screen_position[0],
            screen_position[1],
            int(entity_rect.width),
            int(entity_rect.height),
        )

    def _floating_anchor(
        self,
        camera: Camera,
        player: PlayerState,
        height_with_offset: int,
    ) -> tuple[int, int]:
        """
        Возвращает точку привязки текста над головой игрока.
        """
        body = self._player_screen_rect(camera, player)
        return self._floating_anchor_for_rect(body, height_with_offset)

    def _floating_anchor_for_rect(
        self,
        body: pygame.Rect,
        height_with_offset: int,
    ) -> tuple[int, int]:
        """
        Возвращает точку привязки текста над экранным прямоугольником.
        """
        return body.centerx, body.top - height_with_offset - 8

    def _wrap_text(
        self,
        text: str,
        max_width: int,
        font: pygame.font.Font,
    ) -> list[str]:
        """
        Разбивает текст на строки, помещающиеся в заданную ширину.
        """
        words = text.split()
        if not words:
            return [""]

        lines: list[str] = []
        current_line = ""
        for word in words:
            for part in self._split_word_to_width(word, max_width, font):
                candidate = part if not current_line else f"{current_line} {part}"
                if not current_line or font.size(candidate)[0] <= max_width:
                    current_line = candidate
                    continue
                lines.append(current_line)
                current_line = part
        if current_line:
            lines.append(current_line)
        return lines[:4]

    def _split_word_to_width(
        self,
        word: str,
        max_width: int,
        font: pygame.font.Font,
    ) -> list[str]:
        """
        Разбивает длинное слово на куски, которые помещаются в заданную ширину.
        """
        if font.size(word)[0] <= max_width:
            return [word]

        chunks: list[str] = []
        current_chunk = ""
        for char in word:
            candidate = f"{current_chunk}{char}"
            if current_chunk and font.size(candidate)[0] > max_width:
                chunks.append(current_chunk)
                current_chunk = char
            else:
                current_chunk = candidate
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    def _tail_to_width(
        self,
        text: str,
        max_width: int,
        font: pygame.font.Font,
    ) -> str:
        """
        Возвращает правую часть строки, которая помещается в заданную ширину.
        """
        if max_width <= 0:
            return ""
        if font.size(text)[0] <= max_width:
            return text

        visible_text = text
        while visible_text and font.size(visible_text)[0] > max_width:
            visible_text = visible_text[1:]
        return visible_text

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
