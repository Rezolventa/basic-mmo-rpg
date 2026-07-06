from __future__ import annotations

import random
from dataclasses import replace

from basic_mmo_rpg.domain.geometry import Vec2
from basic_mmo_rpg.domain.inventory import LEATHER_ITEM_ID
from basic_mmo_rpg.domain.movement import MovementIntent
from basic_mmo_rpg.server.world import MultiplayerWorld
from basic_mmo_rpg.shared.protocol import (
    entities_from_snapshot_payload,
    players_from_snapshot_payload,
)
from basic_mmo_rpg.storage.map_loader import tile_map_from_dict


def _open_map() -> object:
    """
    Возвращает небольшую открытую карту для тестирования серверного мира.
    """
    return {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            "......",
            "......",
            "......",
            "......",
        ],
    }


def _open_map_with_gate_and_sheep() -> object:
    """
    Возвращает карту с калиткой и овцой для тестов runtime-сущностей.
    """
    return {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            ".....",
            ".....",
            ".....",
            ".....",
        ],
        "entities": [
            {
                "id": "gate-sheep-pen",
                "kind": "gate",
                "name": "Калитка",
                "position": [64, 32],
                "size": [32, 32],
                "interaction_radius": 64,
                "solid": True,
                "is_open": False,
            },
            {
                "id": "creature-barbara",
                "kind": "creature",
                "name": "Овца",
                "position": [34, 66],
                "size": [20, 20],
                "interaction_radius": 64,
                "solid": True,
                "hit_points": 15,
                "max_hit_points": 15,
                "has_wool": True,
            },
        ],
    }


def _wide_open_map_with_sheep() -> object:
    """
    Возвращает широкую карту с овцой для тестов leash-возврата.
    """
    return {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            "................",
            "................",
            "................",
            "................",
        ],
        "entities": [
            {
                "id": "creature-barbara",
                "kind": "creature",
                "name": "Овца",
                "position": [34, 66],
                "size": [20, 20],
                "interaction_radius": 64,
                "solid": True,
                "hit_points": 15,
                "max_hit_points": 15,
                "has_wool": True,
            },
        ],
    }


def _open_map_with_gate_in_sheep_path() -> object:
    """
    Возвращает карту, где открытая калитка стоит в выбранном пути овцы.
    """
    return {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            ".....",
            ".....",
            ".....",
            ".....",
        ],
        "entities": [
            {
                "id": "gate-sheep-pen",
                "kind": "gate",
                "name": "Калитка",
                "position": [64, 64],
                "size": [32, 32],
                "interaction_radius": 64,
                "solid": True,
                "is_open": False,
            },
            {
                "id": "creature-barbara",
                "kind": "creature",
                "name": "Овца",
                "position": [34, 66],
                "size": [20, 20],
                "interaction_radius": 64,
                "solid": True,
                "hit_points": 15,
                "max_hit_points": 15,
                "has_wool": True,
            },
        ],
    }


def _open_map_with_training_dummy() -> object:
    """
    Возвращает карту с attackable-манекеном для тестов combat-runtime.
    """
    return {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            ".....",
            ".....",
            ".....",
            ".....",
        ],
        "entities": [
            {
                "id": "lootable-training-dummy",
                "components": {
                    "identity": {
                        "kind": "object",
                        "name": "Тренировочный манекен",
                        "destroyed_name": "Разрушенный тренировочный манекен",
                        "visual": "training_dummy",
                    },
                    "body": {
                        "position": [64, 32],
                        "size": [24, 34],
                        "solid": True,
                    },
                    "combat": {
                        "hit_points": 20,
                        "max_hit_points": 20,
                        "attackable": True,
                        "destroyed": False,
                    },
                    "respawn": {
                        "seconds": 10,
                    },
                },
            }
        ],
    }


