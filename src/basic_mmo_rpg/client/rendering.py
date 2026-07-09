from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

import pygame

from basic_mmo_rpg.client.camera import Camera
from basic_mmo_rpg.client.ui import ChatLine, InventoryPanelHit
from basic_mmo_rpg.domain.entities import EntityKind, WorldEntity
from basic_mmo_rpg.domain.equipment import CHEST_SLOT, MAIN_HAND_SLOT, Equipment
from basic_mmo_rpg.domain.geometry import Rect, Vec2
from basic_mmo_rpg.domain.inventory import (
    ItemStack,
    armor_points_for_item,
    is_equippable_item,
    item_definition_for,
)
from basic_mmo_rpg.domain.movement import PlayerState
from basic_mmo_rpg.domain.skills import DEMO_SKILL_CAP, CharacterSkill, format_skill_percent
from basic_mmo_rpg.domain.tiles import TileDefinition, TileMap
from basic_mmo_rpg.shared.protocol import (
    InteractionMenu,
    InteractionMenuOption,
    VendorOffer,
    VendorWindow,
)

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
FORGE_STONE = (82, 86, 92)
FORGE_FIRE = (213, 80, 42)
FORGE_EMBER = (245, 162, 73)
ANVIL_BODY = (92, 101, 112)
ANVIL_TOP = (146, 156, 166)
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
DISABLED_SLOT_BACKGROUND = (31, 34, 39)
TILE_SPRITE_ROOT = Path(__file__).resolve().parents[3] / "assets" / "sprites"
ENTITY_SPRITE_ROOT = TILE_SPRITE_ROOT / "entities"
ENTITY_SPRITE_PATHS = {
    "training_dummy": "training_dummy.png",
}


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
        self.tile_sprites = {
            key: self._load_tile_sprites(definition.sprites)
            for key, definition in tile_map.definitions.items()
        }
        self.tile_sprite_offsets = {
            key: self._tile_sprite_offsets_for_definition(definition)
            for key, definition in tile_map.definitions.items()
        }
        self.entity_sprites = {
            visual: self._load_entity_sprite(sprite_path)
            for visual, sprite_path in ENTITY_SPRITE_PATHS.items()
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
        event_feed: Sequence[str] = (),
        chat_input_active: bool = False,
        chat_input_text: str = "",
        chat_journal_visible: bool = False,
        inventory_items: Sequence[ItemStack] = (),
        equipment: Equipment | None = None,
        inventory_visible: bool = False,
        character_skills: Sequence[CharacterSkill] = (),
        skills_visible: bool = False,
        interaction_menu: InteractionMenu | None = None,
        vendor_window: VendorWindow | None = None,
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
        self._draw_tile_sprites(screen, camera, foreground=True)
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
        if skills_visible:
            self._draw_skills(screen, character_skills, inventory_visible)
        if interaction_menu is not None:
            self._draw_interaction_menu(screen, interaction_menu)
        if vendor_window is not None:
            self._draw_vendor_window(screen, vendor_window)
        if event_feed:
            self._draw_event_feed(screen, event_feed, chat_input_active)
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
        if self._chest_slot_rect(screen).collidepoint(position):
            return InventoryPanelHit(slot=CHEST_SLOT)

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

    def interaction_menu_hit_at_position(
        self,
        screen: pygame.Surface,
        position: tuple[int, int],
        menu: InteractionMenu,
    ) -> InteractionMenuOption | None:
        """
        Возвращает опцию NPC-окна под курсором.
        """
        for option, rect in self._interaction_menu_option_rects(screen, menu):
            if rect.collidepoint(position):
                return option
        return None

    def vendor_hit_at_position(
        self,
        screen: pygame.Surface,
        position: tuple[int, int],
        vendor_window: VendorWindow,
    ) -> VendorOffer | None:
        """
        Возвращает позицию торговца под курсором.
        """
        for offer, rect in self._vendor_offer_rects(screen, vendor_window):
            if rect.collidepoint(position):
                return offer
        return None

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
        self._draw_tile_sprites(screen, camera, foreground=False)

    def _draw_tile_sprites(
        self,
        screen: pygame.Surface,
        camera: Camera,
        *,
        foreground: bool,
    ) -> None:
        """
        Рисует спрайтовые тайлы. Деревья можно вывести отдельным foreground-слоем.
        """
        tile_size = self.tile_map.tile_size
        for tile_y in range(self.tile_map.height):
            for tile_x in range(self.tile_map.width):
                tile_key = self.tile_map.tile_at(tile_x, tile_y)
                is_foreground_tile = self.tile_map.definitions[tile_key].name == "tree"
                if is_foreground_tile != foreground:
                    continue
                sprites = self.tile_sprites.get(tile_key, ())
                if not sprites:
                    continue
                sprite_index = self._sprite_index_for_tile(tile_key, sprites, tile_x, tile_y)
                sprite = sprites[sprite_index]
                sprite_offsets = self.tile_sprite_offsets.get(tile_key, ())
                offset_x, offset_y = sprite_offsets[sprite_index]
                world_position = Vec2(tile_x * tile_size, tile_y * tile_size)
                screen_x, screen_y = camera.world_to_screen(world_position)
                sprite_x = screen_x + (tile_size - sprite.get_width()) // 2 + offset_x
                sprite_y = screen_y + tile_size - sprite.get_height() + offset_y
                screen.blit(sprite, (sprite_x, sprite_y))

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
        if self.tile_map.is_mineable_tile(tile_x, tile_y):
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
        if entity.visual == "forge":
            self._draw_forge(screen, body, outline_color)
            return
        if entity.visual == "anvil":
            self._draw_anvil(screen, body, outline_color)
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
        if entity.visual == "training_dummy" and self._draw_entity_sprite(
            screen,
            body,
            entity.visual,
            outline_color,
            hovered or attack_hovered,
        ):
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

    def _draw_forge(
        self,
        screen: pygame.Surface,
        body: pygame.Rect,
        outline_color: tuple[int, int, int],
    ) -> None:
        """
        Рисует горн как каменную чашу с огнем.
        """
        pygame.draw.rect(screen, outline_color, body.inflate(5, 5), border_radius=4)
        pygame.draw.rect(screen, FORGE_STONE, body, border_radius=4)
        mouth = pygame.Rect(body.left + 4, body.top + 6, body.width - 8, body.height - 10)
        pygame.draw.rect(screen, INPUT_BACKGROUND, mouth, border_radius=3)
        flame = pygame.Rect(mouth.left + 4, mouth.top + 4, mouth.width - 8, mouth.height - 6)
        pygame.draw.ellipse(screen, FORGE_FIRE, flame)
        ember = flame.inflate(-8, -8)
        if ember.width > 0 and ember.height > 0:
            pygame.draw.ellipse(screen, FORGE_EMBER, ember)

    def _draw_anvil(
        self,
        screen: pygame.Surface,
        body: pygame.Rect,
        outline_color: tuple[int, int, int],
    ) -> None:
        """
        Рисует наковальню простым силуэтом.
        """
        pygame.draw.rect(screen, outline_color, body.inflate(5, 5), border_radius=3)
        top = pygame.Rect(body.left + 2, body.top + 5, body.width - 4, max(8, body.height // 4))
        horn = pygame.Rect(body.right - 5, body.top + 6, 8, max(6, body.height // 5))
        waist = pygame.Rect(
            body.left + body.width // 4,
            top.bottom,
            body.width // 2,
            max(8, body.height // 3),
        )
        base = pygame.Rect(body.left + 4, body.bottom - 8, body.width - 8, 8)
        pygame.draw.rect(screen, ANVIL_TOP, top, border_radius=2)
        pygame.draw.rect(screen, ANVIL_TOP, horn, border_radius=2)
        pygame.draw.rect(screen, ANVIL_BODY, waist, border_radius=2)
        pygame.draw.rect(screen, ANVIL_BODY, base, border_radius=2)

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

    def _draw_entity_sprite(
        self,
        screen: pygame.Surface,
        body: pygame.Rect,
        visual: str,
        outline_color: tuple[int, int, int],
        highlighted: bool,
    ) -> bool:
        """
        Рисует PNG-спрайт world-entity, привязанный нижним центром к body.
        """
        sprite = self.entity_sprites.get(visual)
        if sprite is None:
            return False
        sprite_x = body.centerx - sprite.get_width() // 2
        sprite_y = body.bottom - sprite.get_height()
        if highlighted:
            pygame.draw.rect(screen, outline_color, body.inflate(6, 6), width=2, border_radius=3)
        screen.blit(sprite, (sprite_x, sprite_y))
        return True

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

    def _draw_event_feed(
        self,
        screen: pygame.Surface,
        messages: Sequence[str],
        chat_input_active: bool,
    ) -> None:
        """
        Рисует временные игровые сообщения в левом нижнем углу.
        """
        max_width = min(460, screen.get_width() - 36)
        if max_width <= 80:
            return

        bottom_offset = 72 if chat_input_active else 18
        y = screen.get_height() - bottom_offset
        x = 18
        line_height = self.small_font.get_linesize()
        for message in reversed(messages[-8:]):
            lines = self._wrap_text(message, max_width=max_width - 20, font=self.small_font)
            height = 10 + len(lines) * line_height
            top = y - height
            if top < 12:
                return

            rect = pygame.Rect(x, top, max_width, height)
            panel = pygame.Surface(rect.size, pygame.SRCALPHA)
            panel.fill(INPUT_BACKGROUND)
            screen.blit(panel, rect.topleft)
            pygame.draw.rect(screen, SLOT_BORDER, rect, width=1, border_radius=5)

            text_y = rect.top + 5
            for line in lines:
                surface = self.small_font.render(line, True, TEXT_COLOR)
                screen.blit(surface, (rect.left + 10, text_y))
                text_y += line_height
            y = rect.top - 6

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

    def _draw_interaction_menu(self, screen: pygame.Surface, menu: InteractionMenu) -> None:
        """
        Рисует серверное окно взаимодействия с NPC.
        """
        panel_rect = self._interaction_menu_rect(screen, menu)
        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        panel.fill(PANEL_BACKGROUND)
        screen.blit(panel, panel_rect.topleft)
        pygame.draw.rect(screen, BUBBLE_BORDER, panel_rect, width=1, border_radius=6)

        title = self.font.render(
            self._tail_to_width(menu.title, panel_rect.width - 28, self.font),
            True,
            TEXT_COLOR,
        )
        screen.blit(title, (panel_rect.left + 14, panel_rect.top + 12))

        y = panel_rect.top + 42
        if menu.body:
            for line in self._wrap_text(menu.body, panel_rect.width - 28, self.small_font):
                surface = self.small_font.render(line, True, MUTED_TEXT_COLOR)
                screen.blit(surface, (panel_rect.left + 14, y))
                y += self.small_font.get_linesize()
            y += 8

        for option, row_rect in self._interaction_menu_option_rects(screen, menu):
            background = SLOT_BACKGROUND if option.enabled else DISABLED_SLOT_BACKGROUND
            border = EQUIPPED_BORDER if option.enabled else SLOT_BORDER
            text_color = TEXT_COLOR if option.enabled else MUTED_TEXT_COLOR
            pygame.draw.rect(screen, background, row_rect, border_radius=4)
            pygame.draw.rect(screen, border, row_rect, width=1, border_radius=4)
            label = self._tail_to_width(option.label, row_rect.width - 16, self.small_font)
            surface = self.small_font.render(label, True, text_color)
            screen.blit(surface, (row_rect.left + 8, row_rect.centery - surface.get_height() // 2))

    def _interaction_menu_rect(
        self,
        screen: pygame.Surface,
        menu: InteractionMenu,
    ) -> pygame.Rect:
        """
        Возвращает прямоугольник NPC-окна.
        """
        width = min(460, max(320, screen.get_width() - 40))
        body_lines = self._wrap_text(menu.body, width - 28, self.small_font) if menu.body else []
        height = 62 + len(body_lines) * self.small_font.get_linesize()
        height += len(menu.options) * 38 + 18
        height = min(height, screen.get_height() - 40)
        return pygame.Rect(
            screen.get_width() // 2 - width // 2,
            screen.get_height() // 2 - height // 2,
            width,
            height,
        )

    def _interaction_menu_option_rects(
        self,
        screen: pygame.Surface,
        menu: InteractionMenu,
    ) -> list[tuple[InteractionMenuOption, pygame.Rect]]:
        """
        Возвращает прямоугольники строк опций NPC-окна.
        """
        panel_rect = self._interaction_menu_rect(screen, menu)
        body_lines = (
            self._wrap_text(menu.body, panel_rect.width - 28, self.small_font)
            if menu.body
            else []
        )
        y = panel_rect.top + 42 + len(body_lines) * self.small_font.get_linesize()
        if body_lines:
            y += 8
        result: list[tuple[InteractionMenuOption, pygame.Rect]] = []
        for option in menu.options:
            row_rect = pygame.Rect(panel_rect.left + 14, y, panel_rect.width - 28, 32)
            if row_rect.bottom > panel_rect.bottom - 10:
                break
            result.append((option, row_rect))
            y += 38
        return result

    def _draw_vendor_window(self, screen: pygame.Surface, vendor_window: VendorWindow) -> None:
        """
        Рисует серверное окно торговца.
        """
        panel_rect = self._vendor_window_rect(screen, vendor_window)
        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        panel.fill(PANEL_BACKGROUND)
        screen.blit(panel, panel_rect.topleft)
        pygame.draw.rect(screen, BUBBLE_BORDER, panel_rect, width=1, border_radius=6)

        title = self.font.render(
            self._tail_to_width(
                f"{vendor_window.title}: торговля",
                panel_rect.width - 28,
                self.font,
            ),
            True,
            TEXT_COLOR,
        )
        screen.blit(title, (panel_rect.left + 14, panel_rect.top + 12))

        for offer, row_rect in self._vendor_offer_rects(screen, vendor_window):
            background = SLOT_BACKGROUND if offer.enabled else DISABLED_SLOT_BACKGROUND
            border = EQUIPPED_BORDER if offer.enabled else SLOT_BORDER
            text_color = TEXT_COLOR if offer.enabled else MUTED_TEXT_COLOR
            pygame.draw.rect(screen, background, row_rect, border_radius=4)
            pygame.draw.rect(screen, border, row_rect, width=1, border_radius=4)

            price_text = (
                f"{offer.display_name} - {offer.price_quantity} {offer.price_display_name}"
            )
            if offer.details is not None:
                price_text = f"{price_text} ({offer.details})"
            if offer.disabled_reason is not None:
                price_text = f"{price_text} - {offer.disabled_reason}"
            visible_text = self._tail_to_width(price_text, row_rect.width - 16, self.small_font)
            surface = self.small_font.render(visible_text, True, text_color)
            screen.blit(surface, (row_rect.left + 8, row_rect.centery - surface.get_height() // 2))

    def _vendor_window_rect(
        self,
        screen: pygame.Surface,
        vendor_window: VendorWindow,
    ) -> pygame.Rect:
        """
        Возвращает прямоугольник окна торговца.
        """
        width = min(500, max(340, screen.get_width() - 40))
        height = 74 + len(vendor_window.offers) * 42
        height = min(height, screen.get_height() - 40)
        return pygame.Rect(
            screen.get_width() // 2 - width // 2,
            screen.get_height() // 2 - height // 2,
            width,
            height,
        )

    def _vendor_offer_rects(
        self,
        screen: pygame.Surface,
        vendor_window: VendorWindow,
    ) -> list[tuple[VendorOffer, pygame.Rect]]:
        """
        Возвращает прямоугольники строк торговца.
        """
        panel_rect = self._vendor_window_rect(screen, vendor_window)
        y = panel_rect.top + 48
        result: list[tuple[VendorOffer, pygame.Rect]] = []
        for offer in vendor_window.offers:
            row_rect = pygame.Rect(panel_rect.left + 14, y, panel_rect.width - 28, 34)
            if row_rect.bottom > panel_rect.bottom - 10:
                break
            result.append((offer, row_rect))
            y += 42
        return result

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

        self._draw_equipment_slots(screen, equipment)

        if not items:
            empty = self.small_font.render("Пусто", True, MUTED_TEXT_COLOR)
            screen.blit(empty, (inventory_title_position[0], panel_rect.top + 42))
            return

        for item, row_rect in self._inventory_item_rects(screen, items):
            quantity_suffix = f" x{item.quantity}" if item.quantity > 1 else ""
            text = f"{item.display_name}{quantity_suffix}"
            if equipment.main_hand == item.item_id:
                text = f"{text} (в руке)"
            elif equipment.chest == item.item_id:
                text = f"{text} (на себе)"
            color = EQUIPPABLE_TEXT_COLOR if is_equippable_item(item.item_id) else MUTED_TEXT_COLOR
            surface = self.small_font.render(
                self._tail_to_width(text, row_rect.width - 10, self.small_font),
                True,
                color,
            )
            screen.blit(surface, (row_rect.left + 5, row_rect.top + 3))

    def _draw_skills(
        self,
        screen: pygame.Surface,
        skills: Sequence[CharacterSkill],
        inventory_visible: bool,
    ) -> None:
        """
        Рисует панель игровых скиллов персонажа.
        """
        panel_rect = self._skills_panel_rect(screen, inventory_visible)
        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        panel.fill(PANEL_BACKGROUND)
        screen.blit(panel, panel_rect.topleft)
        pygame.draw.rect(screen, BUBBLE_BORDER, panel_rect, width=1, border_radius=6)

        title = self.font.render("Скиллы", True, TEXT_COLOR)
        screen.blit(title, (panel_rect.left + 12, panel_rect.top + 10))

        if not skills:
            empty = self.small_font.render("Пусто", True, MUTED_TEXT_COLOR)
            screen.blit(empty, (panel_rect.left + 12, panel_rect.top + 42))
            return

        y = panel_rect.top + 44
        for skill in skills:
            if y + 32 > panel_rect.bottom - 10:
                break
            name = self._tail_to_width(skill.display_name, panel_rect.width - 96, self.small_font)
            value = format_skill_percent(skill.value_tenths)
            name_surface = self.small_font.render(name, True, TEXT_COLOR)
            value_surface = self.small_font.render(value, True, MUTED_TEXT_COLOR)
            screen.blit(name_surface, (panel_rect.left + 12, y))
            screen.blit(
                value_surface,
                (panel_rect.right - 12 - value_surface.get_width(), y),
            )

            bar_rect = pygame.Rect(panel_rect.left + 12, y + 20, panel_rect.width - 24, 6)
            pygame.draw.rect(screen, SLOT_BACKGROUND, bar_rect, border_radius=3)
            fill_width = int(
                bar_rect.width * min(skill.value_tenths, DEMO_SKILL_CAP) / DEMO_SKILL_CAP
            )
            if fill_width > 0:
                fill_rect = pygame.Rect(bar_rect.left, bar_rect.top, fill_width, bar_rect.height)
                pygame.draw.rect(screen, EQUIPPED_BORDER, fill_rect, border_radius=3)
            y += 38

    def _draw_equipment_slots(self, screen: pygame.Surface, equipment: Equipment) -> None:
        """
        Рисует слоты paperdoll и суммарную броню.
        """
        self._draw_main_hand_slot(screen, equipment)
        self._draw_chest_slot(screen, equipment)
        armor = 0
        if equipment.chest is not None:
            armor = armor_points_for_item(equipment.chest)
        armor_text = self.small_font.render(f"Броня: +{armor}", True, TEXT_COLOR)
        chest_rect = self._chest_slot_rect(screen)
        screen.blit(armor_text, (chest_rect.left, chest_rect.bottom + 10))

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

    def _draw_chest_slot(self, screen: pygame.Surface, equipment: Equipment) -> None:
        """
        Рисует слот нагрудной брони.
        """
        slot_rect = self._chest_slot_rect(screen)
        label = self.small_font.render("Грудь", True, MUTED_TEXT_COLOR)
        screen.blit(label, (slot_rect.left, slot_rect.top - self.small_font.get_linesize() - 2))

        border_color = EQUIPPED_BORDER if equipment.chest is not None else SLOT_BORDER
        pygame.draw.rect(screen, SLOT_BACKGROUND, slot_rect, border_radius=4)
        pygame.draw.rect(screen, border_color, slot_rect, width=1, border_radius=4)

        item_text = "Пусто"
        text_color = MUTED_TEXT_COLOR
        if equipment.chest is not None:
            item_text = item_definition_for(equipment.chest).display_name
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

    def _skills_panel_rect(
        self,
        screen: pygame.Surface,
        inventory_visible: bool,
    ) -> pygame.Rect:
        """
        Возвращает прямоугольник панели скиллов персонажа.
        """
        width = min(300, max(240, screen.get_width() - 40))
        height = 176
        left = max(20, screen.get_width() - width - 20)
        top = 20
        if inventory_visible:
            inventory_rect = self._inventory_panel_rect(screen)
            candidate_top = inventory_rect.bottom + 12
            if candidate_top + height <= screen.get_height() - 20:
                top = candidate_top
            else:
                left = 20
        return pygame.Rect(left, top, width, min(height, screen.get_height() - 40))

    def _main_hand_slot_rect(self, screen: pygame.Surface) -> pygame.Rect:
        """
        Возвращает прямоугольник слота предмета в руке.
        """
        panel_rect = self._inventory_panel_rect(screen)
        slot_width = min(138, max(104, panel_rect.width // 3))
        return pygame.Rect(panel_rect.left + 12, panel_rect.top + 66, slot_width, 34)

    def _chest_slot_rect(self, screen: pygame.Surface) -> pygame.Rect:
        """
        Возвращает прямоугольник слота нагрудной брони.
        """
        main_hand_rect = self._main_hand_slot_rect(screen)
        return pygame.Rect(
            main_hand_rect.left,
            main_hand_rect.bottom + 34,
            main_hand_rect.width,
            main_hand_rect.height,
        )

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

    def _load_tile_sprites(self, sprite_paths: Sequence[str]) -> tuple[pygame.Surface, ...]:
        """
        Загружает PNG-спрайты тайла.
        """
        sprites: list[pygame.Surface] = []
        for sprite_path in sprite_paths:
            path = TILE_SPRITE_ROOT / sprite_path
            try:
                sprites.append(pygame.image.load(path).convert_alpha())
            except (FileNotFoundError, pygame.error):
                continue
        return tuple(sprites)

    def _load_entity_sprite(self, sprite_path: str) -> pygame.Surface | None:
        """
        Загружает PNG-спрайт entity.
        """
        path = ENTITY_SPRITE_ROOT / sprite_path
        try:
            return pygame.image.load(path).convert_alpha()
        except (FileNotFoundError, pygame.error):
            return None

    def _tile_sprite_offsets_for_definition(
        self,
        definition: TileDefinition,
    ) -> tuple[tuple[int, int], ...]:
        """
        Возвращает offset для каждого загруженного варианта спрайта.
        """
        sprite_count = len(self.tile_sprites.get(definition.key, ()))
        if sprite_count == 0:
            return ()
        if definition.sprite_offsets:
            return definition.sprite_offsets[:sprite_count]
        return (definition.sprite_offset,) * sprite_count

    def _sprite_index_for_tile(
        self,
        tile_key: str,
        sprites: Sequence[pygame.Surface],
        tile_x: int,
        tile_y: int,
    ) -> int:
        """
        Выбирает индекс варианта спрайта по координатам.
        """
        if self.tile_map.definitions[tile_key].name == "stone wall" and len(sprites) >= 16:
            return self._wall_sprite_mask(tile_x, tile_y)
        return (tile_x * 73856093 ^ tile_y * 19349663) % len(sprites)

    def _wall_sprite_mask(self, tile_x: int, tile_y: int) -> int:
        """
        Выбирает wall-вариант по соседям: N=1, E=2, S=4, W=8.
        """
        mask = 0
        for bit, offset_x, offset_y in (
            (1, 0, -1),
            (2, 1, 0),
            (4, 0, 1),
            (8, -1, 0),
        ):
            neighbor_x = tile_x + offset_x
            neighbor_y = tile_y + offset_y
            if self._is_connected_wall_neighbor(neighbor_x, neighbor_y):
                mask |= bit
        return mask

    def _is_connected_wall_neighbor(self, tile_x: int, tile_y: int) -> bool:
        if not self.tile_map.in_bounds(tile_x, tile_y):
            return False
        tile_key = self.tile_map.tile_at(tile_x, tile_y)
        return self.tile_map.definitions[tile_key].name == "stone wall"
