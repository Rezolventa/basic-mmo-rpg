from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import pygame

from basic_mmo_rpg.client.camera import Camera
from basic_mmo_rpg.client.ui import ChatLine, InventoryPanelHit
from basic_mmo_rpg.domain.entities import EntityKind, WorldEntity
from basic_mmo_rpg.domain.equipment import MAIN_HAND_SLOT, Equipment
from basic_mmo_rpg.domain.geometry import Rect, Vec2
from basic_mmo_rpg.domain.inventory import ItemStack, is_equippable_item, item_definition_for
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
GATE_CLOSED = (126, 88, 48)
GATE_OPEN = (91, 65, 42)
SHEEP_WOOL = (226, 226, 213)
SHEEP_SHORN = (176, 169, 158)
SHEEP_FACE = (58, 49, 44)
BOAR_BODY = (92, 67, 52)
BOAR_BACK = (122, 91, 68)
BOAR_SNOUT = (65, 45, 38)
CORPSE_BODY = (82, 64, 56)
CORPSE_OUTLINE = (42, 34, 32)
RESPAWN_CROSS = (219, 214, 196)
RESPAWN_CROSS_SHADOW = (78, 72, 65)
DUMMY_WOOD = (147, 102, 58)
DUMMY_CLOTH = (117, 85, 54)
DUMMY_BASE = (82, 60, 42)
HOVER_OUTLINE = (238, 216, 112)
WATER_HOVER_FILL = (112, 190, 235, 70)
WATER_HOVER_BORDER = (178, 226, 250)
TREE_HOVER_FILL = (204, 179, 89, 85)
TREE_HOVER_BORDER = (235, 209, 118)
ROCK_HOVER_FILL = (178, 184, 192, 85)
ROCK_HOVER_BORDER = (218, 224, 232)
ATTACK_HOVER_OUTLINE = (172, 38, 48)
TARGET_CROSSHAIR = (92, 9, 22)
HEALTH_BAR_BACK = (45, 18, 20)
HEALTH_BAR_FILL = (176, 43, 54)
TEXT_COLOR = (236, 238, 241)
MUTED_TEXT_COLOR = (180, 187, 196)
EQUIPPABLE_TEXT_COLOR = (223, 215, 166)
BUBBLE_BACKGROUND = (20, 22, 26)
BUBBLE_BORDER = (224, 225, 228)
PANEL_BACKGROUND = (16, 18, 22, 220)
INPUT_BACKGROUND = (12, 14, 18, 230)
SLOT_BACKGROUND = (29, 32, 38, 230)
SLOT_BORDER = (92, 104, 118)
EQUIPPED_BORDER = (225, 198, 104)


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
        equipment: Equipment | None = None,
        inventory_visible: bool = False,
        combat_mode_active: bool = False,
        hovered_attackable_entity_id: str | None = None,
        selected_attack_target_id: str | None = None,
        death_dialog_visible: bool = False,
        system_message: str | None = None,
    ) -> None:
        """
        Рисует полный игровой кадр на переданной поверхности.
        """
        other_player_list = list(other_players)
        player_names = player_names or {}
        speech_bubbles = speech_bubbles or {}
        name_tags = name_tags or {}
        entity_speech_bubbles = entity_speech_bubbles or {}
        equipment = equipment or Equipment()
        entity_list = [entity for entity in world_entities if entity.visible]

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
                attack_hovered=(
                    combat_mode_active and entity.entity_id == hovered_attackable_entity_id
                ),
                selected=entity.entity_id == selected_attack_target_id,
            )
        for other_player in other_player_list:
            if other_player.is_alive:
                self._draw_player(
                    screen,
                    camera,
                    other_player,
                    body_color=REMOTE_PLAYER_BODY,
                    tunic_color=REMOTE_PLAYER_TUNIC,
                )
        if player.is_alive:
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
            self._draw_inventory(screen, inventory_items, equipment)
        if chat_input_active:
            self._draw_chat_input(screen, chat_input_text)
        if system_message:
            self._draw_system_message(screen, system_message)
        if death_dialog_visible:
            self._draw_death_dialog(screen)

    def inventory_hit_at_position(
        self,
        screen: pygame.Surface,
        position: tuple[int, int],
        items: Sequence[ItemStack],
    ) -> InventoryPanelHit | None:
        """
        Возвращает цель панели инвентаря или пустой hit для consume-а клика внутри панели.
        """
        if not self._inventory_panel_rect(screen).collidepoint(position):
            return None
        if self._main_hand_slot_rect(screen).collidepoint(position):
            return InventoryPanelHit(slot=MAIN_HAND_SLOT)

        for item, row_rect in self._inventory_item_rects(screen, items):
            if row_rect.collidepoint(position) and is_equippable_item(item.item_id):
                return InventoryPanelHit(item_id=item.item_id)
        return InventoryPanelHit()

    def respawn_button_hit_at_position(
        self,
        screen: pygame.Surface,
        position: tuple[int, int],
    ) -> bool:
        """
        Возвращает, попал ли клик по кнопке возрождения.
        """
        return self._respawn_button_rect(screen).collidepoint(position)

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

    def _draw_system_message(self, screen: pygame.Surface, message: str) -> None:
        """
        Рисует важное системное сообщение поверх игрового кадра.
        """
        max_width = min(720, screen.get_width() - 24)
        lines = self._wrap_text(message, max_width - 24, self.small_font)
        line_height = self.small_font.get_height() + 3
        panel_height = 16 + len(lines) * line_height
        panel = pygame.Rect(12, 12, max_width, panel_height)
        pygame.draw.rect(screen, INPUT_BACKGROUND, panel, border_radius=6)
        pygame.draw.rect(screen, SLOT_BORDER, panel, width=1, border_radius=6)
        y = panel.top + 8
        for line in lines:
            text_surface = self.small_font.render(line, True, TEXT_COLOR)
            screen.blit(text_surface, (panel.left + 12, y))
            y += line_height

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
        attack_hovered: bool,
        selected: bool,
    ) -> None:
        """
        Рисует один объект мира в экранных координатах.
        """
        body = self._entity_screen_rect(camera, entity)
        outline_color = NPC_OUTLINE
        if hovered:
            outline_color = HOVER_OUTLINE
        if attack_hovered:
            outline_color = ATTACK_HOVER_OUTLINE
        if entity.visual == "boar_corpse":
            self._draw_boar_corpse(screen, body, outline_color)
            return
        if entity.visual == "respawn_cross":
            self._draw_respawn_cross(screen, body, outline_color)
            return
        if entity.kind == EntityKind.GATE:
            self._draw_gate(screen, body, entity, outline_color)
            if selected:
                self._draw_target_crosshair(screen, body)
            self._draw_health_bar(screen, body, entity, selected or attack_hovered)
            return
        if entity.kind == EntityKind.CREATURE:
            self._draw_creature(screen, body, entity, outline_color)
            self._draw_health_bar(screen, body, entity, selected or attack_hovered)
            if selected:
                self._draw_target_crosshair(screen, body)
            return
        if entity.kind == EntityKind.LOOTABLE or entity.visual == "training_dummy":
            self._draw_lootable(screen, body, outline_color)
            self._draw_health_bar(screen, body, entity, selected or attack_hovered)
            if selected:
                self._draw_target_crosshair(screen, body)
            return

        pygame.draw.rect(screen, outline_color, body.inflate(6, 6), border_radius=3)
        pygame.draw.rect(screen, NPC_BODY, body, border_radius=3)

        tunic = pygame.Rect(body.left + 4, body.top + 9, body.width - 8, body.height - 11)
        pygame.draw.rect(screen, NPC_TUNIC, tunic, border_radius=2)
        face = pygame.Rect(body.left + 7, body.top + 4, body.width - 14, 7)
        pygame.draw.rect(screen, TEXT_COLOR, face, border_radius=2)
        if selected:
            self._draw_target_crosshair(screen, body)
        self._draw_health_bar(screen, body, entity, selected or attack_hovered)

    def _draw_target_crosshair(self, screen: pygame.Surface, body: pygame.Rect) -> None:
        """
        Рисует темно-красное перекрестие выбранной боевой цели.
        """
        center = body.center
        outer = max(body.width, body.height) // 2 + 7
        gap = max(5, min(body.width, body.height) // 3)
        pygame.draw.line(
            screen,
            TARGET_CROSSHAIR,
            (center[0] - outer, center[1]),
            (center[0] - gap, center[1]),
            width=2,
        )
        pygame.draw.line(
            screen,
            TARGET_CROSSHAIR,
            (center[0] + gap, center[1]),
            (center[0] + outer, center[1]),
            width=2,
        )
        pygame.draw.line(
            screen,
            TARGET_CROSSHAIR,
            (center[0], center[1] - outer),
            (center[0], center[1] - gap),
            width=2,
        )
        pygame.draw.line(
            screen,
            TARGET_CROSSHAIR,
            (center[0], center[1] + gap),
            (center[0], center[1] + outer),
            width=2,
        )

    def _draw_gate(
        self,
        screen: pygame.Surface,
        body: pygame.Rect,
        entity: WorldEntity,
        outline_color: tuple[int, int, int],
    ) -> None:
        """
        Рисует калитку с учетом открытого или закрытого состояния.
        """
        pygame.draw.rect(screen, outline_color, body.inflate(4, 4), border_radius=2)
        if entity.is_open:
            rail_width = max(4, body.width // 5)
            left_rail = pygame.Rect(body.left, body.top, rail_width, body.height)
            right_rail = pygame.Rect(body.right - rail_width, body.top, rail_width, body.height)
            pygame.draw.rect(screen, GATE_OPEN, left_rail, border_radius=2)
            pygame.draw.rect(screen, GATE_OPEN, right_rail, border_radius=2)
            return

        pygame.draw.rect(screen, GATE_CLOSED, body, border_radius=2)
        for y in (body.top + 8, body.centery, body.bottom - 8):
            pygame.draw.line(screen, GATE_OPEN, (body.left + 3, y), (body.right - 3, y), width=2)

    def _draw_creature(
        self,
        screen: pygame.Surface,
        body: pygame.Rect,
        entity: WorldEntity,
        outline_color: tuple[int, int, int],
    ) -> None:
        """
        Рисует creature-сущность мира.
        """
        if entity.visual == "boar":
            self._draw_boar(screen, body, outline_color)
            return
        pygame.draw.rect(screen, outline_color, body.inflate(4, 4), border_radius=6)
        body_color = SHEEP_WOOL if entity.has_wool is not False else SHEEP_SHORN
        pygame.draw.rect(screen, body_color, body, border_radius=7)
        face = pygame.Rect(body.left + body.width - 9, body.top + 8, 8, 12)
        pygame.draw.rect(screen, SHEEP_FACE, face, border_radius=3)

    def _draw_boar(
        self,
        screen: pygame.Surface,
        body: pygame.Rect,
        outline_color: tuple[int, int, int],
    ) -> None:
        """
        Рисует кабана.
        """
        pygame.draw.rect(screen, outline_color, body.inflate(4, 4), border_radius=6)
        pygame.draw.ellipse(screen, BOAR_BODY, body)
        back = pygame.Rect(body.left + 3, body.top + 3, body.width - 7, body.height // 2)
        pygame.draw.ellipse(screen, BOAR_BACK, back)
        snout = pygame.Rect(body.right - 7, body.centery - 4, 9, 8)
        pygame.draw.rect(screen, BOAR_SNOUT, snout, border_radius=3)
        tusk_y = body.centery + 3
        pygame.draw.line(
            screen,
            RESPAWN_CROSS,
            (body.right - 1, tusk_y),
            (body.right + 4, tusk_y),
        )

    def _draw_boar_corpse(
        self,
        screen: pygame.Surface,
        body: pygame.Rect,
        outline_color: tuple[int, int, int],
    ) -> None:
        """
        Рисует лежащий труп кабана.
        """
        corpse_rect = body.inflate(4, -4)
        pygame.draw.rect(screen, outline_color, corpse_rect.inflate(4, 4), border_radius=6)
        pygame.draw.ellipse(screen, CORPSE_BODY, corpse_rect)
        pygame.draw.line(
            screen,
            CORPSE_OUTLINE,
            (corpse_rect.left + 5, corpse_rect.centery),
            (corpse_rect.right - 5, corpse_rect.centery + 2),
            width=2,
        )

    def _draw_respawn_cross(
        self,
        screen: pygame.Surface,
        body: pygame.Rect,
        outline_color: tuple[int, int, int],
    ) -> None:
        """
        Рисует точку возрождения персонажа.
        """
        pygame.draw.rect(screen, outline_color, body.inflate(4, 4), border_radius=3)
        pygame.draw.rect(screen, RESPAWN_CROSS_SHADOW, body, border_radius=3)
        vertical = pygame.Rect(body.centerx - 4, body.top + 3, 8, body.height - 6)
        horizontal = pygame.Rect(body.left + 3, body.centery - 4, body.width - 6, 8)
        pygame.draw.rect(screen, RESPAWN_CROSS, vertical, border_radius=2)
        pygame.draw.rect(screen, RESPAWN_CROSS, horizontal, border_radius=2)

    def _draw_health_bar(
        self,
        screen: pygame.Surface,
        body: pygame.Rect,
        entity: WorldEntity,
        visible: bool,
    ) -> None:
        """
        Рисует маленькую полоску HP над боевой целью.
        """
        if not visible or entity.combat is None or entity.combat.max_hit_points <= 0:
            return
        ratio = max(0.0, min(1.0, entity.combat.hit_points / entity.combat.max_hit_points))
        width = max(24, body.width + 8)
        rect = pygame.Rect(body.centerx - width // 2, body.top - 9, width, 4)
        pygame.draw.rect(screen, HEALTH_BAR_BACK, rect)
        fill = pygame.Rect(rect.left, rect.top, int(rect.width * ratio), rect.height)
        pygame.draw.rect(screen, HEALTH_BAR_FILL, fill)

    def _draw_lootable(
        self,
        screen: pygame.Surface,
        body: pygame.Rect,
        outline_color: tuple[int, int, int],
    ) -> None:
        """
        Рисует lootable-объект мира в виде тренировочного манекена.
        """
        pygame.draw.rect(screen, outline_color, body.inflate(5, 5), border_radius=3)
        post_width = max(5, body.width // 4)
        post = pygame.Rect(
            body.centerx - post_width // 2,
            body.top + 2,
            post_width,
            body.height - 5,
        )
        arms = pygame.Rect(body.left + 2, body.top + 10, body.width - 4, max(5, body.height // 5))
        torso = pygame.Rect(body.left + 5, body.top + 16, body.width - 10, body.height - 20)
        base = pygame.Rect(body.left + 1, body.bottom - 5, body.width - 2, 5)

        pygame.draw.rect(screen, DUMMY_WOOD, post, border_radius=2)
        pygame.draw.rect(screen, DUMMY_WOOD, arms, border_radius=2)
        pygame.draw.rect(screen, DUMMY_CLOTH, torso, border_radius=2)
        pygame.draw.rect(screen, DUMMY_BASE, base, border_radius=2)

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
            if entity.entity_id == hovered_entity_id and entity.kind != EntityKind.GATE:
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

    def _draw_death_dialog(self, screen: pygame.Surface) -> None:
        """
        Рисует окно смерти персонажа.
        """
        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 110))
        screen.blit(overlay, (0, 0))

        dialog = self._death_dialog_rect(screen)
        pygame.draw.rect(screen, PANEL_BACKGROUND, dialog, border_radius=6)
        pygame.draw.rect(screen, BUBBLE_BORDER, dialog, width=1, border_radius=6)

        title = self.font.render("Вы погибли", True, TEXT_COLOR)
        screen.blit(title, (dialog.centerx - title.get_width() // 2, dialog.top + 28))

        button = self._respawn_button_rect(screen)
        pygame.draw.rect(screen, SLOT_BACKGROUND, button, border_radius=5)
        pygame.draw.rect(screen, EQUIPPED_BORDER, button, width=1, border_radius=5)
        text = self.font.render("Возродиться", True, TEXT_COLOR)
        screen.blit(
            text,
            (
                button.centerx - text.get_width() // 2,
                button.centery - text.get_height() // 2,
            ),
        )

    def _death_dialog_rect(self, screen: pygame.Surface) -> pygame.Rect:
        """
        Возвращает прямоугольник окна смерти.
        """
        width = min(300, screen.get_width() - 40)
        height = 150
        return pygame.Rect(
            screen.get_width() // 2 - width // 2,
            screen.get_height() // 2 - height // 2,
            width,
            height,
        )

    def _respawn_button_rect(self, screen: pygame.Surface) -> pygame.Rect:
        """
        Возвращает прямоугольник кнопки возрождения.
        """
        dialog = self._death_dialog_rect(screen)
        width = min(180, dialog.width - 40)
        height = 38
        return pygame.Rect(
            dialog.centerx - width // 2,
            dialog.bottom - height - 24,
            width,
            height,
        )

    def _draw_inventory(
        self,
        screen: pygame.Surface,
        items: Sequence[ItemStack],
        equipment: Equipment,
    ) -> None:
        """
        Рисует простую панель инвентаря и paperdoll.
        """
        panel_rect = self._inventory_panel_rect(screen)
        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        panel.fill(PANEL_BACKGROUND)
        screen.blit(panel, panel_rect.topleft)

        paper_title = self.font.render("Paperdoll", True, TEXT_COLOR)
        screen.blit(paper_title, (panel_rect.left + 12, panel_rect.top + 10))
        inventory_title_position = self._inventory_list_origin(screen)
        title = self.font.render("Инвентарь", True, TEXT_COLOR)
        screen.blit(title, (inventory_title_position[0], panel_rect.top + 10))

        self._draw_main_hand_slot(screen, equipment)

        if not items:
            empty = self.small_font.render("Пусто", True, MUTED_TEXT_COLOR)
            screen.blit(empty, (inventory_title_position[0], panel_rect.top + 42))
            return

        for item, row_rect in self._inventory_item_rects(screen, items):
            quantity_suffix = f" x{item.quantity}" if item.quantity > 1 else ""
            text = f"{item.display_name}{quantity_suffix}"
            if equipment.main_hand == item.item_id:
                text = f"{text} (в руке)"
            color = EQUIPPABLE_TEXT_COLOR if is_equippable_item(item.item_id) else MUTED_TEXT_COLOR
            surface = self.small_font.render(
                self._tail_to_width(text, row_rect.width - 10, self.small_font),
                True,
                color,
            )
            screen.blit(surface, (row_rect.left + 5, row_rect.top + 3))

    def _draw_main_hand_slot(self, screen: pygame.Surface, equipment: Equipment) -> None:
        """
        Рисует слот предмета в руке.
        """
        slot_rect = self._main_hand_slot_rect(screen)
        label = self.small_font.render("В руке", True, MUTED_TEXT_COLOR)
        screen.blit(label, (slot_rect.left, slot_rect.top - self.small_font.get_linesize() - 2))

        border_color = EQUIPPED_BORDER if equipment.main_hand is not None else SLOT_BORDER
        pygame.draw.rect(screen, SLOT_BACKGROUND, slot_rect, border_radius=4)
        pygame.draw.rect(screen, border_color, slot_rect, width=1, border_radius=4)

        item_text = "Пусто"
        text_color = MUTED_TEXT_COLOR
        if equipment.main_hand is not None:
            item_text = item_definition_for(equipment.main_hand).display_name
            text_color = TEXT_COLOR
        visible_text = self._tail_to_width(item_text, slot_rect.width - 12, self.small_font)
        surface = self.small_font.render(visible_text, True, text_color)
        screen.blit(surface, (slot_rect.left + 6, slot_rect.centery - surface.get_height() // 2))

    def _inventory_panel_rect(self, screen: pygame.Surface) -> pygame.Rect:
        """
        Возвращает прямоугольник панели инвентаря и paperdoll.
        """
        width = min(460, max(300, screen.get_width() - 40))
        height = min(320, screen.get_height() - 90)
        left = max(20, screen.get_width() - width - 20)
        return pygame.Rect(left, 20, width, height)

    def _main_hand_slot_rect(self, screen: pygame.Surface) -> pygame.Rect:
        """
        Возвращает прямоугольник слота предмета в руке.
        """
        panel_rect = self._inventory_panel_rect(screen)
        slot_width = min(138, max(104, panel_rect.width // 3))
        return pygame.Rect(panel_rect.left + 12, panel_rect.top + 66, slot_width, 34)

    def _inventory_list_origin(self, screen: pygame.Surface) -> tuple[int, int]:
        """
        Возвращает верхнюю левую точку списка предметов.
        """
        slot_rect = self._main_hand_slot_rect(screen)
        return slot_rect.right + 18, self._inventory_panel_rect(screen).top + 42

    def _inventory_item_rects(
        self,
        screen: pygame.Surface,
        items: Sequence[ItemStack],
    ) -> list[tuple[ItemStack, pygame.Rect]]:
        """
        Возвращает прямоугольники строк инвентаря.
        """
        panel_rect = self._inventory_panel_rect(screen)
        x, y = self._inventory_list_origin(screen)
        row_height = self.small_font.get_linesize() + 4
        width = max(80, panel_rect.right - x - 12)
        result: list[tuple[ItemStack, pygame.Rect]] = []
        for item in items:
            if y > panel_rect.bottom - row_height - 8:
                break
            result.append((item, pygame.Rect(x, y, width, row_height)))
            y += row_height + 2
        return result

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
