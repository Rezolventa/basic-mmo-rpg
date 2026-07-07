from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import math
import random
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from websockets.asyncio.server import ServerConnection, serve

from basic_mmo_rpg.domain.entities import EntityKind, LootClaimPolicy, WorldEntity
from basic_mmo_rpg.domain.equipment import (
    CHEST_SLOT,
    MAIN_HAND_SLOT,
    Equipment,
    EquipmentError,
)
from basic_mmo_rpg.domain.inventory import (
    FISH_ITEM_ID,
    FISHING_ROD_ITEM_ID,
    GOLD_ITEM_ID,
    IRON_CHEST_ARMOR_ITEM_ID,
    LOG_ITEM_ID,
    LUMBER_AXE_ITEM_ID,
    PICKAXE_ITEM_ID,
    RUSTY_SWORD_ITEM_ID,
    SHEARS_ITEM_ID,
    STONE_ITEM_ID,
    WOOL_ITEM_ID,
    InventoryLimitError,
    ItemStack,
    armor_points_for_item,
    item_definition_for,
)
from basic_mmo_rpg.domain.movement import PlayerState
from basic_mmo_rpg.server.world import MultiplayerWorld
from basic_mmo_rpg.shared.protocol import (
    INTERACTION_PRESENTATION_BUBBLE,
    INTERACTION_PRESENTATION_FEED,
    ClientMessageType,
    InteractionMenuOption,
    ProtocolError,
    ProtocolMessage,
    ServerMessageType,
    VendorOffer,
    attack_target_from_payload,
    character_name_from_payload,
    chat_message_payload,
    chat_text_from_payload,
    combat_event_payload,
    decode_message,
    encode_message,
    equip_item_id_from_payload,
    equipment_slot_from_payload,
    equipment_updated_payload,
    interaction_menu_opened_payload,
    interaction_option_selection_from_payload,
    interaction_result_payload,
    interaction_target_from_payload,
    inventory_updated_payload,
    map_fingerprint_from_payload,
    movement_intent_from_payload,
    tile_map_to_payload,
    vendor_opened_payload,
    vendor_purchase_request_from_payload,
)
from basic_mmo_rpg.storage.characters import CharacterRepository
from basic_mmo_rpg.storage.map_loader import load_tile_map

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MAP_PATH = PROJECT_ROOT / "assets" / "maps" / "starter_map.json"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "game.sqlite3"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TICK_RATE = 30.0
DEFAULT_SNAPSHOT_RATE = 20.0
DEFAULT_SAVE_INTERVAL = 5.0
JOIN_TIMEOUT_SECONDS = 5.0
TILE_GATHERING_DISTANCE = 64.0
GATHERING_ACTION_SECONDS = 2.0
FISHING_SUCCESS_CHANCE = 0.5
FUNDAY_REQUIRED_FISH = 2
FUNDAY_GOLD_REWARD = 1
LUMBERJACKING_SUCCESS_CHANCE = 1.0
JACK_REQUIRED_LOGS = 5
JACK_GOLD_REWARD = 1
MINING_SUCCESS_CHANCE = 0.8
KOPAI_REQUIRED_STONES = 3
KOPAI_GOLD_REWARD = 1
FOGU_REQUIRED_WOOL = 1
FOGU_GOLD_REWARD = 1
WOOL_REGROW_SECONDS = 30.0
INVENTORY_FULL_TEXT = "Инвентарь полон"
ATTACK_DISTANCE = 64.0
ATTACK_HIT_CHANCE = 0.85
UNARMED_MIN_DAMAGE = 1
UNARMED_MAX_DAMAGE = 2
UNARMED_SWING_COOLDOWN_SECONDS = 1.5
RUSTY_SWORD_MIN_DAMAGE = 3
RUSTY_SWORD_MAX_DAMAGE = 6
RUSTY_SWORD_SWING_COOLDOWN_SECONDS = 1.2
PLAYER_DEATH_TEXT = "Вы погибли"
BJORN_VENDOR_ID = "npc-bjorn"
IRON_CHEST_ARMOR_PRICE = 25
CHAT_COMMAND_PREFIX = "/"
SET_SPEED_COMMAND = "/setspeed"
MIN_MANUAL_PLAYER_SPEED = 0.0
MAX_MANUAL_PLAYER_SPEED = 600.0
UNKNOWN_COMMAND_TEXT = "Неизвестная команда"
SET_SPEED_USAGE_TEXT = "Использование: /setspeed <0-600>"
SET_SPEED_INVALID_TEXT = "Скорость должна быть числом от 0 до 600"

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PlayerSession:
    """
    Хранит связь websocket-сессии с активным персонажем.
    """

    session_id: str
    player_id: str
    character_name: str
    websocket: ServerConnection


@dataclass(frozen=True, slots=True)
class TileGatheringRule:
    """
    Описывает server-authoritative правило добычи ресурса из тайла.
    """

    tile_name: str
    tool_item_id: str
    reward_item_id: str
    success_chance: float
    missing_tool_text: str
    success_text: str
    failure_text: str | None = None


@dataclass(frozen=True, slots=True)
class PendingGatheringAction:
    """
    Хранит запланированную server-authoritative добычу ресурса.
    """

    session_id: str
    player_id: str
    character_name: str
    tile: tuple[int, int]
    rule: TileGatheringRule
    completes_at: float


@dataclass(frozen=True, slots=True)
class WeaponCombatRule:
    """
    Описывает server-authoritative параметры удара оружием.
    """

    min_damage: int
    max_damage: int
    swing_cooldown_seconds: float


@dataclass(frozen=True, slots=True)
class VendorOfferDefinition:
    """
    Описывает server-authoritative позицию покупки у NPC-торговца.
    """

    offer_id: str
    item_id: str
    price_item_id: str
    price_quantity: int
    details: str | None = None


@dataclass(frozen=True, slots=True)
class ToolGrantOption:
    """
    Описывает NPC-опцию одноразовой tutorial-выдачи инструмента.
    """

    option_id: str
    item_id: str
    label: str


@dataclass(frozen=True, slots=True)
class RepeatableQuestDefinition:
    """
    Описывает простой repeatable-квест обмена предметов у NPC.
    """

    quest_id: str
    option_id: str
    cost_item_id: str
    cost_quantity: int
    reward_item_id: str
    reward_quantity: int
    success_text: str


OPTION_KIND_ACTION = "action"
QUEST_KIND_REPEATABLE = "repeatable"
OPTION_KIND_VENDOR = "vendor"
VENDOR_OPTION_ID = "vendor:open"

NPC_DIALOGUE_LINES: dict[str, tuple[str, ...]] = {
    BJORN_VENDOR_ID: ("Примеришь?", "Тебе это пригодится."),
}

NPC_VENDOR_OFFERS: dict[str, tuple[VendorOfferDefinition, ...]] = {
    BJORN_VENDOR_ID: (
        VendorOfferDefinition(
            offer_id="iron_chest_armor",
            item_id=IRON_CHEST_ARMOR_ITEM_ID,
            price_item_id=GOLD_ITEM_ID,
            price_quantity=IRON_CHEST_ARMOR_PRICE,
            details="Броня +2",
        ),
    ),
}

NPC_TOOL_GRANTS: dict[str, ToolGrantOption] = {
    "npc-funday": ToolGrantOption(
        option_id="action:grant_fishing_rod",
        item_id=FISHING_ROD_ITEM_ID,
        label="Получить удочку",
    ),
    "npc-jack-lumber": ToolGrantOption(
        option_id="action:grant_lumber_axe",
        item_id=LUMBER_AXE_ITEM_ID,
        label="Получить топор",
    ),
    "npc-kopai": ToolGrantOption(
        option_id="action:grant_pickaxe",
        item_id=PICKAXE_ITEM_ID,
        label="Получить кирку",
    ),
    "npc-fogu": ToolGrantOption(
        option_id="action:grant_shears",
        item_id=SHEARS_ITEM_ID,
        label="Получить ножницы",
    ),
}

