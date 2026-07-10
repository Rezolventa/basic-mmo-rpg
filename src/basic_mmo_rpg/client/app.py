from __future__ import annotations

import argparse
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import pygame

from basic_mmo_rpg.client.camera import Camera
from basic_mmo_rpg.client.network import NetworkClient
from basic_mmo_rpg.client.rendering import Renderer
from basic_mmo_rpg.client.ui import ChatLine, TimedText
from basic_mmo_rpg.domain.entities import WorldEntity
from basic_mmo_rpg.domain.equipment import CHEST_SLOT, MAIN_HAND_SLOT, Equipment
from basic_mmo_rpg.domain.geometry import Rect, Vec2
from basic_mmo_rpg.domain.inventory import ItemStack
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState, move_player
from basic_mmo_rpg.domain.skills import CharacterSkill
from basic_mmo_rpg.shared.protocol import (
    INTERACTION_PRESENTATION_FEED,
    InteractionMenu,
    ProtocolError,
    ServerMessageType,
    VendorWindow,
    entities_from_snapshot_payload,
    equipment_from_payload,
    interaction_menu_from_payload,
    interaction_presentation_from_payload,
    inventory_items_from_payload,
    player_snapshots_from_payload,
    skills_from_payload,
    tile_map_from_payload,
    vendor_window_from_payload,
)
from basic_mmo_rpg.storage.map_loader import load_tile_map

DEFAULT_MAP_PATH = Path(__file__).resolve().parents[3] / "assets" / "maps" / "starter_map.json"
DEFAULT_SERVER_URL = "ws://127.0.0.1:8765"
WINDOW_SIZE = (1280, 720)
PLAYER_ID = "local-player"
LOCAL_RECONCILE_RATE = 8.0
LOCAL_RECONCILE_DEAD_ZONE = 3.0
LOCAL_SNAP_DISTANCE = 96.0
REMOTE_INTERPOLATION_RATE = 14.0
REMOTE_INTERPOLATION_DEAD_ZONE = 0.25
REMOTE_SNAP_DISTANCE = 128.0
ENTITY_INTERPOLATION_RATE = 18.0
ENTITY_INTERPOLATION_DEAD_ZONE = 0.25
ENTITY_SNAP_DISTANCE = 128.0
FLOATING_TEXT_SECONDS = 3.0
EVENT_FEED_SECONDS = 12.0
MAX_EVENT_FEED_MESSAGES = 8
MAX_CHAT_LOG_MESSAGES = 50
MAX_CHAT_INPUT_LENGTH = 160


@dataclass(slots=True)
class RemotePlayerView:
    """
    Хранит отображаемое и целевое состояние удаленного игрока для интерполяции.
    """

    name: str
    rendered: PlayerState
    target: PlayerState

    def set_target(self, name: str, target: PlayerState) -> None:
        """
        Обновляет целевое authoritative-состояние удаленного игрока.
        """
        self.name = name
        self.target = target

    def update(self, delta_seconds: float) -> None:
        """
        Плавно приближает отображаемое состояние к последнему server snapshot-у.
        """
        self.rendered = _smooth_player_toward(
            current=self.rendered,
            target=self.target,
            delta_seconds=delta_seconds,
            rate=REMOTE_INTERPOLATION_RATE,
            snap_distance=REMOTE_SNAP_DISTANCE,
            dead_zone=REMOTE_INTERPOLATION_DEAD_ZONE,
        )


@dataclass(slots=True)
class WorldEntityView:
    """
    Хранит отображаемое и целевое состояние world-entity для интерполяции.
    """

    rendered: WorldEntity
    target: WorldEntity

    def set_target(self, target: WorldEntity) -> None:
        """
        Обновляет целевое authoritative-состояние и сразу применяет не-позиционные поля.
        """
        self.target = target
        if target.visible and not self.rendered.visible:
            self.rendered = target
            return
        if (target.position - self.rendered.position).length >= ENTITY_SNAP_DISTANCE:
            self.rendered = target
            return
        self.rendered = _entity_with_position(target, self.rendered.position)

    def update(self, delta_seconds: float) -> None:
        """
        Плавно приближает отображаемую позицию к последнему server snapshot-у.
        """
        self.rendered = _smooth_entity_toward(
            current=self.rendered,
            target=self.target,
            delta_seconds=delta_seconds,
            rate=ENTITY_INTERPOLATION_RATE,
            snap_distance=ENTITY_SNAP_DISTANCE,
            dead_zone=ENTITY_INTERPOLATION_DEAD_ZONE,
        )


