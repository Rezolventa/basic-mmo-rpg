from __future__ import annotations

import random
from dataclasses import dataclass, field, replace

from basic_mmo_rpg.domain.entities import (
    BodyComponent,
    EntityKind,
    IdentityComponent,
    InteractionComponent,
    LootableComponent,
    LootClaimPolicy,
    WorldEntity,
)
from basic_mmo_rpg.domain.geometry import Rect, Vec2
from basic_mmo_rpg.domain.inventory import LEATHER_ITEM_ID
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState, move_player
from basic_mmo_rpg.domain.tiles import TileMap
from basic_mmo_rpg.shared.protocol import EntitySnapshot, PlayerSnapshot, world_snapshot_payload

CREATURE_MOVE_SECONDS = 2.0
CREATURE_COOLDOWN_SECONDS = 2.0
CREATURE_COOLDOWN_JITTER_FRACTION = 0.20
CREATURE_INITIAL_COOLDOWN_MAX_FRACTION = 1.0
CREATURE_CHASE_MOVE_SECONDS = 0.45
CREATURE_RETURN_MOVE_SECONDS = 0.7
CREATURE_LEASH_DISTANCE = 256.0
CORPSE_LIFETIME_SECONDS = 300.0
PLAYER_RESPAWN_ENTITY_ID = "object-player-respawn"
PLAYER_RESPAWN_HEALTH_FRACTION = 0.5
CREATURE_DIRECTIONS = (
    Vec2(0, -1),
    Vec2(0, 1),
    Vec2(-1, 0),
    Vec2(1, 0),
)
CREATURE_WANDER_DIRECTIONS = (*CREATURE_DIRECTIONS, Vec2(0, 0))


@dataclass(slots=True)
class CreatureMotion:
    """
    Хранит runtime-состояние плавного движения creature-сущности.
    """

    entity_id: str
    home_position: Vec2
    cooldown_remaining: float = CREATURE_COOLDOWN_SECONDS
    action_remaining: float = 0.0
    action_duration: float = CREATURE_MOVE_SECONDS
    start_position: Vec2 | None = None
    target_position: Vec2 | None = None
    wool_regrow_remaining: float = 0.0
    aggro_target_id: str | None = None
    returning_home: bool = False


