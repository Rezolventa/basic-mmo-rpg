from __future__ import annotations

import pytest

from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState
from basic_mmo_rpg.shared.protocol import (
    ClientMessageType,
    ProtocolError,
    ProtocolMessage,
    decode_message,
    encode_message,
    movement_intent_from_payload,
    movement_intent_to_payload,
    players_from_snapshot_payload,
    world_snapshot_payload,
)


def test_protocol_message_round_trips_through_json() -> None:
    """
    Проверяет, что протокольное сообщение сериализуется и десериализуется через JSON.
    """
    message = ProtocolMessage(
        type=ClientMessageType.MOVE_REQUESTED,
        payload=movement_intent_to_payload(MovementIntent(right=True)),
    )

    decoded = decode_message(encode_message(message))

    assert decoded == message
    assert movement_intent_from_payload(decoded.payload) == MovementIntent(right=True)


def test_decode_message_rejects_invalid_shape() -> None:
    """
    Проверяет, что протокол отклоняет сообщение без корректной payload-структуры.
    """
    with pytest.raises(ProtocolError):
        decode_message('{"type":"move_requested","payload":[]}')


def test_world_snapshot_payload_round_trips_players() -> None:
    """
    Проверяет, что игроки сериализуются и восстанавливаются из payload snapshot-а.
    """
    player = PlayerState(entity_id="p1", position=Vec2(10, 20), speed=123)

    decoded_players = players_from_snapshot_payload(world_snapshot_payload([player]))

    assert decoded_players == [player]