def _open_map_with_boar_and_respawn_cross() -> object:
    """
    Возвращает карту с кабаном и точкой возрождения для combat-runtime тестов.
    """
    return {
        "tile_size": 32,
        "spawn": [32, 32],
        "legend": {
            ".": {"name": "floor", "solid": False, "color": [50, 120, 60]},
            "#": {"name": "wall", "solid": True, "color": [90, 90, 90]},
        },
        "tiles": [
            "......",
            "......",
            "......",
            "......",
        ],
        "entities": [
            {
                "id": "object-player-respawn",
                "components": {
                    "identity": {
                        "kind": "object",
                        "name": "Крест возрождения",
                        "visual": "respawn_cross",
                    },
                    "body": {
                        "position": [96, 32],
                        "size": [28, 28],
                        "solid": False,
                    },
                },
            },
            {
                "id": "creature-boar",
                "components": {
                    "identity": {
                        "kind": "creature",
                        "name": "Кабан",
                        "visual": "boar",
                    },
                    "body": {
                        "position": [64, 32],
                        "size": [24, 22],
                        "solid": True,
                    },
                    "combat": {
                        "hit_points": 18,
                        "max_hit_points": 18,
                        "attackable": True,
                        "destroyed": False,
                        "min_damage": 2,
                        "max_damage": 4,
                        "hit_chance": 0.75,
                        "attack_distance": 64,
                        "swing_cooldown_seconds": 1.6,
                    },
                    "respawn": {
                        "seconds": 60,
                    },
                },
            },
        ],
    }


def test_world_spawns_players_and_returns_snapshot() -> None:
    """
    Проверяет, что серверный мир добавляет игроков и отдает их в snapshot-е.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))

    first = world.add_player("p1", "Alice")
    second = world.add_player("p2", "Bob")
    players = players_from_snapshot_payload(world.snapshot_payload())

    assert first.entity_id == "p1"
    assert second.entity_id == "p2"
    assert first.position == world.tile_map.spawn
    assert {player.entity_id for player in players} == {"p1", "p2"}


def test_world_applies_latest_movement_intent_on_tick() -> None:
    """
    Проверяет, что серверный мир двигает игрока по последнему intent-у.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))
    player = world.add_player("p1", "Alice")

    world.set_intent("p1", MovementIntent(right=True))
    world.tick(0.5)

    assert world.players["p1"].position.x > player.position.x
    assert world.players["p1"].position.y == player.position.y


def test_world_removes_player_and_ignores_missing_intent() -> None:
    """
    Проверяет, что удаленный игрок исчезает и больше не принимает intent-ы.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))
    world.add_player("p1", "Alice")

    world.remove_player("p1")
    world.set_intent("p1", MovementIntent(right=True))
    world.tick(0.5)

    assert world.players == {}


def test_world_updates_player_runtime_speed() -> None:
    """
    Проверяет ручное runtime-изменение скорости персонажа.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))
    world.add_player("p1", "Alice")

    updated = world.set_player_speed("p1", 220.0)

    assert updated is not None
    assert updated.speed == 220.0
    assert world.players["p1"].speed == 220.0
    assert world.set_player_speed("missing", 220.0) is None


def test_world_reuses_only_unoccupied_spawn_positions() -> None:
    """
    Проверяет, что новый игрок не появляется поверх оставшегося игрока после disconnect-а.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))

    first = world.add_player("p1", "Alice")
    second = world.add_player("p2", "Bob")
    world.remove_player("p1")
    third = world.add_player("p3", "Cara")

    assert first.position == third.position
    assert third.position != second.position


def test_world_uses_nearby_position_when_saved_position_is_occupied() -> None:
    """
    Проверяет, что занятая сохраненная позиция не сбрасывает игрока к общему spawn-у.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map()))
    saved_position = Vec2(128, 64)

    first = world.add_player("p1", "Alice", position=saved_position)
    second = world.add_player("p2", "Bob", position=saved_position)

    assert first.position == saved_position
    assert second.position != saved_position
    assert second.position != world.tile_map.spawn
    assert (second.position - saved_position).length <= world.tile_map.tile_size