NPC_REPEATABLE_QUESTS: dict[str, RepeatableQuestDefinition] = {
    "npc-funday": RepeatableQuestDefinition(
        quest_id="funday_fish",
        option_id="quest:funday_fish",
        cost_item_id=FISH_ITEM_ID,
        cost_quantity=FUNDAY_REQUIRED_FISH,
        reward_item_id=GOLD_ITEM_ID,
        reward_quantity=FUNDAY_GOLD_REWARD,
        success_text="Отличная рыба. Держи Gold.",
    ),
    "npc-jack-lumber": RepeatableQuestDefinition(
        quest_id="jack_lumber_logs",
        option_id="quest:jack_lumber_logs",
        cost_item_id=LOG_ITEM_ID,
        cost_quantity=JACK_REQUIRED_LOGS,
        reward_item_id=GOLD_ITEM_ID,
        reward_quantity=JACK_GOLD_REWARD,
        success_text="Отличная древесина. Держи Gold.",
    ),
    "npc-kopai": RepeatableQuestDefinition(
        quest_id="kopai_stones",
        option_id="quest:kopai_stones",
        cost_item_id=STONE_ITEM_ID,
        cost_quantity=KOPAI_REQUIRED_STONES,
        reward_item_id=GOLD_ITEM_ID,
        reward_quantity=KOPAI_GOLD_REWARD,
        success_text="Отличный камень. Держи Gold.",
    ),
    "npc-fogu": RepeatableQuestDefinition(
        quest_id="fogu_wool",
        option_id="quest:fogu_wool",
        cost_item_id=WOOL_ITEM_ID,
        cost_quantity=FOGU_REQUIRED_WOOL,
        reward_item_id=GOLD_ITEM_ID,
        reward_quantity=FOGU_GOLD_REWARD,
        success_text="Спасибо. Вот, держи.",
    ),
}


TILE_GATHERING_RULES: dict[str, TileGatheringRule] = {
    "water": TileGatheringRule(
        tile_name="water",
        tool_item_id=FISHING_ROD_ITEM_ID,
        reward_item_id=FISH_ITEM_ID,
        success_chance=FISHING_SUCCESS_CHANCE,
        missing_tool_text="Нужна удочка в руке",
        success_text="Вы поймали рыбу",
        failure_text="Рыба сорвалась",
    ),
    "tree": TileGatheringRule(
        tile_name="tree",
        tool_item_id=LUMBER_AXE_ITEM_ID,
        reward_item_id=LOG_ITEM_ID,
        success_chance=LUMBERJACKING_SUCCESS_CHANCE,
        missing_tool_text="Нужен топор в руке",
        success_text="Вы нарубили древесины",
    ),
    "rock": TileGatheringRule(
        tile_name="rock",
        tool_item_id=PICKAXE_ITEM_ID,
        reward_item_id=STONE_ITEM_ID,
        success_chance=MINING_SUCCESS_CHANCE,
        missing_tool_text="Нужна кирка в руке",
        success_text="Вы добыли камень",
        failure_text="Не удалось добыть камень",
    ),
}

UNARMED_COMBAT_RULE = WeaponCombatRule(
    min_damage=UNARMED_MIN_DAMAGE,
    max_damage=UNARMED_MAX_DAMAGE,
    swing_cooldown_seconds=UNARMED_SWING_COOLDOWN_SECONDS,
)

WEAPON_COMBAT_RULES: dict[str, WeaponCombatRule] = {
    RUSTY_SWORD_ITEM_ID: WeaponCombatRule(
        min_damage=RUSTY_SWORD_MIN_DAMAGE,
        max_damage=RUSTY_SWORD_MAX_DAMAGE,
        swing_cooldown_seconds=RUSTY_SWORD_SWING_COOLDOWN_SECONDS,
    ),
}


