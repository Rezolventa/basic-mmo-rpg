from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import random
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from websockets.asyncio.server import ServerConnection, serve

from basic_mmo_rpg.domain.entities import EntityKind, WorldEntity
from basic_mmo_rpg.domain.equipment import (
    MAIN_HAND_SLOT,
    Equipment,
    EquipmentError,
)
from basic_mmo_rpg.domain.inventory import (
    FISH_ITEM_ID,
    FISHING_ROD_ITEM_ID,
    GOLD_ITEM_ID,
    LOG_ITEM_ID,
    LUMBER_AXE_ITEM_ID,
    PICKAXE_ITEM_ID,
    RUSTY_SWORD_ITEM_ID,
    SHEARS_ITEM_ID,
    STONE_ITEM_ID,
    WOOL_ITEM_ID,
    InventoryLimitError,
    ItemStack,
)
from basic_mmo_rpg.server.world import MultiplayerWorld
from basic_mmo_rpg.shared.protocol import (
    ClientMessageType,
    ProtocolError,
    ProtocolMessage,
    ServerMessageType,
    character_name_from_payload,
    chat_message_payload,
    chat_text_from_payload,
    decode_message,
    encode_message,
    equip_item_id_from_payload,
    equipment_slot_from_payload,
    equipment_updated_payload,
    interaction_result_payload,
    interaction_target_from_payload,
    inventory_updated_payload,
    movement_intent_from_payload,
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
TILE_GATHERING_COOLDOWN_SECONDS = 1.0
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
TRAINING_DUMMY_REWARD_TEXT = "Вы вытащили Ржавый меч из манекена"

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
class LootableRule:
    """
    Описывает server-authoritative награду lootable-объекта мира.
    """

    reward_item_id: str
    reward_quantity: int
    success_text: str


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

LOOTABLE_RULES: dict[str, LootableRule] = {
    "lootable-training-dummy": LootableRule(
        reward_item_id=RUSTY_SWORD_ITEM_ID,
        reward_quantity=1,
        success_text=TRAINING_DUMMY_REWARD_TEXT,
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
        self.gathering_available_at: dict[str, float] = {}
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
            return character_name_from_payload(message.payload)
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
        self.world.add_player(player_id, character_name, character.position)

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

        self._save_session_position(session)
        self._remove_session_state(session)
        logger.info("Player left: name=%s player_id=%s", session.character_name, session.player_id)
        await self._broadcast_removed(session)
        await self._broadcast_snapshot()

    def _remove_session_state(self, session: PlayerSession) -> None:
        """
        Удаляет runtime-состояние активной сессии из сервера и мира.
        """
        self.world.remove_player(session.player_id)
        self.connections.pop(session.player_id, None)
        self.sessions.pop(session.session_id, None)
        self.active_character_sessions.pop(session.character_name, None)

    def _save_session_position(self, session: PlayerSession) -> None:
        """
        Сохраняет текущую позицию персонажа, если он еще есть в мире.
        """
        player = self.world.players.get(session.player_id)
        if player is None:
            return
        self.character_repository.save_position(session.character_name, player.position)
        logger.debug(
            "Player position saved: name=%s x=%.2f y=%.2f",
            session.character_name,
            player.position.x,
            player.position.y,
        )

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
                self.world.set_intent(
                    session.player_id,
                    movement_intent_from_payload(message.payload),
                )
            elif message.type == ClientMessageType.CHAT_SENT:
                await self._handle_chat_message(session, message.payload)
            elif message.type == ClientMessageType.INTERACT_REQUESTED:
                await self._handle_interaction(session, message.payload)
            elif message.type == ClientMessageType.EQUIP_ITEM_REQUESTED:
                await self._handle_equip_item(session, message.payload)
            elif message.type == ClientMessageType.UNEQUIP_ITEM_REQUESTED:
                await self._handle_unequip_item(session, message.payload)
        except (ProtocolError, UnicodeDecodeError) as exc:
            await self._send_error(session.player_id, str(exc))
            logger.warning("Protocol error from %s: %s", session.character_name, exc)

    async def _handle_equip_item(
        self,
        session: PlayerSession,
        payload: dict[str, object],
    ) -> None:
        """
        Проверяет и применяет запрос экипировки предмета.
        """
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
            MAIN_HAND_SLOT,
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
        Проверяет сообщение чата и рассылает его всем клиентам.
        """
        text = chat_text_from_payload(payload)
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

    async def _handle_interaction(
        self,
        session: PlayerSession,
        payload: dict[str, object],
    ) -> None:
        """
        Проверяет запрос взаимодействия и отправляет результат только инициатору.
        """
        target = interaction_target_from_payload(payload)
        if target.entity_id is not None:
            await self._handle_entity_interaction(session, target.entity_id)
        elif target.tile is not None:
            await self._handle_tile_interaction(session, target.tile)

    async def _handle_entity_interaction(self, session: PlayerSession, target_id: str) -> None:
        """
        Проверяет взаимодействие с объектом мира.
        """
        player = self.world.players.get(session.player_id)
        entity = self.world.get_entity(target_id)
        if player is None or entity is None:
            logger.info(
                "Interaction ignored: name=%s target_id=%s reason=missing_target",
                session.character_name,
                target_id,
            )
            return
        if entity.kind not in {
            EntityKind.NPC,
            EntityKind.GATE,
            EntityKind.CREATURE,
            EntityKind.LOOTABLE,
        }:
            logger.info(
                "Interaction ignored: name=%s target_id=%s reason=unsupported_kind",
                session.character_name,
                target_id,
            )
            return

        distance = (player.center - entity.center).length
        if distance > entity.interaction_radius:
            logger.info(
                "Interaction ignored: name=%s target_id=%s distance=%.2f radius=%.2f",
                session.character_name,
                target_id,
                distance,
                entity.interaction_radius,
            )
            return

        logger.info(
            "Interaction accepted: name=%s target_id=%s",
            session.character_name,
            target_id,
        )
        if entity.kind == EntityKind.GATE:
            await self._handle_gate_interaction(session, entity.entity_id, entity.name)
            return
        if entity.kind == EntityKind.CREATURE:
            await self._handle_creature_interaction(session, entity)
            return
        if entity.kind == EntityKind.LOOTABLE:
            await self._handle_lootable_interaction(session, entity)
            return

        if entity.entity_id == "npc-funday":
            await self._handle_funday_interaction(
                session,
                entity.entity_id,
                entity.name,
                entity.dialogue,
            )
            return
        if entity.entity_id == "npc-jack-lumber":
            await self._handle_jack_lumber_interaction(
                session,
                entity.entity_id,
                entity.name,
                entity.dialogue,
            )
            return
        if entity.entity_id == "npc-kopai":
            await self._handle_kopai_interaction(
                session,
                entity.entity_id,
                entity.name,
                entity.dialogue,
            )
            return
        if entity.entity_id == "npc-fogu":
            await self._handle_fogu_interaction(
                session,
                entity.entity_id,
                entity.name,
                entity.dialogue,
            )
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

    async def _handle_funday_interaction(
        self,
        session: PlayerSession,
        target_id: str,
        target_name: str,
        default_dialogue: str,
    ) -> None:
        """
        Обрабатывает туториальную логику NPC Funday.
        """
        if not self.character_repository.has_item(session.character_name, FISHING_ROD_ITEM_ID):
            await self._send_interaction_result(
                session=session,
                target_id=target_id,
                target_name=target_name,
                text=default_dialogue,
            )
            await self._grant_fishing_rod_if_needed(session)
            return

        fish_quantity = self.character_repository.item_quantity(
            session.character_name,
            FISH_ITEM_ID,
        )
        if fish_quantity >= FUNDAY_REQUIRED_FISH:
            try:
                inventory, exchanged = self.character_repository.exchange_items(
                    name=session.character_name,
                    cost_item_id=FISH_ITEM_ID,
                    cost_quantity=FUNDAY_REQUIRED_FISH,
                    reward_item_id=GOLD_ITEM_ID,
                    reward_quantity=FUNDAY_GOLD_REWARD,
                )
            except InventoryLimitError as exc:
                logger.info(
                    "Inventory limit reached: name=%s error=%s",
                    session.character_name,
                    exc,
                )
                await self._send_interaction_result(
                    session=session,
                    target_id=target_id,
                    target_name=target_name,
                    text=INVENTORY_FULL_TEXT,
                )
                return
            if exchanged:
                await self._send_interaction_result(
                    session=session,
                    target_id=target_id,
                    target_name=target_name,
                    text="Отличная рыба. Держи Gold.",
                )
                await self._send_inventory_update(session, inventory)
            return

        await self._send_interaction_result(
            session=session,
            target_id=target_id,
            target_name=target_name,
            text=default_dialogue,
        )

    async def _handle_jack_lumber_interaction(
        self,
        session: PlayerSession,
        target_id: str,
        target_name: str,
        default_dialogue: str,
    ) -> None:
        """
        Обрабатывает туториальную логику NPC Jack Lumber.
        """
        if not self.character_repository.has_item(session.character_name, LUMBER_AXE_ITEM_ID):
            await self._send_interaction_result(
                session=session,
                target_id=target_id,
                target_name=target_name,
                text=default_dialogue,
            )
            await self._grant_item_if_needed(session, LUMBER_AXE_ITEM_ID)
            return

        log_quantity = self.character_repository.item_quantity(
            session.character_name,
            LOG_ITEM_ID,
        )
        if log_quantity >= JACK_REQUIRED_LOGS:
            try:
                inventory, exchanged = self.character_repository.exchange_items(
                    name=session.character_name,
                    cost_item_id=LOG_ITEM_ID,
                    cost_quantity=JACK_REQUIRED_LOGS,
                    reward_item_id=GOLD_ITEM_ID,
                    reward_quantity=JACK_GOLD_REWARD,
                )
            except InventoryLimitError as exc:
                await self._send_inventory_limit_result(session, target_id, target_name, exc)
                return
            if exchanged:
                await self._send_interaction_result(
                    session=session,
                    target_id=target_id,
                    target_name=target_name,
                    text="Отличная древесина. Держи Gold.",
                )
                await self._send_inventory_update(session, inventory)
            return

        await self._send_interaction_result(
            session=session,
            target_id=target_id,
            target_name=target_name,
            text=default_dialogue,
        )

    async def _handle_kopai_interaction(
        self,
        session: PlayerSession,
        target_id: str,
        target_name: str,
        default_dialogue: str,
    ) -> None:
        """
        Обрабатывает туториальную логику NPC Kopai.
        """
        if not self.character_repository.has_item(session.character_name, PICKAXE_ITEM_ID):
            await self._send_interaction_result(
                session=session,
                target_id=target_id,
                target_name=target_name,
                text=default_dialogue,
            )
            await self._grant_item_if_needed(session, PICKAXE_ITEM_ID)
            return

        stone_quantity = self.character_repository.item_quantity(
            session.character_name,
            STONE_ITEM_ID,
        )
        if stone_quantity >= KOPAI_REQUIRED_STONES:
            try:
                inventory, exchanged = self.character_repository.exchange_items(
                    name=session.character_name,
                    cost_item_id=STONE_ITEM_ID,
                    cost_quantity=KOPAI_REQUIRED_STONES,
                    reward_item_id=GOLD_ITEM_ID,
                    reward_quantity=KOPAI_GOLD_REWARD,
                )
            except InventoryLimitError as exc:
                await self._send_inventory_limit_result(session, target_id, target_name, exc)
                return
            if exchanged:
                await self._send_interaction_result(
                    session=session,
                    target_id=target_id,
                    target_name=target_name,
                    text="Отличный камень. Держи Gold.",
                )
                await self._send_inventory_update(session, inventory)
            return

        await self._send_interaction_result(
            session=session,
            target_id=target_id,
            target_name=target_name,
            text=default_dialogue,
        )

    async def _handle_fogu_interaction(
        self,
        session: PlayerSession,
        target_id: str,
        target_name: str,
        default_dialogue: str,
    ) -> None:
        """
        Обрабатывает туториальную логику NPC Fogu.
        """
        if not self.character_repository.has_item(session.character_name, SHEARS_ITEM_ID):
            await self._send_interaction_result(
                session=session,
                target_id=target_id,
                target_name=target_name,
                text=default_dialogue,
            )
            await self._grant_item_if_needed(session, SHEARS_ITEM_ID)
            return

        wool_quantity = self.character_repository.item_quantity(
            session.character_name,
            WOOL_ITEM_ID,
        )
        if wool_quantity >= FOGU_REQUIRED_WOOL:
            try:
                inventory, exchanged = self.character_repository.exchange_items(
                    name=session.character_name,
                    cost_item_id=WOOL_ITEM_ID,
                    cost_quantity=FOGU_REQUIRED_WOOL,
                    reward_item_id=GOLD_ITEM_ID,
                    reward_quantity=FOGU_GOLD_REWARD,
                )
            except InventoryLimitError as exc:
                await self._send_inventory_limit_result(session, target_id, target_name, exc)
                return
            if exchanged:
                await self._send_interaction_result(
                    session=session,
                    target_id=target_id,
                    target_name=target_name,
                    text="Спасибо. Вот, держи.",
                )
                await self._send_inventory_update(session, inventory)
            return

        await self._send_interaction_result(
            session=session,
            target_id=target_id,
            target_name=target_name,
            text=default_dialogue,
        )

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
        rule = LOOTABLE_RULES.get(entity.entity_id)
        if rule is None:
            logger.info(
                "Lootable interaction ignored: name=%s target_id=%s reason=missing_rule",
                session.character_name,
                entity.entity_id,
            )
            return

        try:
            inventory, claimed = self.character_repository.claim_loot_once(
                name=session.character_name,
                source_id=entity.entity_id,
                item_id=rule.reward_item_id,
                quantity=rule.reward_quantity,
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
            rule.reward_item_id,
            rule.reward_quantity,
        )
        await self._send_inventory_update(session, inventory)
        await self._send_interaction_result(
            session=session,
            target_id=session.player_id,
            target_name=session.character_name,
            text=rule.success_text,
        )

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
        if player is None:
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
            )
            return

        now = time.monotonic()
        if now < self.gathering_available_at.get(session.character_name, 0.0):
            return
        self.gathering_available_at[session.character_name] = now + TILE_GATHERING_COOLDOWN_SECONDS

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
                )
                return
            await self._send_inventory_update(session, inventory)
            await self._send_interaction_result(
                session=session,
                target_id=session.player_id,
                target_name=session.character_name,
                text=rule.success_text,
            )
            return

        if rule.failure_text is not None:
            await self._send_interaction_result(
                session=session,
                target_id=session.player_id,
                target_name=session.character_name,
                text=rule.failure_text,
            )

    async def _send_interaction_result(
        self,
        session: PlayerSession,
        target_id: str,
        target_name: str,
        text: str,
        add_to_journal: bool = True,
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
                ),
            ),
        )

    async def _grant_fishing_rod_if_needed(self, session: PlayerSession) -> None:
        """
        Выдает персонажу удочку, если ее еще нет в инвентаре.
        """
        await self._grant_item_if_needed(session, FISHING_ROD_ITEM_ID)

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