@dataclass(slots=True)
class MultiplayerWorld:
    """
    Хранит authoritative-состояние multiplayer-мира и применяет намерения движения игроков.
    """

    tile_map: TileMap
    players: dict[str, PlayerState] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    intents: dict[str, MovementIntent] = field(default_factory=dict)
    entity_states: dict[str, WorldEntity] = field(init=False)
    creature_motions: dict[str, CreatureMotion] = field(init=False)
    entity_lifetimes: dict[str, float] = field(init=False)
    next_runtime_entity_index: int = field(init=False, default=0)
    random_source: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        """
        Создает изменяемое runtime-состояние объектов мира из загруженной карты.
        """
        self.entity_states = {entity.entity_id: entity for entity in self.tile_map.entities}
        self.creature_motions = {
            entity.entity_id: CreatureMotion(
                entity_id=entity.entity_id,
                home_position=entity.position,
                cooldown_remaining=self._initial_creature_cooldown_seconds(),
            )
            for entity in self.entity_states.values()
            if entity.kind == EntityKind.CREATURE
        }
        self.entity_lifetimes = {}

    @property
    def entities(self) -> tuple[WorldEntity, ...]:
        """
        Возвращает актуальные runtime-объекты мира.
        """
        return tuple(self.entity_states.values())

    def add_player(
        self,
        player_id: str,
        name: str,
        position: Vec2 | None = None,
    ) -> PlayerState:
        """
        Добавляет нового игрока в мир и возвращает его состояние после spawn-а.
        """
        spawn_position = self._select_spawn_position(position)
        player = PlayerState(entity_id=player_id, position=spawn_position)
        self.players[player_id] = player
        self.names[player_id] = name
        self.intents[player_id] = MovementIntent()
        return player

    def add_player_state(
        self,
        player_id: str,
        name: str,
        state: PlayerState,
    ) -> PlayerState:
        """
        Добавляет игрока из runtime-состояния без проверки spawn-позиции.
        """
        player = PlayerState(
            entity_id=player_id,
            position=state.position,
            width=state.width,
            height=state.height,
            speed=state.speed,
            hit_points=state.hit_points,
            max_hit_points=state.max_hit_points,
            busy=state.busy,
            action=state.action,
        )
        self.players[player_id] = player
        self.names[player_id] = name
        self.intents[player_id] = MovementIntent()
        return player

    def remove_player(self, player_id: str) -> None:
        """
        Удаляет игрока и его последнее намерение движения из мира.
        """
        self.players.pop(player_id, None)
        self.names.pop(player_id, None)
        self.intents.pop(player_id, None)

    def set_intent(self, player_id: str, intent: MovementIntent) -> None:
        """
        Сохраняет последнее намерение движения для существующего игрока.
        """
        player = self.players.get(player_id)
        if player is not None and player.can_act:
            self.intents[player_id] = intent

    def tick(self, delta_seconds: float) -> None:
        """
        Продвигает authoritative-симуляцию мира на один серверный тик.
        """
        blockers = self.movement_blocker_rects()
        for player_id, player in list(self.players.items()):
            if not player.can_act:
                self.intents[player_id] = MovementIntent()
                continue
            intent = self.intents.get(player_id, MovementIntent())
            self.players[player_id] = move_player(
                player,
                intent,
                delta_seconds,
                self.tile_map,
                blockers,
            )
        self._tick_creatures(delta_seconds)
        self._tick_respawns(delta_seconds)
        self._tick_entity_lifetimes(delta_seconds)

    def snapshot_payload(self) -> dict[str, object]:
        """
        Возвращает JSON-готовый payload snapshot-а для всех подключенных игроков.
        """
        snapshots = [
            PlayerSnapshot(
                state=player,
                name=self.names.get(player.entity_id, player.entity_id),
            )
            for player in self.players.values()
        ]
        entity_snapshots = [EntitySnapshot(state=entity) for entity in self.entities]
        return world_snapshot_payload(snapshots, entity_snapshots)

    def get_entity(self, entity_id: str) -> WorldEntity | None:
        """
        Возвращает объект мира по id или `None`, если такого объекта нет.
        """
        return self.entity_states.get(entity_id)

    def damage_player(self, player_id: str, amount: int) -> tuple[PlayerState, bool] | None:
        """
        Наносит урон персонажу и возвращает флаг новой смерти.
        """
        if amount <= 0:
            msg = "damage amount must be positive"
            raise ValueError(msg)

        player = self.players.get(player_id)
        if player is None or not player.is_alive:
            return None

        next_hit_points = max(0, player.hit_points - amount)
        killed = next_hit_points == 0
        updated = replace(
            player,
            hit_points=next_hit_points,
            busy=False if killed else player.busy,
            action=None if killed else player.action,
        )
        self.players[player_id] = updated
        if killed:
            self.intents[player_id] = MovementIntent()
        return updated, killed

    def respawn_player(self, player_id: str) -> PlayerState | None:
        """
        Возрождает мертвого персонажа у runtime-точки респауна.
        """
        player = self.players.get(player_id)
        if player is None or player.is_alive:
            return None

        hit_points = max(1, int(player.max_hit_points * PLAYER_RESPAWN_HEALTH_FRACTION))
        updated = replace(
            player,
            position=self.player_respawn_position(),
            hit_points=hit_points,
            busy=False,
            action=None,
        )
        self.players[player_id] = updated
        self.intents[player_id] = MovementIntent()
        return updated

    def set_player_action(self, player_id: str, action: str) -> PlayerState | None:
        """
        Помечает персонажа занятым выполнением server-authoritative действия.
        """
        player = self.players.get(player_id)
        if player is None or not player.is_alive:
            return None
        updated = replace(player, busy=True, action=action)
        self.players[player_id] = updated
        self.intents[player_id] = MovementIntent()
        return updated

    def clear_player_action(self, player_id: str) -> PlayerState | None:
        """
        Снимает занятость персонажа, если он все еще находится в мире.
        """
        player = self.players.get(player_id)
        if player is None:
            return None
        updated = replace(player, busy=False, action=None)
        self.players[player_id] = updated
        self.intents[player_id] = MovementIntent()
        return updated

    def set_player_speed(self, player_id: str, speed: float) -> PlayerState | None:
        """
        Меняет runtime-скорость текущего персонажа для ручного тестирования.
        """
        player = self.players.get(player_id)
        if player is None:
            return None
        updated = replace(player, speed=speed)
        self.players[player_id] = updated
        return updated

    def player_respawn_position(self) -> Vec2:
        """
        Возвращает позицию креста возрождения или базовый spawn карты.
        """
        entity = self.entity_states.get(PLAYER_RESPAWN_ENTITY_ID)
        if entity is not None and entity.visible:
            return entity.position
        return self.tile_map.spawn

    def aggro_creature(self, entity_id: str, player_id: str) -> None:
        """
        Переводит creature-сущность в преследование указанного персонажа.
        """
        motion = self.creature_motions.get(entity_id)
        entity = self.entity_states.get(entity_id)
        player = self.players.get(player_id)
        if motion is None or entity is None or player is None:
            return
        if not entity.visible or not entity.is_attackable or not player.is_alive:
            return
        motion.aggro_target_id = player_id
        motion.returning_home = False

    def clear_creature_aggro(self, entity_id: str, return_home: bool = True) -> None:
        """
        Сбрасывает боевую цель creature-сущности.
        """
        motion = self.creature_motions.get(entity_id)
        if motion is None:
            return
        motion.aggro_target_id = None
        motion.returning_home = return_home

    def creature_target_player_id(self, entity_id: str) -> str | None:
        """
        Возвращает текущую цель creature-сущности.
        """
        motion = self.creature_motions.get(entity_id)
        if motion is None:
            return None
        return motion.aggro_target_id

    def clear_entity_lootable(self, entity_id: str) -> None:
        """
        Убирает lootable-компонент у runtime-объекта после выдачи добычи.
        """
        entity = self.entity_states.get(entity_id)
        if entity is not None:
            self.entity_states[entity_id] = replace(entity, lootable=None)

    def solid_entity_rects(self, exclude_entity_id: str | None = None) -> tuple[Rect, ...]:
        """
        Возвращает прямоугольники solid-объектов runtime-мира.
        """
        return tuple(
            entity.rect
            for entity in self.entity_states.values()
            if entity.visible and entity.solid and entity.entity_id != exclude_entity_id
        )

    def movement_blocker_rects(self, exclude_entity_id: str | None = None) -> tuple[Rect, ...]:
        """
        Возвращает текущие и зарезервированные прямоугольники, блокирующие движение.
        """
        return (
            *self.solid_entity_rects(exclude_entity_id=exclude_entity_id),
            *self.creature_reserved_rects(exclude_entity_id=exclude_entity_id),
        )

    def creature_reserved_rects(self, exclude_entity_id: str | None = None) -> tuple[Rect, ...]:
        """
        Возвращает целевые прямоугольники creature-сущностей, уже начавших шаг.
        """
        reserved: list[Rect] = []
        for motion in self.creature_motions.values():
            if motion.entity_id == exclude_entity_id or motion.target_position is None:
                continue
            entity = self.entity_states.get(motion.entity_id)
            if entity is None or not entity.visible or not entity.solid:
                continue
            reserved_entity = replace(
                entity,
                body=replace(entity.body, position=motion.target_position),
            )
            reserved.append(reserved_entity.rect)
        return tuple(reserved)

    def toggle_gate(self, entity_id: str) -> WorldEntity | None:
        """
        Переключает runtime-состояние калитки и возвращает обновленную сущность.
        """
        entity = self.entity_states.get(entity_id)
        if entity is None or entity.gate is None:
            return None

        if entity.is_open and self.is_gate_occupied(entity_id):
            return None

        is_open = not bool(entity.is_open)
        updated = replace(
            entity,
            body=replace(entity.body, solid=not is_open),
            gate=replace(entity.gate, is_open=is_open),
        )
        self.entity_states[entity_id] = updated
        return updated

    def is_gate_occupied(self, entity_id: str) -> bool:
        """
        Проверяет, пересекается ли калитка с игроком или другой solid-сущностью.
        """
        entity = self.entity_states.get(entity_id)
        if entity is None or entity.gate is None:
            return False

        blockers = (
            *self.solid_entity_rects(exclude_entity_id=entity.entity_id),
            *(player.rect for player in self.players.values()),
        )
        if any(entity.rect.intersects(blocker) for blocker in blockers):
            return True
        return self._is_gate_reserved_by_creature_motion(entity)

    def mark_creature_sheared(
        self,
        entity_id: str,
        wool_regrow_seconds: float,
    ) -> WorldEntity | None:
        """
        Снимает шерсть с creature-сущности и запускает таймер отрастания.
        """
        entity = self.entity_states.get(entity_id)
        if entity is None or entity.kind != EntityKind.CREATURE or entity.shearable is None:
            return None
        if entity.shearable.has_wool is not True:
            return None

        updated = replace(entity, shearable=replace(entity.shearable, has_wool=False))
        self.entity_states[entity_id] = updated
        motion = self.creature_motions.get(entity_id)
        if motion is not None:
            motion.wool_regrow_remaining = wool_regrow_seconds
        return updated

    def damage_entity(self, entity_id: str, amount: int) -> tuple[WorldEntity, bool] | None:
        """
        Наносит урон combat-компоненту объекта и возвращает флаг нового разрушения.
        """
        if amount <= 0:
            msg = "damage amount must be positive"
            raise ValueError(msg)

        entity = self.entity_states.get(entity_id)
        if entity is None or entity.combat is None or entity.combat.destroyed:
            return None

        next_hit_points = max(0, entity.combat.hit_points - amount)
        destroyed = next_hit_points == 0
        updated_combat = replace(
            entity.combat,
            hit_points=next_hit_points,
            destroyed=destroyed,
        )
        updated_respawn = entity.respawn
        if destroyed and entity.respawn is not None:
            updated_respawn = replace(entity.respawn, remaining=entity.respawn.seconds)
        updated_body = entity.body
        if destroyed and entity.kind == EntityKind.CREATURE and entity.respawn is not None:
            updated_body = replace(entity.body, solid=False, visible=False)
            self._spawn_corpse_for(entity)
            self.clear_creature_aggro(entity.entity_id, return_home=False)
        updated = replace(
            entity,
            body=updated_body,
            combat=updated_combat,
            respawn=updated_respawn,
        )
        self.entity_states[entity_id] = updated
        return updated, destroyed

    def _tick_respawns(self, delta_seconds: float) -> None:
        """
        Обновляет таймеры восстановления destructible-объектов мира.
        """
        if delta_seconds <= 0:
            return

        for entity in list(self.entity_states.values()):
            if entity.respawn is None or entity.combat is None:
                continue
            if entity.respawn.remaining <= 0:
                continue

            remaining = max(0.0, entity.respawn.remaining - delta_seconds)
            updated_respawn = replace(entity.respawn, remaining=remaining)
            updated_combat = entity.combat
            updated_body = entity.body
            if remaining == 0.0:
                updated_combat = replace(
                    entity.combat,
                    hit_points=entity.combat.max_hit_points,
                    destroyed=False,
                )
                if entity.kind == EntityKind.CREATURE:
                    motion = self.creature_motions.get(entity.entity_id)
                    respawn_position = (
                        motion.home_position if motion is not None else entity.position
                    )
                    updated_body = replace(
                        entity.body,
                        position=respawn_position,
                        solid=True,
                        visible=True,
                    )
                    if motion is not None:
                        motion.aggro_target_id = None
                        motion.returning_home = False
                        motion.action_remaining = 0.0
                        motion.start_position = None
                        motion.target_position = None
                        motion.cooldown_remaining = self._creature_cooldown_seconds()
            self.entity_states[entity.entity_id] = replace(
                entity,
                body=updated_body,
                combat=updated_combat,
                respawn=updated_respawn,
            )

    def _tick_entity_lifetimes(self, delta_seconds: float) -> None:
        """
        Удаляет временные runtime-объекты мира после истечения их жизни.
        """
        if delta_seconds <= 0:
            return

        for entity_id, remaining in list(self.entity_lifetimes.items()):
            remaining = max(0.0, remaining - delta_seconds)
            if remaining > 0:
                self.entity_lifetimes[entity_id] = remaining
                continue
            self.entity_lifetimes.pop(entity_id, None)
            self.entity_states.pop(entity_id, None)

    def _spawn_corpse_for(self, entity: WorldEntity) -> WorldEntity:
        """
        Создает временный проходимый труп creature-сущности.
        """
        self.next_runtime_entity_index += 1
        corpse_id = f"corpse-{entity.entity_id}-{self.next_runtime_entity_index}"
        corpse_name = "Труп кабана" if entity.base_name == "Кабан" else f"Труп {entity.base_name}"
        lootable = None
        if entity.visual == "boar":
            lootable = LootableComponent(
                reward_item_id=LEATHER_ITEM_ID,
                reward_quantity=2,
                success_text="Вы забрали Кожа x2",
                claim_policy=LootClaimPolicy.RUNTIME_ONCE,
            )
        corpse = WorldEntity(
            entity_id=corpse_id,
            identity=IdentityComponent(
                kind=EntityKind.OBJECT,
                name=corpse_name,
                visual="boar_corpse" if entity.visual == "boar" else "corpse",
            ),
            body=BodyComponent(
                position=entity.position,
                width=entity.width,
                height=entity.height,
                solid=False,
                visible=True,
            ),
            interaction=InteractionComponent(radius=64.0, dialogue=""),
            lootable=lootable,
        )
        self.entity_states[corpse_id] = corpse
        self.entity_lifetimes[corpse_id] = CORPSE_LIFETIME_SECONDS
        return corpse

    def _select_spawn_position(self, preferred_position: Vec2 | None) -> Vec2:
        """
        Выбирает сохраненную позицию или ближайший свободный spawn.
        """
        if preferred_position is not None and self._is_spawn_position_available(preferred_position):
            return preferred_position
        if preferred_position is not None:
            nearby_position = self._nearest_available_position(preferred_position)
            if nearby_position is not None:
                return nearby_position
        return self._next_spawn_position()

    def _next_spawn_position(self) -> Vec2:
        """
        Находит ближайшую проходимую позицию spawn-а для следующего игрока.
        """
        nearby_position = self._nearest_available_position(self.tile_map.spawn)
        if nearby_position is not None:
            return nearby_position
        return self.tile_map.spawn

    def _nearest_available_position(self, origin: Vec2) -> Vec2 | None:
        """
        Ищет свободную позицию рядом с указанной точкой, сохраняя локальность spawn-а.
        """
        tile_size = self.tile_map.tile_size
        max_radius = max(self.tile_map.width, self.tile_map.height)

        for radius in range(0, max_radius + 1):
            for offset_x, offset_y in _spawn_offsets_at_radius(radius):
                offset = Vec2(offset_x * tile_size, offset_y * tile_size)
                candidate = origin + offset
                if self._is_spawn_position_available(candidate):
                    return candidate

        return None

    def _is_spawn_position_available(self, position: Vec2) -> bool:
        """
        Проверяет, что позиция spawn-а проходима и не занята другим игроком.
        """
        candidate_rect = PlayerState(entity_id="spawn-check", position=position).rect
        if self.tile_map.is_rect_blocked(candidate_rect, self.solid_entity_rects()):
            return False

        return all(
            not existing_player.is_alive or not candidate_rect.intersects(existing_player.rect)
            for existing_player in self.players.values()
        )

    def _tick_creatures(self, delta_seconds: float) -> None:
        """
        Продвигает движение и отрастание шерсти у creature-сущностей.
        """
        if delta_seconds <= 0:
            return

        for motion in self.creature_motions.values():
            self._tick_creature_wool(motion, delta_seconds)
            entity = self.entity_states.get(motion.entity_id)
            if entity is None:
                continue
            if not entity.visible or entity.is_destroyed:
                continue

            if motion.action_remaining > 0:
                self._continue_creature_action(entity, motion, delta_seconds)
                continue

            if (
                motion.aggro_target_id is None
                and not motion.returning_home
                and self._is_creature_outside_home_leash(entity, motion)
            ):
                motion.returning_home = True

            if motion.aggro_target_id is not None:
                if self._should_leash_creature(entity, motion):
                    self.clear_creature_aggro(entity.entity_id, return_home=True)
                else:
                    self._start_creature_chase_action(entity, motion)
                    continue

            if motion.returning_home:
                if self._is_creature_at_home(entity, motion):
                    motion.returning_home = False
                else:
                    self._start_creature_return_action(entity, motion)
                    continue

            if motion.cooldown_remaining > 0:
                motion.cooldown_remaining = max(0.0, motion.cooldown_remaining - delta_seconds)
                if motion.cooldown_remaining > 0:
                    continue

            self._start_creature_action(entity, motion)

    def _tick_creature_wool(self, motion: CreatureMotion, delta_seconds: float) -> None:
        """
        Обновляет таймер отрастания шерсти у creature-сущности.
        """
        if motion.wool_regrow_remaining <= 0:
            return

        motion.wool_regrow_remaining = max(0.0, motion.wool_regrow_remaining - delta_seconds)
        if motion.wool_regrow_remaining > 0:
            return

        entity = self.entity_states.get(motion.entity_id)
        if (
            entity is not None
            and entity.kind == EntityKind.CREATURE
            and entity.shearable is not None
        ):
            self.entity_states[motion.entity_id] = replace(
                entity,
                shearable=replace(entity.shearable, has_wool=True),
            )

    def _continue_creature_action(
        self,
        entity: WorldEntity,
        motion: CreatureMotion,
        delta_seconds: float,
    ) -> None:
        """
        Продолжает плавное движение creature или ожидание после заблокированной попытки.
        """
        motion.action_remaining = max(0.0, motion.action_remaining - delta_seconds)
        if motion.target_position is not None and motion.start_position is not None:
            progress = 1.0 - motion.action_remaining / motion.action_duration
            position = _interpolate_position(
                motion.start_position,
                motion.target_position,
                progress,
            )
            self.entity_states[entity.entity_id] = replace(
                entity,
                body=replace(entity.body, position=position),
            )

        if motion.action_remaining > 0:
            return

        if motion.target_position is not None:
            updated = self.entity_states[entity.entity_id]
            self.entity_states[entity.entity_id] = replace(
                updated,
                body=replace(updated.body, position=motion.target_position),
            )
        motion.start_position = None
        motion.target_position = None
        motion.cooldown_remaining = (
            0.0
            if motion.aggro_target_id is not None or motion.returning_home
            else self._creature_cooldown_seconds()
        )

    def _start_creature_action(self, entity: WorldEntity, motion: CreatureMotion) -> None:
        """
        Выбирает направление creature и начинает движение или ожидание на месте.
        """
        direction = self.random_source.choice(CREATURE_WANDER_DIRECTIONS)
        tile_size = self.tile_map.tile_size
        target_position = entity.position + Vec2(direction.x * tile_size, direction.y * tile_size)
        if self._is_creature_target_available(entity, target_position):
            motion.start_position = entity.position
            motion.target_position = target_position
        else:
            motion.start_position = None
            motion.target_position = None
        motion.action_duration = CREATURE_MOVE_SECONDS
        motion.action_remaining = CREATURE_MOVE_SECONDS

    def _start_creature_chase_action(
        self,
        entity: WorldEntity,
        motion: CreatureMotion,
    ) -> None:
        """
        Начинает короткий шаг creature-сущности к текущей боевой цели.
        """
        if motion.aggro_target_id is None:
            return
        target = self.players.get(motion.aggro_target_id)
        if target is None or not target.is_alive:
            self.clear_creature_aggro(entity.entity_id, return_home=True)
            return
        if entity.combat is not None:
            distance = (entity.center - target.center).length
            if distance <= entity.combat.attack_distance * 0.9:
                return
        self._start_creature_step_toward(
            entity=entity,
            motion=motion,
            destination=target.position,
            duration=CREATURE_CHASE_MOVE_SECONDS,
        )

    def _start_creature_return_action(
        self,
        entity: WorldEntity,
        motion: CreatureMotion,
    ) -> None:
        """
        Начинает шаг creature-сущности обратно к домашней точке.
        """
        self._start_creature_step_toward(
            entity=entity,
            motion=motion,
            destination=motion.home_position,
            duration=CREATURE_RETURN_MOVE_SECONDS,
        )

    def _start_creature_step_toward(
        self,
        entity: WorldEntity,
        motion: CreatureMotion,
        destination: Vec2,
        duration: float,
    ) -> None:
        """
        Выбирает соседний тайл в сторону цели и запускает плавное перемещение.
        """
        tile_size = self.tile_map.tile_size
        for direction in _directions_toward(entity.position, destination):
            target_position = entity.position + Vec2(
                direction.x * tile_size,
                direction.y * tile_size,
            )
            if self._is_creature_target_available(entity, target_position):
                motion.start_position = entity.position
                motion.target_position = target_position
                break
        else:
            motion.start_position = None
            motion.target_position = None
        motion.action_duration = duration
        motion.action_remaining = duration

    def _creature_cooldown_seconds(self) -> float:
        """
        Возвращает базовый cooldown creature с небольшим случайным рассинхроном.
        """
        jitter = self.random_source.random() * CREATURE_COOLDOWN_JITTER_FRACTION
        return CREATURE_COOLDOWN_SECONDS * (1.0 + jitter)

    def _initial_creature_cooldown_seconds(self) -> float:
        """
        Возвращает стартовую задержку creature, чтобы сущности не начинали шаг синхронно.
        """
        return (
            CREATURE_COOLDOWN_SECONDS
            * self.random_source.random()
            * CREATURE_INITIAL_COOLDOWN_MAX_FRACTION
        )

    def _is_creature_at_home(self, entity: WorldEntity, motion: CreatureMotion) -> bool:
        """
        Проверяет, вернулась ли creature-сущность к домашней точке.
        """
        return (entity.position - motion.home_position).length < 1.0

    def _should_leash_creature(self, entity: WorldEntity, motion: CreatureMotion) -> bool:
        """
        Проверяет, должна ли creature-сущность сбросить агро по leash-радиусу.
        """
        if motion.aggro_target_id is None:
            return False
        target = self.players.get(motion.aggro_target_id)
        if target is None or not target.is_alive:
            return True
        return (
            self._is_creature_outside_home_leash(entity, motion)
            or self._is_position_outside_home_leash(target.center, entity, motion)
        )

    def _is_creature_outside_home_leash(
        self,
        entity: WorldEntity,
        motion: CreatureMotion,
    ) -> bool:
        """
        Проверяет, вышла ли creature-сущность за домашний leash-радиус.
        """
        return self._is_position_outside_home_leash(entity.center, entity, motion)

    def _is_position_outside_home_leash(
        self,
        position: Vec2,
        entity: WorldEntity,
        motion: CreatureMotion,
    ) -> bool:
        """
        Проверяет, находится ли позиция за leash-радиусом от дома creature-сущности.
        """
        home_center = Rect(
            motion.home_position.x,
            motion.home_position.y,
            entity.width,
            entity.height,
        ).center
        return (position - home_center).length > CREATURE_LEASH_DISTANCE

    def _is_creature_target_available(
        self,
        entity: WorldEntity,
        target_position: Vec2,
    ) -> bool:
        """
        Проверяет, может ли creature занять целевую позицию.
        """
        target_entity = replace(entity, body=replace(entity.body, position=target_position))
        target_rect = target_entity.rect
        blockers = (
            *self.movement_blocker_rects(exclude_entity_id=entity.entity_id),
            *(player.rect for player in self.players.values() if player.is_alive),
        )
        return not self.tile_map.is_rect_blocked(target_rect, blockers)

    def _is_gate_reserved_by_creature_motion(self, gate: WorldEntity) -> bool:
        """
        Проверяет, движется ли creature в прямоугольник калитки.
        """
        for target_rect in self.creature_reserved_rects():
            if gate.rect.intersects(target_rect):
                return True
        return False