class GameClient:
    """
    Управляет pygame-клиентом, локальным рендером и сетевой игрой.
    """

    def __init__(
        self,
        map_path: Path,
        server_url: str,
        character_name: str,
    ) -> None:
        """
        Инициализирует окно, карту, состояние игрока, камеру, рендерер и сетевой клиент.
        """
        pygame.init()
        pygame.display.set_caption("Basic MMO RPG - multiplayer MVP")

        self.screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.tile_map = load_tile_map(map_path)
        self.map_fingerprint = self.tile_map.fingerprint
        self.local_character_name = character_name
        self.player = PlayerState(
            entity_id=PLAYER_ID,
            position=self.tile_map.spawn,
        )
        self.authoritative_player: PlayerState | None = None
        self.local_correction_offset = Vec2(0, 0)
        self.other_players: dict[str, RemotePlayerView] = {}
        self.world_entity_views: dict[str, WorldEntityView] = {
            entity.entity_id: WorldEntityView(rendered=entity, target=entity)
            for entity in self.tile_map.entities
        }
        self.world_entities: dict[str, WorldEntity] = {}
        self._sync_rendered_world_entities()
        self.hovered_entity_id: str | None = None
        self.hovered_tile: tuple[int, int] | None = None
        self.local_player_id: str | None = PLAYER_ID
        self.player_names: dict[str, str] = {PLAYER_ID: self.local_character_name}
        self.chat_input_active = False
        self.chat_input_text = ""
        self.chat_journal_visible = False
        self.inventory_visible = False
        self.hotkey_help_visible = False
        self.inventory_items: list[ItemStack] = []
        self.equipment = Equipment()
        self.skills_visible = False
        self.character_skills: list[CharacterSkill] = []
        self.interaction_menu: InteractionMenu | None = None
        self.vendor_window: VendorWindow | None = None
        self.combat_mode_active = False
        self.hovered_attackable_entity_id: str | None = None
        self.selected_attack_target_id: str | None = None
        self.death_dialog_visible = False
        self.chat_lines: deque[ChatLine] = deque(maxlen=MAX_CHAT_LOG_MESSAGES)
        self.event_feed: deque[TimedText] = deque(maxlen=MAX_EVENT_FEED_MESSAGES)
        self.system_message: str | None = None
        self.speech_bubbles: dict[str, TimedText] = {}
        self.entity_speech_bubbles: dict[str, TimedText] = {}
        self.name_tags: dict[str, TimedText] = {}
        self.camera = Camera()
        self.renderer = Renderer(self.tile_map)
        self.network_client = NetworkClient(
            server_url,
            character_name=self.local_character_name,
            map_fingerprint=self.map_fingerprint,
        )
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
                else:
                    self._handle_event(event)

            delta_seconds = min(self.clock.tick(60) / 1000.0, 0.05)
            self._update(delta_seconds)
            self._draw()

        self.network_client.stop()
        pygame.quit()

    def _update(self, delta_seconds: float) -> None:
        """
        Обновляет локальный ввод, состояние игрока и камеру за один кадр.
        """
        self._prune_timed_texts(time.monotonic())
        self._update_hovered_targets()
        intent = self._read_movement_intent()
        self.network_client.send_movement_intent(intent)
        self._apply_network_messages()
        self._predict_local_player(intent, delta_seconds)
        self._reconcile_local_player(delta_seconds)
        self._update_remote_players(delta_seconds)
        self._update_world_entities(delta_seconds)

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
        other_players = [
            player_view.rendered
            for player_view in self.other_players.values()
            if player_view.rendered.is_alive
        ]
        self.renderer.draw(
            screen=self.screen,
            camera=self.camera,
            player=self.player,
            other_players=other_players,
            world_entities=self.world_entities.values(),
            player_names=self.player_names,
            speech_bubbles=_timed_text_values(self.speech_bubbles),
            name_tags=_timed_text_values(self.name_tags),
            entity_speech_bubbles=_timed_text_values(self.entity_speech_bubbles),
            hovered_entity_id=self.hovered_entity_id,
            hovered_tile=self.hovered_tile,
            chat_lines=list(self.chat_lines),
            event_feed=[entry.text for entry in self.event_feed],
            chat_input_active=self.chat_input_active,
            chat_input_text=self.chat_input_text,
            chat_journal_visible=self.chat_journal_visible,
            inventory_items=self.inventory_items,
            equipment=self.equipment,
            inventory_visible=self.inventory_visible,
            character_skills=self.character_skills,
            skills_visible=self.skills_visible,
            hotkey_help_visible=self.hotkey_help_visible,
            interaction_menu=self.interaction_menu,
            vendor_window=self.vendor_window,
            combat_mode_active=self.combat_mode_active,
            hovered_attackable_entity_id=self.hovered_attackable_entity_id,
            selected_attack_target_id=self.selected_attack_target_id,
            death_dialog_visible=getattr(self, "death_dialog_visible", False),
            system_message=self.system_message,
        )
        pygame.display.flip()

    def _handle_event(self, event: pygame.event.Event) -> None:
        """
        Обрабатывает одно pygame-событие пользовательского ввода.
        """
        if event.type == pygame.KEYDOWN:
            self._handle_key_down(event)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._handle_left_click(event.pos)

    def _handle_key_down(self, event: pygame.event.Event) -> None:
        """
        Обрабатывает нажатие клавиши с учетом режима ввода чата.
        """
        if event.key == pygame.K_F1:
            self.hotkey_help_visible = not self.hotkey_help_visible
            return
        if self.chat_input_active:
            self._handle_chat_input_key(event)
            return
        if getattr(self, "death_dialog_visible", False):
            return
        if getattr(self, "interaction_menu", None) is not None:
            if event.key == pygame.K_ESCAPE:
                self.interaction_menu = None
            return
        if getattr(self, "vendor_window", None) is not None:
            if event.key == pygame.K_ESCAPE:
                self.vendor_window = None
            return

        if event.key == pygame.K_RETURN:
            self.chat_input_active = True
            self.chat_input_text = ""
        elif event.key == pygame.K_j:
            self.chat_journal_visible = not self.chat_journal_visible
        elif event.key == pygame.K_b:
            self.inventory_visible = not self.inventory_visible
        elif event.key == pygame.K_k:
            self.skills_visible = not self.skills_visible
        elif not self._local_player_can_act():
            return
        elif event.key == pygame.K_TAB:
            self._toggle_combat_mode()
        elif event.key == pygame.K_f:
            self._send_interaction_under_cursor()
        elif event.key == pygame.K_h:
            self.network_client.send_apply_bandage_request()

    def _toggle_combat_mode(self) -> None:
        """
        Переключает боевой режим клиента и сбрасывает auto-attack при выключении.
        """
        if not self._local_player_can_act():
            return
        self.combat_mode_active = not self.combat_mode_active
        if self.combat_mode_active:
            return
        self.selected_attack_target_id = None
        self.hovered_attackable_entity_id = None
        self.network_client.send_stop_attack_request()

    def _handle_chat_input_key(self, event: pygame.event.Event) -> None:
        """
        Обрабатывает клавиши во время ввода сообщения чата.
        """
        if event.key == pygame.K_ESCAPE:
            self.chat_input_active = False
            self.chat_input_text = ""
            return
        if event.key == pygame.K_RETURN:
            self._send_chat_input()
            return
        if event.key == pygame.K_BACKSPACE:
            self.chat_input_text = self.chat_input_text[:-1]
            return

        if event.unicode and len(self.chat_input_text) < MAX_CHAT_INPUT_LENGTH:
            self.chat_input_text += event.unicode

    def _send_chat_input(self) -> None:
        """
        Отправляет набранное сообщение чата и закрывает строку ввода.
        """
        text = self.chat_input_text.strip()
        self.chat_input_active = False
        self.chat_input_text = ""
        if not text:
            return
        self.network_client.send_chat_message(text)

    def _handle_left_click(self, position: tuple[int, int]) -> None:
        """
        Обрабатывает клики по UI и показывает никнейм удаленного персонажа.
        """
        if getattr(self, "death_dialog_visible", False):
            if self.renderer.respawn_button_hit_at_position(self.screen, position):
                self.network_client.send_respawn_request()
            return
        if getattr(self, "interaction_menu", None) is not None:
            self._handle_interaction_menu_click(position)
            return
        if getattr(self, "vendor_window", None) is not None:
            self._handle_vendor_click(position)
            return
        if not self._local_player_can_act():
            return

        if self.inventory_visible and self._handle_inventory_click(position):
            return

        if self.combat_mode_active:
            entity = self._attackable_entity_at_screen_position(position)
            if entity is not None:
                self.selected_attack_target_id = entity.entity_id
                self.network_client.send_attack_request(entity.entity_id)
                return

        now = time.monotonic()
        for player_view in self.other_players.values():
            if self._player_screen_rect(player_view.rendered).collidepoint(position):
                self.name_tags[player_view.rendered.entity_id] = TimedText(
                    text=player_view.name,
                    expires_at=now + FLOATING_TEXT_SECONDS,
                )
                return

    def _handle_inventory_click(self, position: tuple[int, int]) -> bool:
        """
        Отправляет запрос экипировки или снятия предмета при клике по панели.
        """
        hit = self.renderer.inventory_hit_at_position(
            self.screen,
            position,
            self.inventory_items,
        )
        if hit is None:
            return False
        if not self._local_player_can_act():
            return True
        if hit.item_id is not None:
            self.network_client.send_equip_item_request(hit.item_id)
            return True
        if hit.slot == MAIN_HAND_SLOT and self.equipment.main_hand is not None:
            self.network_client.send_unequip_item_request(MAIN_HAND_SLOT)
            return True
        if hit.slot == CHEST_SLOT and self.equipment.chest is not None:
            self.network_client.send_unequip_item_request(CHEST_SLOT)
            return True
        return True

    def _handle_interaction_menu_click(self, position: tuple[int, int]) -> None:
        """
        Отправляет выбор активной опции NPC-окна.
        """
        menu = self.interaction_menu
        if menu is None:
            return
        option = self.renderer.interaction_menu_hit_at_position(self.screen, position, menu)
        if option is None or not option.enabled:
            return
        self.network_client.send_interaction_option_selected(menu.entity_id, option.option_id)

    def _handle_vendor_click(self, position: tuple[int, int]) -> None:
        """
        Отправляет запрос покупки активной позиции торговца.
        """
        vendor_window = self.vendor_window
        if vendor_window is None:
            return
        offer = self.renderer.vendor_hit_at_position(self.screen, position, vendor_window)
        if offer is None or not offer.enabled:
            return
        self.network_client.send_vendor_buy_request(vendor_window.vendor_id, offer.offer_id)

    def _send_interaction_under_cursor(self) -> None:
        """
        Отправляет запрос взаимодействия с объектом, который находится строго под курсором.
        """
        if not self._local_player_can_act():
            return

        entity = self._entity_at_screen_position(pygame.mouse.get_pos())
        if entity is not None:
            self.network_client.send_interaction_request(entity.entity_id)
            return

        tile = self._resource_tile_at_screen_position(pygame.mouse.get_pos())
        if tile is not None:
            self.network_client.send_tile_interaction_request(*tile)

    def _read_movement_intent(self) -> MovementIntent:
        """
        Читает состояние клавиатуры и преобразует его в намерение движения.
        """
        if (
            self.chat_input_active
            or getattr(self, "interaction_menu", None) is not None
            or getattr(self, "vendor_window", None) is not None
            or not self._local_player_can_act()
        ):
            return MovementIntent()

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
        for message in self.network_client.drain_messages():
            if message.type == ServerMessageType.CONNECTION_ACCEPTED:
                if not self._apply_server_map(message.payload):
                    continue
                player_id = message.payload.get("player_id")
                if isinstance(player_id, str):
                    self.local_player_id = player_id
                    name = message.payload.get("name")
                    if isinstance(name, str):
                        self.local_character_name = name
                    self.player_names[player_id] = self.local_character_name
            elif message.type == ServerMessageType.WORLD_SNAPSHOT:
                self._apply_world_snapshot(message.payload)
            elif message.type == ServerMessageType.CHAT_MESSAGE:
                self._apply_chat_message(message.payload)
            elif message.type == ServerMessageType.INTERACTION_RESULT:
                self._apply_interaction_result(message.payload)
            elif message.type == ServerMessageType.INTERACTION_MENU_OPENED:
                self._apply_interaction_menu_opened(message.payload)
            elif message.type == ServerMessageType.VENDOR_OPENED:
                self._apply_vendor_opened(message.payload)
            elif message.type == ServerMessageType.COMBAT_EVENT:
                self._apply_combat_event(message.payload)
            elif message.type == ServerMessageType.INVENTORY_UPDATED:
                self._apply_inventory_updated(message.payload)
            elif message.type == ServerMessageType.EQUIPMENT_UPDATED:
                self._apply_equipment_updated(message.payload)
            elif message.type == ServerMessageType.SKILLS_UPDATED:
                self._apply_skills_updated(message.payload)
            elif message.type == ServerMessageType.ENTITY_REMOVED:
                player_id = message.payload.get("id")
                if isinstance(player_id, str):
                    self.other_players.pop(player_id, None)
                    self.player_names.pop(player_id, None)
                    self.speech_bubbles.pop(player_id, None)
                    self.name_tags.pop(player_id, None)
            elif message.type == ServerMessageType.ERROR:
                error_message = message.payload.get("message")
                if isinstance(error_message, str):
                    self._show_system_message(error_message)

    def _apply_server_map(self, payload: dict[str, object]) -> bool:
        """
        Принимает карту сервера как единственный источник истины для online-мира.
        """
        raw_map = payload.get("map")
        if not isinstance(raw_map, Mapping):
            self._show_system_message("Server did not send map data; restart the server.")
            self.network_client.stop()
            return False
        try:
            server_tile_map = tile_map_from_payload(raw_map)
        except (ProtocolError, ValueError) as exc:
            self._show_system_message(f"Server sent invalid map data: {exc}")
            self.network_client.stop()
            return False

        self.tile_map = server_tile_map
        self.map_fingerprint = server_tile_map.fingerprint
        self.renderer = Renderer(self.tile_map)
        self.world_entity_views = {
            entity.entity_id: WorldEntityView(rendered=entity, target=entity)
            for entity in self.tile_map.entities
        }
        self._sync_rendered_world_entities()
        self.system_message = None
        return True

    def _show_system_message(self, text: str) -> None:
        """
        Показывает важное системное сообщение поверх игры и добавляет его в журнал.
        """
        self.system_message = text
        self.chat_lines.append(
            ChatLine(
                player_id="system",
                name="System",
                text=text,
                created_at=time.time(),
            )
        )

    def _apply_world_snapshot(self, payload: dict[str, object]) -> None:
        """
        Обновляет состояния локального и удаленных игроков из authoritative snapshot-а.
        """
        try:
            snapshots = player_snapshots_from_payload(payload)
            entities = entities_from_snapshot_payload(payload)
        except ProtocolError:
            return

        self._receive_world_entities(entities)
        self._clear_stale_attack_target()
        next_other_players: dict[str, PlayerState] = {}
        next_other_names: dict[str, str] = {}
        for snapshot in snapshots:
            player = snapshot.state
            self.player_names[player.entity_id] = snapshot.name
            if player.entity_id == self.local_player_id:
                self.local_character_name = snapshot.name
                self._receive_authoritative_local_player(player)
            else:
                next_other_players[player.entity_id] = player
                next_other_names[player.entity_id] = snapshot.name
        self._receive_remote_players(next_other_players, next_other_names)

    def _apply_chat_message(self, payload: dict[str, object]) -> None:
        """
        Добавляет серверное сообщение чата в журнал и показывает реплику над игроком.
        """
        player_id = payload.get("player_id")
        name = payload.get("name")
        text = payload.get("text")
        created_at = payload.get("created_at")
        if not isinstance(player_id, str) or not isinstance(name, str) or not isinstance(text, str):
            return
        if not isinstance(created_at, int | float):
            created_at = time.time()

        self.player_names[player_id] = name
        self.chat_lines.append(
            ChatLine(
                player_id=player_id,
                name=name,
                text=text,
                created_at=float(created_at),
            )
        )
        self.speech_bubbles[player_id] = TimedText(
            text=text,
            expires_at=time.monotonic() + FLOATING_TEXT_SECONDS,
        )

    def _apply_interaction_result(self, payload: dict[str, object]) -> None:
        """
        Добавляет результат взаимодействия в журнал и показывает реплику над объектом.
        """
        target_id = payload.get("target_id")
        target_name = payload.get("target_name")
        text = payload.get("text")
        created_at = payload.get("created_at")
        add_to_journal = payload.get("add_to_journal", True)
        if not isinstance(target_id, str) or not isinstance(target_name, str):
            return
        if not isinstance(text, str):
            return
        if not isinstance(created_at, int | float):
            created_at = time.time()
        try:
            presentation = interaction_presentation_from_payload(payload)
        except ProtocolError:
            return

        if isinstance(add_to_journal, bool) and add_to_journal:
            self.chat_lines.append(
                ChatLine(
                    player_id=target_id,
                    name=target_name,
                    text=text,
                    created_at=float(created_at),
                )
            )
        if presentation == INTERACTION_PRESENTATION_FEED:
            self.event_feed.append(
                TimedText(
                    text=text,
                    expires_at=time.monotonic() + EVENT_FEED_SECONDS,
                )
            )
            return

        timed_text = TimedText(
            text=text,
            expires_at=time.monotonic() + FLOATING_TEXT_SECONDS,
        )
        if target_id in self.world_entities:
            self.entity_speech_bubbles[target_id] = timed_text
        else:
            self.player_names[target_id] = target_name
            self.speech_bubbles[target_id] = timed_text

    def _apply_interaction_menu_opened(self, payload: dict[str, object]) -> None:
        """
        Открывает или обновляет server-authoritative NPC-окно.
        """
        try:
            self.interaction_menu = interaction_menu_from_payload(payload)
            self.vendor_window = None
        except ProtocolError:
            return

    def _apply_vendor_opened(self, payload: dict[str, object]) -> None:
        """
        Открывает или обновляет server-authoritative окно торговца.
        """
        try:
            self.vendor_window = vendor_window_from_payload(payload)
            self.interaction_menu = None
        except ProtocolError:
            return

    def _apply_combat_event(self, payload: dict[str, object]) -> None:
        """
        Добавляет событие боя в журнал и показывает floating text над целью.
        """
        actor_id = payload.get("actor_id")
        actor_name = payload.get("actor_name")
        target_id = payload.get("target_id")
        target_name = payload.get("target_name")
        text = payload.get("text")
        floating_text = payload.get("floating_text")
        created_at = payload.get("created_at")
        add_to_journal = payload.get("add_to_journal", True)
        destroyed = payload.get("destroyed", False)
        if not isinstance(actor_id, str) or not isinstance(actor_name, str):
            return
        if not isinstance(target_id, str) or not isinstance(target_name, str):
            return
        if not isinstance(text, str) or not isinstance(floating_text, str):
            return
        if not isinstance(created_at, int | float):
            created_at = time.time()

        if isinstance(add_to_journal, bool) and add_to_journal:
            self.chat_lines.append(
                ChatLine(
                    player_id=actor_id,
                    name=actor_name,
                    text=text,
                    created_at=float(created_at),
                )
            )
        timed_text = TimedText(
            text=floating_text,
            expires_at=time.monotonic() + FLOATING_TEXT_SECONDS,
        )
        if target_id in self.world_entities:
            self.entity_speech_bubbles[target_id] = timed_text
        else:
            self.player_names[target_id] = target_name
            self.speech_bubbles[target_id] = timed_text
        if destroyed is True and getattr(self, "selected_attack_target_id", None) == target_id:
            self.selected_attack_target_id = None

    def _apply_inventory_updated(self, payload: dict[str, object]) -> None:
        """
        Обновляет локальное отображение инвентаря из server authoritative payload-а.
        """
        try:
            self.inventory_items = inventory_items_from_payload(payload)
        except ProtocolError:
            return

    def _apply_equipment_updated(self, payload: dict[str, object]) -> None:
        """
        Обновляет локальное отображение экипировки из server authoritative payload-а.
        """
        try:
            self.equipment = equipment_from_payload(payload)
        except ProtocolError:
            return

    def _apply_skills_updated(self, payload: dict[str, object]) -> None:
        """
        Обновляет локальное отображение игровых скиллов из server authoritative payload-а.
        """
        try:
            self.character_skills = skills_from_payload(payload)
        except ProtocolError:
            return

    def _predict_local_player(self, intent: MovementIntent, delta_seconds: float) -> None:
        """
        Сразу применяет локальный ввод игрока до получения подтверждения сервера.
        """
        if getattr(self, "death_dialog_visible", False):
            return
        self.player = move_player(
            self.player,
            intent,
            delta_seconds,
            self.tile_map,
            self._solid_entity_rects(),
        )

    def _reconcile_local_player(self, delta_seconds: float) -> None:
        """
        Мягко подтягивает предсказанную позицию локального игрока к authoritative-позиции.
        """
        distance = self.local_correction_offset.length
        if distance <= LOCAL_RECONCILE_DEAD_ZONE or delta_seconds <= 0:
            self.local_correction_offset = Vec2(0, 0)
            return

        alpha = min(1.0, LOCAL_RECONCILE_RATE * delta_seconds)
        correction = self.local_correction_offset * alpha
        self.player = _player_with_position(self.player, self.player.position + correction)
        self.local_correction_offset = self.local_correction_offset - correction

    def _receive_authoritative_local_player(self, player: PlayerState) -> None:
        """
        Сохраняет authoritative-состояние локального игрока из server snapshot-а.
        """
        self.authoritative_player = player
        self.death_dialog_visible = not player.is_alive
        if not player.can_act:
            self.interaction_menu = None
            self.vendor_window = None
            self.combat_mode_active = False
            self.hovered_attackable_entity_id = None
            self.selected_attack_target_id = None
        if self.player.entity_id != player.entity_id:
            self.player = player
            self.local_correction_offset = Vec2(0, 0)
            return

        difference = player.position - self.player.position
        distance = difference.length
        if distance >= LOCAL_SNAP_DISTANCE:
            self.player = player
            self.local_correction_offset = Vec2(0, 0)
        elif distance > LOCAL_RECONCILE_DEAD_ZONE:
            self.player = _player_with_position(player, self.player.position)
            self.local_correction_offset = difference
        else:
            self.player = player
            self.local_correction_offset = Vec2(0, 0)

    def _receive_remote_players(
        self,
        players: dict[str, PlayerState],
        names: dict[str, str],
    ) -> None:
        """
        Обновляет целевые состояния удаленных игроков и удаляет пропавшие сущности.
        """
        for player_id, player in players.items():
            if player_id in self.other_players:
                self.other_players[player_id].set_target(names[player_id], player)
            else:
                self.other_players[player_id] = RemotePlayerView(
                    name=names[player_id],
                    rendered=player,
                    target=player,
                )

        for player_id in set(self.other_players) - set(players):
            del self.other_players[player_id]

    def _update_remote_players(self, delta_seconds: float) -> None:
        """
        Обновляет интерполированные позиции всех удаленных игроков.
        """
        for player_view in self.other_players.values():
            player_view.update(delta_seconds)

    def _receive_world_entities(self, entities: list[WorldEntity]) -> None:
        """
        Обновляет целевые состояния world-entity и удаляет пропавшие сущности.
        """
        next_entities = {entity.entity_id: entity for entity in entities}
        for entity_id, entity in next_entities.items():
            if entity_id in self.world_entity_views:
                self.world_entity_views[entity_id].set_target(entity)
            else:
                self.world_entity_views[entity_id] = WorldEntityView(
                    rendered=entity,
                    target=entity,
                )

        for entity_id in set(self.world_entity_views) - set(next_entities):
            del self.world_entity_views[entity_id]
        self._sync_rendered_world_entities()

    def _update_world_entities(self, delta_seconds: float) -> None:
        """
        Обновляет интерполированные позиции world-entity на клиентском кадре.
        """
        for entity_view in self.world_entity_views.values():
            entity_view.update(delta_seconds)
        self._sync_rendered_world_entities()

    def _sync_rendered_world_entities(self) -> None:
        """
        Обновляет словарь сущностей, который используют рендер, hover и prediction.
        """
        self.world_entities = {
            entity_id: entity_view.rendered
            for entity_id, entity_view in self.world_entity_views.items()
        }

    def _prune_timed_texts(self, now: float) -> None:
        """
        Удаляет истекшие временные реплики и никнеймы.
        """
        self.speech_bubbles = _active_timed_texts(self.speech_bubbles, now)
        self.entity_speech_bubbles = _active_timed_texts(self.entity_speech_bubbles, now)
        self.name_tags = _active_timed_texts(self.name_tags, now)
        self.event_feed = deque(
            (entry for entry in self.event_feed if entry.expires_at > now),
            maxlen=MAX_EVENT_FEED_MESSAGES,
        )

    def _local_player_can_act(self) -> bool:
        """
        Проверяет, может ли локальный персонаж выполнять игровые команды.
        """
        return self.player.can_act and not getattr(self, "death_dialog_visible", False)

    def _player_screen_rect(self, player: PlayerState) -> pygame.Rect:
        """
        Возвращает экранный прямоугольник игрока для обработки кликов.
        """
        x, y = self.camera.world_to_screen(player.position)
        return pygame.Rect(x, y, player.width, player.height)

    def _update_hovered_targets(self) -> None:
        """
        Обновляет объект или водный тайл под курсором мыши.
        """
        if not self._local_player_can_act():
            self.hovered_entity_id = None
            self.hovered_attackable_entity_id = None
            self.hovered_tile = None
            return

        mouse_position = pygame.mouse.get_pos()
        entity = self._entity_at_screen_position(mouse_position)
        self.hovered_entity_id = entity.entity_id if entity is not None else None
        self.hovered_attackable_entity_id = (
            entity.entity_id
            if self.combat_mode_active and entity is not None and entity.is_attackable
            else None
        )
        if self.combat_mode_active or entity is not None:
            self.hovered_tile = None
        else:
            self.hovered_tile = self._resource_tile_at_screen_position(mouse_position)

    def _entity_at_screen_position(self, position: tuple[int, int]) -> WorldEntity | None:
        """
        Возвращает объект мира под экранной позицией курсора.
        """
        world_position = self.camera.screen_to_world(position)
        for entity in self.world_entities.values():
            if entity.visible and entity.rect.contains_point(world_position):
                return entity
        return None

    def _attackable_entity_at_screen_position(
        self,
        position: tuple[int, int],
    ) -> WorldEntity | None:
        """
        Возвращает attackable-объект мира под экранной позицией курсора.
        """
        entity = self._entity_at_screen_position(position)
        if entity is None or not entity.is_attackable:
            return None
        return entity

    def _clear_stale_attack_target(self) -> None:
        """
        Сбрасывает выбранную цель, если она исчезла или больше не attackable.
        """
        target_id = getattr(self, "selected_attack_target_id", None)
        if target_id is None:
            return
        entity = self.world_entities.get(target_id)
        if entity is None or not entity.is_attackable:
            self.selected_attack_target_id = None

    def _water_tile_at_screen_position(self, position: tuple[int, int]) -> tuple[int, int] | None:
        """
        Возвращает координаты водного тайла под экранной позицией курсора.
        """
        tile = self._resource_tile_at_screen_position(position)
        if tile is None:
            return None
        tile_x, tile_y = tile
        if not self.tile_map.is_water_tile(tile_x, tile_y):
            return None
        return tile

    def _resource_tile_at_screen_position(
        self,
        position: tuple[int, int],
    ) -> tuple[int, int] | None:
        """
        Возвращает координаты ресурсного тайла под экранной позицией курсора.
        """
        world_position = self.camera.screen_to_world(position)
        tile = self.tile_map.tile_coordinates_at(world_position)
        if tile is None:
            return None
        tile_x, tile_y = tile
        if (
            not self.tile_map.is_water_tile(tile_x, tile_y)
            and not self.tile_map.is_tree_tile(tile_x, tile_y)
            and not self.tile_map.is_mineable_tile(tile_x, tile_y)
        ):
            return None
        return tile

    def _solid_entity_rects(self) -> tuple[Rect, ...]:
        """
        Возвращает прямоугольники коллизионных объектов, известных клиенту.
        """
        return tuple(
            entity.rect
            for entity in self.world_entities.values()
            if entity.visible and entity.solid
        )


