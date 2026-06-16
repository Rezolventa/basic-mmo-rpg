from __future__ import annotations

from basic_mmo_rpg.client.app import GameClient, RemotePlayerView, _smooth_player_toward
from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.movement import PlayerState


def test_local_authoritative_snapshot_creates_correction_offset() -> None:
    """
    Проверяет, что snapshot локального игрока создает плавную коррекцию prediction-а.
    """
    client = _client_without_pygame(PlayerState(entity_id="p1", position=Vec2(100, 0)))

    client._receive_authoritative_local_player(PlayerState(entity_id="p1", position=Vec2(80, 0)))
    client._reconcile_local_player(0.05)

    assert 80 < client.player.position.x < 100
    assert client.local_correction_offset.length < 20


def test_local_authoritative_snapshot_snaps_large_error() -> None:
    """
    Проверяет, что большая ошибка prediction-а исправляется мгновенным snap-ом.
    """
    client = _client_without_pygame(PlayerState(entity_id="p1", position=Vec2(0, 0)))

    client._receive_authoritative_local_player(PlayerState(entity_id="p1", position=Vec2(200, 0)))

    assert client.player.position == Vec2(200, 0)
    assert client.local_correction_offset == Vec2(0, 0)


def test_remote_player_view_interpolates_to_snapshot_target() -> None:
    """
    Проверяет, что удаленный игрок плавно движется к позиции из server snapshot-а.
    """
    view = RemotePlayerView(
        rendered=PlayerState(entity_id="p2", position=Vec2(0, 0)),
        target=PlayerState(entity_id="p2", position=Vec2(30, 0)),
    )

    view.update(1 / 60)

    assert 0 < view.rendered.position.x < 30


def test_smooth_player_toward_keeps_current_position_without_elapsed_time() -> None:
    """
    Проверяет, что сглаживание не двигает игрока при нулевом delta_seconds.
    """
    current = PlayerState(entity_id="p2", position=Vec2(0, 0))
    target = PlayerState(entity_id="p2", position=Vec2(30, 0))

    smoothed = _smooth_player_toward(
        current=current,
        target=target,
        delta_seconds=0,
        rate=10,
        snap_distance=100,
        dead_zone=0,
    )

    assert smoothed == current


def _client_without_pygame(player: PlayerState) -> GameClient:
    """
    Создает объект клиента для тестирования сетевого сглаживания без pygame-инициализации.
    """
    client = object.__new__(GameClient)
    client.player = player
    client.authoritative_player = None
    client.local_correction_offset = Vec2(0, 0)
    return client