def test_world_toggles_gate_collision_state() -> None:
    """
    Проверяет, что открытая калитка перестает быть solid-сущностью.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map_with_gate_and_sheep()))

    closed_gate = world.get_entity("gate-sheep-pen")
    opened_gate = world.toggle_gate("gate-sheep-pen")
    closed_again = world.toggle_gate("gate-sheep-pen")

    assert closed_gate is not None
    assert opened_gate is not None
    assert closed_again is not None
    assert closed_gate.solid is True
    assert opened_gate.solid is False
    assert opened_gate.is_open is True
    assert closed_again.solid is True
    assert closed_again.is_open is False


def test_world_treats_gate_as_occupied_by_creature_pending_target() -> None:
    """
    Проверяет, что калитку нельзя закрыть перед уже движущейся в нее овцой.
    """
    world = MultiplayerWorld(
        tile_map=tile_map_from_dict(_open_map_with_gate_in_sheep_path()),
        random_source=random.Random(0),
    )
    opened_gate = world.toggle_gate("gate-sheep-pen")
    assert opened_gate is not None

    world.tick(2.0)
    world.tick(0.1)
    gate = world.get_entity("gate-sheep-pen")
    moving_sheep = world.get_entity("creature-barbara")

    assert gate is not None
    assert moving_sheep is not None
    assert gate.rect.intersects(moving_sheep.rect) is False
    assert world.is_gate_occupied("gate-sheep-pen") is True
    assert world.toggle_gate("gate-sheep-pen") is None
    assert world.get_entity("gate-sheep-pen") == opened_gate


def test_world_blocks_player_from_creature_reserved_target() -> None:
    """
    Проверяет, что игрок не может войти в тайл, куда creature уже начала движение.
    """
    world = MultiplayerWorld(
        tile_map=tile_map_from_dict(_open_map_with_gate_and_sheep()),
        random_source=random.Random(0),
    )
    player = world.add_player("p1", "Alice", position=Vec2(66, 32))

    world.tick(2.0)
    reserved_targets = world.creature_reserved_rects()
    world.set_intent("p1", MovementIntent(down=True))
    world.tick(0.2)

    assert len(reserved_targets) == 1
    assert world.players["p1"].position == player.position


def test_world_moves_creature_smoothly_between_tiles() -> None:
    """
    Проверяет, что овца плавно проходит к свободному соседнему тайлу.
    """
    world = MultiplayerWorld(
        tile_map=tile_map_from_dict(_open_map_with_gate_and_sheep()),
        random_source=random.Random(0),
    )
    sheep = world.get_entity("creature-barbara")
    assert sheep is not None

    world.tick(2.0)
    world.tick(1.0)
    halfway_sheep = world.get_entity("creature-barbara")
    world.tick(1.0)
    moved_sheep = world.get_entity("creature-barbara")

    assert halfway_sheep is not None
    assert moved_sheep is not None
    assert halfway_sheep.position == Vec2(sheep.position.x + 16, sheep.position.y)
    assert moved_sheep.position == Vec2(sheep.position.x + 32, sheep.position.y)


def test_world_returns_neutral_creature_after_leash_distance() -> None:
    """
    Проверяет, что neutral creature возвращается домой, если ушла за leash-радиус.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_wide_open_map_with_sheep()))
    sheep = world.get_entity("creature-barbara")
    assert sheep is not None
    far_position = Vec2(sheep.position.x + 320, sheep.position.y)
    world.entity_states[sheep.entity_id] = replace(
        sheep,
        body=replace(sheep.body, position=far_position),
    )
    motion = world.creature_motions[sheep.entity_id]

    world.tick(0.1)
    expected_step = Vec2(far_position.x - world.tile_map.tile_size, far_position.y)
    reserved_step = motion.target_position
    world.tick(0.7)
    returned_sheep = world.get_entity("creature-barbara")

    assert motion.aggro_target_id is None
    assert reserved_step == expected_step
    assert returned_sheep is not None
    assert returned_sheep.position == expected_step