def _smooth_player_toward(
    current: PlayerState,
    target: PlayerState,
    delta_seconds: float,
    rate: float,
    snap_distance: float,
    dead_zone: float,
) -> PlayerState:
    """
    Возвращает состояние игрока, плавно сдвинутое от текущей позиции к целевой.
    """
    difference = target.position - current.position
    distance = difference.length
    if distance <= dead_zone or distance >= snap_distance:
        return target
    if delta_seconds <= 0:
        return current

    alpha = min(1.0, rate * delta_seconds)
    position = current.position + difference * alpha
    return _player_with_position(target, position)


def _smooth_entity_toward(
    current: WorldEntity,
    target: WorldEntity,
    delta_seconds: float,
    rate: float,
    snap_distance: float,
    dead_zone: float,
) -> WorldEntity:
    """
    Возвращает world-entity, плавно сдвинутую от текущей позиции к целевой.
    """
    difference = target.position - current.position
    distance = difference.length
    if distance <= dead_zone or distance >= snap_distance:
        return target
    if delta_seconds <= 0:
        return _entity_with_position(target, current.position)

    alpha = min(1.0, rate * delta_seconds)
    position = current.position + difference * alpha
    return _entity_with_position(target, position)


def _player_with_position(player: PlayerState, position: Vec2) -> PlayerState:
    """
    Создает копию состояния игрока с новой позицией.
    """
    return replace(player, position=position)


def _entity_with_position(entity: WorldEntity, position: Vec2) -> WorldEntity:
    """
    Создает копию world-entity с новой позицией тела.
    """
    return replace(entity, body=replace(entity.body, position=position))


def _active_timed_texts(texts: dict[str, TimedText], now: float) -> dict[str, TimedText]:
    """
    Возвращает только те временные тексты, срок жизни которых еще не истек.
    """
    return {
        player_id: timed_text
        for player_id, timed_text in texts.items()
        if timed_text.expires_at > now
    }


def _timed_text_values(texts: dict[str, TimedText]) -> dict[str, str]:
    """
    Преобразует временные тексты в словарь строк для рендерера.
    """
    return {player_id: timed_text.text for player_id, timed_text in texts.items()}


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
        default=DEFAULT_SERVER_URL,
        help=f"Websocket server URL. Defaults to {DEFAULT_SERVER_URL}.",
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Character name for multiplayer mode.",
    )
    args = parser.parse_args()
    return args


def main() -> None:
    """
    Создает клиент из аргументов командной строки и запускает его.
    """
    args = parse_args()
    GameClient(args.map, args.server, args.name).run()


if __name__ == "__main__":
    main()
