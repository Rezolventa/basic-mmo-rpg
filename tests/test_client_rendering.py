from __future__ import annotations

from pathlib import Path

import pytest

from basic_mmo_rpg.client.ui import ChatLine
from basic_mmo_rpg.domain.skills import SKILL_DEFINITIONS, CharacterSkill
from basic_mmo_rpg.storage.map_loader import load_tile_map


def test_renderer_loads_tile_sprites_independent_of_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    Проверяет, что клиентский renderer ищет PNG-спрайты от корня проекта, а не от cwd.
    """
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")

    import pygame

    from basic_mmo_rpg.client.rendering import Renderer

    tile_map = load_tile_map(Path("assets/maps/starter_map.json"))
    pygame.init()
    try:
        pygame.display.set_mode((1, 1))
        monkeypatch.chdir(tmp_path)

        renderer = Renderer(tile_map)

        assert len(renderer.tile_sprites["#"]) == 16
        assert renderer._sprite_index_for_tile("#", renderer.tile_sprites["#"], 0, 0) == 6
        assert len(renderer.tile_sprites["T"]) == 8
        assert len(renderer.tile_sprites["R"]) == 3
        assert len(renderer.tile_sprites["C"]) == 1
        assert renderer.entity_sprites["spinning_wheel"] is not None
        assert renderer.entity_sprites["spinning_wheel"].get_size() == (32, 32)
        assert renderer.entity_sprites["training_dummy"] is not None
        assert renderer.entity_sprites["training_dummy"].get_size() == (32, 32)
        assert renderer.entity_sprites["training_dummy_broken"] is not None
        assert renderer.entity_sprites["training_dummy_broken"].get_size() == (32, 32)
    finally:
        pygame.quit()


def test_renderer_chat_journal_draws_latest_visible_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Проверяет, что журнал показывает последние строки, которые помещаются в панель.
    """
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")

    import pygame

    from basic_mmo_rpg.client.rendering import Renderer

    class RecordingJournalFont:
        def __init__(self) -> None:
            self.texts: list[str] = []

        def get_linesize(self) -> int:
            return 10

        def render(
            self,
            text: str,
            _antialias: bool,
            _color: tuple[int, int, int],
        ) -> pygame.Surface:
            self.texts.append(text)
            return pygame.Surface((1, 1), pygame.SRCALPHA)

    tile_map = load_tile_map(Path("assets/maps/starter_map.json"))
    pygame.init()
    try:
        pygame.display.set_mode((1, 1))
        renderer = Renderer(tile_map)
        recording_font = RecordingJournalFont()
        renderer.small_font = recording_font
        monkeypatch.setattr(
            renderer,
            "_wrap_text",
            lambda text, max_width, font: [text],
        )
        screen = pygame.Surface((800, 600), pygame.SRCALPHA)
        chat_lines = [
            ChatLine(
                player_id="player-1",
                name="Alice",
                text=f"msg-{index}",
                created_at=float(index),
            )
            for index in range(30)
        ]

        renderer._draw_chat_journal(screen, chat_lines)

        assert len(recording_font.texts) > 12
        assert recording_font.texts[0] == "Alice: msg-3"
        assert recording_font.texts[-1] == "Alice: msg-29"
    finally:
        pygame.quit()


def test_renderer_skills_panel_draws_all_current_skills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Проверяет, что K-панель помещает все текущие игровые скиллы.
    """
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")

    import pygame

    from basic_mmo_rpg.client.rendering import Renderer

    class RecordingSkillFont:
        def __init__(self) -> None:
            self.texts: list[str] = []

        def size(self, text: str) -> tuple[int, int]:
            return len(text) * 6, 12

        def render(
            self,
            text: str,
            _antialias: bool,
            _color: tuple[int, int, int],
        ) -> pygame.Surface:
            self.texts.append(text)
            return pygame.Surface((max(1, len(text) * 6), 12), pygame.SRCALPHA)

    pygame.init()
    try:
        pygame.display.set_mode((1, 1))
        renderer = object.__new__(Renderer)
        renderer.font = RecordingSkillFont()
        renderer.small_font = RecordingSkillFont()
        screen = pygame.Surface((800, 600), pygame.SRCALPHA)
        skills = [
            CharacterSkill(
                skill_id=definition.skill_id,
                display_name=definition.display_name,
                value_tenths=100,
            )
            for definition in SKILL_DEFINITIONS
        ]

        renderer._draw_skills(screen, skills, inventory_visible=False)

        for definition in SKILL_DEFINITIONS:
            assert definition.display_name in renderer.small_font.texts
    finally:
        pygame.quit()