def _interpolate_position(start: Vec2, target: Vec2, progress: float) -> Vec2:
    """
    Возвращает позицию между начальной и целевой точками.
    """
    clamped_progress = min(1.0, max(0.0, progress))
    return start + (target - start) * clamped_progress


def _directions_toward(start: Vec2, target: Vec2) -> tuple[Vec2, ...]:
    """
    Возвращает соседние направления, упорядоченные по близости к цели.
    """
    delta = target - start
    horizontal = Vec2(1 if delta.x > 0 else -1, 0) if delta.x != 0 else None
    vertical = Vec2(0, 1 if delta.y > 0 else -1) if delta.y != 0 else None
    fallback = tuple(direction for direction in CREATURE_DIRECTIONS)
    if horizontal is None and vertical is None:
        return fallback
    if horizontal is None:
        return (vertical, *fallback) if vertical is not None else fallback
    if vertical is None:
        return (horizontal, *fallback)
    if abs(delta.x) >= abs(delta.y):
        return (horizontal, vertical, *fallback)
    return (vertical, horizontal, *fallback)


def _spawn_offsets_at_radius(radius: int) -> tuple[tuple[int, int], ...]:
    """
    Возвращает смещения на квадратном кольце, начиная с ближайших к центру.
    """
    offsets = [
        (offset_x, offset_y)
        for offset_y in range(-radius, radius + 1)
        for offset_x in range(-radius, radius + 1)
        if max(abs(offset_x), abs(offset_y)) == radius
    ]
    return tuple(
        sorted(
            offsets,
            key=lambda offset: (
                offset[0] * offset[0] + offset[1] * offset[1],
                abs(offset[1]),
                abs(offset[0]),
                offset[1],
                offset[0],
            ),
        )
    )
