from __future__ import annotations

import pytest

from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.movement import MovementIntent, PlayerState
from basic_mmo_rpg.shared.protocol import (
    ClientMessageType,
    PlayerSnapshot,
    ProtocolError,
    ProtocolMessage,
    character_name_from_payload,
    chat_text_from_payload,
    decode_message,
    encode_message,
    join_request_payload,
    movement_intent_from_payload,
    movement_intent_to_payload,
    player_snapshots_from_payload,
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
    snapshot = PlayerSnapshot(state=player, name="Alice")

    payload = world_snapshot_payload([snapshot])
    decoded_players = players_from_snapshot_payload(payload)
    decoded_snapshots = player_snapshots_from_payload(payload)

    assert decoded_players == [player]
    assert decoded_snapshots == [snapshot]


def test_character_name_payload_is_trimmed_and_limited() -> None:
    """
    Проверяет нормализацию имени персонажа и базовые ограничения протокола входа.
    """
    assert character_name_from_payload(join_request_payload(" Alice ")) == "Alice"

    with pytest.raises(ProtocolError):
        character_name_from_payload(join_request_payload(""))
    with pytest.raises(ProtocolError):
        character_name_from_payload(join_request_payload("A" * 25))


def test_chat_text_payload_is_trimmed_and_limited() -> None:
    """
    Проверяет нормализацию текста чата и базовые ограничения длины.
    """
    assert chat_text_from_payload({"text": " Привет "}) == "Привет"

    with pytest.raises(ProtocolError):
        chat_text_from_payload({"text": ""})
    with pytest.raises(ProtocolError):
        chat_text_from_payload({"text": "A" * 161})