class MultiplayerServer:
    """
    Принимает websocket-клиентов и связывает сетевые сообщения с authoritative-миром.
    """

    def __init__(
        self,
        world: MultiplayerWorld,
        character_repository: CharacterRepository,
        tick_rate: float = DEFAULT_TICK_RATE,
        snapshot_rate: float = DEFAULT_SNAPSHOT_RATE,
        save_interval: float = DEFAULT_SAVE_INTERVAL,
        random_source: random.Random | None = None,
    ) -> None:
        """
        Инициализирует состояние сервера, настройки таймингов и хранилище подключений.
        """
        self.world = world
        self.character_repository = character_repository
        self.tick_rate = tick_rate
        self.snapshot_rate = snapshot_rate
        self.save_interval = save_interval
        self.connections: dict[str, ServerConnection] = {}
        self.sessions: dict[str, PlayerSession] = {}
        self.active_character_sessions: dict[str, str] = {}
        self.pending_gathering_actions: dict[str, PendingGatheringAction] = {}
        self.combat_targets: dict[str, str] = {}
        self.next_combat_swing_at: dict[str, float] = {}
        self.enemy_damage_totals: dict[str, dict[str, int]] = {}
        self.next_enemy_swing_at: dict[str, float] = {}
        self.runtime_loot_claims: set[str] = set()
        self.disconnected_player_states: dict[str, PlayerState] = {}
        self.random = random_source or random.Random()

    async def run(self, host: str, port: int) -> None:
        """
        Запускает websocket-listener и authoritative-цикл симуляции.
        """
        async with serve(self._handle_connection, host, port):
            logger.info("Server listening on ws://%s:%s", host, port)
            await self._game_loop()

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        """
        Авторизует websocket-клиента по имени персонажа и обрабатывает его сообщения.
        """
        session: PlayerSession | None = None
        try:
            character_name = await self._receive_join_request(websocket)
            await self._kick_existing_character(character_name)
            session = self._create_session(websocket, character_name)

            await self._send(
                websocket,
                ProtocolMessage(
                    type=ServerMessageType.CONNECTION_ACCEPTED,
                    payload={
                        "player_id": session.player_id,
                        "name": session.character_name,
                        "map_fingerprint": self.world.tile_map.fingerprint,
                        "map": tile_map_to_payload(self.world.tile_map),
                    },
                ),
            )
            await self._send_inventory_update(session)
            await self._send_equipment_update(session)
            await self._broadcast_snapshot()

            async for raw_message in websocket:
                await self._handle_raw_message(session, raw_message)
        finally:
            if session is not None:
                await self._cleanup_session(session)

    async def _receive_join_request(self, websocket: ServerConnection) -> str:
        """
        Получает первое join_requested-сообщение и возвращает имя персонажа.
        """
        try:
            raw_message = await asyncio.wait_for(websocket.recv(), timeout=JOIN_TIMEOUT_SECONDS)
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8")
            message = decode_message(raw_message)
            if message.type != ClientMessageType.JOIN_REQUESTED:
                msg = "first message must be join_requested"
                raise ProtocolError(msg)
            character_name = character_name_from_payload(message.payload)
            client_map_fingerprint = map_fingerprint_from_payload(message.payload)
            if (
                client_map_fingerprint is not None
                and client_map_fingerprint != self.world.tile_map.fingerprint
            ):
                logger.warning(
                    "Client map differs from server map: name=%s client=%s server=%s",
                    character_name,
                    client_map_fingerprint,
                    self.world.tile_map.fingerprint,
                )
            return character_name
        except (ProtocolError, UnicodeDecodeError, TimeoutError) as exc:
            await self._send_protocol_error(websocket, str(exc))
            logger.warning("Join rejected: %s", exc)
            raise

    def _create_session(self, websocket: ServerConnection, character_name: str) -> PlayerSession:
        """
        Создает активную сессию персонажа и добавляет его в мир.
        """
        player_id = self._new_player_id()
        session_id = uuid.uuid4().hex
        character = self.character_repository.load_or_create(
            name=character_name,
            default_position=self.world.tile_map.spawn,
        )
        disconnected_state = self.disconnected_player_states.pop(character_name, None)
        if disconnected_state is None:
            self.world.add_player(player_id, character_name, character.position)
        else:
            self.world.add_player_state(player_id, character_name, disconnected_state)

        session = PlayerSession(
            session_id=session_id,
            player_id=player_id,
            character_name=character_name,
            websocket=websocket,
        )
        self.sessions[session_id] = session
        self.active_character_sessions[character_name] = session_id
        self.connections[player_id] = websocket
        logger.info("Player joined: name=%s player_id=%s", character_name, player_id)
        return session

    async def _kick_existing_character(self, character_name: str) -> None:
        """
        Отключает старую сессию персонажа, если он уже находится в мире.
        """
        session_id = self.active_character_sessions.get(character_name)
        if session_id is None:
            return

        session = self.sessions.get(session_id)
        if session is None:
            self.active_character_sessions.pop(character_name, None)
            return

        self._remember_disconnected_player_state(session)
        self._save_session_position(session)
        self._remove_session_state(session)
        logger.info("Player kicked by reconnect: name=%s", character_name)
        with contextlib.suppress(Exception):
            await self._send(
                session.websocket,
                ProtocolMessage(
                    type=ServerMessageType.ERROR,
                    payload={"message": "character connected elsewhere"},
                ),
            )
        with contextlib.suppress(Exception):
            await session.websocket.close(code=4000, reason="character connected elsewhere")
        await self._broadcast_removed(session)
        await self._broadcast_snapshot()

    async def _cleanup_session(self, session: PlayerSession) -> None:
        """
        Сохраняет позицию и удаляет сессию, если она все еще актуальна.
        """
        if self.active_character_sessions.get(session.character_name) != session.session_id:
            return

        self._remember_disconnected_player_state(session)
        self._save_session_position(session)
        self._remove_session_state(session)
        logger.info("Player left: name=%s player_id=%s", session.character_name, session.player_id)
        await self._broadcast_removed(session)
        await self._broadcast_snapshot()

    def _remove_session_state(self, session: PlayerSession) -> None:
        """
        Удаляет runtime-состояние активной сессии из сервера и мира.
        """
        self.pending_gathering_actions.pop(session.player_id, None)
        self.world.remove_player(session.player_id)
        self.connections.pop(session.player_id, None)
        self.combat_targets.pop(session.player_id, None)
        self.next_combat_swing_at.pop(session.player_id, None)
        self._clear_enemy_targeting_player(session.player_id)
        self.sessions.pop(session.session_id, None)
        self.active_character_sessions.pop(session.character_name, None)

    def _save_session_position(self, session: PlayerSession) -> None:
        """
        Сохраняет текущую позицию персонажа, если он еще есть в мире.
        """
        player = self.world.players.get(session.player_id)
        if player is None or not player.is_alive:
            return
        self.character_repository.save_position(session.character_name, player.position)
        logger.debug(
            "Player position saved: name=%s x=%.2f y=%.2f",
            session.character_name,
            player.position.x,
            player.position.y,
        )

    def _remember_disconnected_player_state(self, session: PlayerSession) -> None:
        """
        Запоминает runtime-смерть персонажа, чтобы reconnect не обходил respawn.
        """
        player = self.world.players.get(session.player_id)
        if player is None:
            return
        if player.is_alive:
            self.disconnected_player_states.pop(session.character_name, None)
            return
        self.disconnected_player_states[session.character_name] = player

    async def _handle_raw_message(
        self,
        session: PlayerSession,
        raw_message: str | bytes,
    ) -> None:
        """
        Декодирует и применяет одно клиентское сообщение подключенного игрока.
        """
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")

        try:
            message = decode_message(raw_message)
            if message.type == ClientMessageType.MOVE_REQUESTED:
                if not self._is_player_busy(session.player_id):
                    self.world.set_intent(
                        session.player_id,
                        movement_intent_from_payload(message.payload),
                    )
            elif message.type == ClientMessageType.CHAT_SENT:
                await self._handle_chat_message(session, message.payload)
            elif self._is_player_busy(session.player_id):
                return
            elif message.type == ClientMessageType.INTERACT_REQUESTED:
                await self._handle_interaction(session, message.payload)
            elif message.type == ClientMessageType.INTERACTION_OPTION_SELECTED:
                await self._handle_interaction_option_selection(session, message.payload)
            elif message.type == ClientMessageType.EQUIP_ITEM_REQUESTED:
                await self._handle_equip_item(session, message.payload)
            elif message.type == ClientMessageType.UNEQUIP_ITEM_REQUESTED:
                await self._handle_unequip_item(session, message.payload)
            elif message.type == ClientMessageType.VENDOR_BUY_REQUESTED:
                await self._handle_vendor_buy_request(session, message.payload)
            elif message.type == ClientMessageType.ATTACK_REQUESTED:
                await self._handle_attack_request(session, message.payload)
            elif message.type == ClientMessageType.STOP_ATTACK_REQUESTED:
                self._stop_attack(session)
            elif message.type == ClientMessageType.RESPAWN_REQUESTED:
                await self._handle_respawn_request(session)
        except (ProtocolError, UnicodeDecodeError) as exc:
            await self._send_error(session.player_id, str(exc))
            logger.warning("Protocol error from %s: %s", session.character_name, exc)

    async def _handle_attack_request(
        self,
        session: PlayerSession,
        payload: dict[str, object],
    ) -> None:
        """
        Проверяет и запоминает цель auto-attack для игрока.
        """
        if not self._can_player_act(session.player_id):
            return

        target = attack_target_from_payload(payload)
        entity = self.world.get_entity(target.entity_id)
        if entity is None or not entity.is_attackable:
            logger.info(
                "Attack ignored: name=%s target_id=%s reason=not_attackable",
                session.character_name,
                target.entity_id,
            )
            return

        rule = self._combat_rule_for_character(session.character_name)
        self.combat_targets[session.player_id] = target.entity_id
        self.next_combat_swing_at[session.player_id] = (
            time.monotonic() + rule.swing_cooldown_seconds
        )
        logger.info(
            "Attack target selected: name=%s target_id=%s",
            session.character_name,
            target.entity_id,
        )

    def _stop_attack(self, session: PlayerSession) -> None:
        """
        Сбрасывает цель auto-attack для игрока.
        """
        self.combat_targets.pop(session.player_id, None)
        self.next_combat_swing_at.pop(session.player_id, None)
        logger.info("Attack stopped: name=%s", session.character_name)

    async def _handle_respawn_request(self, session: PlayerSession) -> None:
        """
        Возрождает персонажа после смерти по явному запросу клиента.
        """
        respawned = self.world.respawn_player(session.player_id)
        if respawned is None:
            return
        self.pending_gathering_actions.pop(session.player_id, None)
        self._stop_attack(session)
        await self._broadcast_snapshot()

    async def _handle_equip_item(
        self,
        session: PlayerSession,
        payload: dict[str, object],
    ) -> None:
        """
        Проверяет и применяет запрос экипировки предмета.
        """
        if not self._can_player_act(session.player_id):
            return

        item_id = equip_item_id_from_payload(payload)
        try:
            equipment = self.character_repository.equip_item(session.character_name, item_id)
        except EquipmentError as exc:
            await self._send_error(session.player_id, str(exc))
            logger.info("Equipment rejected: name=%s error=%s", session.character_name, exc)
            return

        logger.info(
            "Equipment updated: name=%s slot=%s item_id=%s",
            session.character_name,
            item_definition_for(item_id).equipment_slot,
            item_id,
        )
        await self._send_equipment_update(session, equipment)

    async def _handle_unequip_item(
        self,
        session: PlayerSession,
        payload: dict[str, object],
    ) -> None:
        """
        Проверяет и применяет запрос снятия предмета из слота.
        """
        if not self._can_player_act(session.player_id):
            return

        slot = equipment_slot_from_payload(payload)
        try:
            equipment = self.character_repository.unequip_slot(session.character_name, slot)
        except EquipmentError as exc:
            await self._send_error(session.player_id, str(exc))
            logger.info("Equipment rejected: name=%s error=%s", session.character_name, exc)
            return

        logger.info("Equipment updated: name=%s slot=%s item_id=None", session.character_name, slot)
        await self._send_equipment_update(session, equipment)

    async def _handle_chat_message(
        self,
        session: PlayerSession,
        payload: dict[str, object],
    ) -> None:
        """
        Проверяет сообщение чата, обрабатывает команды или рассылает текст всем клиентам.
        """
        text = chat_text_from_payload(payload)
        if text.startswith(CHAT_COMMAND_PREFIX):
            await self._handle_chat_command(session, text)
            return

        logger.info("Chat: %s: %s", session.character_name, text)
        await self._broadcast(
            ProtocolMessage(
                type=ServerMessageType.CHAT_MESSAGE,
                payload=chat_message_payload(
                    player_id=session.player_id,
                    name=session.character_name,
                    text=text,
                    created_at=time.time(),
                ),
            )
        )

    async def _handle_chat_command(self, session: PlayerSession, text: str) -> None:
        """
        Разбирает ручные chat-команды текущего персонажа.
        """
        parts = text.split()
        command = parts[0].lower()
        if command == SET_SPEED_COMMAND:
            await self._handle_set_speed_command(session, parts)
            return

        await self._send_chat_command_feedback(session, UNKNOWN_COMMAND_TEXT)

    async def _handle_set_speed_command(
        self,
        session: PlayerSession,
        parts: list[str],
    ) -> None:
        """
        Меняет runtime-скорость текущего персонажа через ручную команду.
        """
        if len(parts) != 2:
            await self._send_chat_command_feedback(session, SET_SPEED_USAGE_TEXT)
            return

        try:
            speed = float(parts[1])
        except ValueError:
            await self._send_chat_command_feedback(session, SET_SPEED_INVALID_TEXT)
            return

        if (
            not math.isfinite(speed)
            or speed < MIN_MANUAL_PLAYER_SPEED
            or speed > MAX_MANUAL_PLAYER_SPEED
        ):
            await self._send_chat_command_feedback(session, SET_SPEED_INVALID_TEXT)
            return

        updated = self.world.set_player_speed(session.player_id, speed)
        if updated is None:
            return

        logger.info(
            "Manual command: name=%s command=setspeed speed=%s",
            session.character_name,
            updated.speed,
        )
        await self._send_chat_command_feedback(session, f"Скорость персонажа: {updated.speed:g}")
        await self._broadcast_snapshot()

    async def _send_chat_command_feedback(
        self,
        session: PlayerSession,
        text: str,
    ) -> None:
        """
        Отправляет приватный результат ручной команды без записи в журнал.
        """
        await self._send_interaction_result(
            session=session,
            target_id=session.player_id,
            target_name=session.character_name,
            text=text,
            add_to_journal=False,
            presentation=INTERACTION_PRESENTATION_FEED,
        )

    async def _handle_interaction(
        self,
        session: PlayerSession,
        payload: dict[str, object],
    ) -> None:
        """
        Проверяет запрос взаимодействия и отправляет результат только инициатору.
        """
        if not self._can_player_act(session.player_id):
            return

        target = interaction_target_from_payload(payload)
        if target.entity_id is not None:
            await self._handle_entity_interaction(session, target.entity_id)
        elif target.tile is not None:
            await self._handle_tile_interaction(session, target.tile)

    async def _handle_entity_interaction(self, session: PlayerSession, target_id: str) -> None:
        """
        Проверяет взаимодействие с объектом мира.
        """
        entity = self._resolve_interaction_entity(session, target_id)
        if entity is None:
            return

        logger.info(
            "Interaction accepted: name=%s target_id=%s",
            session.character_name,
            target_id,
        )
        if entity.gate is not None:
            await self._handle_gate_interaction(session, entity.entity_id, entity.name)
            return
        if entity.lootable is not None:
            await self._handle_lootable_interaction(session, entity)
            return
        if entity.kind == EntityKind.CREATURE:
            await self._handle_creature_interaction(session, entity)
            return
        if entity.kind == EntityKind.NPC:
            await self._send_npc_interaction_menu(session, entity)
            return

        if not entity.dialogue:
            return

        await self._send(
            session.websocket,
            ProtocolMessage(
                type=ServerMessageType.INTERACTION_RESULT,
                payload=interaction_result_payload(
                    actor_id=session.player_id,
                    target_id=entity.entity_id,
                    target_name=entity.name,
                    text=entity.dialogue,
                    created_at=time.time(),
                ),
            ),
        )

    async def _handle_interaction_option_selection(
        self,
        session: PlayerSession,
        payload: dict[str, object],
    ) -> None:
        """
        Проверяет и применяет выбранную опцию окна взаимодействия с NPC.
        """
        if not self._can_player_act(session.player_id):
            return

        selection = interaction_option_selection_from_payload(payload)
        entity = self._resolve_interaction_entity(session, selection.entity_id)
        if entity is None or entity.kind != EntityKind.NPC:
            return

        option = self._npc_option_by_id(session, entity, selection.option_id)
        if option is None:
            logger.info(
                "Interaction option ignored: name=%s target_id=%s option_id=%s reason=missing",
                session.character_name,
                entity.entity_id,
                selection.option_id,
            )
            return
        if not option.enabled:
            await self._send_npc_interaction_menu(session, entity)
            return

        if self._is_tool_grant_option(entity.entity_id, selection.option_id):
            await self._handle_tool_grant_option(session, entity, selection.option_id)
        elif self._is_repeatable_quest_option(entity.entity_id, selection.option_id):
            await self._handle_repeatable_quest_option(session, entity, selection.option_id)
        elif self._is_vendor_option(entity.entity_id, selection.option_id):
            await self._send_vendor_window(session, entity)
            return

        await self._send_npc_interaction_menu(session, entity)

    async def _send_npc_interaction_menu(
        self,
        session: PlayerSession,
        entity: WorldEntity,
    ) -> None:
        """
        Отправляет клиенту актуальное server-authoritative окно взаимодействия с NPC.
        """
        await self._send(
            session.websocket,
            ProtocolMessage(
                type=ServerMessageType.INTERACTION_MENU_OPENED,
                payload=interaction_menu_opened_payload(
                    entity_id=entity.entity_id,
                    title=entity.name,
                    body=self._npc_dialogue_for(entity),
                    options=tuple(self._npc_interaction_options(session, entity)),
                ),
            ),
        )

    def _npc_option_by_id(
        self,
        session: PlayerSession,
        entity: WorldEntity,
        option_id: str,
    ) -> InteractionMenuOption | None:
        """
        Находит опцию в актуальном серверном списке NPC.
        """
        for option in self._npc_interaction_options(session, entity):
            if option.option_id == option_id:
                return option
        return None

    def _npc_interaction_options(
        self,
        session: PlayerSession,
        entity: WorldEntity,
    ) -> list[InteractionMenuOption]:
        """
        Собирает доступные игроку опции NPC на текущий момент.
        """
        options: list[InteractionMenuOption] = []
        tool_option = NPC_TOOL_GRANTS.get(entity.entity_id)
        if tool_option is not None and not self.character_repository.has_item(
            session.character_name,
            tool_option.item_id,
        ):
            options.append(
                InteractionMenuOption(
                    option_id=tool_option.option_id,
                    label=tool_option.label,
                    kind=OPTION_KIND_ACTION,
                )
            )

        quest = NPC_REPEATABLE_QUESTS.get(entity.entity_id)
        if quest is not None:
            options.append(self._repeatable_quest_menu_option(session, quest))
        if entity.entity_id in NPC_VENDOR_OFFERS:
            options.append(
                InteractionMenuOption(
                    option_id=VENDOR_OPTION_ID,
                    label="Торговля",
                    kind=OPTION_KIND_VENDOR,
                )
            )
        return options

    def _npc_dialogue_for(self, entity: WorldEntity) -> str:
        """
        Возвращает актуальную реплику NPC, включая случайные фразы торговцев.
        """
        lines = NPC_DIALOGUE_LINES.get(entity.entity_id)
        if lines is None:
            return entity.dialogue
        return self.random.choice(lines)

    def _repeatable_quest_menu_option(
        self,
        session: PlayerSession,
        quest: RepeatableQuestDefinition,
    ) -> InteractionMenuOption:
        """
        Создает UI-опцию repeatable-квеста обмена с прогрессом по предметам.
        """
        current_quantity = self.character_repository.item_quantity(
            session.character_name,
            quest.cost_item_id,
        )
        cost_name = item_definition_for(quest.cost_item_id).display_name
        reward_name = item_definition_for(quest.reward_item_id).display_name
        progress = f"{cost_name} {current_quantity}/{quest.cost_quantity}"
        enabled = current_quantity >= quest.cost_quantity
        return InteractionMenuOption(
            option_id=quest.option_id,
            label=(
                f"Обменять {cost_name} x{quest.cost_quantity} "
                f"на {reward_name} x{quest.reward_quantity} "
                f"({current_quantity}/{quest.cost_quantity})"
            ),
            kind=QUEST_KIND_REPEATABLE,
            enabled=enabled,
            progress=progress,
            disabled_reason=None if enabled else f"Нужно: {progress}",
        )

    def _is_tool_grant_option(self, entity_id: str, option_id: str) -> bool:
        """
        Проверяет, относится ли option_id к выдаче tutorial-инструмента NPC.
        """
        option = NPC_TOOL_GRANTS.get(entity_id)
        return option is not None and option.option_id == option_id

    def _is_repeatable_quest_option(self, entity_id: str, option_id: str) -> bool:
        """
        Проверяет, относится ли option_id к repeatable-квесту NPC.
        """
        quest = NPC_REPEATABLE_QUESTS.get(entity_id)
        return quest is not None and quest.option_id == option_id

    def _is_vendor_option(self, entity_id: str, option_id: str) -> bool:
        """
        Проверяет, открывает ли option_id окно торговца.
        """
        return option_id == VENDOR_OPTION_ID and entity_id in NPC_VENDOR_OFFERS

    async def _handle_tool_grant_option(
        self,
        session: PlayerSession,
        entity: WorldEntity,
        option_id: str,
    ) -> None:
        """
        Выполняет выбранную опцию выдачи tutorial-инструмента.
        """
        option = NPC_TOOL_GRANTS.get(entity.entity_id)
        if option is None or option.option_id != option_id:
            return
        await self._grant_item_if_needed(session, option.item_id)

    async def _handle_repeatable_quest_option(
        self,
        session: PlayerSession,
        entity: WorldEntity,
        option_id: str,
    ) -> None:
        """
        Выполняет выбранный repeatable-квест обмена.
        """
        quest = NPC_REPEATABLE_QUESTS.get(entity.entity_id)
        if quest is None or quest.option_id != option_id:
            return
        try:
            inventory, exchanged = self.character_repository.complete_repeatable_quest_exchange(
                name=session.character_name,
                quest_id=quest.quest_id,
                cost_item_id=quest.cost_item_id,
                cost_quantity=quest.cost_quantity,
                reward_item_id=quest.reward_item_id,
                reward_quantity=quest.reward_quantity,
            )
        except InventoryLimitError as exc:
            await self._send_inventory_limit_result(
                session=session,
                target_id=entity.entity_id,
                target_name=entity.name,
                error=exc,
            )
            return
        if not exchanged:
            return

        await self._send_interaction_result(
            session=session,
            target_id=entity.entity_id,
            target_name=entity.name,
            text=quest.success_text,
        )
        await self._send_inventory_update(session, inventory)

    async def _handle_vendor_buy_request(
        self,
        session: PlayerSession,
        payload: dict[str, object],
    ) -> None:
        """
        Проверяет и применяет покупку у NPC-торговца.
        """
        if not self._can_player_act(session.player_id):
            return

        request = vendor_purchase_request_from_payload(payload)
        entity = self._resolve_interaction_entity(session, request.vendor_id)
        if entity is None or entity.kind != EntityKind.NPC:
            return

        offer = self._vendor_offer_definition(entity.entity_id, request.offer_id)
        if offer is None:
            logger.info(
                "Vendor purchase ignored: name=%s vendor_id=%s offer_id=%s reason=missing",
                session.character_name,
                entity.entity_id,
                request.offer_id,
            )
            return

        try:
            inventory, purchased = self.character_repository.exchange_items(
                name=session.character_name,
                cost_item_id=offer.price_item_id,
                cost_quantity=offer.price_quantity,
                reward_item_id=offer.item_id,
            )
        except InventoryLimitError as exc:
            await self._send_inventory_limit_result(
                session=session,
                target_id=entity.entity_id,
                target_name=entity.name,
                error=exc,
                presentation=INTERACTION_PRESENTATION_FEED,
            )
            await self._send_vendor_window(session, entity)
            return

        if not purchased:
            await self._send_interaction_result(
                session=session,
                target_id=entity.entity_id,
                target_name=entity.name,
                text="Недостаточно Gold",
                add_to_journal=False,
                presentation=INTERACTION_PRESENTATION_FEED,
            )
            await self._send_vendor_window(session, entity)
            return

        item_name = item_definition_for(offer.item_id).display_name
        logger.info(
            "Vendor purchase: name=%s vendor_id=%s offer_id=%s item_id=%s",
            session.character_name,
            entity.entity_id,
            offer.offer_id,
            offer.item_id,
        )
        await self._send_inventory_update(session, inventory)
        await self._send_interaction_result(
            session=session,
            target_id=session.player_id,
            target_name=session.character_name,
            text=f"Вы купили {item_name}",
            presentation=INTERACTION_PRESENTATION_FEED,
        )
        await self._send_vendor_window(session, entity)

    async def _send_vendor_window(
        self,
        session: PlayerSession,
        entity: WorldEntity,
    ) -> None:
        """
        Отправляет клиенту актуальное server-authoritative окно торговца.
        """
        await self._send(
            session.websocket,
            ProtocolMessage(
                type=ServerMessageType.VENDOR_OPENED,
                payload=vendor_opened_payload(
                    vendor_id=entity.entity_id,
                    title=entity.name,
                    offers=tuple(self._vendor_offers(session, entity.entity_id)),
                ),
            ),
        )

    def _vendor_offers(
        self,
        session: PlayerSession,
        vendor_id: str,
    ) -> list[VendorOffer]:
        """
        Собирает видимые игроку позиции торговца с актуальной доступностью.
        """
        offers: list[VendorOffer] = []
        for offer in NPC_VENDOR_OFFERS.get(vendor_id, ()):
            current_quantity = self.character_repository.item_quantity(
                session.character_name,
                offer.price_item_id,
            )
            price_definition = item_definition_for(offer.price_item_id)
            item_definition = item_definition_for(offer.item_id)
            enabled = current_quantity >= offer.price_quantity
            offers.append(
                VendorOffer(
                    offer_id=offer.offer_id,
                    item_id=offer.item_id,
                    display_name=item_definition.display_name,
                    price_item_id=offer.price_item_id,
                    price_display_name=price_definition.display_name,
                    price_quantity=offer.price_quantity,
                    enabled=enabled,
                    details=offer.details,
                    disabled_reason=(
                        None
                        if enabled
                        else f"Нужно: {price_definition.display_name} {offer.price_quantity}"
                    ),
                )
            )
        return offers

    def _vendor_offer_definition(
        self,
        vendor_id: str,
        offer_id: str,
    ) -> VendorOfferDefinition | None:
        """
        Возвращает server-side определение позиции торговца.
        """
        for offer in NPC_VENDOR_OFFERS.get(vendor_id, ()):
            if offer.offer_id == offer_id:
                return offer
        return None

    async def _handle_gate_interaction(
        self,
        session: PlayerSession,
        target_id: str,
        target_name: str,
    ) -> None:
        """
        Переключает открытую или закрытую калитку.
        """
        entity = self.world.get_entity(target_id)
        if entity is not None and entity.is_open and self.world.is_gate_occupied(target_id):
            await self._send_interaction_result(
                session=session,
                target_id=target_id,
                target_name=target_name,
                text="Проход занят",
                add_to_journal=False,
            )
            return

        updated = self.world.toggle_gate(target_id)
        if updated is None:
            return

        await self._broadcast_snapshot()

    async def _handle_lootable_interaction(
        self,
        session: PlayerSession,
        entity: WorldEntity,
    ) -> None:
        """
        Обрабатывает одноразовую выдачу loot-награды из объекта мира.
        """
        lootable = entity.lootable
        if lootable is None:
            logger.info(
                "Lootable interaction ignored: name=%s target_id=%s reason=missing_rule",
                session.character_name,
                entity.entity_id,
            )
            return
        if lootable.claim_policy == LootClaimPolicy.AFTER_DESTROYED and not entity.is_destroyed:
            logger.info(
                "Lootable interaction ignored: name=%s target_id=%s reason=not_destroyed",
                session.character_name,
                entity.entity_id,
            )
            return
        if lootable.claim_policy == LootClaimPolicy.RUNTIME_ONCE:
            await self._handle_runtime_loot_interaction(session, entity)
            return

        try:
            inventory, claimed = self.character_repository.claim_loot_once(
                name=session.character_name,
                source_id=entity.entity_id,
                item_id=lootable.reward_item_id,
                quantity=lootable.reward_quantity,
            )
        except InventoryLimitError as exc:
            await self._send_inventory_limit_result(
                session,
                session.player_id,
                session.character_name,
                exc,
            )
            return

        if not claimed:
            return

        logger.info(
            "Loot granted: name=%s source_id=%s item_id=%s quantity=%s",
            session.character_name,
            entity.entity_id,
            lootable.reward_item_id,
            lootable.reward_quantity,
        )
        await self._send_inventory_update(session, inventory)
        await self._send_interaction_result(
            session=session,
            target_id=session.player_id,
            target_name=session.character_name,
            text=lootable.success_text,
        )

    async def _handle_runtime_loot_interaction(
        self,
        session: PlayerSession,
        entity: WorldEntity,
    ) -> None:
        """
        Выдает runtime-добычу из временного объекта без persistent loot-claim.
        """
        lootable = entity.lootable
        if lootable is None or entity.entity_id in self.runtime_loot_claims:
            return

        try:
            inventory = self.character_repository.add_item(
                session.character_name,
                lootable.reward_item_id,
                quantity=lootable.reward_quantity,
            )
        except InventoryLimitError as exc:
            await self._send_inventory_limit_result(
                session,
                session.player_id,
                session.character_name,
                exc,
            )
            return

        self.runtime_loot_claims.add(entity.entity_id)
        self.world.clear_entity_lootable(entity.entity_id)
        await self._send_inventory_update(session, inventory)
        await self._send_interaction_result(
            session=session,
            target_id=session.player_id,
            target_name=session.character_name,
            text=lootable.success_text,
        )
        await self._broadcast_snapshot()

    async def _handle_creature_interaction(
        self,
        session: PlayerSession,
        entity: WorldEntity,
    ) -> None:
        """
        Обрабатывает взаимодействие с creature-сущностью мира.
        """
        if entity.entity_id != "creature-barbara":
            return
        await self._handle_barbara_interaction(session, entity)

    async def _handle_barbara_interaction(
        self,
        session: PlayerSession,
        entity: WorldEntity,
    ) -> None:
        """
        Обрабатывает стрижку овцы Барбары.
        """
        if not self.character_repository.is_item_equipped(
            session.character_name,
            MAIN_HAND_SLOT,
            SHEARS_ITEM_ID,
        ):
            await self._send_interaction_result(
                session=session,
                target_id=session.player_id,
                target_name=session.character_name,
                text="Нужны ножницы в руке",
                add_to_journal=False,
            )
            return
        if entity.has_wool is not True:
            await self._send_interaction_result(
                session=session,
                target_id=session.player_id,
                target_name=session.character_name,
                text="Шерсть еще не выросла",
                add_to_journal=False,
            )
            return

        try:
            inventory = self.character_repository.add_item(
                session.character_name,
                WOOL_ITEM_ID,
            )
        except InventoryLimitError as exc:
            await self._send_inventory_limit_result(
                session,
                session.player_id,
                session.character_name,
                exc,
            )
            return

        self.world.mark_creature_sheared(entity.entity_id, WOOL_REGROW_SECONDS)
        await self._send_inventory_update(session, inventory)
        await self._send_interaction_result(
            session=session,
            target_id=session.player_id,
            target_name=session.character_name,
            text="Вы состригли шерсть с овцы",
        )
        await self._broadcast_snapshot()

    async def _handle_tile_interaction(
        self,
        session: PlayerSession,
        tile: tuple[int, int],
    ) -> None:
        """
        Проверяет взаимодействие с тайлом карты.
        """
        tile_x, tile_y = tile
        if not self.world.tile_map.in_bounds(tile_x, tile_y):
            return
        tile_name = self.world.tile_map.tile_name_at(tile_x, tile_y)
        rule = TILE_GATHERING_RULES.get(tile_name)
        if rule is None:
            return

        player = self.world.players.get(session.player_id)
        if player is None or not player.can_act:
            return

        tile_center = self.world.tile_map.tile_rect(tile_x, tile_y).center
        if (player.center - tile_center).length > TILE_GATHERING_DISTANCE:
            return
        if not self.character_repository.is_item_equipped(
            session.character_name,
            MAIN_HAND_SLOT,
            rule.tool_item_id,
        ):
            await self._send_interaction_result(
                session=session,
                target_id=session.player_id,
                target_name=session.character_name,
                text=rule.missing_tool_text,
                add_to_journal=False,
                presentation=INTERACTION_PRESENTATION_FEED,
            )
            return

        await self._start_gathering_action(session, tile, rule, time.monotonic())

    async def _start_gathering_action(
        self,
        session: PlayerSession,
        tile: tuple[int, int],
        rule: TileGatheringRule,
        now: float,
    ) -> None:
        """
        Запускает подготовку добычи ресурса и блокирует новые команды персонажа.
        """
        if self.world.set_player_action(session.player_id, "gathering") is None:
            return
        self._stop_attack(session)
        self.pending_gathering_actions[session.player_id] = PendingGatheringAction(
            session_id=session.session_id,
            player_id=session.player_id,
            character_name=session.character_name,
            tile=tile,
            rule=rule,
            completes_at=now + GATHERING_ACTION_SECONDS,
        )
        await self._broadcast_snapshot()

    async def _tick_player_actions(self, now: float) -> None:
        """
        Завершает отложенные действия персонажей, срок которых наступил.
        """
        snapshot_needed = False
        for player_id, action in list(self.pending_gathering_actions.items()):
            if now < action.completes_at:
                continue
            self.pending_gathering_actions.pop(player_id, None)
            snapshot_needed = True
            session = self.sessions.get(action.session_id)
            if (
                session is not None
                and session.player_id == action.player_id
                and session.character_name == action.character_name
            ):
                await self._complete_gathering_action(session, action)
            self.world.clear_player_action(player_id)
        if snapshot_needed:
            await self._broadcast_snapshot()

    async def _complete_gathering_action(
        self,
        session: PlayerSession,
        action: PendingGatheringAction,
    ) -> None:
        """
        Повторно проверяет и применяет результат добычи после подготовки.
        """
        tile_x, tile_y = action.tile
        if not self.world.tile_map.in_bounds(tile_x, tile_y):
            return
        if self.world.tile_map.tile_name_at(tile_x, tile_y) != action.rule.tile_name:
            return

        player = self.world.players.get(session.player_id)
        if player is None or not player.is_alive:
            return
        tile_center = self.world.tile_map.tile_rect(tile_x, tile_y).center
        if (player.center - tile_center).length > TILE_GATHERING_DISTANCE:
            return
        if not self.character_repository.is_item_equipped(
            session.character_name,
            MAIN_HAND_SLOT,
            action.rule.tool_item_id,
        ):
            await self._send_interaction_result(
                session=session,
                target_id=session.player_id,
                target_name=session.character_name,
                text=action.rule.missing_tool_text,
                add_to_journal=False,
                presentation=INTERACTION_PRESENTATION_FEED,
            )
            return

        rule = action.rule
        if rule.success_chance >= 1.0 or self.random.random() < rule.success_chance:
            try:
                inventory = self.character_repository.add_item(
                    session.character_name,
                    rule.reward_item_id,
                )
            except InventoryLimitError as exc:
                await self._send_inventory_limit_result(
                    session,
                    session.player_id,
                    session.character_name,
                    exc,
                    presentation=INTERACTION_PRESENTATION_FEED,
                )
                return
            await self._send_inventory_update(session, inventory)
            await self._send_interaction_result(
                session=session,
                target_id=session.player_id,
                target_name=session.character_name,
                text=rule.success_text,
                presentation=INTERACTION_PRESENTATION_FEED,
            )
            return

        if rule.failure_text is not None:
            await self._send_interaction_result(
                session=session,
                target_id=session.player_id,
                target_name=session.character_name,
                text=rule.failure_text,
                presentation=INTERACTION_PRESENTATION_FEED,
            )

    async def _tick_combat(self, now: float) -> None:
        """
        Выполняет server-authoritative auto-attack для активных целей игроков.
        """
        for session in list(self.sessions.values()):
            if not self._can_player_act(session.player_id):
                self._stop_attack(session)
                continue

            target_id = self.combat_targets.get(session.player_id)
            if target_id is None:
                continue

            player = self.world.players.get(session.player_id)
            target = self.world.get_entity(target_id)
            if player is None or target is None or not target.is_attackable:
                self._stop_attack(session)
                continue

            distance = (player.center - target.center).length
            if distance > ATTACK_DISTANCE:
                continue
            if now < self.next_combat_swing_at.get(session.player_id, 0.0):
                continue

            rule = self._combat_rule_for_character(session.character_name)
            self.next_combat_swing_at[session.player_id] = now + rule.swing_cooldown_seconds
            target_name = target.base_name
            if self.random.random() >= ATTACK_HIT_CHANCE:
                if target.kind == EntityKind.CREATURE:
                    self.world.aggro_creature(target.entity_id, session.player_id)
                await self._send_combat_event(
                    session=session,
                    target_id=target.entity_id,
                    target_name=target_name,
                    text="Вы промахнулись",
                    floating_text="Промах",
                )
                continue

            damage = self.random.randint(rule.min_damage, rule.max_damage)
            damage_result = self.world.damage_entity(target.entity_id, damage)
            if damage_result is None:
                self._stop_attack(session)
                continue

            _, destroyed = damage_result
            if target.kind == EntityKind.CREATURE:
                self._add_enemy_damage(target.entity_id, session.player_id, damage)
            await self._send_combat_event(
                session=session,
                target_id=target.entity_id,
                target_name=target_name,
                text=f"Вы атаковали {target_name}: -{damage}",
                floating_text=f"-{damage}",
                destroyed=destroyed,
            )
            if destroyed:
                self._stop_attacks_against(target.entity_id)
                self._clear_enemy_state(target.entity_id)
                destroyed_text = f"{target_name} разрушен"
                destroyed_floating_text = "Разрушен"
                if target.kind == EntityKind.CREATURE:
                    destroyed_text = f"{target_name} погиб"
                    destroyed_floating_text = "Погиб"
                await self._send_combat_event(
                    session=session,
                    target_id=target.entity_id,
                    target_name=target_name,
                    text=destroyed_text,
                    floating_text=destroyed_floating_text,
                    destroyed=True,
                )
            await self._broadcast_snapshot()

    async def _tick_enemy_combat(self, now: float) -> None:
        """
        Выполняет ответные auto-attack удары creature-врагов по игрокам.
        """
        for entity in self.world.entities:
            if entity.kind != EntityKind.CREATURE or entity.combat is None:
                continue
            if not entity.visible or entity.is_destroyed:
                continue
            if entity.combat.max_damage <= 0:
                continue

            target_player_id = self.world.creature_target_player_id(entity.entity_id)
            if target_player_id is None:
                continue
            target_session = self._session_for_player_id(target_player_id)
            target_player = self.world.players.get(target_player_id)
            if target_session is None or target_player is None or not target_player.is_alive:
                self._clear_enemy_targeting_player(target_player_id)
                continue

            distance = (entity.center - target_player.center).length
            if distance > entity.combat.attack_distance:
                continue
            if now < self.next_enemy_swing_at.get(entity.entity_id, 0.0):
                continue

            self.next_enemy_swing_at[entity.entity_id] = (
                now + entity.combat.swing_cooldown_seconds
            )
            if self.random.random() >= entity.combat.hit_chance:
                await self._send_combat_event_to_session(
                    session=target_session,
                    actor_id=entity.entity_id,
                    actor_name=entity.base_name,
                    target_id=target_session.player_id,
                    target_name=target_session.character_name,
                    text=f"{entity.base_name} промахнулся",
                    floating_text="Промах",
                )
                continue

            raw_damage = self.random.randint(entity.combat.min_damage, entity.combat.max_damage)
            armor_points = self._armor_points_for_character(target_session.character_name)
            damage = max(1, raw_damage - armor_points)
            absorbed = raw_damage - damage
            damage_result = self.world.damage_player(target_player_id, damage)
            if damage_result is None:
                continue
            _, killed = damage_result
            combat_text = f"{entity.base_name} атаковал вас: -{damage}"
            if armor_points > 0:
                combat_text = (
                    f"{combat_text} ({absorbed}/{armor_points} поглощено броней)"
                )
            await self._send_combat_event_to_session(
                session=target_session,
                actor_id=entity.entity_id,
                actor_name=entity.base_name,
                target_id=target_session.player_id,
                target_name=target_session.character_name,
                text=combat_text,
                floating_text=f"-{damage}",
            )
            if killed:
                self._clear_player_action(target_session.player_id)
                self._stop_attack(target_session)
                self._clear_enemy_targeting_player(target_session.player_id)
                await self._send_combat_event_to_session(
                    session=target_session,
                    actor_id=entity.entity_id,
                    actor_name=entity.base_name,
                    target_id=target_session.player_id,
                    target_name=target_session.character_name,
                    text=PLAYER_DEATH_TEXT,
                    floating_text=PLAYER_DEATH_TEXT,
                    add_to_journal=False,
                )
            await self._broadcast_snapshot()

    def _combat_rule_for_character(self, character_name: str) -> WeaponCombatRule:
        """
        Возвращает параметры удара для предмета в руке или unarmed-атаки.
        """
        equipment = self.character_repository.load_equipment(character_name)
        if equipment.main_hand is None:
            return UNARMED_COMBAT_RULE
        if not self.character_repository.is_item_equipped(
            character_name,
            MAIN_HAND_SLOT,
            equipment.main_hand,
        ):
            return UNARMED_COMBAT_RULE
        return WEAPON_COMBAT_RULES.get(equipment.main_hand, UNARMED_COMBAT_RULE)

    def _armor_points_for_character(self, character_name: str) -> int:
        """
        Возвращает суммарную броню экипировки персонажа.
        """
        equipment = self.character_repository.load_equipment(character_name)
        if equipment.chest is None:
            return 0
        if not self.character_repository.is_item_equipped(
            character_name,
            CHEST_SLOT,
            equipment.chest,
        ):
            return 0
        return armor_points_for_item(equipment.chest)

    def _is_player_alive(self, player_id: str) -> bool:
        """
        Проверяет, жив ли персонаж в runtime-мире.
        """
        player = self.world.players.get(player_id)
        return player is not None and player.is_alive

    def _is_player_busy(self, player_id: str) -> bool:
        """
        Проверяет, выполняет ли персонаж блокирующее server-authoritative действие.
        """
        player = self.world.players.get(player_id)
        return player is not None and player.busy

    def _can_player_act(self, player_id: str) -> bool:
        """
        Проверяет, может ли персонаж принимать новые gameplay-команды.
        """
        player = self.world.players.get(player_id)
        return player is not None and player.can_act

    def _clear_player_action(self, player_id: str) -> None:
        """
        Сбрасывает блокирующее действие персонажа и связанные pending-операции.
        """
        self.pending_gathering_actions.pop(player_id, None)
        self.world.clear_player_action(player_id)

    def _session_for_player_id(self, player_id: str) -> PlayerSession | None:
        """
        Возвращает активную websocket-сессию по id персонажа.
        """
        for session in self.sessions.values():
            if session.player_id == player_id:
                return session
        return None

    def _add_enemy_damage(self, entity_id: str, player_id: str, damage: int) -> None:
        """
        Запоминает нанесенный врагу урон и обновляет цель по наибольшему вкладу.
        """
        totals = self.enemy_damage_totals.setdefault(entity_id, {})
        totals[player_id] = totals.get(player_id, 0) + damage
        preferred_target = self._preferred_enemy_target(entity_id)
        if preferred_target is not None:
            self.world.aggro_creature(entity_id, preferred_target)

    def _preferred_enemy_target(self, entity_id: str) -> str | None:
        """
        Выбирает живого персонажа, нанесшего врагу больше всего урона.
        """
        totals = self.enemy_damage_totals.get(entity_id, {})
        alive_totals = {
            player_id: damage
            for player_id, damage in totals.items()
            if self._is_player_alive(player_id)
        }
        if not alive_totals:
            return None
        return max(alive_totals, key=lambda player_id: alive_totals[player_id])

    def _clear_enemy_state(self, entity_id: str) -> None:
        """
        Сбрасывает runtime-боевое состояние врага.
        """
        self.enemy_damage_totals.pop(entity_id, None)
        self.next_enemy_swing_at.pop(entity_id, None)
        self.world.clear_creature_aggro(entity_id, return_home=False)

    def _clear_enemy_targeting_player(self, player_id: str) -> None:
        """
        Убирает персонажа из целей врагов и при возможности выбирает следующую цель.
        """
        for entity_id, totals in list(self.enemy_damage_totals.items()):
            totals.pop(player_id, None)
            if not totals:
                self.enemy_damage_totals.pop(entity_id, None)
            if self.world.creature_target_player_id(entity_id) != player_id:
                continue
            preferred_target = self._preferred_enemy_target(entity_id)
            if preferred_target is None:
                self.world.clear_creature_aggro(entity_id, return_home=True)
            else:
                self.world.aggro_creature(entity_id, preferred_target)
        for entity in self.world.entities:
            if self.world.creature_target_player_id(entity.entity_id) == player_id:
                self.world.clear_creature_aggro(entity.entity_id, return_home=True)

    def _stop_attacks_against(self, target_id: str) -> None:
        """
        Сбрасывает auto-attack у всех игроков, которые били указанную цель.
        """
        for player_id, current_target_id in list(self.combat_targets.items()):
            if current_target_id != target_id:
                continue
            self.combat_targets.pop(player_id, None)
            self.next_combat_swing_at.pop(player_id, None)

    async def _send_combat_event(
        self,
        session: PlayerSession,
        target_id: str,
        target_name: str,
        text: str,
        floating_text: str,
        destroyed: bool = False,
    ) -> None:
        """
        Отправляет событие боя инициатору атаки.
        """
        await self._send(
            session.websocket,
            ProtocolMessage(
                type=ServerMessageType.COMBAT_EVENT,
                payload=combat_event_payload(
                    actor_id=session.player_id,
                    actor_name=session.character_name,
                    target_id=target_id,
                    target_name=target_name,
                    text=text,
                    floating_text=floating_text,
                    created_at=time.time(),
                    destroyed=destroyed,
                ),
            ),
        )

    async def _send_combat_event_to_session(
        self,
        session: PlayerSession,
        actor_id: str,
        actor_name: str,
        target_id: str,
        target_name: str,
        text: str,
        floating_text: str,
        destroyed: bool = False,
        add_to_journal: bool = True,
    ) -> None:
        """
        Отправляет combat_event конкретному клиенту с произвольным actor-ом.
        """
        await self._send(
            session.websocket,
            ProtocolMessage(
                type=ServerMessageType.COMBAT_EVENT,
                payload=combat_event_payload(
                    actor_id=actor_id,
                    actor_name=actor_name,
                    target_id=target_id,
                    target_name=target_name,
                    text=text,
                    floating_text=floating_text,
                    created_at=time.time(),
                    add_to_journal=add_to_journal,
                    destroyed=destroyed,
                ),
            ),
        )

    async def _send_interaction_result(
        self,
        session: PlayerSession,
        target_id: str,
        target_name: str,
        text: str,
        add_to_journal: bool = True,
        presentation: str = INTERACTION_PRESENTATION_BUBBLE,
    ) -> None:
        """
        Отправляет результат взаимодействия одному клиенту.
        """
        await self._send(
            session.websocket,
            ProtocolMessage(
                type=ServerMessageType.INTERACTION_RESULT,
                payload=interaction_result_payload(
                    actor_id=session.player_id,
                    target_id=target_id,
                    target_name=target_name,
                    text=text,
                    created_at=time.time(),
                    add_to_journal=add_to_journal,
                    presentation=presentation,
                ),
            ),
        )

    def _resolve_interaction_entity(
        self,
        session: PlayerSession,
        target_id: str,
    ) -> WorldEntity | None:
        """
        Проверяет, что interactable-объект существует и находится в радиусе игрока.
        """
        player = self.world.players.get(session.player_id)
        entity = self.world.get_entity(target_id)
        if player is None or entity is None:
            logger.info(
                "Interaction ignored: name=%s target_id=%s reason=missing_target",
                session.character_name,
                target_id,
            )
            return None
        if entity.interaction is None:
            logger.info(
                "Interaction ignored: name=%s target_id=%s reason=not_interactable",
                session.character_name,
                target_id,
            )
            return None

        distance = (player.center - entity.center).length
        if distance > entity.interaction_radius:
            logger.info(
                "Interaction ignored: name=%s target_id=%s distance=%.2f radius=%.2f",
                session.character_name,
                target_id,
                distance,
                entity.interaction_radius,
            )
            return None
        return entity

    async def _grant_item_if_needed(self, session: PlayerSession, item_id: str) -> None:
        """
        Выдает персонажу предмет, если такого предмета еще нет в инвентаре.
        """
        _, granted = self.character_repository.add_item_if_absent(session.character_name, item_id)
        if not granted:
            return

        logger.info(
            "Inventory item granted: name=%s item_id=%s",
            session.character_name,
            item_id,
        )
        await self._send_inventory_update(session)

    async def _send_inventory_limit_result(
        self,
        session: PlayerSession,
        target_id: str,
        target_name: str,
        error: InventoryLimitError,
        presentation: str = INTERACTION_PRESENTATION_BUBBLE,
    ) -> None:
        """
        Логирует переполнение инвентаря и отправляет игровой отказ игроку.
        """
        logger.info(
            "Inventory limit reached: name=%s error=%s",
            session.character_name,
            error,
        )
        await self._send_interaction_result(
            session=session,
            target_id=target_id,
            target_name=target_name,
            text=INVENTORY_FULL_TEXT,
            presentation=presentation,
        )

    async def _send_inventory_update(
        self,
        session: PlayerSession,
        inventory: list[ItemStack] | None = None,
    ) -> None:
        """
        Отправляет актуальное состояние инвентаря одному клиенту.
        """
        if inventory is None:
            inventory = self.character_repository.load_inventory(session.character_name)
        await self._send(
            session.websocket,
            ProtocolMessage(
                type=ServerMessageType.INVENTORY_UPDATED,
                payload=inventory_updated_payload(inventory),
            ),
        )

    async def _send_equipment_update(
        self,
        session: PlayerSession,
        equipment: Equipment | None = None,
    ) -> None:
        """
        Отправляет актуальное состояние экипировки одному клиенту.
        """
        if equipment is None:
            equipment = self.character_repository.load_equipment(session.character_name)
        await self._send(
            session.websocket,
            ProtocolMessage(
                type=ServerMessageType.EQUIPMENT_UPDATED,
                payload=equipment_updated_payload(equipment),
            ),
        )

    async def _game_loop(self) -> None:
        """
        Продвигает мир с фиксированной частотой тиков и периодически рассылает snapshot-ы.
        """
        tick_interval = 1.0 / self.tick_rate
        snapshot_interval = 1.0 / self.snapshot_rate
        previous_time = time.monotonic()
        snapshot_elapsed = 0.0
        save_elapsed = 0.0

        while True:
            await asyncio.sleep(tick_interval)
            current_time = time.monotonic()
            delta_seconds = min(current_time - previous_time, 0.1)
            previous_time = current_time

            self.world.tick(delta_seconds)
            await self._tick_player_actions(current_time)
            await self._tick_combat(current_time)
            await self._tick_enemy_combat(current_time)
            snapshot_elapsed += delta_seconds
            save_elapsed += delta_seconds

            if snapshot_elapsed >= snapshot_interval:
                snapshot_elapsed = 0.0
                await self._broadcast_snapshot()
            if save_elapsed >= self.save_interval:
                save_elapsed = 0.0
                self._save_active_positions()

    def _save_active_positions(self) -> None:
        """
        Сохраняет позиции всех актуальных активных сессий.
        """
        for session_id in list(self.active_character_sessions.values()):
            session = self.sessions.get(session_id)
            if session is not None:
                self._save_session_position(session)

    async def _broadcast_snapshot(self) -> None:
        """
        Отправляет текущий authoritative snapshot мира всем подключенным клиентам.
        """
        if not self.connections:
            return

        await self._broadcast(
            ProtocolMessage(
                type=ServerMessageType.WORLD_SNAPSHOT,
                payload=self.world.snapshot_payload(),
            )
        )

    async def _broadcast_removed(self, session: PlayerSession) -> None:
        """
        Рассылает событие удаления игрока из мира.
        """
        await self._broadcast(
            ProtocolMessage(
                type=ServerMessageType.ENTITY_REMOVED,
                payload={"id": session.player_id, "name": session.character_name},
            )
        )

    async def _broadcast(self, message: ProtocolMessage) -> None:
        """
        Отправляет одно протокольное сообщение всем текущим подключенным клиентам.
        """
        sends = [self._send(connection, message) for connection in list(self.connections.values())]
        if sends:
            await asyncio.gather(*sends, return_exceptions=True)

    async def _send(self, websocket: ServerConnection, message: ProtocolMessage) -> None:
        """
        Отправляет одно закодированное протокольное сообщение одному websocket-клиенту.
        """
        await websocket.send(encode_message(message))

    async def _send_error(self, player_id: str, error_message: str) -> None:
        """
        Отправляет ответ с протокольной ошибкой одному подключенному клиенту.
        """
        websocket = self.connections.get(player_id)
        if websocket is None:
            return

        await self._send_protocol_error(websocket, error_message)

    async def _send_protocol_error(
        self,
        websocket: ServerConnection,
        error_message: str,
    ) -> None:
        """
        Отправляет протокольную ошибку конкретному websocket-клиенту.
        """
        await self._send(
            websocket,
            ProtocolMessage(
                type=ServerMessageType.ERROR,
                payload={"message": error_message},
            ),
        )

    def _new_player_id(self) -> str:
        """
        Создает короткий уникальный id для нового подключенного игрока.
        """
        return f"player-{uuid.uuid4().hex[:8]}"