def test_world_keeps_creature_in_place_when_target_is_blocked() -> None:
    """
    Проверяет, что овца ждет на месте, если выбранный тайл занят.
    """
    world = MultiplayerWorld(
        tile_map=tile_map_from_dict(_open_map_with_gate_and_sheep()),
        random_source=random.Random(0),
    )
    sheep = world.get_entity("creature-barbara")
    assert sheep is not None
    world.add_player("p1", "Alice", position=Vec2(sheep.position.x + 32, sheep.position.y))

    world.tick(2.0)
    world.tick(2.0)
    blocked_sheep = world.get_entity("creature-barbara")

    assert blocked_sheep is not None
    assert blocked_sheep.position == sheep.position


def test_world_regrows_creature_wool_after_timer() -> None:
    """
    Проверяет, что шерсть овцы отрастает после server-side таймера.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map_with_gate_and_sheep()))

    sheared = world.mark_creature_sheared("creature-barbara", wool_regrow_seconds=30.0)
    world.tick(30.0)
    entities = {
        entity.entity_id: entity
        for entity in entities_from_snapshot_payload(world.snapshot_payload())
    }

    assert sheared is not None
    assert sheared.has_wool is False
    assert entities["creature-barbara"].has_wool is True


def test_world_destroys_and_respawns_training_dummy() -> None:
    """
    Проверяет разрушение и runtime-восстановление attackable-манекена.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map_with_training_dummy()))

    result = world.damage_entity("lootable-training-dummy", 20)
    destroyed_dummy = world.get_entity("lootable-training-dummy")
    assert result is not None
    assert result[1] is True
    assert destroyed_dummy is not None
    assert destroyed_dummy.name == "Разрушенный тренировочный манекен"
    assert destroyed_dummy.hit_points == 0
    assert destroyed_dummy.is_attackable is False
    assert destroyed_dummy.solid is True

    world.tick(10.0)
    restored_dummy = world.get_entity("lootable-training-dummy")

    assert restored_dummy is not None
    assert restored_dummy.name == "Тренировочный манекен"
    assert restored_dummy.hit_points == 20
    assert restored_dummy.is_attackable is True


def test_world_spawns_boar_corpse_and_respawns_boar_later() -> None:
    """
    Проверяет, что смерть кабана оставляет runtime-труп и не мешает respawn-у кабана.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map_with_boar_and_respawn_cross()))

    result = world.damage_entity("creature-boar", 18)
    dead_boar = world.get_entity("creature-boar")
    corpses = [
        entity
        for entity in world.entities
        if entity.entity_id.startswith("corpse-creature-boar-")
    ]

    assert result is not None
    assert result[1] is True
    assert dead_boar is not None
    assert dead_boar.visible is False
    assert dead_boar.solid is False
    assert dead_boar.is_attackable is False
    assert len(corpses) == 1
    corpse = corpses[0]
    assert corpse.name == "Труп кабана"
    assert corpse.solid is False
    assert corpse.is_attackable is False
    assert corpse.lootable is not None
    assert corpse.lootable.reward_item_id == LEATHER_ITEM_ID
    assert corpse.lootable.reward_quantity == 2

    world.tick(60.0)
    respawned_boar = world.get_entity("creature-boar")
    assert respawned_boar is not None
    assert respawned_boar.visible is True
    assert respawned_boar.solid is True
    assert respawned_boar.hit_points == 18
    assert world.get_entity(corpse.entity_id) is not None

    world.tick(240.0)
    assert world.get_entity(corpse.entity_id) is None


def test_world_kills_and_respawns_player_at_cross() -> None:
    """
    Проверяет runtime-смерть игрока и возрождение с половиной max HP.
    """
    world = MultiplayerWorld(tile_map=tile_map_from_dict(_open_map_with_boar_and_respawn_cross()))
    player = world.add_player("p1", "Alice")

    damage_result = world.damage_player("p1", 30)
    world.set_intent("p1", MovementIntent(right=True))
    world.tick(1.0)
    dead_player = world.players["p1"]

    assert damage_result is not None
    assert damage_result[1] is True
    assert dead_player.hit_points == 0
    assert dead_player.position == player.position

    respawned = world.respawn_player("p1")
    assert respawned is not None
    assert respawned.hit_points == 15
    assert respawned.max_hit_points == 30
    assert respawned.position == Vec2(96, 32)
