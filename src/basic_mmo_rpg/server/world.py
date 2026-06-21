from __future__ import annotations

import random
from dataclasses import dataclass, field, replace

from basic_mmo_rpg.domain.entities import EntityKind, WorldEntity
from basic_mmo_rpg.domain.geometry import Rect, Vec2
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState, move_player
from basic_mmo_rpg.domain.tiles import TileMap
from basic_mmo_rpg.shared.protocol import EntitySnapshot, PlayerSnapshot, world_snapshot_payload

CREATURE_MOVE_SECONDS = 2.0
CREATURE_COOLDOWN_SECONDS = 2.0
CREATURE_DIRECTIONS = (
    Vec2(0, -1),
    Vec2(0, 1),
    Vec2(-1, 0),
    Vec2(1, 0),
)


@dataclass(slots=True)
class CreatureMotion:
    """
    Хранит runtime-состояние плавного движения creature-сущности.
    """

    entity_id: str
    cooldown_remaining: float = CREATURE_COOLDOWN_SECONDS
    action_remaining: float = 0.0
    action_duration: float = CREATURE_MOVE_SECONDS
    start_position: Vec2 | None = None
    target_position: Vec2 | None = None
    wool_regrow_remaining: float = 0.0


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
    random_source: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        """
        Создает изменяемое runtime-состояние объектов мира из загруженной карты.
        """
        self.entity_states = {entity.entity_id: entity for entity in self.tile_map.entities}
        self.creature_motions = {
            entity.entity_id: CreatureMotion(entity_id=entity.entity_id)
            for entity in self.entity_states.values()
            if entity.kind == EntityKind.CREATURE
        }

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
        if player_id in self.players:
            self.intents[player_id] = intent

    def tick(self, delta_seconds: float) -> None:
        """
        Продвигает authoritative-симуляцию мира на один серверный тик.
        """
        blockers = self.solid_entity_rects()
        for player_id, player in list(self.players.items()):
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

    def solid_entity_rects(self, exclude_entity_id: str | None = None) -> tuple[Rect, ...]:
        """
        Возвращает прямоугольники solid-объектов runtime-мира.
        """
        return tuple(
            entity.rect
            for entity in self.entity_states.values()
            if entity.solid and entity.entity_id != exclude_entity_id
        )

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
        updated = replace(entity, combat=updated_combat, respawn=updated_respawn)
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
            if remaining == 0.0:
                updated_combat = replace(
                    entity.combat,
                    hit_points=entity.combat.max_hit_points,
                    destroyed=False,
                )
            self.entity_states[entity.entity_id] = replace(
                entity,
                combat=updated_combat,
                respawn=updated_respawn,
            )

    def _select_spawn_position(self, preferred_position: Vec2 | None) -> Vec2:
        """
        Выбирает сохраненную позицию или ближайший свободный spawn.
        """
        if preferred_position is not None and self._is_spawn_position_available(preferred_position):
            return preferred_position
        return self._next_spawn_position()

    def _next_spawn_position(self) -> Vec2:
        """
        Находит ближайшую проходимую позицию spawn-а для следующего игрока.
        """
        tile_size = self.tile_map.tile_size
        max_attempts = self.tile_map.width * self.tile_map.height

        for index in range(max_attempts):
            offset = Vec2((index % 6) * tile_size, (index // 6) * tile_size)
            candidate = self.tile_map.spawn + offset
            if self._is_spawn_position_available(candidate):
                return candidate

        return self.tile_map.spawn

    def _is_spawn_position_available(self, position: Vec2) -> bool:
        """
        Проверяет, что позиция spawn-а проходима и не занята другим игроком.
        """
        candidate_rect = PlayerState(entity_id="spawn-check", position=position).rect
        if self.tile_map.is_rect_blocked(candidate_rect, self.solid_entity_rects()):
            return False

        return all(
            not candidate_rect.intersects(existing_player.rect)
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

            if motion.action_remaining > 0:
                self._continue_creature_action(entity, motion, delta_seconds)
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
        motion.cooldown_remaining = CREATURE_COOLDOWN_SECONDS

    def _start_creature_action(self, entity: WorldEntity, motion: CreatureMotion) -> None:
        """
        Выбирает направление creature и начинает движение или ожидание на месте.
        """
        direction = self.random_source.choice(CREATURE_DIRECTIONS)
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
            *self.solid_entity_rects(exclude_entity_id=entity.entity_id),
            *(player.rect for player in self.players.values()),
        )
        return not self.tile_map.is_rect_blocked(target_rect, blockers)

    def _is_gate_reserved_by_creature_motion(self, gate: WorldEntity) -> bool:
        """
        Проверяет, движется ли creature в прямоугольник калитки.
        """
        for motion in self.creature_motions.values():
            if motion.target_position is None:
                continue
            creature = self.entity_states.get(motion.entity_id)
            if creature is None:
                continue
            target_creature = replace(
                creature,
                body=replace(creature.body, position=motion.target_position),
            )
            target_rect = target_creature.rect
            if gate.rect.intersects(target_rect):
                return True
        return False


def _interpolate_position(start: Vec2, target: Vec2, progress: float) -> Vec2:
    """
    Возвращает позицию между начальной и целевой точками.
    """
    clamped_progress = min(1.0, max(0.0, progress))
    return start + (target - start) * clamped_progress
