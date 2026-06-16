from __future__ import annotations

from dataclasses import dataclass, field

from basic_mmo_rpg.domain.geometry import Rect, Vec2
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState, move_player
from basic_mmo_rpg.domain.tiles import TileMap
from basic_mmo_rpg.shared.protocol import PlayerSnapshot, world_snapshot_payload


@dataclass(slots=True)
class MultiplayerWorld:
    """
    Хранит authoritative-состояние multiplayer-мира и применяет намерения движения игроков.
    """

    tile_map: TileMap
    players: dict[str, PlayerState] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    intents: dict[str, MovementIntent] = field(default_factory=dict)

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
        for player_id, player in list(self.players.items()):
            intent = self.intents.get(player_id, MovementIntent())
            self.players[player_id] = move_player(player, intent, delta_seconds, self.tile_map)

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
        return world_snapshot_payload(snapshots)

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
        if self.tile_map.is_rect_blocked(candidate_rect):
            return False

        return all(
            not _rects_overlap(candidate_rect, existing_player.rect)
            for existing_player in self.players.values()
        )


def _rects_overlap(left: Rect, right: Rect) -> bool:
    """
    Проверяет, пересекаются ли два прямоугольника.
    """
    return (
        left.left < right.right
        and left.right > right.left
        and left.top < right.bottom
        and left.bottom > right.top
    )
