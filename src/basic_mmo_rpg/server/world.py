from __future__ import annotations

from dataclasses import dataclass, field

from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState, move_player
from basic_mmo_rpg.domain.tiles import TileMap
from basic_mmo_rpg.shared.protocol import world_snapshot_payload


@dataclass(slots=True)
class MultiplayerWorld:
    """
    Хранит authoritative-состояние multiplayer-мира и применяет намерения движения игроков.
    """

    tile_map: TileMap
    players: dict[str, PlayerState] = field(default_factory=dict)
    intents: dict[str, MovementIntent] = field(default_factory=dict)

    def add_player(self, player_id: str) -> PlayerState:
        """
        Добавляет нового игрока в мир и возвращает его состояние после spawn-а.
        """
        player = PlayerState(entity_id=player_id, position=self._next_spawn_position())
        self.players[player_id] = player
        self.intents[player_id] = MovementIntent()
        return player

    def remove_player(self, player_id: str) -> None:
        """
        Удаляет игрока и его последнее намерение движения из мира.
        """
        self.players.pop(player_id, None)
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
        return world_snapshot_payload(list(self.players.values()))

    def _next_spawn_position(self) -> Vec2:
        """
        Находит ближайшую проходимую позицию spawn-а для следующего игрока.
        """
        tile_size = self.tile_map.tile_size
        player_count = len(self.players)
        max_attempts = self.tile_map.width * self.tile_map.height

        for index in range(player_count, player_count + max_attempts):
            offset = Vec2((index % 6) * tile_size, (index // 6) * tile_size)
            candidate = self.tile_map.spawn + offset
            candidate_player = PlayerState(entity_id="spawn-check", position=candidate)
            if not self.tile_map.is_rect_blocked(candidate_player.rect):
                return candidate

        return self.tile_map.spawn