def parse_args() -> argparse.Namespace:
    """
    Разбирает аргументы командной строки для multiplayer-сервера.
    """
    parser = argparse.ArgumentParser(description="Run the authoritative 2D RPG server.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host/IP for the websocket server.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Websocket server port.")
    parser.add_argument(
        "--map",
        type=Path,
        default=DEFAULT_MAP_PATH,
        help=f"Path to a prototype JSON map. Defaults to {DEFAULT_MAP_PATH}.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=f"Path to SQLite database. Defaults to {DEFAULT_DATABASE_PATH}.",
    )
    parser.add_argument("--tick-rate", type=float, default=DEFAULT_TICK_RATE)
    parser.add_argument("--snapshot-rate", type=float, default=DEFAULT_SNAPSHOT_RATE)
    parser.add_argument("--save-interval", type=float, default=DEFAULT_SAVE_INTERVAL)
    return parser.parse_args()


async def async_main(args: argparse.Namespace) -> None:
    """
    Создает мир и асинхронно запускает multiplayer-сервер.
    """
    configure_logging()
    tile_map = load_tile_map(args.map)
    logger.info(
        "Loaded map: path=%s size=%sx%s entities=%s fingerprint=%s",
        args.map,
        tile_map.width,
        tile_map.height,
        len(tile_map.entities),
        tile_map.fingerprint,
    )
    character_repository = CharacterRepository(args.database)
    character_repository.initialize()
    server = MultiplayerServer(
        world=MultiplayerWorld(tile_map=tile_map),
        character_repository=character_repository,
        tick_rate=args.tick_rate,
        snapshot_rate=args.snapshot_rate,
        save_interval=args.save_interval,
    )
    await server.run(args.host, args.port)


def configure_logging() -> None:
    """
    Настраивает простой вывод серверных логов в консоль.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    """
    Запускает multiplayer-сервер до остановки пользователем.
    """
    args = parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
